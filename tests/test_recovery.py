import subprocess
import sys

import pytest

from weekly_report.model import mock_draft
from weekly_report.service import EmployeeService
from weekly_report.store import task_path


def test_process_exit_recovers_committed_steps(service, spec, files):
    task_id = service.create(spec, files)
    program = """
import os, sys
import weekly_report.graph as graph
from weekly_report.service import EmployeeService
from weekly_report.settings import Settings
async def crash(settings, state):
    os._exit(93)
graph.generate = crash
service = EmployeeService(Settings(data_dir=sys.argv[1], mode='mock'))
service.run(sys.argv[2])
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(service.settings.data_dir), task_id],
        capture_output=True,
        timeout=45,
    )
    assert result.returncode == 93, result.stderr.decode(errors="replace")
    state = EmployeeService(service.settings).run(task_id)
    assert state["status"] == "REVIEW", state.get("reason")
    events = service.store.events(task_id)
    assert sum(e["kind"] == "tool_completed" and e["payload"]["tool"] == "read_sales" for e in events) == 1
    # Even a call interrupted before a checkpoint consumes the persistent model budget.
    assert state["model_calls"] == 2


def test_model_round_budget_is_enforced(service, spec, files, monkeypatch):
    employee = service.settings.employee()
    employee["limits"]["model_calls"] = 1
    monkeypatch.setattr(service.settings, "employee", lambda: employee)

    async def bad_model(settings, state):
        result = mock_draft(state)
        result["summary"] += "增长99%。"
        return result

    monkeypatch.setattr("weekly_report.graph.generate", bad_model)
    task_id = service.create(spec, files)
    state = service.run(task_id)
    assert state["status"] == "PAUSED" and state["error_kind"] == "budget"
    assert state["model_calls"] == 1


def test_concurrent_mutations_rejected(service, spec, files):
    from filelock import FileLock

    from weekly_report.schemas import EmployeeError

    task_id = service.create(spec, files)
    with FileLock(task_path(service.settings.data_dir, task_id, "task.lock")):
        with pytest.raises(EmployeeError, match="正在执行"):
            service.run(task_id)
