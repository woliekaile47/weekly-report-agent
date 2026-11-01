import type { Metric, RunStatus } from "../api/types";

export const STATUS: Record<string, string> = {
  pending: "待执行",
  running: "正在执行",
  paused: "已暂停",
  awaiting_human: "等待审核",
  approved: "正在交付",
  completed: "已交付",
  error: "执行出错",
  rejected: "已退回",
};
export const NODES: Record<string, string> = {
  ingest: "识别材料",
  calculate: "计算指标",
  evidence: "核对纪要",
  analyze: "分析经营",
  render: "生成周报",
  quality: "自动质检",
  rework: "登记问题与定向返工",
  human_review: "人工审核",
  finalize: "交付成果",
  pause: "暂停与人工处理",
};
export const money = (v: number) =>
  new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(v / 100);
export const pct = (v: number | null) =>
  v == null ? "不适用" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
export const sub = (text: string, tokens: Record<string, string>) =>
  text.replace(/\{\{([^{}]+)\}\}/g, (_, k: string) => tokens[k] ?? `{{${k}}}`);

// Status badges follow the upstream RunHistoryList component (MIT).
export function StatusBadge({ status }: { status: RunStatus }) {
  const colors =
    status === "paused" || status === "awaiting_human"
      ? "bg-amber-100 text-amber-800"
      : status === "error" || status === "rejected"
        ? "bg-rose-100 text-rose-800"
        : status === "completed"
          ? "bg-emerald-100 text-emerald-800"
          : "bg-brand-100 text-brand-800";
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${colors}`}
    >
      {STATUS[status] ?? status}
    </span>
  );
}

export function FileInput({
  label,
  name,
  accept,
  required = false,
}: {
  label: string;
  name: string;
  accept: string;
  required?: boolean;
}) {
  return (
    <label className="upload">
      <span>{label}</span>
      <input
        aria-label={label}
        type="file"
        name={name}
        accept={accept}
        required={required}
      />
      <small>单个文件最多 20 MB</small>
    </label>
  );
}

export function MetricsTable({ rows }: { rows: Metric[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>对象</th>
            <th>实收（元）</th>
            <th>环比</th>
            <th>毛利率</th>
            <th>目标达成率</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.label}</td>
              <td>{money(r.cents)}</td>
              <td
                className={r.change != null && r.change < 0 ? "negative" : ""}
              >
                {pct(r.change)}
              </td>
              <td>{r.margin == null ? "不适用" : r.margin.toFixed(1) + "%"}</td>
              <td>
                {r.target_rate == null ? "—" : r.target_rate.toFixed(1) + "%"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
