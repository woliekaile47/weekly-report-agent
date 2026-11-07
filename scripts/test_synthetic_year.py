"""Run isolated fixture checks; environment must be set before application imports."""
# ruff: noqa: E402
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["REPORT_AGENT_DATA"] = str(ROOT / "runtime/synthetic-2025/test-state")
from report_agent.config import snapshot
from report_agent.data_tools import compute_metrics, read_minutes, read_sales
from report_agent.models import WorkflowError
from report_agent.service import Service

out = ROOT / "runtime/synthetic-2025"
expected = json.loads((out / "expected.json").read_text(encoding="utf-8"))
s = Service()
book = (out / "模拟年度2025.xlsx").read_bytes()
tid = s.create({"year": 2025, "week": 1}, {"sales": ("simulation.xlsx", book)})
state = s.store.get(tid)
sales = read_sales(tid, state["inputs"]["sales"], snapshot()["columns"])
assert sales["removed_duplicates"] == 29
checks = []
for week in range(1, 53):
    m = compute_metrics(tid, sales, {"year": 2025, "week": week})
    e = expected["weeks"][f"2025W{week:02}"]
    assert m["total"]["cents"] == e["cents"]
    assert m["quality"]["return_count"] == e["returns"]
    assert m["quality"]["return_cents"] == e["return_cents"]
    f = s.save_input(tid, "minutes", "minutes.txt", (out / f"纪要_2025W{week:02}.txt").read_bytes())
    minutes = read_minutes(tid, f)
    assert minutes["year"] == 2025 and minutes["week"] == week
    checks.append({"week": week, "cents": m["total"]["cents"], "returns": e["returns"], "passed": True})
    print("week", week, "PASS", flush=True)
cid = s.create(
    {"year": 2025, "week": 1},
    {"sales": ("conflict.csv", (out / "冲突重复记录.csv").read_bytes()), "master": ("master.xlsx", book)},
)
cs = s.store.get(cid)
try:
    read_sales(
        cid,
        cs["inputs"]["sales"],
        snapshot()["columns"],
        options={"sheet": "CSV"},
        master_file=cs["inputs"]["master"],
    )
    raise AssertionError("conflict accepted")
except WorkflowError as ex:
    assert "不同内容" in str(ex)
(out / "test-results.json").write_text(
    json.dumps(
        {
            "scope": "52 ISO weeks: deterministic production import/calculation/minutes; not 52 model-generated deliveries",
            "weeks": checks,
            "duplicate_conflict_rejected": True,
            "removed_duplicates": sales["removed_duplicates"],
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print("52-week production data tests passed")
