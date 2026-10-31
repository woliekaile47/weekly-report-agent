import logoUrl from "@/assets/weekly-report-logo.svg";
import { cn } from "@/lib/utils";

export function ProjectBrand({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2.5", className)}>
      <img
        src={logoUrl}
        alt=""
        width={28}
        height={28}
        className="size-7 shrink-0"
        data-project-logo="weekly-report"
      />
      {!compact && <span className="truncate font-medium">经营周报</span>}
    </span>
  );
}
