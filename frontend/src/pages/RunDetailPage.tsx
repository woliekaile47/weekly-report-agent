// Layout adapted from Invoice Audit Assistant RunDetailPage.tsx (a0a0fc5, MIT).
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fileUrl, request } from "../api/client";
import { normalizeSnapshot } from "../api/snapshot";
import type { StateSnapshot } from "../api/types";
import { GraphView } from "../components/GraphView";
import { NodePanel } from "../components/NodePanel";
import {
  FileInput,
  MetricsTable,
  NODES,
  StatusBadge,
  pct,
  sub,
} from "../components/ui";
import { useRunStream } from "../hooks/useRunStream";

export function RunDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [generation, setGeneration] = useState(0);
  const stream = useRunStream(id, generation);
  const [state, setState] = useState<StateSnapshot>({});
  const [tab, setTab] = useState("report");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [events, setEvents] = useState<
    {
      seq: number;
      time: string;
      kind: string;
      payload: Record<string, unknown>;
    }[]
  >([]);
  const refresh = () =>
    request<StateSnapshot>(`/runs/${id}`)
      .then((value) => {
        setState(normalizeSnapshot(value));
        setLoadError("");
      })
      .catch((e) => setLoadError(String(e)));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [id, generation]);
  useEffect(() => {
    if (stream.snapshot.task_id) setState(normalizeSnapshot(stream.snapshot));
  }, [stream.snapshot]);
  useEffect(() => {
    if (tab === "events")
      request<{ events: typeof events }>(`/runs/${id}/events`)
        .then((r) => setEvents(r.events))
        .catch((e) => setError(String(e)));
  }, [tab, state.status]);
  async function operation(path: string, data: BodyInit, json = false) {
    setBusy(true);
    setError("");
    try {
      await request(`/runs/${id}/${path}`, {
        method: "POST",
        body: data,
        headers: json ? { "Content-Type": "application/json" } : undefined,
      });
      setGeneration((g) => g + 1);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const metrics = state.metrics;
  const draft = state.draft;
  const tokens = metrics?.tokens ?? {};
  const active = state.worker_active || busy;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <Link to="/history" className="text-sm text-brand-600 hover:underline">
          ← 返回任务历史
        </Link>
        <h2 className="mt-1 text-xl font-semibold text-slate-900">
          {state.spec?.title ?? "正在读取任务…"}
        </h2>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
          任务状态：
          {state.status ? <StatusBadge status={state.status} /> : "读取中"}
          <span>
            ·{" "}
            {metrics?.period ??
              `${state.spec?.year ?? ""} 年第 ${state.spec?.week ?? ""} 周`}
          </span>
          <span>· 版本 {state.version ?? 1}</span>
          {active && <span className="text-brand-600">实时更新中</span>}
        </p>
        <p className="mt-2 break-all font-mono text-xs text-slate-400">
          任务 {id} · 配置 {state.config_version ?? "读取中"}
        </p>
      </div>
      {(error || loadError) && (
        <div role="alert" className="error">
          {error || loadError}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <GraphView
          currentNode={
            state.status === "paused"
              ? (state.resume_node ?? null)
              : stream.currentNode
          }
          completedNodes={stream.completedNodes}
        />
        <NodePanel snapshot={state} trace={stream.trace} />
      </div>
      <div className="space-y-6" id="task-actions">
        <section className="results">
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
                  operation("resume", data);
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
                    onClick={() => operation("recheck", new FormData())}
                  >
                    复检现有草稿（不调用模型）
                  </button>
                )}
              </form>
            </div>
          )}
          {state.status === "running" && !active && (
            <div className="notice">
              <strong>执行已中断，进度已保存</strong>
              <p>可从最近检查点继续，已完成的工具结果按缓存复用。</p>
              <button
                className="primary"
                onClick={() => operation("resume", new FormData())}
              >
                从检查点继续
              </button>
            </div>
          )}
          {active && (
            <div className="running-strip">
              <span className="loading-dot" />
              员工正在{NODES[state.current_node ?? ""] ?? "处理任务"}
              ，执行记录实时保存。
            </div>
          )}
          <div className="tabs" role="tablist">
            {[
              ["report", "周报与审核"],
              ["quality", "质检记录"],
              ["materials", "材料识别"],
              ["events", "执行记录"],
            ].map(([k, label]) => (
              <button
                role="tab"
                aria-selected={tab === k}
                key={k}
                className={tab === k ? "selected" : ""}
                onClick={() => setTab(k)}
              >
                {label}
              </button>
            ))}
          </div>
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
                      {state.status === "completed"
                        ? "已交付版本"
                        : "待审核草稿"}
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
                          ...metrics.groups.filter(
                            (g) => g.dimension === "region",
                          ),
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
                              <span className="tag">
                                {pct(m?.change ?? null)}
                              </span>
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
                <p className="muted">
                  生成 Word 后执行检查；当前没有质检记录。
                </p>
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
        {state.status === "awaiting_human" && (
          <form
            className="review rounded-xl border border-amber-300 bg-amber-50 p-5"
            onSubmit={(e) => {
              e.preventDefault();
              const d = new FormData(e.currentTarget);
              operation(
                "review",
                JSON.stringify({
                  decision: d.get("decision"),
                  reviewer: d.get("reviewer"),
                  feedback: d.get("feedback"),
                  version: state.version,
                }),
                true,
              );
            }}
          >
            <h2 className="text-amber-800">人工审核 · 版本 {state.version}</h2>
            <p className="muted">
              请核对指标、原因、证据与 Word
              排版。通过后生成正式交付包；退回意见进入同一任务下一版。
            </p>
            <div className="uploads">
              <label>
                审核人
                <input name="reviewer" required />
              </label>
              <label>
                审核决定
                <select name="decision">
                  <option value="revise">退回修改</option>
                  <option value="approve">通过并交付</option>
                </select>
              </label>
            </div>
            <label>
              审核意见
              <textarea
                name="feedback"
                placeholder="退回时必填，请指出需要修改的内容"
                rows={3}
              />
            </label>
            <button className="primary" disabled={active}>
              提交审核决定
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
