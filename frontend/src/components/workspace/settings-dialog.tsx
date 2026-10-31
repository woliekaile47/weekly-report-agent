// Adapted from DeerFlow settings/settings-dialog.tsx, e0f5483 (MIT).
import {
  BotIcon,
  InfoIcon,
  ShieldCheckIcon,
  UserRoundCogIcon,
} from "lucide-react";
import { useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Configuration } from "@/pages/Configuration";
import { cn } from "@/lib/utils";
import type { SettingsSection } from "./settings-context";
import { ProjectBrand } from "./project-brand";

const sections = [
  { id: "models", label: "模型连接", icon: BotIcon },
  { id: "employee", label: "员工配置", icon: UserRoundCogIcon },
  { id: "limits", label: "执行限制", icon: ShieldCheckIcon },
  { id: "about", label: "关于工作空间", icon: InfoIcon },
] as const;

export function SettingsDialog({
  open,
  section,
  onOpenChange,
  onSectionChange,
}: {
  open: boolean;
  section: SettingsSection;
  onOpenChange: (open: boolean) => void;
  onSectionChange: (section: SettingsSection) => void;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        ref={contentRef}
        onOpenAutoFocus={(event) => {
          const selected = contentRef.current?.querySelector<HTMLButtonElement>(
            'button[aria-current="page"]',
          );
          if (selected) {
            event.preventDefault();
            selected.focus();
          }
        }}
        className="flex h-[80vh] max-h-[calc(100dvh-2rem)] flex-col sm:max-w-5xl md:max-w-6xl"
        aria-describedby={undefined}
      >
        <DialogHeader className="gap-1">
          <DialogTitle>设置</DialogTitle>
          <p className="text-muted-foreground text-sm">
            配置模型连接、员工技能和执行限制。
          </p>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-4 md:grid-cols-[220px_minmax(0,1fr)] md:grid-rows-1">
          <nav
            aria-label="设置分类"
            className="bg-sidebar min-h-0 overflow-auto rounded-lg border p-2"
          >
            <ul className="flex gap-1 md:block md:space-y-1 md:pr-1">
              {sections.map(({ id, label, icon: Icon }) => (
                <li key={id} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => onSectionChange(id)}
                    aria-current={section === id ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      section === id
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    <span>{label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <ScrollArea className="h-full min-h-0 min-w-0 rounded-lg border">
            <div className="space-y-8 p-4 md:p-6">
              {section !== "about" ? (
                <Configuration
                  key={section}
                  page={section === "models" ? "settings" : section}
                />
              ) : (
                <div className="space-y-5 text-sm leading-7">
                  <div>
                    <h2 className="text-xl">
                      <ProjectBrand />
                    </h2>
                    <p className="text-muted-foreground">经营周报工作空间</p>
                  </div>
                  <p>
                    使用 LangGraph 编排、MCP 官方 SDK 工具和可修改的 Agent
                    Skills，生成周报并等待人工审核。
                  </p>
                  <p>
                    岗位职责、工作步骤和注意事项可在员工配置中修改。超出调用轮次或时长上限后，任务暂停并转人工处理。
                  </p>
                  <div className="rounded-lg border p-4">
                    <h3 className="mb-2 font-medium">开源来源</h3>
                    <p className="text-muted-foreground">
                      界面基于 DeerFlow
                      e0f5483（MIT）适配，复用主题、侧栏、Radix
                      组件、分屏与设置布局；周报业务接入现有后端。
                    </p>
                    <a
                      className="mt-2 inline-block underline underline-offset-4"
                      href="https://github.com/bytedance/deer-flow"
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看 DeerFlow 源码
                    </a>
                    <p className="mt-3 text-xs text-muted-foreground">
                      Copyright © 2025 ByteDance Ltd. and/or its affiliates; ©
                      2025–2026 DeerFlow Authors. 完整许可及差异记录见
                      THIRD_PARTY_NOTICES.md。
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    本地单用户工作空间。审核姓名用于操作留痕。
                  </p>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
