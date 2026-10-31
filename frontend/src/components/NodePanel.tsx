// Layout adapted from Invoice Audit Assistant NodePanel.tsx (a0a0fc5, MIT).
import type { StateSnapshot, TraceEventOut } from "../api/types";
import { money, NODES, pct, STATUS } from "./ui";

export function NodePanel({
  snapshot: s,
  trace,
}: {
  snapshot: StateSnapshot;
  trace: TraceEventOut[];
}) {
  return (
    <div className="flex h-[560px] flex-col gap-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold tracking-wide text-slate-500">
        实时节点输出
      </h3>
      {s.status === "paused" && (
        <div
          role="status"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <p className="font-semibold">
            {s.error_kind === "budget"
              ? "超限暂停，等待人工处理"
              : "任务已暂停"}
          </p>
          <p className="mt-1 leading-6">{s.reason}</p>
          <a
            className="mt-2 inline-block text-brand-600 hover:underline"
            href="#task-actions"
          >
            补充材料或恢复执行 ↓
          </a>
        </div>
      )}
      <section>
        <h4 className="mb-2 text-sm font-semibold text-slate-800">执行用量</h4>
        <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-1.5 text-sm">
          <dt className="text-slate-500">分析模型</dt>
          <dd className="break-all">{s.model ?? "读取中"}</dd>
          <dt className="text-slate-500">模型调用</dt>
          <dd>
            {s.model_calls ?? 0} / {s.limits?.model_calls ?? "—"} 次
          </dd>
          <dt className="text-slate-500">活动耗时</dt>
          <dd>
            {Math.round(s.active_seconds ?? 0)} /{" "}
            {s.limits?.active_seconds ?? "—"} 秒
          </dd>
        </dl>
      </section>
      {s.sales && (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-slate-800">
            材料识别
          </h4>
          <p className="text-sm leading-6 text-slate-600">
            {s.sales.sheet} · {s.sales.raw_rows.toLocaleString()}{" "}
            条原始记录，去重后 {s.sales.rows.toLocaleString()} 条。
          </p>
        </section>
      )}
      {s.metrics && (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-slate-800">
            计算结果
          </h4>
          <p className="text-sm leading-6 text-slate-600">
            实收 {money(s.metrics.total.cents)} 元 · 环比{" "}
            {pct(s.metrics.total.change)} · {s.metrics.anomalies.length} 项异常
          </p>
        </section>
      )}
      {s.quality && (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-slate-800">
            程序质检
          </h4>
          <p
            className={`text-sm ${s.quality.passed ? "text-emerald-700" : "text-rose-700"}`}
          >
            {s.quality.checks.filter((c) => c.passed).length} /{" "}
            {s.quality.checks.length} 项通过
            {s.quality.page_audit?.pages != null &&
              ` · Word ${s.quality.page_audit.pages} 页`}
          </p>
        </section>
      )}
      <section className="mt-auto">
        <h4 className="mb-1 text-sm font-semibold text-slate-800">节点记录</h4>
        <ul className="space-y-1 text-xs text-slate-500">
          {trace.slice(-8).map((t, i) => (
            <li key={`${t.node}-${i}`}>
              <span className="font-mono text-slate-400">
                {new Date(t.timestamp).toLocaleTimeString("zh-CN")}
              </span>{" "}
              <span className="font-semibold text-slate-600">
                {NODES[t.node] ?? t.node}
              </span>
              ：{STATUS[t.summary] ?? t.summary}
            </li>
          ))}
        </ul>
        {!trace.length && (
          <p className="text-xs text-slate-400">
            节点执行后显示记录，完整留痕见下方“执行记录”。
          </p>
        )}
      </section>
    </div>
  );
}
