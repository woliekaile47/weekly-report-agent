"""Browser entrypoints must survive refresh, and missing APIs must not return HTML."""

import asyncio

import httpx

from report_agent.api import app


def test_page_refresh_uses_current_build_and_unknown_api_is_404():
    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for route in ("/", "/history", "/runs/a" + "1" * 31, "/settings/employee"):
                response = await client.get(route)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                assert 'id="startup-message"' in response.text
            missing = await client.get("/api/not-an-endpoint")
            assert missing.status_code == 404
            assert missing.json()["detail"] == "接口不存在"

    asyncio.run(check())
