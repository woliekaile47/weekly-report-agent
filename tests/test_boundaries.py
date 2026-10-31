import asyncio

import httpx
import pandas as pd
import pytest

from report_agent.config import snapshot
from report_agent.data_tools import compute_metrics, read_sales
from report_agent.mcp_client import Gateway
from report_agent.models import WorkflowError
from report_agent.service import Service
from report_agent.store import task_path


def csv_input(amounts=(100, 0), ids=("R1", "R2"), dates=("2026-10-26", "2026-10-19")):
    frame = pd.DataFrame(
        {
            "记录ID": ids,
            "销售日期": dates,
            "门店编码": ["SH01", "SH01"],
            "商品编码": ["B01", "B01"],
            "渠道": ["外卖", "堂食自提"],
            "销售数量": [1, 1],
            "实收金额": amounts,
            "成本金额": [40, 0],
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


def parse(content):
    s = Service()
    tid = s.create({"year": 2026, "week": 44}, {"sales": ("sales.csv", content)})
    return tid, read_sales(tid, s.store.get(tid)["inputs"]["sales"], snapshot()["columns"])


def test_zero_baseline_not_infinity():
    tid, sales = parse(csv_input())
    result = compute_metrics(tid, sales, {"year": 2026, "week": 44})
    assert result["total"]["change"] is None
    assert "上期为零" in result["tokens"]["total_change"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "abc", ""])
def test_invalid_money_is_not_zero(value):
    with pytest.raises(WorkflowError):
        parse(csv_input((value, 100)))


def test_conflicting_id_pauses_instead_of_deduping():
    with pytest.raises(WorkflowError, match="不同内容"):
        parse(csv_input((100, 200), ids=("same", "same")))


def test_bad_date_pauses():
    with pytest.raises(WorkflowError):
        parse(csv_input(dates=("not-a-date", "2026-10-19")))


def test_task_path_escape_rejected():
    with pytest.raises(ValueError):
        task_path("a" * 32, "../../.env")


def test_unlisted_tool_is_denied_and_logged():
    async def run():
        s = Service()
        tid = s.create({"year": 2026, "week": 44})
        async with Gateway(s.store, tid, s.store.get(tid)["bundle"]) as client:
            with pytest.raises(WorkflowError, match="越权"):
                await client.call("execute_shell", {})
        assert any(e["kind"] == "tool_denied" for e in s.store.events(tid))

    asyncio.run(run())


def test_429_stops_after_one_real_request(monkeypatch, public_data):
    async def run():
        calls = []
        original = httpx.AsyncClient

        def respond(request):
            calls.append(1)
            return httpx.Response(429, json={"error": "quota"})

        monkeypatch.setattr(
            "report_agent.model.httpx.AsyncClient",
            lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
        )
        s = Service()
        tid = s.create(
            {"year": 2026, "week": 44},
            {
                "sales": ("sales.xlsx", (public_data / "销售明细.xlsx").read_bytes()),
                "minutes": ("minutes.docx", (public_data / "周会纪要_2026W44.docx").read_bytes()),
            },
        )
        r = await s.operate(tid)
        assert r["status"] == "paused" and r["error_kind"] == "rate_limit"
        assert r["model_calls"] == 1 and len(calls) == 1

    asyncio.run(run())
