"""Promptfoo engineering scenarios over the real graph/MCP; model replacement is explicit."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["REPORT_AGENT_ROOT"] = str(ROOT)
os.environ["REPORT_AGENT_DATA"] = str(ROOT / "runtime/evals")
sys.path.insert(0, str(ROOT))


def call_api(prompt, options, context):
    import json

    from report_agent.service import Service
    from tests.helpers import test_model

    folder = (
        Path(os.environ["PUBLIC_DATA_DIR"])
        if os.environ.get("PUBLIC_DATA_DIR")
        else next(p for parent in ROOT.parents for p in parent.glob("赛题/**/周报格式要求.md")).parent
    )
    case = context.get("vars", {}).get("scenario", str(prompt))

    async def run():
        service = Service(
            model=test_model, faults={"compute_metrics": -1} if case == "tool_failure" else None
        )
        week = 46 if case == "A-05" else 43 if case == "A-02" else 42 if case == "A-04" else 44
        files = {"sales": ("sales.xlsx", (folder / "销售明细.xlsx").read_bytes())}
        if week != 46:
            files["minutes"] = ("minutes.docx", (folder / f"周会纪要_2026W{week}.docx").read_bytes())
        if case == "A-03":
            files.pop("sales")
        tid = service.create({"year": 2026, "week": week}, files)
        state = await service.operate(tid)
        initial = state["status"]
        if case == "A-03":
            state = await service.operate(
                tid, action="resume", files={"sales": ("sales.xlsx", (folder / "销售明细.xlsx").read_bytes())}
            )
        metrics = state.get("metrics", {})
        quality = state.get("quality", {})
        return {
            "scenario": case,
            "model_source": "test replacement, not live",
            "task_id": tid,
            "status": state["status"],
            "initial_status": initial,
            "reason": state.get("reason", ""),
            "total": metrics.get("total"),
            "data_quality": metrics.get("quality"),
            "quality_passed": quality.get("passed"),
            "pages": quality.get("page_audit", {}).get("pages"),
            "tool_failures": len([e for e in service.store.events(tid) if e["kind"] == "tool_failed"]),
        }

    return {"output": json.dumps(asyncio.run(run()), ensure_ascii=False)}
