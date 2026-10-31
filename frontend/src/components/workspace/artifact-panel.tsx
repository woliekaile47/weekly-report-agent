// Adapted from DeerFlow artifacts/artifact-file-detail.tsx and ai-elements/artifact.tsx (MIT).
import {
  ArrowLeftIcon,
  DownloadIcon,
  FileTextIcon,
  FilesIcon,
} from "lucide-react";
import { lazy, Suspense } from "react";
import type { StateSnapshot, TaskFile } from "@/api/types";
import {
  Artifact,
  ArtifactHeader,
  ArtifactTitle,
  ArtifactActions,
  ArtifactAction,
  ArtifactClose,
  ArtifactContent,
} from "@/components/ai-elements/artifact";
import { ArtifactFileList } from "./artifact-file-list";
import { Button } from "@/components/ui/button";

const PdfPreview = lazy(() => import("./pdf-preview"));

export function ArtifactPanel({
  files,
  selected,
  state,
  onSelect,
  onClose,
}: {
  files: TaskFile[];
  selected: string | null;
  state: StateSnapshot;
  onSelect: (id: string | null) => void;
  onClose: () => void;
}) {
  const file = files.find((f) => f.id === selected);
  const pdf = files.find((f) => f.id === "pdf");
  const previewPdf =
    file && (file.id === "pdf" || file.id === "docx") ? pdf : null;
  return (
    <Artifact className="h-full min-h-0 rounded-lg shadow-none">
      <ArtifactHeader className="min-h-12 gap-2 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          {file && (
            <ArtifactAction
              icon={ArrowLeftIcon}
              label="返回文件列表"
              tooltip="返回文件列表"
              onClick={() => onSelect(null)}
            />
          )}
          <ArtifactTitle className="min-w-0 truncate">
            {file?.name ?? "任务文件"}
          </ArtifactTitle>
        </div>
        <ArtifactActions>
          {file && (
            <Button variant="ghost" size="icon-sm" asChild>
              <a href={file.url} aria-label="下载当前文件">
                <DownloadIcon className="size-4" />
              </a>
            </Button>
          )}
          <ArtifactClose aria-label="关闭成果面板" onClick={onClose} />
        </ArtifactActions>
      </ArtifactHeader>
      {previewPdf ? (
        <div className="min-h-0 flex-1">
          <Suspense
            fallback={
              <div role="status" className="p-6 text-sm text-muted-foreground">
                正在加载 PDF 预览…
              </div>
            }
          >
            <PdfPreview url={`${previewPdf.url}?v=${state.version ?? 1}`} />
          </Suspense>
        </div>
      ) : (
        <ArtifactContent className="space-y-5 p-4">
          {!file ? (
            <>
              <p className="text-xs leading-6 text-muted-foreground">
                {state.artifact
                  ? `当前版本 ${state.version} · ${state.status === "completed" ? "已交付" : state.status === "paused" ? "暂停中的草稿" : state.status === "awaiting_human" ? "待审核草稿" : "草稿"}`
                  : "上传的材料和后续成果会显示在这里。"}
              </p>
              {files.length ? (
                <ArtifactFileList
                  files={files}
                  onSelect={(f) => onSelect(f.id)}
                />
              ) : (
                <div className="grid min-h-60 place-content-center gap-3 text-center text-muted-foreground">
                  <FilesIcon className="mx-auto size-7 opacity-50" />
                  <p className="text-sm">暂无任务文件</p>
                </div>
              )}
            </>
          ) : file.id === "minutes" ? (
            <>
              <h3 className="text-sm font-medium">纪要原文与来源编号</h3>
              {state.minutes?.sources?.length ? (
                state.minutes.sources.map((source) => (
                  <section
                    key={source.id}
                    className="space-y-1 border-b pb-3 text-sm leading-7"
                  >
                    <span className="font-mono text-xs text-muted-foreground">
                      {source.id}
                    </span>
                    <p className="whitespace-pre-wrap">{source.text}</p>
                  </section>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  完成材料读取后展示原文。可先下载上传文件。
                </p>
              )}
            </>
          ) : file.id === "sales" || file.id === "master" ? (
            <>
              <h3 className="text-sm font-medium">材料识别与口径</h3>
              {state.sales ? (
                <>
                  <p className="text-sm leading-7 text-muted-foreground">
                    工作表 {state.sales.sheet}，原始{" "}
                    {state.sales.raw_rows.toLocaleString()} 行，去重后{" "}
                    {state.sales.rows.toLocaleString()} 行。
                  </p>
                  <div className="table-wrap">
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
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  材料解析后展示识别结果，可先下载原文件。
                </p>
              )}
            </>
          ) : (
            <div className="grid min-h-60 place-content-center gap-3 text-center text-muted-foreground">
              <FileTextIcon className="mx-auto size-8 opacity-50" />
              <p className="text-sm">此文件请下载后查看</p>
              <a className="secondary" href={file.url}>
                下载 {file.name}
              </a>
            </div>
          )}
        </ArtifactContent>
      )}
    </Artifact>
  );
}
