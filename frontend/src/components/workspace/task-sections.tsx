import { useState, type ReactNode } from "react";
import type { StateSnapshot, TaskEvent } from "@/api/types";
import { fileUrl } from "@/api/client";
import { FileInput, MetricsTable, NODES, pct, sub } from "@/components/ui";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { UserRoundCheckIcon } from "lucide-react";
import { reportStageLabel } from "@/lib/report-stage";

type Operation = (
  path: string,
  data: BodyInit,
  json?: boolean,
) => Promise<void>;

const SECTION_LABELS: Record<string, string> = {
  summary: "本周摘要",
  anomalies: "异常与原因",
  conflicts: "纪要冲突",
  data_notes: "数据质量说明",
  actions: "下周关注事项",
};

const RECOVERY_UPLOAD_LABELS: Record<string, string> = {
  sales: "销售文件",
  minutes: "周会纪要",
  master: "基础资料",
};

function RevisionContent({
  values,
  tokens = {},
}: {
  values: Record<string, unknown>;
  tokens?: Record<string, string>;
}) {
  if (!Object.keys(values).length)
    return <p className="text-muted-foreground">版式调整不改动业务正文。</p>;
  return (
    <div className="space-y-3">
      {Object.entries(values).map(([section, value]) => (
        <div key={section}>
          <h4 className="font-medium">{SECTION_LABELS[section] ?? section}</h4>
          <div className="whitespace-pre-wrap break-words text-xs leading-6">
            {sub(
              Array.isArray(value)
                ? value
                    .map((entry) =>
                      typeof entry === "string" ? entry : (entry?.reason ?? ""),
                    )
                    .join("\n")
                : String(value ?? "等待生成"),
              tokens,
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function PauseForm({
  state,
  active,
  onOperation,
}: {
  state: StateSnapshot;
  active: boolean;
  onOperation: Operation;
}) {
  const [uploadError, setUploadError] = useState("");
  const reason = state.reason ?? "";
  const missingSales = !state.inputs?.sales;
  const showSales = missingSales || /销售明细|销售文件|实际覆盖/.test(reason);
  const showMinutes = /纪要/.test(reason) || (state.resume_node === "evidence" && !state.inputs?.minutes);
  const showPeriod = /周期|周次|实际覆盖/.test(reason);
  const salesField = <FileInput label="替换或补充销售明细" name="sales" accept=".xlsx,.csv" />;
  const minutesField = <FileInput label="替换或补充周会纪要" name="minutes" accept=".docx,.txt,.md" />;
  const periodFields = (
    <div className="form-grid">
      <label>年份<input name="year" type="number" defaultValue={state.spec?.year} /></label>
      <label>ISO 周<input name="week" type="number" defaultValue={state.spec?.week} /></label>
    </div>
  );
  const nextStep = missingSales
    ? "上传销售明细并继续。系统将校验所选周及上一周记录。"
    : showPeriod
      ? "核对所选周期与材料覆盖范围；可修改周次或替换材料后继续。"
      : showMinutes
        ? "上传与所选周一致的纪要后继续。"
        : state.error_kind === "rate_limit" || state.error_kind === "model"
          ? "模型服务暂不可用；确认服务恢复后重试当前步骤。"
          : state.quality?.passed === false
            ? "查看未通过的质检项，补充或修改材料后复检。"
            : "问题处理完成后从已保存的步骤继续。";
  return (
    <>
      {state.status === "paused" && (
        <div className="notice">
          <strong>
            {state.error_kind === "budget"
              ? "已超限，等待人工处理"
              : "任务已暂停"}
          </strong>
          <p>{state.reason}</p>
          <div className="mt-3 space-y-1 text-sm">
            <strong>下一步</strong>
            <p>{nextStep}</p>
            {showPeriod && <p>所选周期：{state.spec?.year} 年第 {state.spec?.week} 周{state.sales && `；销售覆盖：${state.sales.date_start} 至 ${state.sales.date_end}`}{state.minutes?.year && `；纪要识别：${state.minutes.year} 年第 ${state.minutes.week} 周`}</p>}
            {state.quality?.passed === false && state.quality.checks?.filter((check) => !check.passed).map((check) => (
              <p key={check.name}>未通过：{check.name}。{check.details}</p>
            ))}
          </div>
          <form
            onChange={(e) => {
              const input = e.target;
              if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
              const invalid = Array.from(e.currentTarget.querySelectorAll<HTMLInputElement>('input[type="file"]'))
                .find((field) => field.files?.[0]?.size === 0);
              const file = invalid?.files?.[0];
              setUploadError(file ? `${RECOVERY_UPLOAD_LABELS[invalid?.name ?? ""]}“${file.name}”为空，请选择非空文件。` : "");
            }}
            onSubmit={(e) => {
              e.preventDefault();
              for (const input of e.currentTarget.querySelectorAll<HTMLInputElement>('input[type="file"]')) {
                const file = input.files?.[0];
                if (file && file.size === 0) {
                  setUploadError(`${RECOVERY_UPLOAD_LABELS[input.name]}“${file.name}”为空，请选择非空文件。`);
                  return;
                }
              }
              const data = new FormData(e.currentTarget);
              setUploadError("");
              data.set(
                "spec",
                JSON.stringify({
                  ...state.spec,
                  year: Number(data.get("year")),
                  week: Number(data.get("week")),
                }),
              );
              const fields = { ...state.import_options?.fields };
              for (const key of ["amount", "date", "cost"]) {
                const value = String(data.get(key) ?? "");
                if (value) fields[key] = value;
                else delete fields[key];
              }
              const mapping = {
                sheet: String(data.get("sheet") ?? ""),
                fields,
              };
              data.set("import_options", JSON.stringify(mapping));
              for (const k of ["sales", "minutes", "master"]) {
                const input = e.currentTarget.elements.namedItem(k) as HTMLInputElement | null;
                const selected = input?.files?.[0];
                if (selected) data.set(k, selected);
                else data.delete(k);
              }
              onOperation("resume", data);
            }}
          >
            {(showSales || showMinutes) && (
              <div className="uploads">
                {showSales && salesField}
                {showMinutes && minutesField}
              </div>
            )}
            {showPeriod && periodFields}
            <details>
              <summary>补充材料、调整周期或列映射</summary>
              <div className="uploads">
                {!showSales && salesField}
                {!showMinutes && minutesField}
              </div>
              <FileInput
                label="基础资料（可选）"
                name="master"
                accept=".xlsx"
              />
              {state.inputs?.master && (
                <div className="mt-2 flex items-start gap-2 text-sm text-foreground">
                  <input
                    id="remove-master"
                    name="remove_master"
                    type="checkbox"
                    value="true"
                    className="mt-1 size-4 shrink-0"
                  />
                  <label htmlFor="remove-master" className="cursor-pointer">
                    移除已有基础资料。改用完整 Excel 时，系统也会自动移除旧资料。
                  </label>
                </div>
              )}
              {!showPeriod && periodFields}
              <div className="form-grid">
                <label>
                  明细工作表
                  <input
                    name="sheet"
                    defaultValue={state.import_options?.sheet ?? ""}
                    placeholder="自动识别"
                  />
                </label>
              </div>
              <div className="form-grid">
                {(
                  [
                    ["amount", "实收金额"],
                    ["date", "销售日期"],
                    ["cost", "成本金额"],
                  ] as const
                ).map(([k, label]) => (
                  <label key={k}>
                    {label}列名
                    <input
                      name={k}
                      defaultValue={state.import_options?.fields?.[k] ?? ""}
                      placeholder="自动识别"
                    />
                  </label>
                ))}
              </div>
            </details>
            {state.error_kind === "budget" && (
              <>
                <label>
                  处理人
                  <input name="handler" required />
                </label>
                <label>
                  处理意见
                  <textarea name="note" required />
                </label>
              </>
            )}
            {uploadError && <p role="alert" className="error">{uploadError}</p>}
            <button className="primary" disabled={active}>
              {missingSales ? "上传销售明细并继续" : showMinutes ? "上传纪要并继续" : state.error_kind === "rate_limit" || state.error_kind === "model" ? "重试当前步骤" : "恢复执行"}
            </button>
            {state.draft && state.error_kind !== "budget" && (
              <button
                type="button"
                className="secondary"
                onClick={() => onOperation("recheck", new FormData())}
              >
                复检现有草稿（不调用模型）
              </button>
            )}
          </form>
        </div>
      )}
    </>
  );
}

export function TaskOutputs({
  state,
  id,
  tab,
  setTab,
  events,
  progress,
  workflow,
}: {
  state: StateSnapshot;
  id: string;
  tab: string;
  setTab: (tab: string) => void;
  events: TaskEvent[];
  progress: ReactNode;
  workflow: ReactNode;
}) {
  const metrics = state.metrics;
  const draft = state.draft;
  const tokens = metrics?.tokens ?? {};
  return (
    <section className="results min-w-0">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto w-full justify-start overflow-auto bg-transparent p-0 pb-2">
          {[
            ["progress", "工作进度"],
            ["report", "周报内容"],
            ["quality", "质检记录"],
            ["revisions", "修改台账"],
            ["materials", "材料识别"],
            ["events", "执行记录"],
            ["workflow", "执行图谱"],
          ].map(([value, label]) => (
            <TabsTrigger
              key={value}
              value={value}
              className="shrink-0 px-3 py-2 text-xs data-[state=active]:bg-secondary data-[state=active]:shadow-none"
            >
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {tab === "progress" && progress}
      {tab === "workflow" && workflow}
      {tab === "report" && (
        <>
          {!draft ? (
            <div className="empty">
              <h3>等待周报成果</h3>
              <p>
                完成材料识别、指标计算和模型分析后显示。生成的草稿会先通过程序质检，再交给你审核。
              </p>
            </div>
          ) : (
            <div className="report-content card">
              <div className="section-heading">
                <h2>本周摘要</h2>
                <span className="tag">
                  {reportStageLabel(state)}
                </span>
              </div>
              <p>{state.report_summary ?? sub(draft.summary, tokens)}</p>
              {metrics && (
                <>
                  <h2>核心经营指标</h2>
                  <MetricsTable
                    rows={[
                      metrics.total,
                      ...metrics.groups.filter((g) => g.dimension === "region"),
                    ]}
                  />
                  <h2>异常与原因</h2>
                  {state.report_anomaly_groups?.map((group) => (
                    <section className="anomaly-group" key={group.region}>
                      <h3 className="region-band">{group.header}</h3>
                      {group.rows.map((row, i) => (
                        <article className={`finding ${row.kind}`} key={row.metric_id ?? `${row.kind}-${i}`}>
                          <h3>
                            {row.label}
                            <span className="tag">{row.change}</span>
                          </h3>
                          <p>{row.text}</p>
                          {row.evidence.map((ev, j) => (
                            <blockquote key={j}>
                              [{ev.source_id}] {ev.quote}
                            </blockquote>
                          ))}
                        </article>
                      ))}
                    </section>
                  ))}
                  <h2>品类表现</h2>
                  <MetricsTable
                    rows={metrics.groups.filter(
                      (g) => g.dimension === "category",
                    )}
                  />
                  {metrics.category_margins?.map((r) => (
                    <p className="conflict" key={r.region + r.category}>
                      {r.region}
                      {r.category}毛利率：{r.previous_margin.toFixed(1)}% →{" "}
                      {r.margin.toFixed(1)}%
                    </p>
                  ))}
                  <p className="muted">
                    实收前五单品：
                    {metrics.top_products.map((p) => p.product).join("、")}
                  </p>
                </>
              )}
              <h2>下周关注事项</h2>
              <ul>
                {(state.report_actions ?? draft.actions).map((a, i) => (
                  <li key={i}>{sub(a, tokens)}</li>
                ))}
              </ul>
              {(state.report_quality_notes?.length || draft.data_notes?.length > 0) && (
                <>
                  <h2>数据质量说明</h2>
                  {(state.report_quality_notes ?? draft.data_notes ?? []).map((n, i) => (
                    <p key={i}>{sub(n, tokens)}</p>
                  ))}
                </>
              )}
              <p className="muted">网页展示报告内容；请以右侧 PDF 预览核对最终 Word 排版。</p>
              {draft.review_response && (
                <div className="notice">
                  <strong>修改说明</strong>
                  <p>{sub(draft.review_response, tokens)}</p>
                </div>
              )}
              <div className="download-row">
                {state.artifact?.file && (
                  <>
                    <a className="secondary" href={fileUrl(id, "docx")}>
                      下载 Word {state.status !== "completed" && "草稿"}
                    </a>
                    <a
                      className="secondary"
                      target="_blank"
                      rel="noreferrer"
                      href={fileUrl(id, "pdf")}
                    >
                      查看排版预览
                    </a>
                  </>
                )}
                {state.status === "completed" && (
                  <a className="primary" href={fileUrl(id, "package")}>
                    下载正式交付包
                  </a>
                )}
              </div>
            </div>
          )}
        </>
      )}
      {tab === "quality" && (
        <section className="card">
          <h2>自动质检</h2>
          {state.quality?.checks?.map((c, i) => (
            <div className="check" key={i}>
              <span className={c.passed ? "pass" : "fail"}>
                {c.passed ? "✓" : "!"}
              </span>
              <div>
                <strong>{c.name}</strong>
                <p>{c.details}</p>
              </div>
            </div>
          ))}
          {!state.quality?.checks && (
            <p className="muted">生成 Word 后执行检查；当前没有质检记录。</p>
          )}
        </section>
      )}
      {tab === "revisions" && (
        <section className="card space-y-4">
          <h2>审核意见与逐项修改</h2>
          <p className="text-xs text-muted-foreground">
            程序核对回应、实际内容差异和引用来源；修改是否充分，仍由审核人确认。
          </p>
          {!state.revision_items?.length && (
            <p className="muted">暂无人工退回意见。</p>
          )}
          {state.revision_items?.map((item) => (
            <article
              key={item.id}
              className="rounded-lg border p-4 text-sm space-y-2"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <strong>
                  {item.id} · {item.text}
                </strong>
                <span
                  className={
                    item.status === "verified"
                      ? "text-emerald-700"
                      : "text-amber-700"
                  }
                >
                  {item.status === "verified"
                    ? state.status === "completed" ||
                      state.status === "approved"
                      ? "已随当前版本审核通过"
                      : "程序核验通过，待人工确认"
                    : "待处理"}
                </span>
              </div>
              <p>{item.response || "等待员工回应"}</p>
              <p className="text-xs text-muted-foreground">
                {item.verification}
              </p>
              <details>
                <summary className="cursor-pointer">查看修改前后内容</summary>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div className="min-w-0">
                    <strong>修改前</strong>
                    <RevisionContent
                      values={item.before}
                      tokens={item.before_tokens}
                    />
                  </div>
                  <div className="min-w-0">
                    <strong>修改后</strong>
                    <RevisionContent
                      values={item.after ?? {}}
                      tokens={item.after_tokens}
                    />
                  </div>
                </div>
              </details>
            </article>
          ))}
        </section>
      )}
      {tab === "materials" && (
        <section className="card">
          <h2>材料识别与口径</h2>
          {state.news && <div className="my-4 rounded border p-4">
            <h3>外部信息核对</h3><p>{state.news.message}</p>
            {state.news.plan?.items.map((q, i) => <p key={i} className="text-sm">{q.origin === "auto" ? "自动检索" : "手动补充"}：{q.query}{q.claim && `（核实：${q.claim}）`}</p>)}
            {!!state.news.plan?.dropped.length && <p className="text-xs text-muted-foreground">已拦截 {state.news.plan.dropped.length} 条可能含内部信息的检索词，未发送：{state.news.plan.dropped.map(d => d.reason).join("、")}</p>}
            {state.draft?.news_assessments?.map((a,i) => <div key={i} className="my-2"><strong>{a.source_id} · 模型判断（待人工确认）：{a.verdict === "support" ? "存在支持线索" : a.verdict === "conflict" ? "存在冲突线索" : "无法核实"}</strong><p>{a.explanation}</p>{a.citations.map(c => <p key={c.source_id}>[{c.source_id}] {c.quote}</p>)}</div>)}
            <p className="text-xs">检索时间：{state.news.retrieved_at ?? "未检索"}</p>
            {state.news.sources.map(n => <article key={n.id} className="my-3 border-t pt-2">
              <a href={/^https?:\/\//.test(n.url) ? n.url : undefined} target="_blank" rel="noopener noreferrer">[{n.id}] {n.title}</a>
              <p>{n.publisher} · {n.published_at || "发布日期不明"} · {n.time_status === "in_range" ? "检索期内" : "日期需复核"} · {n.verdict}</p>
              <p className="text-sm">{n.excerpt}</p>
            </article>)}
          </div>}
          {state.sales ? (
            <>
              <p>
                {state.sales.sheet} · 原始{" "}
                {state.sales.raw_rows.toLocaleString()} 行 · 去重后{" "}
                {state.sales.rows.toLocaleString()} 行
              </p>
              <p>
                覆盖 {state.sales.date_start} 至 {state.sales.date_end} ·
                剔除相同重复 ID {state.sales.removed_duplicates} 条
              </p>
              <table>
                <thead>
                  <tr>
                    <th>标准字段</th>
                    <th>实际列名</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(state.sales.mapping).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="muted">读取材料后展示识别结果。</p>
          )}
        </section>
      )}
      {tab === "events" && (
        <section className="card">
          <h2>执行与审核记录</h2>
          {events.map((e) => (
            <details className="event" key={e.seq}>
              <summary>
                <time>{new Date(e.time).toLocaleTimeString()}</time>{" "}
                {NODES[String(e.payload.node ?? "")] ??
                  (
                    {
                      model_started: "模型请求",
                      model_completed: "模型完成",
                      tool_started: "工具调用",
                      tool_failed: "工具失败",
                      human_review: "人工审核",
                      quality: "质检结果",
                      resumed: "恢复任务",
                    } as Record<string, string>
                  )[e.kind] ??
                  e.kind}
              </summary>
              <pre>{JSON.stringify(e.payload, null, 2)}</pre>
            </details>
          ))}
        </section>
      )}
    </section>
  );
}

export function ReviewForm({
  state,
  active,
  onOperation,
}: {
  state: StateSnapshot;
  active: boolean;
  onOperation: Operation;
}) {
  const [decision, setDecision] = useState("revise");
  if (state.status !== "awaiting_human") return null;
  return (
    <section
      id="human-review"
      className="rounded-xl border bg-card shadow-xs"
      aria-label="人工审核表单"
    >
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <UserRoundCheckIcon className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-medium">人工审核 · 版本 {state.version}</h2>
        <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
          等待处理
        </span>
      </div>
      <div className="space-y-4 p-4">
        <p className="text-xs leading-6 text-muted-foreground">
          请核对周报、原文证据和排版。通过后交付；填写意见退回后，将在同一任务中生成下一版。
        </p>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            void onOperation(
              "review",
              JSON.stringify({
                decision,
                reviewer: data.get("reviewer"),
                feedback: data.get("feedback"),
                items:
                  decision === "revise"
                    ? String(data.get("feedback") ?? "")
                        .split(/\n/)
                        .map((text) => text.trim())
                        .filter(Boolean)
                        .map((text) => ({
                          text,
                          category: String(data.get("category") ?? "auto"),
                        }))
                    : [],
                version: state.version,
              }),
              true,
            );
          }}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label>
              审核人
              <input name="reviewer" autoComplete="name" required />
            </label>
            <label>
              审核决定
              <select
                name="decision"
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
              >
                <option value="revise">退回修改</option>
                <option value="approve">通过并交付</option>
              </select>
            </label>
          </div>
          {decision === "revise" && (
            <label>
              修改类型
              <select name="category" defaultValue="auto">
                <option value="auto">按配置识别（可含多类问题）</option>
                <option value="content">文字与内容</option>
                <option value="evidence">原因与证据</option>
                <option value="layout">图表与排版</option>
                <option value="data">材料与统计口径（需补充材料）</option>
              </select>
            </label>
          )}
          <label>
            审核意见
            <textarea
              name="feedback"
              rows={3}
              placeholder="每行填写一条修改意见，将逐项登记、回应并显示修改前后差异"
              required={decision === "revise"}
            />
          </label>
          <div className="flex justify-end">
            <Button disabled={active} type="submit">
              {active ? "正在提交…" : "提交审核决定"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
