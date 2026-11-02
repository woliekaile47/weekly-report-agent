"""Business regressions reported in the 2026-11-02 user acceptance run."""

from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from report_agent.api import app, service, tasks
from report_agent.config import snapshot
from report_agent.data_tools import compute_metrics, read_minutes, read_sales
from report_agent.models import WorkflowError


def workbook(*, missing_store=False, duplicate_names=False, negative_target=False, invalid_year=False):
    rows = [
        {
            "record_id": f"R{day:02}{store}", "date": str(date(2026, 10, 19) + timedelta(days=day)),
            "store_id": store, "product_id": f"P{store[-1]}", "channel": "外卖", "quantity": 1,
            "amount": 100 if day < 7 else (120 if store == "S01" else 80), "cost": 40,
        }
        for day in range(14) for store in ("S01", "S02")
        if not (missing_store and day >= 7 and store == "S02")
    ]
    stores = [
        {"store_id": store, "store": "同名门店" if duplicate_names else store, "region": region}
        for store, region in (("S01", "东区"), ("S02", "南区"))
    ]
    products = [
        {"product_id": product, "product": "同名商品" if duplicate_names else product, "category": "饮品"}
        for product in ("P1", "P2")
    ]
    targets = [
        {"region": region, "year": "invalid" if invalid_year else 2026, "week": 44,
         "target": -700 if negative_target else 700}
        for region in ("东区", "南区")
    ]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, values in (("销售", rows), ("门店", stores), ("商品", products), ("目标", targets)):
            pd.DataFrame(values).to_excel(writer, sheet_name=sheet, index=False)
    return output.getvalue()


def metrics(content):
    task_id = service.create({"year": 2026, "week": 44}, {"sales": ("data.xlsx", content)})
    state = service.store.get(task_id)
    parsed = read_sales(task_id, state["inputs"]["sales"], snapshot()["columns"])
    return compute_metrics(task_id, parsed, state["spec"])


def test_missing_region_preserves_company_target_and_marks_store_dates():
    result = metrics(workbook(missing_store=True))
    assert result["total"]["target_cents"] == 140000
    assert result["total"]["target_rate"] == 60.0
    assert len([day for day in result["quality"]["missing_days"] if day["store_id"] == "S02"]) == 7
    south = next(group for group in result["groups"] if group["dimension"] == "store" and group["label"] == "S02")
    assert south["change"] is None and south["coverage_status"] == "本期无记录，待核实"


def test_same_names_keep_separate_codes_and_anomalies():
    result = metrics(workbook(duplicate_names=True))
    stores = [group for group in result["groups"] if group["dimension"] == "store"]
    assert len(stores) == 2 and {group["change"] for group in stores} == {20.0, -20.0}
    assert {group["label"] for group in stores} == {"同名门店（S01）", "同名门店（S02）"}
    assert len(result["top_products"]) == 2
    assert {product["product_id"] for product in result["top_products"]} == {"P1", "P2"}


@pytest.mark.parametrize("field", ["negative_target", "invalid_year"])
def test_invalid_target_rows_are_material_errors(field):
    with pytest.raises(WorkflowError, match="目标表字段无效") as exc:
        metrics(workbook(**{field: True}))
    assert exc.value.kind == "materials"
    assert "第 2 行" in str(exc.value)


@pytest.mark.parametrize("heading,year,week", [
    ("2026W43 周会纪要", 2026, 43),
    ("2026-W43 周会纪要", 2026, 43),
    ("2025年第44周周会纪要", 2025, 44),
])
def test_minutes_extract_explicit_year_and_week(heading, year, week):
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", heading.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"]) == (year, week)


def test_resume_oversize_is_rejected_synchronously_without_starting_worker():
    task_id = service.create({"year": 2026, "week": 44})
    state = service.store.get(task_id)
    state.update(status="paused", reason="缺少销售明细", error_kind="materials")
    service.store.save(task_id, state)
    response = TestClient(app).post(
        f"/api/runs/{task_id}/resume",
        files={"sales": ("sales.csv", b"x" * (20 * 1024 * 1024 + 1), "text/csv")},
    )
    assert response.status_code == 422
    assert "超过20MB" in response.json()["detail"]
    assert task_id not in tasks
