// Adapted from Invoice Audit Assistant HistoryPage.tsx (a0a0fc5, MIT).
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { RunSummary } from "../api/types";
import { RunHistoryList } from "../components/RunHistoryList";

export function HistoryPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["runs"],
    queryFn: () => request<{ runs: RunSummary[] }>("/runs"),
    refetchInterval: 5000,
  });
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">任务历史</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            查看已上传的任务、执行进度、周报成果和审核记录。
          </p>
        </div>
        <Link to="/" className="primary shrink-0">
          上传材料
        </Link>
      </div>
      {isLoading && (
        <p role="status" className="text-sm text-slate-500">
          正在读取任务…
        </p>
      )}
      {isError && (
        <p role="alert" className="error">
          {(error as Error).message}
        </p>
      )}
      {data && <RunHistoryList runs={data.runs} />}
    </div>
  );
}
