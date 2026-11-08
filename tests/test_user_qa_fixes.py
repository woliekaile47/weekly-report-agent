"""Business regressions reported in the 2026-11-02 user acceptance run."""

import asyncio
import json
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import pytest
from docx import Document
from fastapi.testclient import TestClient
from openpyxl.utils.datetime import CALENDAR_WINDOWS_1900, to_excel

from report_agent.api import app, public, service, tasks
from report_agent.config import snapshot
from report_agent.data_tools import (
    compute_metrics,
    inspect_office_archive,
    parse_sales_day,
    read_minutes,
    read_sales,
    workbook_has_catalogs,
)
from report_agent.documents import inspect_report, report_quality_notes, sha256
from report_agent.models import Draft, WorkflowError
from report_agent.service import Service
from report_agent.store import task_path


def workbook(*, missing_store=False, duplicate_names=False, negative_target=False,
             invalid_year=False, target_rows=None, current_amounts=None, current_costs=None,
             channel_override=None):
    rows = [
        {
            "record_id": f"R{day:02}{store}", "date": str(date(2026, 10, 19) + timedelta(days=day)),
            "store_id": store, "product_id": f"P{store[-1]}",
            "channel": channel_override if channel_override and day == 7 and store == "S01" else "外卖",
            "quantity": 1,
            "amount": 100 if day < 7 else (current_amounts or {}).get(store, 120 if store == "S01" else 80),
            "cost": 40 if day < 7 else (current_costs or {}).get(store, 40),
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
    if target_rows is not None:
        targets = target_rows
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


def test_review_workspace_uses_word_data_quality_prose():
    task_id = service.create({"year": 2026, "week": 44}, {"sales": ("sales.xlsx", workbook())})
    state = service.store.get(task_id)
    parsed = read_sales(task_id, state["inputs"]["sales"], snapshot()["columns"])
    computed = compute_metrics(task_id, parsed, state["spec"])
    draft = {"summary": "本周经营摘要", "anomalies": [], "actions": ["复核数据"], "data_notes": ["核对门店记录。"]}
    notes = report_quality_notes(computed, draft)
    shown = public({**state, "metrics": computed, "draft": draft})["report_quality_notes"]
    assert shown == notes
    assert any("重复上传" in note for note in shown)
    assert any("退货" in note for note in shown)
    assert shown[-1] == "核对门店记录。"


def test_same_names_keep_separate_codes_and_anomalies():
    result = metrics(workbook(duplicate_names=True))
    stores = [group for group in result["groups"] if group["dimension"] == "store"]
    assert len(stores) == 2 and {group["change"] for group in stores} == {20.0, -20.0}
    assert {group["label"] for group in stores} == {"同名门店（S01）", "同名门店（S02）"}
    assert len(result["top_products"]) == 2
    assert {product["product_id"] for product in result["top_products"]} == {"P1", "P2"}


@pytest.mark.parametrize("amount_value,display,expected", [
    (110.04, 10.0, True),
    (89.96, -10.0, True),
    (110, 10.0, False),
])
def test_raw_change_threshold_is_independent_of_display_rounding(amount_value, display, expected):
    result = metrics(workbook(current_amounts={"S01": amount_value, "S02": 100}))
    east = next(group for group in result["groups"] if group["dimension"] == "region" and group["label"] == "东区")
    assert east["change"] == display
    assert east["anomaly"] is expected
    assert (east in result["anomalies"]) is expected


def test_raw_margin_drop_above_five_points_is_reported_even_if_display_rounds_to_five():
    result = metrics(workbook(current_amounts={"S01": 100, "S02": 100}, current_costs={"S01": 45.04}))
    east = next(item for item in result["category_margins"] if item["region"] == "东区")
    assert (east["previous_margin"], east["margin"]) == (60.0, 55.0)


def test_unknown_channel_is_a_material_error_before_delivery_share_is_computed():
    task_id = service.create({"year": 2026, "week": 44}, {
        "sales": ("mistyped.xlsx", workbook(channel_override="外麦")),
    })
    with pytest.raises(WorkflowError, match="外麦.*允许值.*外卖") as exc:
        read_sales(task_id, service.store.get(task_id)["inputs"]["sales"], snapshot()["columns"])
    assert exc.value.kind == "materials"


@pytest.mark.parametrize("field", ["negative_target", "invalid_year"])
def test_invalid_target_rows_are_material_errors(field):
    with pytest.raises(WorkflowError, match="目标表字段无效") as exc:
        metrics(workbook(**{field: True}))
    assert exc.value.kind == "materials"
    assert "第 2 行" in str(exc.value)


@pytest.mark.parametrize("reverse", [False, True])
def test_equivalent_target_week_spellings_cannot_overwrite_each_other(reverse):
    targets = [
        {"region": "东区", "year": 2026, "week": 44, "target": 700},
        {"region": "南区", "year": 2026, "week": 44, "target": 700},
        {"region": "东区", "year": 2026, "week": "W44", "target": 9999},
    ]
    if reverse:
        targets.reverse()
    with pytest.raises(WorkflowError, match="重复") as exc:
        metrics(workbook(target_rows=targets))
    assert exc.value.kind == "materials"


@pytest.mark.parametrize("heading,expected", [
    ("经营周会纪要\n统计周期：2026W43", (2026, 43)),
    ("经营周会纪要\n统计周期：2025年第44周", (2025, 44)),
    ("经营周会纪要\n统计周期：2026-W44", (2026, 44)),
    ("经营周会纪要\n统计周期 | 2026W43", (2026, 43)),
    ("经营周会纪要\n" + "会议安排\n" * 9 + "统计周期：2025年第44周", (2025, 44)),
])
def test_minutes_period_declared_on_second_line(heading, expected):
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", heading.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"]) == expected


def test_conflicting_minutes_headers_pause_without_using_body_dates():
    text = "2026年第44周纪要\n统计周期：2026W43\n上次讨论 2025年第42周销量。"
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", text.encode())})
    with pytest.raises(WorkflowError, match="相互冲突") as exc:
        read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert exc.value.kind == "materials"

    text = "2026年第44周纪要\n本次讨论引用 2025年第42周销量。"
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", text.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"]) == (2026, 44)


@pytest.mark.parametrize("heading,year,week", [
    ("2026W43 周会纪要", 2026, 43),
    ("2026-W43 周会纪要", 2026, 43),
    ("2025年第44周周会纪要", 2025, 44),
])
def test_minutes_extract_explicit_year_and_week(heading, year, week):
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", heading.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"]) == (year, week)


@pytest.mark.parametrize("text", [
    "# 周会纪要\n**统计周期：2026W43**\n需核实门店经营。",
    "# 周会纪要\n| 字段 | 内容 |\n| --- | --- |\n| 统计周期 | 2026W43 |",
])
def test_markdown_period_declaration_is_checked_before_analysis(text):
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.md", text.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"]) == (2026, 43)


@pytest.mark.parametrize("text", [
    "周会纪要\n讨论本周经营情况。",
    "周会纪要\n报告周期：2026-10-19 至 2026-10-25",
    "2026年第44周周会纪要\n统计周期：2026-10-19 至 2026-10-25",
    "第44周周会纪要",
])
def test_minutes_without_confirmed_matching_period_are_rejected(text):
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.md", text.encode())})
    if "统计周期" in text:
        pattern = "冲突"
    elif "报告周期" in text:
        result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
        assert (result["year"], result["week"], result["period_start"]) == (2026, 43, "2026-10-19")
        return
    else:
        pattern = "缺少|只有"
    with pytest.raises(WorkflowError, match=pattern):
        read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])


@pytest.mark.parametrize("period", [
    "2026-10-26 至 2026-11-01",
    "2026 年 10 月 26 日—11 月 1 日",
])
def test_valid_date_range_normalizes_to_iso_week(period):
    text = "经营纪要\n统计周期：" + period
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", text.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"]) == (2026, 44)
    assert result["period_lines"] == [2]


@pytest.mark.parametrize("text", [
    "2026年第44周 / 2026年第43周 周会纪要",
    "周会纪要\n报告周期：2026-10-26至2026-11-01；2026-10-19至2026-10-25",
])
def test_all_periods_on_one_line_must_agree(text):
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.txt", text.encode())})
    with pytest.raises(WorkflowError, match="冲突") as exc:
        read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert exc.value.kind == "materials"


def test_cross_year_date_range_and_iso_week_agree():
    text = "统计周期：2025年12月29日至2026年1月4日（2026年第1周）"
    task_id = service.create({"year": 2026, "week": 1}, {"minutes": ("minutes.txt", text.encode())})
    result = read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])
    assert (result["year"], result["week"], result["period_start"]) == (2026, 1, "2025-12-29")


def test_csv_blank_rows_cannot_hide_trailing_sales_record():
    header = "记录ID,销售日期,门店编码,商品编码,渠道,销售数量,实收金额,成本金额\n"

    def row(key, day, value):
        return f"{key},{day},SH01,B01,外卖,1,{value},0\n"

    data = (header + row("R1", "2026-10-19", 100) + row("R2", "2026-10-26", 1400)
            + ",,,,,,,\n" * 100_018 + row("R3", "2026-10-27", 99999)).encode("utf-8-sig")
    task_id = service.create({"year": 2026, "week": 44}, {"sales": ("sales.csv", data)})
    state = service.store.get(task_id)
    parsed = read_sales(task_id, state["inputs"]["sales"], snapshot()["columns"])
    result = compute_metrics(task_id, parsed, state["spec"])
    assert parsed["rows"] == 3
    assert result["total"]["cents"] == 10_139_900


@pytest.mark.parametrize("date_value", [
    "2026年10月26日",
    str(to_excel(datetime(2026, 10, 26), CALENDAR_WINDOWS_1900)),
    "2026-10-25T17:00:00Z",
])
def test_duplicate_date_uses_normalized_business_day(date_value):
    sheets = pd.read_excel(BytesIO(workbook()), sheet_name=None)
    row = sheets["销售"].loc[sheets["销售"]["record_id"] == "R07S01"].iloc[0].copy()
    row["date"] = date_value
    sheets["销售"].loc[sheets["销售"]["record_id"] == "R07S01", "date"] = date_value
    sheets["销售"] = pd.concat([sheets["销售"], pd.DataFrame([row])], ignore_index=True)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, values in sheets.items():
            values.to_excel(writer, sheet_name=name, index=False)
    task_id = service.create({"year": 2026, "week": 44}, {"sales": ("sales.xlsx", output.getvalue())})
    state = service.store.get(task_id)
    parsed = read_sales(task_id, state["inputs"]["sales"], snapshot()["columns"])
    normalized = json.loads(task_path(task_id, parsed["file"]).read_text(encoding="utf-8"))
    result = compute_metrics(task_id, parsed, state["spec"])
    assert normalized["removed"] == [{"date": "2026-10-26", "cents": 12000}]
    assert result["quality"]["removed_count"] == 1
    assert result["quality"]["removed_cents"] == 12000


def test_excel_precheck_is_shared_by_master_and_catalog_detection(monkeypatch, tmp_path):
    import report_agent.data_tools as data_tools

    sheets = pd.read_excel(BytesIO(workbook()), sheet_name=None)
    master = BytesIO()
    with pd.ExcelWriter(master, engine="openpyxl") as writer:
        for name in ("门店", "商品", "目标"):
            sheets[name].to_excel(writer, sheet_name=name, index=False)
    master_path = tmp_path / "master.xlsx"
    master_path.write_bytes(master.getvalue())
    sales = sheets["销售"].to_csv(index=False).encode("utf-8-sig")
    task_id = service.create({"year": 2026, "week": 44}, {
        "sales": ("sales.csv", sales), "master": ("master.xlsx", master.getvalue()),
    })
    state = service.store.get(task_id)
    checked = []
    original = data_tools.inspect_office_archive

    def inspect(path, *args, **kwargs):
        checked.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(data_tools, "inspect_office_archive", inspect)
    read_sales(task_id, state["inputs"]["sales"], snapshot()["columns"],
               master_file=state["inputs"]["master"])
    assert task_path(task_id, state["inputs"]["master"]) in checked
    assert workbook_has_catalogs(master_path, snapshot()["columns"])
    assert master_path in checked


def test_oversized_master_archive_is_rejected_before_excel_parser(tmp_path):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for number in range(501):
            archive.writestr(f"xl/worksheets/part{number}.xml", "x")
    master_path = tmp_path / "master.xlsx"
    master_path.write_bytes(output.getvalue())
    assert not workbook_has_catalogs(master_path, snapshot()["columns"])
    sales = pd.read_excel(BytesIO(workbook()), sheet_name="销售").to_csv(index=False).encode("utf-8-sig")
    task_id = service.create({"year": 2026, "week": 44}, {
        "sales": ("sales.csv", sales), "master": ("master.xlsx", output.getvalue()),
    })
    state = service.store.get(task_id)
    with pytest.raises(WorkflowError, match="资源上限") as exc:
        read_sales(task_id, state["inputs"]["sales"], snapshot()["columns"],
                   master_file=state["inputs"]["master"])
    assert exc.value.kind == "materials"


def test_word_table_period_is_read_in_document_order_and_conflicts_with_title():
    doc = Document()
    doc.add_paragraph("2026年第44周周会纪要")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "统计周期"
    table.cell(0, 1).text = "2026W43"
    doc.add_paragraph("会议说明仅供经营分析使用。")
    output = BytesIO()
    doc.save(output)
    task_id = service.create({"year": 2026, "week": 44}, {"minutes": ("minutes.docx", output.getvalue())})
    with pytest.raises(WorkflowError, match="冲突"):
        read_minutes(task_id, service.store.get(task_id)["inputs"]["minutes"])


def test_ambiguous_sales_dates_are_rejected_and_timezone_is_converted():
    with pytest.raises(WorkflowError, match="有歧义"):
        parse_sales_day("10/11/2026")
    assert parse_sales_day("2026年10月26日") == date(2026, 10, 26)
    assert parse_sales_day("2026-10-25T17:00:00Z") == date(2026, 10, 26)
    assert parse_sales_day(str(to_excel(datetime(2026, 10, 26), CALENDAR_WINDOWS_1900)),
                           CALENDAR_WINDOWS_1900) == date(2026, 10, 26)


def test_compressed_office_file_is_bounded_before_parsing(tmp_path):
    path = tmp_path / "huge.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "x" * 101)
    with pytest.raises(WorkflowError, match="资源上限"):
        inspect_office_archive(path, max_uncompressed=100)


@pytest.mark.parametrize("change", [
    {"summary": "  "}, {"actions": [""]}, {"actions": []},
    {"anomalies": [{"metric_id": "g1", "reason": " ", "uncertain": True}]},
])
def test_draft_rejects_empty_required_content(change):
    baseline = {"summary": "本周业务摘要有具体指标。", "anomalies": [], "actions": ["运营负责人核查销售明细。"]}
    with pytest.raises(ValueError):
        Draft.model_validate({**baseline, **change})


def test_word_quality_rejects_wrong_kpi_token_cited_kpi_number_and_empty_sections():
    task_id = service.create({"year": 2026, "week": 44})
    path = task_path(task_id, "artifacts/qa.docx")
    path.parent.mkdir(parents=True, exist_ok=True)
    Document().save(path)
    artifact = {"file": "artifacts/qa.docx", "artifact_id": "qa", "sha256": sha256(path)}
    metrics = {
        "tokens": {"total_amount": "100", "total_margin": "60.0%", "total_change": "-10.0%"},
        "total": {"label": "全公司", "cents": 10000, "change": 0.0, "margin": 60.0, "target_rate": 100.0},
        "groups": [], "anomalies": [],
    }
    minutes = {"sources": [{"id": "M001", "text": "会议于10月20日召开"}]}
    baseline = {
        "summary": "本周实收 {{total_amount}} 元，具体金额已由销售明细核对，管理层按实际数据安排复核。",
        "anomalies": [], "actions": ["运营负责人对照销售明细核查经营变化并反馈。"],
    }

    def failed_check(draft, name):
        report = inspect_report(task_id, artifact, metrics, minutes, draft, snapshot(), [])
        return next(check for check in report["checks"] if check["name"] == name)["passed"] is False

    assert failed_check({**baseline, "summary": "本周实收 {{total_margin}} 元，具体金额已由销售明细核对，管理层按实际数据安排复核。"}, "指标语义一致")
    assert failed_check({**baseline, "summary": "本周环比增长 {{total_change}}，管理层按实际数据安排复核。"}, "指标语义一致")
    assert failed_check({**baseline, "summary": "本周实收20元[M001]，管理层按实际数据安排复核。"}, "正文数字依据")
    assert failed_check({**baseline, "summary": "", "actions": [""], "data_notes": ["已有足够多的文字来填充正文。" * 30]}, "章节内容有效")


def test_complete_excel_replacement_retires_old_master_before_ingest():
    complete = workbook()
    sheets = pd.read_excel(BytesIO(complete), sheet_name=None)
    csv = sheets["销售"].to_csv(index=False).encode("utf-8-sig")
    master = BytesIO()
    with pd.ExcelWriter(master, engine="openpyxl") as writer:
        for name in ("门店", "商品", "目标"):
            sheets[name].to_excel(writer, sheet_name=name, index=False)

    async def no_model(state, store):
        raise WorkflowError("测试模型边界", "qa_boundary")

    async def run():
        agent = Service(model=no_model)
        task_id = agent.create(
            {"year": 2026, "week": 44},
            {"sales": ("sales.csv", csv), "master": ("master.xlsx", master.getvalue())},
        )
        paused = await agent.operate(task_id)
        assert paused["status"] == "paused" and paused["error_kind"] == "materials"
        resumed = await agent.operate(
            task_id,
            action="resume",
            files={
                "sales": ("complete.xlsx", complete),
                "minutes": ("minutes.txt", b"2026W44 weekly meeting"),
            },
        )
        assert resumed["inputs"]["master"] is None
        assert resumed["error_kind"] == "qa_boundary", resumed.get("reason")
        assert resumed["resume_node"] == "analyze"

    asyncio.run(run())


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


def test_resume_empty_file_is_rejected_synchronously_without_starting_worker():
    task_id = service.create({"year": 2026, "week": 44})
    state = service.store.get(task_id)
    state.update(status="paused", reason="缺少销售明细", error_kind="materials")
    service.store.save(task_id, state)
    response = TestClient(app).post(
        f"/api/runs/{task_id}/resume",
        files={"sales": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 422
    assert "销售明细文件为空" in response.json()["detail"]
    assert task_id not in tasks
