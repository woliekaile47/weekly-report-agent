// Adapted from DeerFlow chats/chat-box.tsx, e0f5483 (MIT).
import { useEffect, useRef, type ReactNode } from "react";
import { usePanelRef } from "react-resizable-panels";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";

export function WorkspaceSplit({
  id,
  open,
  onOpenChange,
  children,
  panel,
}: {
  id: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
  panel: ReactNode;
}) {
  const compact = useIsMobile(1100);
  const sidePanelRef = usePanelRef();
  const lastSize = useRef("46%");
  useEffect(() => {
    // Resizing must not open a blocking drawer unexpectedly.
    if (compact) onOpenChange(false);
  }, [compact, onOpenChange]);
  useEffect(() => {
    if (compact) return;
    if (open) sidePanelRef.current?.resize(lastSize.current);
    else sidePanelRef.current?.collapse();
  }, [open, compact, sidePanelRef]);
  if (compact)
    return (
      <>
        <div className="relative flex size-full min-h-0 min-w-0 flex-col">
          {children}
        </div>
        <Sheet open={open} onOpenChange={onOpenChange}>
          <SheetContent
            className="w-[calc(100vw-0.5rem)] max-w-none gap-0 p-0 sm:max-w-2xl [&>button]:hidden"
            side="right"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>任务成果预览</SheetTitle>
              <SheetDescription>
                查看当前任务的文件、报告和质检结果。
              </SheetDescription>
            </SheetHeader>
            <div className="flex h-full min-h-0 flex-col p-2">{panel}</div>
          </SheetContent>
        </Sheet>
      </>
    );
  return (
    <ResizablePanelGroup
      id={`${id}-group`}
      orientation="horizontal"
      className="size-full min-h-0"
    >
      <ResizablePanel
        id={`${id}-task`}
        minSize="32%"
        className="relative min-h-0 min-w-0"
      >
        <div className="flex size-full min-h-0 min-w-0 flex-col">
          {children}
        </div>
      </ResizablePanel>
      <ResizableHandle
        id={`${id}-separator`}
        aria-label="调整成果面板宽度"
        withHandle
        disabled={!open}
        className={
          open
            ? "opacity-40 hover:opacity-100"
            : "pointer-events-none opacity-0"
        }
      />
      <ResizablePanel
        id={`${id}-artifacts`}
        panelRef={sidePanelRef}
        defaultSize={open ? lastSize.current : "0%"}
        minSize="28%"
        collapsible
        collapsedSize="0%"
        onResize={(size) => {
          if (size.asPercentage > 10)
            lastSize.current = `${size.asPercentage}%`;
        }}
        className="min-h-0 min-w-0"
      >
        <aside
          aria-label="任务成果面板"
          aria-hidden={!open}
          inert={!open}
          className={`size-full min-h-0 min-w-0 overflow-hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        >
          <div className="h-full p-3">{panel}</div>
        </aside>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
