from __future__ import annotations

import argparse
import json
from pathlib import Path

from weekly_report.schemas import Review, TaskSpec
from weekly_report.service import EmployeeService
from weekly_report.settings import ROOT, Settings


def main():
    parser = argparse.ArgumentParser(description="经营周报员工")
    parser.add_argument("--mode", choices=["live", "mock"], default=None)
    parser.add_argument("--data-dir", type=Path)
    subs = parser.add_subparsers(dest="command", required=True)
    demo = subs.add_parser("demo", help="用模拟数据发起任务；默认使用真实模型")
    demo.add_argument("--approve", action="store_true", help="仅限 mock 模式自动审核演示")
    for name in ("state", "run", "resume"):
        sub = subs.add_parser(name)
        sub.add_argument("task_id")
    review = subs.add_parser("review")
    review.add_argument("task_id")
    review.add_argument("decision", choices=["approve", "reject"])
    review.add_argument("--version", type=int, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--feedback", default="")
    subs.add_parser("list")
    args = parser.parse_args()
    settings = Settings(data_dir=args.data_dir, mode=args.mode)
    service = EmployeeService(settings)
    if args.command == "demo":
        spec = TaskSpec(title="示例门店经营周报", start_date="2026-10-26", end_date="2026-11-01")
        files = {
            "sales": ("sales.csv", (ROOT / "samples/sales.csv").read_bytes()),
            "minutes": ("minutes.md", (ROOT / "samples/minutes.md").read_bytes()),
        }
        task_id = service.create(spec, files)
        print(json.dumps({"task_id": task_id, "event": "created"}, ensure_ascii=False), flush=True)
        state = service.run(task_id)
        if args.approve:
            if settings.mode != "mock":
                parser.error("真实模型任务须由人工预览后审核；--approve 仅适用于 mock 演示")
            if state["status"] == "REVIEW":
                state = service.review(
                    task_id, Review(decision="approve", version=state["version"], reviewer="离线演示")
                )
    elif args.command == "list":
        print(json.dumps(service.store.tasks(), ensure_ascii=False, indent=2))
        return
    elif args.command == "review":
        state = service.review(
            args.task_id,
            Review(
                decision=args.decision, version=args.version, reviewer=args.reviewer, feedback=args.feedback
            ),
        )
    else:
        state = getattr(service, args.command)(args.task_id)
    summary = {
        k: state[k]
        for k in (
            "task_id",
            "status",
            "version",
            "mode",
            "reason",
            "report_file",
            "delivery",
            "quality",
            "active_seconds",
            "model_calls",
        )
        if k in state
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
