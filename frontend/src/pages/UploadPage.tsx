// Adapted from Invoice Audit Assistant UploadPage.tsx (a0a0fc5, MIT).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../api/client";
import { FileInput } from "../components/ui";

export function UploadPage() {
  const navigate = useNavigate();
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
      navigate(`/runs/${r.id}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h2 className="mb-2 text-xl font-semibold text-slate-900">
          上传业务材料
        </h2>
        <p className="mb-4 text-sm leading-6 text-slate-500">
          上传销售明细与本周周会纪要。系统将计算经营指标、核对原文依据并生成
          Word 周报，完成质检后暂停，等待你审核。
        </p>
        <form
          onSubmit={submit}
          className="flex flex-col gap-4 rounded-lg border border-dashed border-slate-300 bg-white p-6"
        >
          <label>
            任务名称
            <input name="title" defaultValue="门店经营周报" required />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label>
              年份
              <input
                name="year"
                type="number"
                min={2000}
                max={2100}
                defaultValue={2026}
                required
              />
            </label>
            <label>
              ISO 周
              <input
                name="week"
                type="number"
                min={1}
                max={53}
                defaultValue={44}
                required
              />
            </label>
          </div>
          <FileInput
            label="销售明细（Excel / CSV）"
            name="sales"
            accept=".xlsx,.csv"
            required
          />
          <FileInput
            label="本周周会纪要（Word / 文本）"
            name="minutes"
            accept=".docx,.txt,.md"
            required
          />
          <label>
            重点关注（可选）
            <textarea
              name="focus"
              rows={2}
              placeholder="需要重点分析的区域、门店或经营问题"
            />
          </label>
          <details className="text-sm text-slate-600">
            <summary>基础资料与导入说明</summary>
            <p className="my-3 leading-6">
              Excel 可包含销售、门店、商品和目标工作表。CSV
              使用已配置的基础资料，编码须能匹配；也可补充基础资料工作簿。需要环比时，销售文件须包含上一周期数据。
            </p>
            <FileInput label="基础资料（可选）" name="master" accept=".xlsx" />
          </details>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy} className="primary self-start">
            {busy ? "正在上传…" : "上传并执行"}
          </button>
        </form>
      </div>
    </div>
  );
}
