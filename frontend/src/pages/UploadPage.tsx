import { useAccess } from "@/lib/access";
// Form uses DeerFlow input-box/InputGroup shell, e0f5483 (MIT), with weekly-report inputs.
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowUpIcon, ChevronDownIcon, LoaderIcon } from "lucide-react";
import { request } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { AttachmentInput } from "@/components/workspace/attachment-input";
import { useSettingsDialog } from "@/components/workspace/settings-context";
import { describeIsoWeek, isoWeekStart, currentIsoWeek } from "@/lib/iso-week";

export function UploadPage() {
  const access = useAccess();
  const [defaultPeriod] = useState(currentIsoWeek);
  const [year, setYear] = useState(String(defaultPeriod.year));
  const [week, setWeek] = useState(String(defaultPeriod.week));
  const [periodEdited, setPeriodEdited] = useState(false);
  useEffect(() => {
    const update = () => {
      if (periodEdited) return;
      const current = currentIsoWeek();
      setYear(String(current.year)); setWeek(String(current.week));
    };
    const timer = window.setInterval(update, 30000);
    window.addEventListener("focus", update);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", update); };
  }, [periodEdited]);
  const validPeriod = isoWeekStart(Number(year), Number(week)) !== null;
  const { openSettings } = useSettingsDialog();
  const client = useQueryClient();
  const { data: config } = useQuery({
    queryKey: ["connection-summary"],
    enabled: access.admin,
    queryFn: () => request<{ connection: { LLM_MODEL: string } }>("/config"),
  });
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
      const input = e.currentTarget.elements.namedItem(k) as HTMLInputElement | null;
      const selected = input?.files?.[0];
      if (selected) data.set(k, selected);
      else data.delete(k);
    }
    try {
      const r = await request<{ id: string }>("/runs", {
        method: "POST",
        body: data,
      });
      void client.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${r.id}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <WorkspaceHeader title="经营周报" />
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center gap-6 px-4 py-10 sm:px-8">
          <div className="text-center">
            <h1 className="text-2xl font-medium">新建经营周报</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              上传销售明细和本周纪要；材料不齐也可发起，任务会暂停并提示补充。
            </p>
          </div>
          <form onSubmit={submit} className="space-y-3">
            <InputGroup className="h-auto rounded-2xl bg-card/80 shadow-xs">
              <InputGroupAddon
                align="block-start"
                className="grid grid-cols-[minmax(0,1fr)_80px_68px] items-start gap-3 px-4 pt-4"
              >
                <label className="min-w-0 text-xs text-muted-foreground">
                  任务名称
                  <Input
                    name="title"
                    defaultValue="门店经营周报"
                    required
                    className="bg-transparent! text-sm!"
                  />
                </label>
                <label className="text-xs text-muted-foreground">
                  年份
                  <Input
                    name="year"
                    type="number"
                    min={2000}
                    max={2100}
                    value={year}
                    onChange={(event) => { setPeriodEdited(true); setYear(event.target.value); }}
                    required
                    className="bg-transparent! px-2! text-sm!"
                  />
                </label>
                <label className="text-xs text-muted-foreground">
                  周次
                  <Input
                    name="week"
                    type="number"
                    min={1}
                    max={53}
                    value={week}
                    onChange={(event) => { setPeriodEdited(true); setWeek(event.target.value); }}
                    required
                    className="bg-transparent! px-2! text-sm!"
                  />
                </label>
              </InputGroupAddon>
              <p role="status" className="px-4 pt-2 text-xs font-medium text-foreground">
                {describeIsoWeek(Number(year), Number(week))}
              </p>
              <InputGroupTextarea
                aria-label="重点关注"
                name="focus"
                rows={3}
                placeholder="这周需要重点关注哪些区域、门店或经营问题？（可选）"
                className="min-h-26 border-0 px-4 py-4 text-sm"
              />
              <InputGroupAddon
                align="block-end"
                className="flex-col items-stretch gap-4 px-4 pb-4"
              >
                <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
                  <AttachmentInput
                    name="sales"
                    label="销售明细"
                    accept=".xlsx,.csv"
                    hint="支持 .xlsx、.csv，单个文件不超过 20MB；上传一份销售文件，文件内须包含所选周及上一周的记录。"
                  />
                  <AttachmentInput
                    name="minutes"
                    label="本周周会纪要"
                    accept=".docx,.txt,.md"
                    hint="支持 .docx、.txt、.md，单个文件不超过 20MB；纪要周期须与所选周一致。"
                  />
                </div>
                <details className="w-full text-xs text-muted-foreground">
                  <summary className="w-fit cursor-pointer">
                    补充基础资料（可选）
                  </summary>
                  <div className="space-y-3 pt-3">
                    <p className="text-xs leading-6">
                      Excel 可在同一工作簿包含销售、门店、商品和目标表；CSV
                      使用已配置的基础资料。需要替换基础表时，可在这里上传单独的 Excel 工作簿。
                    </p>
                    <AttachmentInput
                      name="master"
                      label="基础资料（可选）"
                      accept=".xlsx"
                    />
                  </div>
                </details>
                <div className="flex w-full flex-wrap items-center justify-between gap-3 border-t border-border/50 pt-3">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 max-w-full gap-1 px-1 text-xs text-muted-foreground"
                    onClick={() => openSettings("models")}
                    disabled={!access.admin}
                  >
                    <span className="truncate">
                      {access.admin ? (config?.connection.LLM_MODEL ?? "模型连接") : "模型已由服务器配置"}
                    </span>
                    <ChevronDownIcon className="size-3" />
                  </Button>
                  <Button
                    type="submit"
                    className="h-9 rounded-full px-4"
                    disabled={busy || !validPeriod}
                  >
                    {busy ? (
                      <LoaderIcon className="size-4 animate-spin" />
                    ) : (
                      <ArrowUpIcon className="size-4" />
                    )}
                    <span>{busy ? "正在提交…" : "发起任务"}</span>
                  </Button>
                </div>
              </InputGroupAddon>
            </InputGroup>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <p className="text-center text-[11px] leading-6 text-muted-foreground/70">
              任务保留在当前浏览器中，清除浏览器数据后无法找回。通过程序质检后，由你审核并确认交付。公开体验每个 IP 每天可新建 3 份周报，请勿上传无权分享的材料。
            </p>
          </form>
        </div>
      </div>
    </>
  );
}
