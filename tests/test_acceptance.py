import asyncio
import zipfile

import pytest

from report_agent.config import snapshot
from report_agent.data_tools import compute_metrics, read_sales
from report_agent.models import WorkflowError
from report_agent.service import Service
from report_agent.store import task_path
from tests.helpers import test_model as fixture_model


@pytest.mark.parametrize(
    "week,cents,change,margin,delivery,returns,duplicates",
    [
        (42, 60590899, -11.7, 61.0, 31.5, 15, 0),
        (43, 63248576, 4.4, 60.1, 31.3, 6, 29),
        (44, 57363487, -9.3, 61.1, 31.8, 11, 0),
    ],
)
def test_public_numeric_acceptance(sales, week, cents, change, margin, delivery, returns, duplicates):
    tid, source = sales
    result = compute_metrics(tid, source, {"year": 2026, "week": week})
    assert result["total"]["cents"] == cents
    assert result["total"]["change"] == change
    assert result["total"]["margin"] == margin
    assert result["total"]["delivery_share"] == delivery
    assert result["quality"]["return_count"] == returns
    assert result["quality"]["removed_count"] == duplicates


def test_a01_regions_top_products_and_anomalies(sales):
    tid, source = sales
    m = compute_metrics(tid, source, {"year": 2026, "week": 44})
    regions = {g["label"]: g for g in m["groups"] if g["dimension"] == "region"}
    assert {k: v["change"] for k, v in regions.items()} == {
        "华东": -12.0,
        "华南": -12.7,
        "华北": -3.3,
        "西南": -2.6,
    }
    assert {k: v["target_rate"] for k, v in regions.items()} == {
        "华东": 84.1,
        "华南": 92.3,
        "华北": 92.1,
        "西南": 96.3,
    }
    assert {g["label"] for g in m["anomalies"]} == {
        "华东",
        "华南",
        "杭州湖滨店",
        "上海静安店",
        "深圳南山店",
        "深圳福田店",
    }
    assert [p["product"] for p in m["top_products"]] == [
        "拿铁",
        "生椰拿铁",
        "美式咖啡",
        "6寸生日蛋糕",
        "草莓奶油切块",
    ]
    assert m["quality"]["return_cents"] == -26000


def test_a02_south_drinks_margin_comparison(sales):
    tid, source = sales
    metrics = compute_metrics(tid, source, {"year": 2026, "week": 43})
    item = next(r for r in metrics["category_margins"] if r["region"] == "华南" and r["category"] == "饮品")
    assert item["previous_margin"] == 70.4
    assert item["margin"] == 60.5


def test_a05_out_of_range_has_actual_coverage(sales):
    tid, source = sales
    with pytest.raises(WorkflowError, match="2026-11-01"):
        compute_metrics(tid, source, {"year": 2026, "week": 46})


def test_csv_and_excel_match(public_data, sales):
    s = Service()
    tid = s.create(
        {"year": 2026, "week": 44}, {"sales": ("sales.csv", (public_data / "销售明细.csv").read_bytes())}
    )
    source = read_sales(tid, s.store.get(tid)["inputs"]["sales"], snapshot()["columns"])
    result = compute_metrics(tid, source, {"year": 2026, "week": 44})
    assert result["total"]["cents"] == 57363487
    assert source["removed_duplicates"] == 29


def test_a03_supplement_review_rework_delivery(public_data):
    async def run():
        s = Service(model=fixture_model)
        tid = s.create(
            {"year": 2026, "week": 44},
            {"minutes": ("minutes.docx", (public_data / "周会纪要_2026W44.docx").read_bytes())},
        )
        paused = await s.operate(tid)
        assert paused["status"] == "paused" and "销售" in paused["reason"]
        with pytest.raises(WorkflowError):
            await s.operate(
                tid, action="review", review={"decision": "approve", "reviewer": "测试", "version": 1}
            )
        review = await s.operate(
            tid,
            action="resume",
            files={"sales": ("sales.xlsx", (public_data / "销售明细.xlsx").read_bytes())},
        )
        assert review["status"] == "awaiting_human", review.get("reason")
        assert review["quality"]["page_audit"]["pages"] <= 3
        assert review["metrics"]["expected_conflicts"][0]["region"] == "华南"
        revised = await s.operate(
            tid,
            action="review",
            review={
                "decision": "revise",
                "reviewer": "工程验收测试",
                "version": 1,
                "feedback": "补充华东原因与核实步骤",
            },
        )
        assert revised["status"] == "awaiting_human" and revised["version"] == 2
        assert revised["draft"]["review_response"]
        with pytest.raises(WorkflowError):
            await s.operate(
                tid, action="review", review={"decision": "approve", "reviewer": "过期版本测试", "version": 1}
            )
        finished = await s.operate(
            tid,
            action="review",
            review={"decision": "approve", "reviewer": "工程验收测试（模型替身）", "version": 2},
        )
        assert finished["status"] == "completed"
        with zipfile.ZipFile(task_path(tid, finished["delivery"])) as z:
            assert {"经营周报.docx", "质检记录.json", "配置快照.json", "审核记录.json"}.issubset(z.namelist())

    asyncio.run(run())


def test_tool_failure_retries_and_recovers(public_data):
    async def run():
        s = Service(model=fixture_model, faults={"compute_metrics": -1})
        tid = s.create(
            {"year": 2026, "week": 44},
            {
                "sales": ("sales.xlsx", (public_data / "销售明细.xlsx").read_bytes()),
                "minutes": ("minutes.docx", (public_data / "周会纪要_2026W44.docx").read_bytes()),
            },
        )
        paused = await s.operate(tid)
        assert paused["status"] == "paused" and paused["resume_node"] == "calculate"
        assert len([e for e in s.store.events(tid) if e["kind"] == "tool_failed"]) == 3
        s2 = Service(model=fixture_model)
        result = await s2.operate(tid, action="resume")
        assert result["status"] == "awaiting_human"
        assert (
            len(
                [
                    e
                    for e in s.store.events(tid)
                    if e["kind"] == "tool_completed" and e["payload"]["tool"] == "read_sales"
                ]
            )
            == 1
        )

    asyncio.run(run())
