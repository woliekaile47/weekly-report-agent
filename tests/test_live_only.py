import json

import pytest

from weekly_report.schemas import EmployeeError
from weekly_report.settings import Settings


def test_env_cannot_enable_offline_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "mock")
    assert Settings(data_dir=tmp_path).mode == "live"


def test_archived_task_not_listed_or_executable(service, spec, files):
    archived = service.create(spec, files)
    active = service.create(spec, files)
    service.store.archive(archived, "历史开发样例")
    assert [task["id"] for task in service.store.tasks()] == [active]
    with pytest.raises(EmployeeError, match="停用"):
        service.run(archived)
    assert service.store.initial(archived)["inputs"]


def test_old_mock_task_cannot_resume_as_live(service, spec):
    task_id = service.create(spec)
    initial = service.store.initial(task_id)
    initial["mode"] = "mock"
    with service.store.connect() as db:
        db.execute("UPDATE tasks SET initial=? WHERE id=?", (json.dumps(initial), task_id))
    assert service.store.tasks() == []
    with pytest.raises(EmployeeError, match="停用"):
        service.run(task_id)
