import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ["REPORT_AGENT_ROOT"] = str(ROOT)
os.environ["REPORT_AGENT_DATA"] = str(ROOT / "runtime" / f"tests-{uuid.uuid4().hex[:8]}")


@pytest.fixture(scope="session")
def public_data():
    explicit = os.environ.get("PUBLIC_DATA_DIR")
    if explicit:
        return Path(explicit)
    for parent in ROOT.parents:
        match = next(parent.glob("赛题/**/周报格式要求.md"), None)
        if match:
            return match.parent
    pytest.skip("请通过 PUBLIC_DATA_DIR 指向企业场景A数据目录")


@pytest.fixture(scope="session")
def sales(public_data):
    from report_agent.config import snapshot
    from report_agent.data_tools import read_sales
    from report_agent.service import Service

    s = Service()
    tid = s.create(
        {"year": 2026, "week": 44}, {"sales": ("sales.xlsx", (public_data / "销售明细.xlsx").read_bytes())}
    )
    state = s.store.get(tid)
    result = read_sales(tid, state["inputs"]["sales"], snapshot()["columns"])
    return tid, result
