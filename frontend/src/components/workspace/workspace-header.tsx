// Adapted from DeerFlow workspace-header.tsx and chat-page.tsx, e0f5483 (MIT).
import type { ReactNode } from "react";
import { WorkspaceSidebarTrigger } from "./workspace-sidebar-trigger";

export function WorkspaceHeader({
  title,
  children,
}: {
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="bg-background/80 z-30 flex h-12 shrink-0 items-center gap-2 border-b border-border/50 px-3 backdrop-blur sm:px-4">
      <WorkspaceSidebarTrigger className="shrink-0" />
      <div className="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium">
        {title}
      </div>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </header>
  );
}
