// Task workspace adapts DeerFlow chat-page/chat-box to the weekly-report API.
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FilesIcon, RefreshCwIcon } from "lucide-react";
import { request } from "@/api/client";
import { normalizeSnapshot } from "@/api/snapshot";
import type { StateSnapshot, TaskEvent, TaskFile } from "@/api/types";
import { Button } from "@/components/ui/button";
import { StatusBadge, sub } from "@/components/ui";
import { useRunStream } from "@/hooks/useRunStream";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { WorkspaceSplit } from "@/components/workspace/workspace-split";
import { ArtifactPanel } from "@/components/workspace/artifact-panel";
import { ArtifactFileList } from "@/components/workspace/artifact-file-list";
import { ExecutionProgress } from "@/components/workspace/execution-progress";
import {
  PauseForm,
  ReviewForm,
  TaskOutputs,
} from "@/components/workspace/task-sections";

const GraphView = lazy(() =>
  import("@/components/GraphView").then((module) => ({
    default: module.GraphView,
  })),
);

export function RunDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  return <RunWorkspace key={id} id={id} />;
}

function RunWorkspace({ id }: { id: string }) {
  const [generation, setGeneration] = useState(0);
  const stream = useRunStream(id, generation);
  const [state, setState] = useState<StateSnapshot>({});
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [files, setFiles] = useState<TaskFile[]>([]);
  const [tab, setTab] = useState("progress");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const cursor = useRef(0);
  const discovered = useRef<number | null>(null);
  const refresh = () =>
    request<StateSnapshot>(`/runs/${id}`)
      .then((raw) => {
        setState(normalizeSnapshot(raw));
        setLoadError("");
      })
      .catch((e) => setLoadError(String(e)));
  useEffect(() => {
    let active = true;
    let pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const [snapshot, audit, manifest] = await Promise.all([
          request<StateSnapshot>(`/runs/${id}`),
          request<{ events: TaskEvent[] }>(
            `/runs/${id}/events?after=${cursor.current}`,
          ),
          request<{ files: TaskFile[] }>(`/runs/${id}/files`),
        ]);
        if (!active) return;
        setState(normalizeSnapshot(snapshot));
        setLoadError("");
        setFiles(manifest.files ?? []);
        const batch = audit.events ?? [];
        if (batch.length) {
          cursor.current = batch[batch.length - 1].seq;
          setEvents((prev) => [...prev, ...batch]);
        }
      } catch (e) {
        if (active) setLoadError(String(e));
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = window.setInterval(load, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [id, generation]);
  useEffect(() => {
    if (stream.snapshot.task_id) setState(normalizeSnapshot(stream.snapshot));
  }, [stream.snapshot]);
  useEffect(() => {
    if (
      files.some((f) => f.id === "pdf") &&
      discovered.current !== state.version
    ) {
      discovered.current = state.version ?? 1;
      setSelected("pdf");
      if (window.innerWidth >= 1100) setArtifactsOpen(true);
    }
  }, [files, state.version]);
  async function operation(path: string, body: BodyInit, json = false) {
    setBusy(true);
    setError("");
    try {
      await request(`/runs/${id}/${path}`, {
        method: "POST",
        body,
        headers: json ? { "Content-Type": "application/json" } : undefined,
      });
      setGeneration((n) => n + 1);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const active = !!state.worker_active || busy;
  const chooseFile = (file: TaskFile) => {
    setSelected(file.id);
    setArtifactsOpen(true);
  };
  const progress = (
    <div className="space-y-6">
      <ExecutionProgress state={state} />
      {state.draft ? (
        <section className="space-y-3 text-sm leading-7">
          <h2 className="font-medium">本周摘要</h2>
          <p>{sub(state.draft.summary, state.metrics?.tokens ?? {})}</p>
          {state.draft.conflicts?.map((c, i) => (
            <p
              key={i}
              className="border-l-2 border-amber-400 pl-3 text-xs leading-6 text-muted-foreground"
            >
              {sub(c, state.metrics?.tokens ?? {})}
            </p>
          ))}
          <button
            className="text-xs underline underline-offset-4"
            onClick={() => setTab("report")}
          >
            查看完整周报内容
          </button>
        </section>
      ) : (
        <section className="py-2 text-sm leading-7 text-muted-foreground">
          <h3 className="mb-1 font-medium">等待周报成果</h3>
          <p>
            完成材料识别、指标计算和模型分析后显示。草稿通过程序质检后交给你审核。
          </p>
        </section>
      )}
      {files.some((f) => f.kind === "artifact") && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium">生成文件</h2>
          <ArtifactFileList
            files={files.filter((f) => f.kind === "artifact")}
            onSelect={chooseFile}
          />
        </section>
      )}
    </div>
  );
  return (
    <WorkspaceSplit
      id={id}
      open={artifactsOpen}
      onOpenChange={setArtifactsOpen}
      panel={
        <ArtifactPanel
          files={files}
          selected={selected}
          state={state}
          onSelect={setSelected}
          onClose={() => setArtifactsOpen(false)}
        />
      }
    >
      <WorkspaceHeader
        title={
          <>
            <span className="truncate">
              {state.spec?.title ?? "正在读取任务…"}
            </span>
            {state.status && (
              <span className="hidden sm:inline-flex">
                <StatusBadge status={state.status} />
              </span>
            )}
          </>
        }
      >
        {state.status === "awaiting_human" && (
          <Button
            size="sm"
            variant="secondary"
            aria-label="前往人工审核"
            onClick={() =>
              document
                .getElementById("human-review")
                ?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            审核
          </Button>
        )}
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="刷新任务"
          onClick={() => void refresh()}
          disabled={active}
        >
          <RefreshCwIcon />
        </Button>
        <Button
          size="sm"
          variant={artifactsOpen ? "secondary" : "ghost"}
          aria-label="打开任务文件"
          aria-expanded={artifactsOpen}
          onClick={() => setArtifactsOpen((v) => !v)}
        >
          <FilesIcon />
          <span className="hidden sm:inline">文件</span>
          {files.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {files.length}
            </span>
          )}
        </Button>
      </WorkspaceHeader>
      <div className="min-h-0 flex-1 overflow-auto" id="task-scroll">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
          {(error || loadError) && (
            <div role="alert" className="error">
              {error || loadError}
            </div>
          )}
          {!state.task_id && !loadError && (
            <p role="status" className="text-sm text-muted-foreground">
              正在读取任务与执行记录…
            </p>
          )}
          {state.task_id && (
            <>
              <div className="space-y-3">
                <div className="ml-auto w-fit max-w-[95%] rounded-2xl rounded-tr-sm bg-secondary px-4 py-3 text-sm leading-7">
                  <h1 className="font-medium">{state.spec?.title}</h1>
                  <p className="text-muted-foreground">
                    {state.metrics?.period ??
                      `${state.spec?.year} 年第 ${state.spec?.week} 周`}
                  </p>
                  {state.spec?.focus && (
                    <p className="mt-2 whitespace-pre-wrap">
                      {state.spec.focus}
                    </p>
                  )}
                </div>
                {files.some((f) => f.kind === "input") && (
                  <div className="flex justify-end">
                    <ArtifactFileList
                      compact
                      files={files.filter((f) => f.kind === "input")}
                      onSelect={chooseFile}
                    />
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>版本 {state.version ?? 1}</span>
                  <span>·</span>
                  <span>任务 {id.slice(0, 8)}</span>
                  <span className="sm:hidden">
                    · <StatusBadge status={state.status ?? "pending"} />
                  </span>
                  <Link to="/history" className="ml-auto hover:underline">
                    任务历史
                  </Link>
                </div>
              </div>
              <PauseForm
                state={state}
                active={active}
                onOperation={operation}
              />
              {state.status === "running" && !active && (
                <div className="notice">
                  <strong>执行已中断，进度已保存</strong>
                  <p>可从最近检查点继续，已完成的工具结果按缓存复用。</p>
                  <Button
                    onClick={() => void operation("resume", new FormData())}
                  >
                    从检查点继续
                  </Button>
                </div>
              )}
              {active && (
                <p role="status" className="text-xs text-muted-foreground">
                  员工正在处理任务，执行记录实时保存。
                </p>
              )}
              <TaskOutputs
                state={state}
                id={id}
                tab={tab}
                setTab={setTab}
                events={events}
                progress={progress}
                workflow={
                  <Suspense
                    fallback={
                      <p
                        role="status"
                        className="py-6 text-sm text-muted-foreground"
                      >
                        正在加载执行图谱…
                      </p>
                    }
                  >
                    <GraphView
                      currentNode={
                        state.status === "paused"
                          ? (state.resume_node ?? null)
                          : stream.currentNode
                      }
                      completedNodes={stream.completedNodes}
                    />
                  </Suspense>
                }
              />
              <ReviewForm
                key={state.version}
                state={state}
                active={active}
                onOperation={operation}
              />
              <p className="pt-2 text-center text-[11px] text-muted-foreground/60">
                模型分析需结合原始材料核查，审核通过后交付。
              </p>
            </>
          )}
          {loadError && !state.task_id && (
            <Link to="/history" className="secondary">
              返回任务历史
            </Link>
          )}
        </div>
      </div>
    </WorkspaceSplit>
  );
}
