// Adapted from DeerFlow artifacts/artifact-file-list.tsx, e0f5483 (MIT).
import {
  DownloadIcon,
  FileSpreadsheetIcon,
  FileTextIcon,
  FileArchiveIcon,
} from "lucide-react";
import type { TaskFile } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function formatBytes(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
export function FileIcon({
  file,
  className = "size-5",
}: {
  file: TaskFile;
  className?: string;
}) {
  return /\.(xlsx|csv)$/i.test(file.name) ? (
    <FileSpreadsheetIcon className={className} />
  ) : /\.zip$/i.test(file.name) ? (
    <FileArchiveIcon className={className} />
  ) : (
    <FileTextIcon className={className} />
  );
}

export function ArtifactFileList({
  files,
  onSelect,
  compact = false,
}: {
  files: TaskFile[];
  onSelect: (file: TaskFile) => void;
  compact?: boolean;
}) {
  return (
    <ul
      className={`flex w-full ${compact ? "flex-row flex-wrap gap-2" : "flex-col gap-3"}`}
    >
      {files.map((file) => (
        <li key={file.id} className={compact ? "min-w-0 max-w-full" : "w-full"}>
          {compact ? (
            <button
              onClick={() => onSelect(file)}
              className="bg-card hover:bg-accent flex max-w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs"
            >
              <FileIcon
                file={file}
                className="size-4 shrink-0 text-muted-foreground"
              />
              <span className="truncate">{file.name}</span>
              <span className="text-muted-foreground">
                {formatBytes(file.bytes)}
              </span>
            </button>
          ) : (
            <Card className="relative p-3 shadow-none">
              <CardHeader className="grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 pr-2 pl-1">
                <CardTitle className="relative min-w-0 pl-8 text-sm leading-tight [overflow-wrap:anywhere]">
                  <button
                    type="button"
                    className="text-left hover:underline"
                    onClick={() => onSelect(file)}
                  >
                    {file.name}
                  </button>
                  <span className="absolute top-1 -left-0.5">
                    <FileIcon
                      file={file}
                      className="size-6 text-muted-foreground"
                    />
                  </span>
                </CardTitle>
                <CardDescription className="min-w-0 pl-8 text-xs">
                  {file.kind === "input" ? "输入材料" : "任务成果"} ·{" "}
                  {formatBytes(file.bytes)}
                </CardDescription>
                <CardAction className="row-span-1 self-center">
                  <Button variant="ghost" size="icon-sm" asChild>
                    <a href={file.url} aria-label={`下载 ${file.name}`}>
                      <DownloadIcon />
                    </a>
                  </Button>
                </CardAction>
              </CardHeader>
            </Card>
          )}
        </li>
      ))}
    </ul>
  );
}
