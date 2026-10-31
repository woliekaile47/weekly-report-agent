// Adapted from Invoice Audit Assistant HistoryPage.tsx (a0a0fc5, MIT).
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { RunSummary } from "../api/types";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { RunHistoryList } from "../components/RunHistoryList";

export function HistoryPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["runs"],
    queryFn: () => request<{ runs: RunSummary[] }>("/runs"),
    refetchInterval: 5000,
  });
  return (
    <>
      <WorkspaceHeader title="任务历史" />
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-foreground">
                任务历史
              </h2>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                查看已上传的任务、执行进度、周报成果和审核记录。
              </p>
            </div>
            <Link to="/" className="primary shrink-0">
              上传材料
            </Link>
          </div>
          {isLoading && (
            <p role="status" className="text-sm text-muted-foreground">
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
      </div>
    </>
  );
}
