import { useState, type ReactNode } from "react";
import type { StateSnapshot, TaskEvent } from "@/api/types";
import { fileUrl } from "@/api/client";
import { FileInput, MetricsTable, NODES, pct, sub } from "@/components/ui";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { UserRoundCheckIcon } from "lucide-react";

type Operation = (
  path: string,
  data: BodyInit,
  json?: boolean,
) => Promise<void>;

export function PauseForm({
  state,
  active,
  onOperation,
}: {
  state: StateSnapshot;
  active: boolean;
  onOperation: Operation;
}) {
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
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              data.set(
                "spec",
                JSON.stringify({
                  ...state.spec,
                  year: Number(data.get("year")),
                  week: Number(data.get("week")),
                }),
              );
              const mapping = {
                sheet: String(data.get("sheet") ?? ""),
                fields: Object.fromEntries(
                  ["amount", "date", "cost"]
                    .map((k) => [k, String(data.get(k) ?? "")])
                    .filter(([, v]) => v),
                ),
              };
              data.set("import_options", JSON.stringify(mapping));
              for (const k of ["sales", "minutes", "master"]) {
                const f = data.get(k);
                if (f instanceof File && !f.size) data.delete(k);
              }
              onOperation("resume", data);
            }}
          >
            <details>
              <summary>补充材料、调整周期或列映射</summary>
              <div className="uploads">
                <FileInput
                  label="替换销售文件"
                  name="sales"
                  accept=".xlsx,.csv"
                />
                <FileInput
                  label="补充纪要"
                  name="minutes"
                  accept=".docx,.txt,.md"
                />
              </div>
              <FileInput
                label="基础资料（可选）"
                name="master"
                accept=".xlsx"
              />
              <div className="form-grid">
                <label>
                  年份
                  <input
                    name="year"
                    type="number"
                    defaultValue={state.spec?.year}
                  />
                </label>
                <label>
                  ISO 周
                  <input
                    name="week"
                    type="number"
                    defaultValue={state.spec?.week}
                  />
                </label>
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
            <button className="primary" disabled={active}>
              恢复执行
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
                  {state.status === "completed" ? "已交付版本" : "待审核草稿"}
                </span>
              </div>
              <p>{sub(draft.summary, tokens)}</p>
              {draft.conflicts?.map((c, i) => (
                <p className="conflict" key={i}>
                  {sub(c, tokens)}
                </p>
              ))}
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
                  {draft.anomalies.map((a) => {
                    const m = metrics.anomalies.find(
                      (x) => x.id === a.metric_id,
                    );
                    return (
                      <article className="finding" key={a.metric_id}>
                        <h3>
                          {m?.label ?? a.metric_id}
                          <span className="tag">{pct(m?.change ?? null)}</span>
                        </h3>
                        <p>
                          {a.uncertain && (
                            <span className="muted">原因待核实：</span>
                          )}
                          {sub(a.reason, tokens)}
                        </p>
                        {a.evidence.map((ev, i) => (
                          <blockquote key={i}>
                            [{ev.source_id}] {ev.quote}
                          </blockquote>
                        ))}
                      </article>
                    );
                  })}
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
                {draft.actions.map((a, i) => (
                  <li key={i}>{sub(a, tokens)}</li>
                ))}
              </ul>
              {draft.data_notes?.length > 0 && (
                <>
                  <h2>数据质量说明</h2>
                  {draft.data_notes.map((n, i) => (
                    <p key={i}>{sub(n, tokens)}</p>
                  ))}
                </>
              )}
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
      {tab === "materials" && (
        <section className="card">
          <h2>材料识别与口径</h2>
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
          <label>
            审核意见
            <textarea
              name="feedback"
              rows={3}
              placeholder="退回时请说明需要修改的内容"
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
