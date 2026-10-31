"""File-browser adaptation exposes only known task inputs and generated artifacts."""

import asyncio

import httpx

from report_agent.api import app, service


def test_task_file_manifest_and_download_do_not_expose_arbitrary_paths():
    async def check():
        task_id = service.create(
            {"title": "文件清单边界验证", "year": 2026, "week": 44},
            {"minutes": ("meeting.txt", "本周周会纪要".encode())},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(f"/api/runs/{task_id}/files")
            assert response.status_code == 200
            files = response.json()["files"]
            assert len(files) == 1
            item = files[0]
            assert item["id"] == "minutes"
            assert item["kind"] == "input"
            assert item["bytes"] == len("本周周会纪要".encode())
            assert "inputs/" not in response.text
            download = await client.get(item["url"])
            assert download.content.decode() == "本周周会纪要"
            assert (await client.get(f"/api/runs/{task_id}/input/configuration")).status_code == 404
            assert (await client.get(f"/api/runs/{task_id}/input/.env")).status_code == 404
            assert (await client.get(f"/api/runs/{task_id}/input/sales")).status_code == 404
            assert (await client.get(f"/api/runs/{task_id}/download/package")).status_code == 409
            assert service.store.get(task_id)["status"] == "pending"

    asyncio.run(check())


def test_two_file_upload_preserves_binary_data_without_starting_a_model(monkeypatch, public_data):
    import json

    import report_agent.api as api

    started = []
    monkeypatch.setattr(api, "start", lambda task_id: started.append(task_id))
    sales = (public_data / "销售明细.xlsx").read_bytes()
    minutes_file = next(public_data.rglob("*2026W44*.docx"))
    minutes = minutes_file.read_bytes()

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/runs",
                data={"spec": json.dumps({"year": 2026, "week": 44, "title": "双文件传输验证"})},
                files={
                    "sales": ("销售明细.xlsx", sales),
                    "minutes": (minutes_file.name, minutes),
                },
            )
            assert response.status_code == 200
            task_id = response.json()["id"]
            assert started == [task_id]
            result = (await client.get(f"/api/runs/{task_id}/files")).json()["files"]
            assert {f["id"]: f["bytes"] for f in result} == {"sales": len(sales), "minutes": len(minutes)}
            for role, expected in (("sales", sales), ("minutes", minutes)):
                assert (await client.get(f"/api/runs/{task_id}/input/{role}")).content == expected

    asyncio.run(check())
