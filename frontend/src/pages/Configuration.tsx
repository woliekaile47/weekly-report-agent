import { useEffect, useState } from "react";
import { request } from "../api/client";

interface Config {
  files: Record<string, string>;
  version: string;
  employee: {
    limits: Record<string, number>;
  };
  connection: Record<string, string>;
  key_configured: boolean;
}

export function Configuration({
  page,
}: {
  page: "employee" | "limits" | "settings";
}) {
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
  async function saveLimits(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setMessage("");
    const values = new FormData(e.currentTarget);
    try {
      const result = await request<{ version: string; limits: Record<string, number> }>(
        "/limits",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            version: config!.version,
            model_calls: Number(values.get("model_calls")),
            model_timeout_seconds: Number(values.get("model_timeout_seconds")),
            active_seconds: Number(values.get("active_seconds")),
          }),
        },
      );
      setConfig({
        ...config!,
        version: result.version,
        employee: { ...config!.employee, limits: result.limits },
      });
      setMessage("已保存。新任务使用新上限；已有任务保留创建时的配置。");
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="config-page">
      <h2 className="mb-4 text-xl font-semibold text-slate-900">
        {page === "employee"
          ? "员工配置"
          : page === "limits"
            ? "执行限制与人工处理"
            : "模型设置与调试"}
      </h2>
      {message && <p className="success">{message}</p>}
      {error && <p className="error">{error}</p>}
      {page === "employee" && (
        <form onSubmit={saveFiles}>
          <p className="muted">
            直接编辑岗位职责、步骤和规则，业务人员无需修改程序。配置随任务保存快照。
          </p>
          {Object.entries(files)
            .sort(([a], [b]) => {
              const priority = (key: string) =>
                key.includes("SKILL") ? 0 : key.includes("employee") ? 1 : 2;
              return priority(a) - priority(b);
            })
            .map(([k, v]) => (
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
                  aria-label={k}
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
        <form className="card" onSubmit={saveLimits}>
          <p>
            实际模型请求（包含失败）计入调用次数。活动执行时间不包含等待人工处理的时间。达到上限后停止执行、保存进度，填写处理人和意见后才能恢复。
          </p>
          {([
            ["model_calls", "模型调用上限", "次"],
            ["model_timeout_seconds", "单次模型时长", "秒"],
            ["active_seconds", "活动执行时长", "秒"],
          ] as const).map(([key, label, unit]) => (
            <label key={key}>
              {label}（{unit}）
              <input
                name={key}
                type="number"
                min={1}
                step={1}
                required
                defaultValue={config.employee.limits[key]}
              />
            </label>
          ))}
          <button className="primary" type="submit">保存执行上限</button>
          <p className="muted">
            上限写入员工配置文件。新任务使用新值；已有任务沿用创建时的配置快照。
          </p>
        </form>
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
            接口地址（Base URL）
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
