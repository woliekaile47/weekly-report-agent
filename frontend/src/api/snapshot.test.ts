import { expect, it } from "vitest";
import { completedFromSnapshot } from "./snapshot";
import { newsStatusLabel } from "@/lib/news-status";

it.each([
  ["retrieved", "已检索，无结果"],
  ["partial", "检索部分完成"],
  ["skipped", "已跳过检索"],
  ["unavailable", "检索不可用"],
  ["plan_failed", "检索规划失败"],
])("preserves processed news status %s in the graph", (status, label) => {
  const news = { status, message: "状态说明", sources: [] };
  expect(completedFromSnapshot({ news })).toContain("news");
  expect(newsStatusLabel(news)).toBe(label);
});

it("keeps an unprocessed news node pending", () => {
  expect(completedFromSnapshot({})).not.toContain("news");
});
