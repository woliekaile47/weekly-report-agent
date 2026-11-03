import { useId, useRef, useState } from "react";
import { FileTextIcon, PaperclipIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "./artifact-file-list";

export function AttachmentInput({
  name,
  label,
  accept,
  required = false,
  hint,
}: {
  name: string;
  label: string;
  accept: string;
  required?: boolean;
  hint?: string;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  return (
    <div className="min-w-0 space-y-2">
      <span className="text-xs text-muted-foreground">
        {label}
        {required && " *"}
      </span>
      <input
        ref={input}
        id={id}
        className="sr-only"
        type="file"
        name={name}
        accept={accept}
        required={required}
        aria-label={label}
        onChange={(e) => {
          const next = e.target.files?.[0] ?? null;
          const formats = accept.split(",").map((format) => format.trim().toLowerCase());
          const issue = next && (
            !formats.some((format) => next.name.toLowerCase().endsWith(format))
              ? `仅支持 ${formats.join("、")} 格式。`
              : next.size === 0
                ? `${next.name} 为空，请选择非空文件。`
                : next.size > 20 * 1024 * 1024
                  ? `${next.name} 超过 20MB，请选择更小的文件。`
                  : ""
          );
          if (issue) {
            setError(issue);
            e.target.value = "";
            setFile(null);
            return;
          }
          setFile(next);
          setError("");
        }}
      />
      {file ? (
        <div className="bg-background flex min-w-0 items-center gap-2 rounded-xl border px-3 py-2">
          <FileTextIcon className="size-4 shrink-0 text-muted-foreground" />
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="min-w-0 flex-1 truncate text-left text-xs"
            title={file.name}
          >
            {file.name}
            <span className="ml-2 text-muted-foreground">
              {formatBytes(file.size)}
            </span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="size-6"
            aria-label={`移除${label}`}
            onClick={() => {
              if (input.current) input.current.value = "";
              setFile(null);
            }}
          >
            <XIcon className="size-3" />
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          className="w-full justify-start gap-2 bg-background/50 text-muted-foreground shadow-none"
          onClick={() => input.current?.click()}
        >
          <PaperclipIcon className="size-4" />
          <span className="text-xs">选择{label}</span>
        </Button>
      )}
      {hint && <p className="text-xs leading-5 text-muted-foreground">{hint}</p>}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
