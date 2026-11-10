"""Invalid imports must be rejected before a task starts or its checkpoint changes."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from report_agent import api
from report_agent.models import ImportOptions


@pytest.mark.parametrize("options", [[], ["sheet"], "CSV", 1, None, {"fields": []},
                                     {"sheet": 1}, {"fields": {"amount": 1}},
                                     {"fields": {"unknown": "金额"}}])
def test_invalid_import_options_rejected_before_create_or_resume(monkeypatch, options):
    task_id = api.service.create({"year": 2026, "week": 44})
    state = api.service.store.get(task_id)
    state["status"] = "paused"
    api.service.store.save(task_id, state)

    def unexpected_start(*args, **kwargs):
        pytest.fail("Invalid mappings must not schedule a worker")

    monkeypatch.setattr(api, "start", unexpected_start)
    before = len(api.service.store.list())
    with TestClient(api.app) as client:
        create = client.post("/api/runs", data={
            "spec": json.dumps({"year": 2026, "week": 44}),
            "import_options": json.dumps(options),
        })
        assert create.status_code == 422
        resume = client.post(f"/api/runs/{task_id}/resume", data={"import_options": json.dumps(options)})
        assert resume.status_code == 422
    assert len(api.service.store.list()) == before
    assert api.service.store.get(task_id) == state


def test_valid_mapping_remains_supported():
    assert ImportOptions.model_validate({"sheet": "CSV", "fields": {"amount": "实收金额"}}).sheet == "CSV"


@pytest.mark.parametrize("cursor", ["broken", "-1"])
def test_invalid_stream_cursor_returns_json_error(cursor):
    task_id = api.service.create({"year": 2026, "week": 44})
    with TestClient(api.app) as client:
        response = client.get(f"/api/runs/{task_id}/stream", headers={"last-event-id": cursor})
        assert response.status_code == 422
        assert "游标" in response.json()["detail"]


def test_finished_worker_is_released_and_stream_has_final_snapshot(monkeypatch):
    async def check():
        task_id = api.service.create({"year": 2026, "week": 44})

        async def operate(*args, **kwargs):
            state = api.service.store.get(task_id)
            state["status"] = "approved"
            api.service.store.save(task_id, state)

        monkeypatch.setattr(api.service, "operate", operate)
        api.start(task_id)
        task = api.tasks[task_id]
        await task
        await asyncio.sleep(0)
        assert task_id not in api.tasks
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
            response = await client.get(f"/api/runs/{task_id}/stream")
        assert '"status": "approved"' in response.text
        assert '"worker_active": false' in response.text
        assert "event: done" in response.text

    asyncio.run(check())
