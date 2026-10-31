// Reuses DeerFlow's ChainOfThought/Step renderer for factual workflow events, not model reasoning.
import {
  CheckCircleIcon,
  CircleIcon,
  ClipboardListIcon,
  LoaderCircleIcon,
  PauseCircleIcon,
} from "lucide-react";
import type { GraphNodeName, StateSnapshot } from "@/api/types";
import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import { money, NODES, pct } from "@/components/ui";

export function ExecutionProgress({ state: s }: { state: StateSnapshot }) {
  const complete: Record<GraphNodeName, boolean> = {
    ingest: !!s.sales,
    calculate: !!s.metrics,
    evidence: !!s.minutes?.sources?.length,
    analyze: !!s.draft,
    render: !!s.artifact,
    quality: s.quality?.passed === true,
    human_review: s.status === "approved" || s.status === "completed",
    finalize: s.status === "completed",
  };
  const current =
    s.status === "paused"
      ? s.resume_node
      : s.status === "awaiting_human"
        ? "human_review"
        : s.current_node;
  const descriptions: Record<string, string> = {
    ingest: s.sales
      ? `${s.sales.raw_rows.toLocaleString()} 条原始记录，去重后 ${s.sales.rows.toLocaleString()} 条`
      : "读取销售明细与关联基础资料",
    calculate: s.metrics
      ? `实收 ${money(s.metrics.total.cents)} 元 · 环比 ${pct(s.metrics.total.change)}`
      : "按门店、区域、品类计算指标",
    evidence: s.minutes?.sources?.length
      ? `已提取 ${s.minutes.sources.length} 条原文，保留来源编号`
      : "识别纪要周期并核对原文依据",
    analyze: s.draft
      ? "已生成经营分析，原因与引用保存在周报中"
      : "结合指标与纪要分析经营异常",
    render: s.artifact ? "已生成 Word 周报" : "按业务模板生成图表与 Word",
    quality: s.quality
      ? `${s.quality.checks.filter((c) => c.passed).length} / ${s.quality.checks.length} 项检查通过${s.quality.page_audit?.pages ? ` · ${s.quality.page_audit.pages} 页` : ""}`
      : "检查指标、证据、图表与页数",
    human_review: complete.human_review
      ? "当前版本已通过人工审核"
      : s.status === "awaiting_human"
        ? "请核对成果并提交审核决定"
        : "程序质检通过后送审",
    finalize:
      s.status === "completed"
        ? "正式交付包已生成"
        : "审核通过后生成正式交付包",
  };
  return (
    <div className="space-y-4">
      <ChainOfThought defaultOpen className="rounded-xl border bg-card/50">
        <ChainOfThoughtHeader
          icon={<ClipboardListIcon className="size-4" />}
          className="p-4"
        >
          执行过程
          <span className="ml-2 text-xs text-muted-foreground">
            {Object.values(complete).filter(Boolean).length} / 8
          </span>
        </ChainOfThoughtHeader>
        <ChainOfThoughtContent className="mt-0 space-y-4 px-4 pb-5">
          {(Object.keys(complete) as GraphNodeName[]).map((node) => {
            const active = current === node && !complete[node];
            const paused = active && s.status === "paused";
            const Icon = complete[node]
              ? CheckCircleIcon
              : paused
                ? PauseCircleIcon
                : active && s.worker_active
                  ? LoaderCircleIcon
                  : CircleIcon;
            return (
              <ChainOfThoughtStep
                key={node}
                status={
                  complete[node] ? "complete" : active ? "active" : "pending"
                }
                icon={
                  <Icon
                    className={`size-4 ${complete[node] ? "text-emerald-600" : paused ? "text-amber-600" : ""} ${active && s.worker_active ? "animate-spin" : ""}`}
                  />
                }
                label={
                  <div className="flex items-center justify-between gap-3">
                    <span>{NODES[node]}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {paused
                        ? "已暂停"
                        : complete[node]
                          ? "已完成"
                          : active
                            ? s.status === "awaiting_human"
                              ? "等待你审核"
                              : "当前步骤"
                            : "待执行"}
                    </span>
                  </div>
                }
                description={
                  complete[node] || active ? descriptions[node] : undefined
                }
              />
            );
          })}
        </ChainOfThoughtContent>
      </ChainOfThought>
      <p className="text-xs leading-6 text-muted-foreground">
        {s.model ?? "读取模型配置"} · 模型调用 {s.model_calls ?? 0}/
        {s.limits?.model_calls ?? "—"} 次 · 活动耗时{" "}
        {Math.round(s.active_seconds ?? 0)}/{s.limits?.active_seconds ?? "—"} 秒
      </p>
    </div>
  );
}
