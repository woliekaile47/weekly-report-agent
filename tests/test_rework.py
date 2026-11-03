"""Behavioral regression: dependency routing, real changes, bounded failures and durable resume."""

import asyncio
from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from report_agent.config import snapshot
from report_agent.models import Review
from report_agent.rework import changed_inputs, merge_revision, plan_rework, register_review, verify_revisions
from report_agent.service import Service
from report_agent.third_party.agentops_ledger import update_revision_ledger
from report_agent.workflow import build_graph
from tests.helpers import test_model as fixture_model


def sample_state():
    return {
        "task_id": "a" * 32,
        "spec": {"year": 2026, "week": 44, "title": "周报", "focus": ""},
        "bundle": snapshot(),
        "inputs": {"sales": "sales.xlsx", "minutes": "minutes.docx"},
        "import_options": {},
        "version": 1,
        "draft": {
            "summary": "旧摘要",
            "anomalies": [],
            "conflicts": [],
            "data_notes": [],
            "actions": ["旧建议"],
        },
        "artifact": {"sha256": "old"},
        "metrics": {"total": "stable"},
        "sales": {"file": "parsed"},
        "minutes": {"sources": [{"id": "M001", "text": "原文"}]},
    }


def test_mixed_issues_route_earliest_and_preserve_union():
    s = sample_state()
    s["quality"] = {
        "checks": [
            {"name": "图表完整", "passed": False, "details": "缺图"},
            {"name": "证据原文可追溯", "passed": False, "details": "引用失效"},
        ]
    }
    plan = plan_rework(s)
    assert plan["route"] == "evidence" and set(plan["categories"]) == {"layout", "evidence"}
    assert "anomalies" in plan["sections"]


def test_page_failure_tries_layout_then_shortens_content():
    s = sample_state()
    s["quality"] = {"checks": [{"name": "Word实际页数", "passed": False, "details": "4页"}]}
    assert plan_rework(s)["route"] == "render"
    s["layout_attempts"] = 1
    assert plan_rework(s)["route"] == "analyze"


@pytest.mark.parametrize(
    "reply,expected,retained",
    [
        ({"inputs": {"minutes": "new.docx"}}, "evidence", ["sales", "metrics"]),
        ({"inputs": {"sales": "new.xlsx"}}, "ingest", []),
        ({"spec": {"year": 2026, "week": 43, "title": "周报", "focus": ""}}, "calculate", ["sales"]),
    ],
)
def test_input_invalidation_respects_dependencies(reply, expected, retained):
    s = sample_state()
    update = changed_inputs(s, reply)
    assert update["route"] == expected
    assert update["approval"] == {} and update["artifact"] == {} and update["draft"] == {}
    for key in retained:
        assert key not in update
    assert not changed_inputs(s, {"inputs": s["inputs"], "spec": s["spec"], "import_options": {}})
    assert not changed_inputs(s, {"import_options": {"sheet": "", "fields": {}}})
    assert (
        changed_inputs(s, {"inputs": {"minutes": "new.docx"}, "import_options": {"sheet": "", "fields": {}}})[
            "route"
        ]
        == "evidence"
    )


def test_unrelated_sections_cannot_be_overwritten_by_model():
    s = sample_state()
    s["rework_plan"] = {"sections": ["actions"]}
    candidate = {**deepcopy(s["draft"]), "summary": "模型擅改摘要", "actions": ["新建议"]}
    merged = merge_revision(s, candidate)
    assert merged["summary"] == "旧摘要" and merged["actions"] == ["新建议"]


def test_claimed_fix_without_content_change_or_valid_source_fails():
    s = sample_state()
    s["revision_items"] = register_review(s, {"reviewer": "测试", "feedback": "修改摘要\n补充行动建议"})
    s["draft"]["revision_responses"] = [
        {"item_id": "R1-1", "response": "已修改", "sections": ["summary"], "source_ids": ["M999"]}
    ]
    items, ledger, check = verify_revisions(s, {"checks": []})
    assert not check["passed"] and ledger["open_issues"] == ["R1-1", "R1-2"]
    assert "实际修改" in items[0]["verification"] and "不存在" in items[0]["verification"]
    s["draft"].update(summary="已补充事实依据的摘要", actions=["已明确负责人核实事项"])
    s["draft"]["revision_responses"] = [
        {"item_id": "R1-1", "response": "摘要说明事实依据", "sections": ["summary"], "source_ids": ["M001"]},
        {"item_id": "R1-2", "response": "补充核实安排", "sections": ["actions"], "source_ids": []},
    ]
    s["revision_ledger"] = ledger
    items, ledger, check = verify_revisions(s, {"checks": []})
    assert check["passed"] and not ledger["open_issues"] and len(ledger["resolved_issues"]) == 2
    assert items[0]["before"]["summary"] == "旧摘要"


def test_ledger_never_resolves_an_omitted_issue():
    ledger = update_revision_ledger({"open_issues": ["R1-1"]}, [], [])
    assert ledger["open_issues"] == ["R1-1"] and not ledger["resolved_issues"]


def test_minutes_change_cannot_claim_sales_correction_and_mixed_layout_needs_actual_layout_change():
    s = sample_state()
    s["revision_items"] = register_review(
        s,
        {
            "reviewer": "测试",
            "items": [
                {"text": "修正销售材料", "category": "data", "sections": ["summary"]},
                {"text": "修改摘要和排版", "category": "auto", "sections": ["summary"]},
            ],
        },
    )
    s["inputs"]["minutes"] = "replacement.docx"
    s["draft"].update(
        summary="新的业务摘要",
        revision_responses=[
            {"item_id": f"R1-{i}", "response": "已处理", "sections": ["summary"], "source_ids": []}
            for i in (1, 2)
        ],
    )
    items, _, check = verify_revisions(s, {"checks": []})
    assert not check["passed"]
    assert "数据类意见" in items[0]["verification"]
    assert "版式变更" in items[1]["verification"]


def test_model_request_cap_blocks_the_next_request(monkeypatch):
    from report_agent.model import generate
    from report_agent.models import WorkflowError

    monkeypatch.setattr("report_agent.model.connection", lambda: {"LLM_API_KEY": "test-key"})
    s = sample_state()
    s["budget_id"] = "limited"

    class BudgetStore:
        def events(self, task_id):
            return [{"kind": "model_started", "payload": {"budget_id": "limited"}}] * 8

        def event(self, *args):
            raise AssertionError("不应启动新的请求")

    with pytest.raises(WorkflowError, match="达到上限"):
        asyncio.run(generate(s, BudgetStore()))


def test_model_input_budget_pauses_before_counting_or_sending_request(monkeypatch):
    from report_agent.model import generate
    from report_agent.models import WorkflowError

    monkeypatch.setattr("report_agent.model.connection", lambda: {"LLM_API_KEY": "test-key"})
    state = sample_state()
    state["budget_id"] = "input-limited"
    state["bundle"]["employee"]["limits"]["model_input_characters"] = 10

    class BudgetStore:
        def events(self, task_id):
            return []

        def event(self, *args):
            raise AssertionError("超出输入预算时不能计入实际模型调用")

    with pytest.raises(WorkflowError, match="字符预算") as exc:
        asyncio.run(generate(state, BudgetStore()))
    assert exc.value.kind == "budget"


def test_structured_review_validation():
    decision = Review(decision="revise", reviewer="运营", version=1, items=[{"text": "摘要简洁些"}])
    assert decision.items[0].category == "auto"
    with pytest.raises(ValueError):
        Review(decision="approve", reviewer="运营", version=1, items=[{"text": "还要修改"}])


def test_graph_bounds_layout_repairs_without_model_calls(monkeypatch):
    async def page_audit(state, result):
        return result

    monkeypatch.setattr("report_agent.workflow.page_inspection", page_audit)

    async def run():
        service = Service()
        tid = service.create({"week": 44, "year": 2026})
        state = service.store.get(tid)
        state.update(
            status="running",
            route="quality",
            metrics={"tokens": {}, "category_margins": []},
            minutes={"sources": []},
            draft={"summary": "摘要", "actions": [], "anomalies": []},
            artifact={"file": "artifacts/start/report.docx"},
        )
        calls = []

        class GatewayStub:
            async def call(self, name, args):
                calls.append(name)
                if name == "generate_report":
                    return {"file": f"artifacts/v{args['version']}/report.docx"}
                assert name == "inspect_report"
                return {"passed": False, "checks": [{"name": "图表完整", "passed": False, "details": "缺图"}]}

        async def forbidden_model(state, store):
            raise AssertionError("纯版式返工不能调用模型")

        graph = build_graph(service.store, GatewayStub(), InMemorySaver(), forbidden_model)
        config = {"configurable": {"thread_id": tid}}
        await graph.aupdate_state(config, state, as_node="render")
        result = await graph.ainvoke(None, config)
        assert result["status"] == "paused" and result["error_kind"] == "quality"
        assert result["repairs"] == 2 and result["version"] == 3
        assert calls.count("generate_report") == 2 and calls.count("inspect_report") == 3
        assert result["resume_node"] == "rework"
        assert not result["approval"]

    asyncio.run(run())


def test_graph_active_budget_pauses_before_tool_or_model(monkeypatch):
    async def run():
        service = Service()
        tid = service.create({"week": 44, "year": 2026})
        state = service.store.get(tid)
        state["active_seconds"] = state["bundle"]["employee"]["limits"]["active_seconds"]
        graph = build_graph(service.store, None, InMemorySaver())
        result = await graph.ainvoke(state, {"configurable": {"thread_id": tid}})
        assert result["status"] == "paused" and result["error_kind"] == "budget"
        assert not any(e["kind"] in {"tool_started", "model_started"} for e in service.store.events(tid))

    asyncio.run(run())


def test_connection_failure_is_checkpointed_and_can_resume(public_data):
    async def run():
        s = Service(model=fixture_model, faults={"connect": -1})
        tid = s.create(
            {"year": 2026, "week": 44},
            {
                "sales": ("sales.xlsx", (public_data / "销售明细.xlsx").read_bytes()),
                "minutes": ("minutes.docx", (public_data / "周会纪要_2026W44.docx").read_bytes()),
            },
        )
        paused = await s.operate(tid)
        assert paused["status"] == "paused" and paused["resume_node"] == "ingest"
        assert len([e for e in s.store.events(tid) if e["kind"] == "mcp_connect_failed"]) == 3
        resumed = await Service(model=fixture_model).operate(tid, action="resume")
        assert resumed["status"] == "awaiting_human", resumed.get("reason")

    asyncio.run(run())


def test_layout_review_and_minutes_replacement_skip_unneeded_work(public_data):
    async def run():
        model_calls = []

        async def model(state, store):
            model_calls.append(state["version"])
            return await fixture_model(state, store)

        s = Service(model=model)
        tid = s.create(
            {"year": 2026, "week": 44},
            {
                "sales": ("sales.xlsx", (public_data / "销售明细.xlsx").read_bytes()),
                "minutes": ("minutes.docx", (public_data / "周会纪要_2026W44.docx").read_bytes()),
            },
        )
        first = await s.operate(tid)
        assert first["status"] == "awaiting_human", first.get("reason")
        second = await s.operate(
            tid,
            action="review",
            review={
                "decision": "revise",
                "version": first["version"],
                "reviewer": "版式测试",
                "items": [{"text": "压缩段后间距", "category": "layout"}],
            },
        )
        assert second["status"] == "awaiting_human", second.get("reason")
        assert len(model_calls) == 1
        for section in ("summary", "anomalies", "actions", "conflicts", "data_notes"):
            assert second["draft"][section] == first["draft"][section]
        assert second["revision_items"][0]["status"] == "verified"
        # A data correction asks for materials instead of silently recomputing identical inputs.
        paused = await s.operate(
            tid,
            action="review",
            review={
                "decision": "revise",
                "version": second["version"],
                "reviewer": "测试",
                "items": [{"text": "请更正销售材料", "category": "data"}],
            },
        )
        assert paused["status"] == "paused" and paused["error_kind"] == "materials"

    asyncio.run(run())
