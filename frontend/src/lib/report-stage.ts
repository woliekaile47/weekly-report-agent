import type { StateSnapshot } from "@/api/types";

export function reportStageLabel(state: StateSnapshot): string {
  if (state.status === "completed") return "已审核交付";
  if (state.quality?.passed === false) return "质检未通过，仅供查看";
  if (state.status === "awaiting_human" && state.quality?.passed)
    return "质检通过，等待人工审核";
  if (state.status === "paused") return "已暂停，仅供查看";
  return "生成或修改中";
}
