"""Keep a small, secret-free evaluation record in Git; leave full artifacts local."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
summary = {"date": "2026-10-25", "timezone": "Asia/Shanghai", "runs": []}
for name in ("offline", "live", "live-recheck"):
    path = root / "evals/results" / f"{name}.json"
    if not path.exists():
        continue
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for result in report["results"]["results"]:
        output = json.loads(result["response"]["output"])
        cases.append(
            {
                "scenario": output["scenario"],
                "mode": output["mode"],
                "passed": result["success"],
                "status": output["status"],
                "version": output["version"],
                "quality_passed": output["quality_passed"],
                "task_id": output["task_id"],
            }
        )
    summary["runs"].append(
        {"name": name, "passed": sum(c["passed"] for c in cases), "total": len(cases), "cases": cases}
    )
(root / "docs/evaluation-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("Saved docs/evaluation-summary.json")
