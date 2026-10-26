import pytest

from weekly_report.analysis import calculate, read_sales_file
from weekly_report.schemas import EmployeeError, TaskSpec
from weekly_report.settings import ROOT
from weekly_report.store import task_path


def test_exact_money_and_zero_baseline(service, spec):
    rows = [
        {"date": "2026-10-26", "store": "A", "region": "R", "category": "C", "cents": 10},
        {"date": "2026-10-26", "store": "A", "region": "R", "category": "C", "cents": 20},
        {"date": "2026-10-19", "store": "A", "region": "R", "category": "C", "cents": 0},
    ]
    result = calculate({"records": rows, "warnings": []}, spec.model_dump(mode="json"), 20)
    assert result["total"]["current_cents"] == 30
    assert result["total"]["change_percent"] is None
    assert result["total"]["change_text"] == "上期为零，不适用"


def test_missing_prior_period_requires_materials(spec):
    sales = {
        "records": [{"date": "2026-10-26", "store": "A", "region": "R", "category": "C", "cents": 10}],
        "warnings": [],
    }
    with pytest.raises(EmployeeError, match="上期"):
        calculate(sales, spec.model_dump(mode="json"), 20)
    spec.require_comparison = False
    assert calculate(sales, spec.model_dump(mode="json"), 20)["total"]["previous_cents"] is None


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "abc", ""])
def test_invalid_amount_is_not_silently_zero(tmp_path, service, amount):
    file = tmp_path / "bad.csv"
    file.write_text(f"date,store,region,category,amount\n2026-10-26,A,R,C,{amount}\n", encoding="utf-8")
    with pytest.raises(EmployeeError):
        read_sales_file(file, service.settings.employee()["column_aliases"])


def test_excel_and_csv_equivalence(tmp_path, service):
    import pandas as pd

    source = ROOT / "tests/fixtures/sales.csv"
    target = tmp_path / "sales.xlsx"
    pd.read_csv(source).to_excel(target, index=False)
    aliases = service.settings.employee()["column_aliases"]
    assert read_sales_file(source, aliases) == read_sales_file(target, aliases)


def test_path_traversal_and_bad_date_rejected(tmp_path):
    with pytest.raises(ValueError):
        task_path(tmp_path, "a" * 32, "../../secrets")
    with pytest.raises(ValueError):
        task_path(tmp_path, "../foo")
    with pytest.raises(ValueError):
        TaskSpec(title="test", start_date="2026-11-01", end_date="2026-10-01")
