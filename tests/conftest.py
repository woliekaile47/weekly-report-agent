import pytest

from tests.fakes import fake_generate
from weekly_report.schemas import TaskSpec
from weekly_report.service import EmployeeService
from weekly_report.settings import ROOT, Settings


@pytest.fixture(autouse=True)
def model_stub(monkeypatch):
    monkeypatch.setattr("weekly_report.graph.generate", fake_generate)


@pytest.fixture
def service(tmp_path):
    return EmployeeService(Settings(data_dir=tmp_path / "runtime"))


@pytest.fixture
def spec():
    return TaskSpec(title="测试经营周报", start_date="2026-10-26", end_date="2026-11-01")


@pytest.fixture
def files():
    return {
        "sales": ("sales.csv", (ROOT / "tests/fixtures/sales.csv").read_bytes()),
        "minutes": ("minutes.md", (ROOT / "tests/fixtures/minutes.md").read_bytes()),
    }
