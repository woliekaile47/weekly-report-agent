import type { StateSnapshot } from "@/api/types";

export function newsStatusLabel(news: StateSnapshot["news"]): string {
  if (!news) return "等待识别";
  switch (news.status) {
    case "disabled": return "已关闭";
    case "retrieved": return news.sources.length ? "已检索" : "已检索，无结果";
    case "partial": return "检索部分完成";
    case "skipped": return "已跳过检索";
    case "plan_failed": return "检索规划失败";
    case "unavailable": return "检索不可用";
    default: return "已处理";
  }
}
