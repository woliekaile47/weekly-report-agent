// Adapted from Invoice Audit Assistant RunHistoryList.tsx (a0a0fc5, MIT).
import { Link } from "react-router-dom";
import type { RunSummary } from "../api/types";
import { StatusBadge } from "./ui";

export function RunHistoryList({ runs }: { runs: RunSummary[] }) {
  if (runs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        暂无任务。上传销售明细与周会纪要后，任务将显示在这里。
      </p>
    );
  }
  return (
    <ul
      className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white"
      role="list"
    >
      {runs.map((run) => (
        <li key={run.id}>
          <Link
            to={`/runs/${run.id}`}
            className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-slate-50"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-800">
                {run.title}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                第 {run.week} 周 ·{" "}
                {new Date(run.created).toLocaleString("zh-CN")} ·{" "}
                {run.id.slice(0, 8)}
              </p>
            </div>
            <StatusBadge status={run.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
