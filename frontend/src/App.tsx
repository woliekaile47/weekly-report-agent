import { useEffect, useState } from "react";
import { fileUrl, request } from "./api/client";
import type { Metric, RunSummary, StateSnapshot } from "./api/types";
import { GraphView } from "./components/GraphView";
import { useRunStream } from "./hooks/useRunStream";

const STATUS: Record<string, string> = {
  pending: "待执行",
  running: "正在执行",
  paused: "已暂停",
  awaiting_human: "等待审核",
  approved: "正在交付",
  completed: "已交付",
};
const NODES: Record<string, string> = {
  ingest: "识别材料",
  calculate: "计算指标",
  evidence: "核对纪要",
  analyze: "分析经营",
  render: "生成周报",
  quality: "自动质检",
  human_review: "人工审核",
  finalize: "交付成果",
};
const money = (v: number) =>
  new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(v / 100);
const pct = (v: number | null) =>
  v === null ? "不适用" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const sub = (text: string, tokens: Record<string, string>) =>
  text.replace(/\{\{([^{}]+)\}\}/g, (_, k: string) => tokens[k] ?? `{{${k}}}`);
type Page = "tasks" | "employee" | "limits" | "settings";
interface Config {
  files: Record<string, string>;
  version: string;
  employee: {
    limits: Record<string, number>;
    limit_reasons: Record<string, string>;
  };
  connection: Record<string, string>;
  key_configured: boolean;
}

export default function App() {
  const [page, setPage] = useState<Page>("tasks");
  const [id, setId] = useState<string | null>(
    localStorage.getItem("weekly-task"),
  );
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [sidebar, setSidebar] = useState(window.innerWidth > 900);
  const [query, setQuery] = useState("");
  const [about, setAbout] = useState(false);
  const refresh = () =>
    request<{ runs: RunSummary[] }>("/runs")
      .then((r) => setRuns(r.runs))
      .catch(() => {});
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);
  const choose = (task: string | null) => {
    setId(task);
    setPage("tasks");
    if (task) localStorage.setItem("weekly-task", task);
    else localStorage.removeItem("weekly-task");
    if (window.innerWidth < 900) setSidebar(false);
    refresh();
  };
  return (
    <div className={`workspace ${sidebar ? "sidebar-open" : ""}`}>
      <nav className="rail" aria-label="工作区导航">
        <button
          aria-label="展开或收起侧栏"
          data-tip="侧栏"
          onClick={() => setSidebar(!sidebar)}
        >
          ☰
        </button>
        <button
          className={page === "tasks" ? "active" : ""}
          aria-label="任务工作台"
          data-tip="任务工作台"
          onClick={() => setPage("tasks")}
        >
          ◫
        </button>
        <button
          className={page === "employee" ? "active" : ""}
          aria-label="员工配置"
          data-tip="员工配置"
          onClick={() => setPage("employee")}
        >
          ▤
        </button>
        <button
          className={page === "limits" ? "active" : ""}
          aria-label="执行限制"
          data-tip="执行限制"
          onClick={() => setPage("limits")}
        >
          ◇
        </button>
        <button
          className={page === "settings" ? "active" : ""}
          aria-label="设置与调试"
          data-tip="设置与调试"
          onClick={() => setPage("settings")}
        >
          ⚙
        </button>
        <button
          className="rail-bottom"
          aria-label="关于工作空间"
          data-tip="关于工作空间"
          onClick={() => setAbout(true)}
        >
          ⓘ
        </button>
      </nav>
      {sidebar && (
        <>
          <div className="mobile-scrim" onClick={() => setSidebar(false)} />
          <aside className="sidebar">
            <div className="brand">
              <span className="brand-mark">◈</span>
              <strong>经营周报</strong>
              <small>工作空间</small>
            </div>
            <button className="new-task" onClick={() => choose(null)}>
              ＋ 新建任务
            </button>
            <input
              aria-label="搜索最近任务"
              placeholder="搜索任务"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <p className="side-label">最近</p>
            <div className="recent">
              {runs
                .filter((r) => r.title.includes(query))
                .map((r) => (
                  <button
                    key={r.id}
                    className={r.id === id ? "selected" : ""}
                    onClick={() => choose(r.id)}
                  >
                    <span>{r.title}</span>
                    <small>
                      第 {r.week} 周 · {STATUS[r.status] ?? r.status}
                    </small>
                  </button>
                ))}
              {!runs.length && (
                <p className="muted">还没有任务。上传材料开始。</p>
              )}
            </div>
            <div className="sidebar-foot">
              <span className="avatar">运</span>
              <div>
                运营工作空间<small>本地文件 · 审核后交付</small>
              </div>
            </div>
          </aside>
        </>
      )}
      <main>
        <header className="topbar">
          <span>
            工作空间 /{" "}
            {
              {
                tasks: "经营周报",
                employee: "员工配置",
                limits: "执行限制",
                settings: "设置与调试",
              }[page]
            }
          </span>
          <span className="online">● 本地服务</span>
        </header>
        {page === "tasks" ? (
          id ? (
            <TaskDetail key={id} id={id} onChange={refresh} />
          ) : (
            <NewTask onCreate={choose} />
          )
        ) : (
          <Configuration key={page} page={page} />
        )}
      </main>
      {about && (
        <div className="modal-backdrop" onClick={() => setAbout(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="close" onClick={() => setAbout(false)}>
              ×
            </button>
            <h2>关于工作空间</h2>
            <p>
              经营周报员工以 LangGraph 编排、MCP 官方 SDK
              调用工具，模型分析之后由程序质检并等待人工审核。
            </p>
            <p>
              复用来源：Invoice Audit
              Assistant、GenSlide；具体版本、许可及改动见项目
              THIRD_PARTY_NOTICES.md。
            </p>
            <p className="muted">
              当前为本地单用户工作空间。岗位和规则在配置文件中维护。
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function FileInput({
  label,
  name,
  accept,
}: {
  label: string;
  name: string;
  accept: string;
}) {
  return (
    <label className="upload">
      <span>{label}</span>
      <input type="file" name={name} accept={accept} />
      <small>文件保存在本地，最多 20 MB</small>
    </label>
  );
}

function NewTask({ onCreate }: { onCreate: (id: string) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    data.set(
      "spec",
      JSON.stringify({
        title: data.get("title"),
        year: Number(data.get("year")),
        week: Number(data.get("week")),
        focus: data.get("focus"),
      }),
    );
    for (const k of ["sales", "minutes", "master"]) {
      const f = data.get(k);
      if (f instanceof File && !f.size) data.delete(k);
    }
    try {
      const r = await request<{ id: string }>("/runs", {
        method: "POST",
        body: data,
      });
      onCreate(r.id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="new-workspace">
      <div className="welcome">
        <div className="spark">✧</div>
        <p className="eyebrow">经营分析 · 周度交付</p>
        <h1>
          让每一份周报，
          <br />
          都有数据和依据。
        </h1>
        <p>上传销售明细与周会纪要，核对指标、分析异常，审核后交付。</p>
      </div>
      <form className="card task-form" onSubmit={submit}>
        <label>
          重点关注
          <textarea
            name="focus"
            placeholder="希望重点了解哪些区域、门店或经营问题？"
            rows={3}
          />
        </label>
        <div className="form-grid">
          <label>
            任务名称
            <input name="title" defaultValue="门店经营周报" required />
          </label>
          <label>
            年份
            <input
              type="number"
              name="year"
              defaultValue={2026}
              min={2000}
              max={2100}
              required
            />
          </label>
          <label>
            ISO 周
            <input
              type="number"
              name="week"
              defaultValue={44}
              min={1}
              max={53}
              required
            />
          </label>
        </div>
        <div className="uploads">
          <FileInput label="销售明细" name="sales" accept=".xlsx,.csv" />
          <FileInput
            label="本周周会纪要"
            name="minutes"
            accept=".docx,.txt,.md"
          />
        </div>
        <details>
          <summary>基础资料与导入说明</summary>
          <p>
            Excel 应包含销售、门店、商品及目标工作表。CSV
            使用已配置的基础资料，编码必须能够匹配；也可补充基础资料工作簿。
          </p>
          <FileInput label="基础资料（可选）" name="master" accept=".xlsx" />
        </details>
        {error && <p className="error">{error}</p>}
        <div className="form-bottom">
          <span className="muted">程序计算指标 · 人工审核交付</span>
          <button className="primary" disabled={busy}>
            {busy ? "正在创建…" : "创建并执行 →"}
          </button>
        </div>
      </form>
      <div className="welcome-hints">
        <span>◈ 按记录 ID 去重</span>
        <span>◈ 两张图表 · 三页以内</span>
        <span>◈ 可退回修改</span>
      </div>
    </div>
  );
}

function MetricsTable({ rows }: { rows: Metric[] }) {
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
                className={r.change !== null && r.change < 0 ? "negative" : ""}
              >
                {pct(r.change)}
              </td>
              <td>
                {r.margin === null ? "不适用" : r.margin.toFixed(1) + "%"}
              </td>
              <td>
                {r.target_rate === null ? "—" : r.target_rate.toFixed(1) + "%"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TaskDetail({ id, onChange }: { id: string; onChange: () => void }) {
  const [generation, setGeneration] = useState(0);
  const stream = useRunStream(id, generation);
  const [state, setState] = useState<StateSnapshot>({});
  const [tab, setTab] = useState("report");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [graph, setGraph] = useState(window.innerWidth > 1100);
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
      .then(setState)
      .catch((e) => setError(String(e)));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [id, generation]);
  useEffect(() => {
    if (stream.snapshot.task_id) setState(stream.snapshot);
  }, [stream.snapshot]);
  useEffect(() => {
    if (tab === "events")
      request<{ events: typeof events }>(`/runs/${id}/events`).then((r) =>
        setEvents(r.events),
      );
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
      onChange();
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
    <div className="task-workspace">
      <div className="task-header">
        <div>
          <p className="eyebrow">
            任务 {id.slice(0, 8)} · 版本 {state.version ?? 1}
          </p>
          <h1>{state.spec?.title ?? "正在读取任务…"}</h1>
          <p className="muted">
            {metrics?.period ??
              `${state.spec?.year ?? ""} 年第 ${state.spec?.week ?? ""} 周`}{" "}
            · 配置 {state.config_version}
          </p>
        </div>
        <button className="secondary" onClick={() => setGraph(!graph)}>
          {graph ? "收起" : "显示"}运行图谱
        </button>
      </div>
      <div className="metric-cards">
        <div>
          <small>任务状态</small>
          <strong>{STATUS[state.status ?? ""] ?? "读取中"}</strong>
        </div>
        <div>
          <small>模型</small>
          <strong className="model-name">{state.model ?? "—"}</strong>
        </div>
        <div>
          <small>本轮模型调用 / 上限</small>
          <strong>
            {state.model_calls ?? 0} <em>/ {state.limits?.model_calls ?? 8}</em>
          </strong>
        </div>
        <div>
          <small>活动耗时 / 上限</small>
          <strong>
            {(state.active_seconds ?? 0).toFixed(0)}{" "}
            <em>/ {state.limits?.active_seconds ?? 600} 秒</em>
          </strong>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className={`work-columns ${graph ? "with-graph" : ""}`}>
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
                  <span>▤</span>
                  <h3>等待周报成果</h3>
                  <p>
                    完成材料识别、指标计算和模型分析后显示。生成的草稿会先通过程序质检，再交给你审核。
                  </p>
                </div>
              ) : (
                <div className="report-content">
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
              {state.status === "awaiting_human" && (
                <form
                  className="review card"
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
                  <h2>人工审核 · 版本 {state.version}</h2>
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
        {graph && (
          <aside className="graph-panel">
            <div className="section-heading">
              <h2>运行图谱</h2>
              <span className="tag">真实执行</span>
            </div>
            <p className="muted">
              {STATUS[state.status ?? ""]} · 检查点与工具事件
            </p>
            <GraphView
              currentNode={
                state.status === "paused"
                  ? (state.resume_node ?? null)
                  : stream.currentNode
              }
              completedNodes={stream.completedNodes}
            />
            <p className="muted">
              点击“执行记录”查看工具、模型、质检与审核留痕。事件重连不会重复提交任务。
            </p>
          </aside>
        )}
      </div>
    </div>
  );
}

function Configuration({ page }: { page: Exclude<Page, "tasks"> }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [files, setFiles] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    request<Config>("/config")
      .then((c) => {
        setConfig(c);
        setFiles(c.files);
      })
      .catch((e) => setError(String(e)));
  }, []);
  if (!config)
    return <div className="config-page">{error || "正在读取配置…"}</div>;
  async function saveFiles(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const r = await request<{ version: string }>("/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: config!.version, files }),
      });
      setConfig({ ...config!, version: r.version });
      setMessage("已保存，新任务使用新配置；已有任务保留快照。");
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="config-page">
      <p className="eyebrow">工作空间设置</p>
      <h1>
        {page === "employee"
          ? "员工配置"
          : page === "limits"
            ? "执行限制与人工处理"
            : "模型设置与调试"}
      </h1>
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}
      {page === "employee" && (
        <form onSubmit={saveFiles}>
          <p className="muted">
            直接编辑岗位职责、步骤和规则，业务人员无需修改程序。配置随任务保存快照。
          </p>
          {Object.entries(files).map(([k, v]) => (
            <section className="card" key={k}>
              <h2>
                {k.includes("SKILL")
                  ? "岗位职责、工作步骤和注意事项"
                  : k.includes("columns")
                    ? "字段与基础表映射"
                    : "调用限制、业务阈值与质检规则"}
              </h2>
              <small>{k}</small>
              <textarea
                className="code-editor"
                value={v}
                onChange={(e) => setFiles({ ...files, [k]: e.target.value })}
                rows={k.includes("SKILL") ? 20 : 14}
              />
            </section>
          ))}
          <button className="primary">保存配置</button>
        </form>
      )}
      {page === "limits" && (
        <section className="card">
          <p>
            实际模型请求（包含失败）计入调用次数。活动执行时间不包含等待人工处理的时间。达到上限后停止执行、保存进度，填写处理人和意见后才能恢复。
          </p>
          <table>
            <thead>
              <tr>
                <th>限制</th>
                <th>取值</th>
                <th>理由</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(config.employee.limit_reasons).map(([k, v]) => (
                <tr key={k}>
                  <td>
                    {(
                      {
                        model_calls: "每轮模型调用",
                        model_timeout_seconds: "单次模型时长",
                        active_seconds: "活动执行时长",
                      } as Record<string, string>
                    )[k] ?? k}
                  </td>
                  <td>{config.employee.limits[k]}</td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            在员工配置中修改数值及取值理由；交付包保存本任务的实际配置说明。
          </p>
        </section>
      )}
      {page === "settings" && (
        <form
          className="card"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            setError("");
            try {
              await request("/connection", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  base_url: d.get("base_url"),
                  model: d.get("model"),
                  api_key: d.get("api_key"),
                  max_tokens: Number(d.get("max_tokens")),
                  reasoning_effort: String(d.get("reasoning_effort") ?? ""),
                }),
              });
              setMessage("连接已保存至后端 .env，后续请求生效。");
              (e.target as HTMLFormElement).reset();
            } catch (err) {
              setError(String(err));
            }
          }}
        >
          <label>
            API Base URL
            <input
              name="base_url"
              defaultValue={config.connection.LLM_BASE_URL}
              required
            />
          </label>
          <label>
            模型名称
            <input
              name="model"
              defaultValue={config.connection.LLM_MODEL}
              required
            />
          </label>
          <label>
            API 密钥
            <input
              name="api_key"
              type="password"
              autoComplete="new-password"
              placeholder={
                config.key_configured ? "已配置；留空保留原密钥" : "请填写密钥"
              }
            />
          </label>
          <label>
            最大输出长度
            <input
              name="max_tokens"
              type="number"
              defaultValue={Number(config.connection.LLM_MAX_TOKENS)}
              min={128}
              max={32000}
            />
          </label>
          <label>
            推理强度（模型支持时）
            <select
              name="reasoning_effort"
              defaultValue={config.connection.LLM_REASONING_EFFORT ?? ""}
            >
              <option value="">默认，不额外指定</option>
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
            </select>
          </label>
          <div className="download-row">
            <button className="primary">保存连接</button>
            <button
              type="button"
              className="secondary"
              onClick={async () => {
                try {
                  const r = await request<{
                    message: string;
                    status_code?: number;
                  }>("/connection/test", { method: "POST" });
                  setMessage(
                    `${r.message}${r.status_code ? `（HTTP ${r.status_code}）` : ""}`,
                  );
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              测试已保存连接
            </button>
          </div>
          <p className="muted">
            密钥只保存在后端 .env，不回传浏览器。测试使用一次真实请求。
          </p>
        </form>
      )}
    </div>
  );
}
