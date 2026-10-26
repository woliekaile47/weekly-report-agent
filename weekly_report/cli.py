from __future__ import annotations

import argparse
import json
from pathlib import Path

from weekly_report.schemas import Review, TaskSpec
from weekly_report.service import EmployeeService
from weekly_report.settings import Settings


def main():
    parser = argparse.ArgumentParser(description="经营周报员工")
    parser.add_argument("--data-dir", type=Path)
    subs = parser.add_subparsers(dest="command", required=True)
    create = subs.add_parser("create", help="使用指定的业务资料创建并执行任务")
    create.add_argument("--title", required=True, help="任务名称")
    create.add_argument("--start", required=True, help="统计开始日期，格式为年-月-日")
    create.add_argument("--end", required=True, help="统计结束日期，格式为年-月-日")
    create.add_argument("--sales", type=Path, help="销售明细文件")
    create.add_argument("--minutes", type=Path, help="周会纪要文件")
    create.add_argument("--focus", default="分析经营表现、异常原因与改进建议。")
    create.add_argument("--no-comparison", action="store_true", help="不要求上期环比")
    for name in ("state", "run", "resume"):
        sub = subs.add_parser(name)
        sub.add_argument("task_id")
        if name == "resume":
            sub.add_argument("--sales", type=Path)
            sub.add_argument("--minutes", type=Path)
    review = subs.add_parser("review")
    review.add_argument("task_id")
    review.add_argument("decision", choices=["approve", "reject"])
    review.add_argument("--version", type=int, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--feedback", default="")
    subs.add_parser("list")
    args = parser.parse_args()
    settings = Settings(data_dir=args.data_dir)
    service = EmployeeService(settings)
    if args.command == "create":
        spec = TaskSpec(
            title=args.title,
            start_date=args.start,
            end_date=args.end,
            require_comparison=not args.no_comparison,
            focus=args.focus,
        )
        files = {
            role: (path.name, path.read_bytes())
            for role in ("sales", "minutes")
            if (path := getattr(args, role, None)) is not None
        }
        task_id = service.create(spec, files)
        print(json.dumps({"task_id": task_id, "event": "created"}, ensure_ascii=False), flush=True)
        state = service.run(task_id)
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
    elif args.command == "resume":
        files = {
            role: (path.name, path.read_bytes())
            for role in ("sales", "minutes")
            if (path := getattr(args, role, None)) is not None
        }
        state = service.resume(args.task_id, files=files)
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
