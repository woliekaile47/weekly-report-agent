import asyncio
import zipfile

import pytest

from weekly_report.mcp_client import MCPGateway
from weekly_report.schemas import EmployeeError, Review
from weekly_report.service import EmployeeService
from weekly_report.store import task_path


def test_review_rework_delivery_and_idempotency(service, spec, files):
    task_id = service.create(spec, files)
    state = service.run(task_id)
    assert state["status"] == "REVIEW", state.get("reason")
    assert state["metrics"]["total"]["current_cents"] == 3900000
    assert state["metrics"]["total"]["change_percent"] == -7.14
    first = state["draft"]
    state = service.review(
        task_id,
        Review(
            decision="reject",
            version=1,
            reviewer="测试审核人",
            feedback="华东区下滑原因没说清楚，请结合周会纪要补充。",
        ),
    )
    assert state["status"] == "REVIEW", state.get("reason")
    assert state["version"] == 2 and state["draft"] != first
    assert state["feedback"][0]["feedback"].startswith("华东区")
    assert state["draft"]["review_response"]
    with pytest.raises(EmployeeError):
        service.review(task_id, Review(decision="approve", version=1, reviewer="过期审核"))
    state = service.review(task_id, Review(decision="approve", version=2, reviewer="测试审核人"))
    assert state["status"] == "DELIVERED"
    with zipfile.ZipFile(task_path(service.settings.data_dir, task_id, state["delivery"])) as package:
        assert {"经营周报.docx", "质检记录.json", "审核记录.json", "执行记录.json"} <= set(package.namelist())
    count = len(service.store.events(task_id))
    service.run(task_id)
    assert len(service.store.events(task_id)) == count
    with pytest.raises(EmployeeError):
        service.resume(task_id)


def test_missing_materials_resume_same_task(service, spec, files):
    task_id = service.create(spec, {"sales": files["sales"]})
    state = service.run(task_id)
    assert state["status"] == "PAUSED" and "纪要" in state["reason"]
    with pytest.raises(EmployeeError):
        service.review(task_id, Review(decision="approve", version=1, reviewer="违规审核"))
    state = service.resume(task_id, {"minutes": files["minutes"]})
    assert state["status"] == "REVIEW" and state["task_id"] == task_id


def test_tool_failure_retry_and_checkpoint_recovery(service, spec, files):
    service.faults = {"compute_metrics": -1}
    task_id = service.create(spec, files)
    state = service.run(task_id)
    assert state["status"] == "PAUSED" and state["resume_node"] == "metrics"
    events = service.store.events(task_id)
    assert sum(e["kind"] == "tool_failed" for e in events) == 3
    restarted = EmployeeService(service.settings)
    state = restarted.resume(task_id)
    assert state["status"] == "REVIEW"
    reads = [
        e
        for e in restarted.store.events(task_id)
        if e["kind"] == "tool_completed" and e["payload"]["tool"] == "read_sales"
    ]
    assert len(reads) == 1


def test_reviewed_file_tampering_rejected(service, spec, files):
    task_id = service.create(spec, files)
    state = service.run(task_id)
    path = task_path(service.settings.data_dir, task_id, state["report_file"])
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(EmployeeError, match="修改"):
        service.review(task_id, Review(decision="approve", version=1, reviewer="测试"))
    assert service.state(task_id)["status"] == "REVIEW"


def test_tools_reject_unauthorized_calls(service, spec):
    task_id = service.create(spec)

    async def run():
        async with MCPGateway(
            service.settings, service.store, task_id, service.settings.employee()
        ) as gateway:
            with pytest.raises(EmployeeError, match="无权"):
                await gateway.call("execute_shell", {})

    asyncio.run(run())
    assert any(e["kind"] == "tool_denied" for e in service.store.events(task_id))


def test_quality_repair_cap(service, spec, files, monkeypatch):
    from tests.fakes import mock_draft

    async def bad_model(settings, state):
        result = mock_draft(state)
        result["summary"] += "本周销售增长99%。"
        return result

    monkeypatch.setattr("weekly_report.graph.generate", bad_model)
    task_id = service.create(spec, files)
    state = service.run(task_id)
    assert state["status"] == "PAUSED" and state["error_kind"] == "quality"
    assert state["qc_repairs"] == 2 and state["model_calls"] == 3
    assert not state["quality"]["passed"]


def test_model_failure_pauses_without_fabrication(service, spec, files, monkeypatch):
    async def unavailable(settings, state):
        raise EmployeeError("模型接口返回 HTTP 429")

    monkeypatch.setattr("weekly_report.graph.generate", unavailable)
    task_id = service.create(spec, files)
    state = service.run(task_id)
    assert state["status"] == "PAUSED" and not state.get("draft")
    assert "429" in state["reason"] and state["model_calls"] == 3
