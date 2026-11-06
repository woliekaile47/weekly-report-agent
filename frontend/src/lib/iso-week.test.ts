import { expect, it } from "vitest";
import { currentIsoWeek, describeIsoWeek, isoWeekStart, lastCompleteIsoWeek } from "./iso-week";

it("selects the previous complete ISO week using the local calendar day", () => {
  expect(lastCompleteIsoWeek(new Date(2026, 10, 3, 0, 30))).toEqual({ year: 2026, week: 44 });
  expect(lastCompleteIsoWeek(new Date(2026, 0, 1, 12))).toEqual({ year: 2025, week: 52 });
  expect(lastCompleteIsoWeek(new Date(2021, 0, 4, 12))).toEqual({ year: 2020, week: 53 });
});

it("shows the selected range and rejects a nonexistent ISO week", () => {
  expect(describeIsoWeek(2026, 44)).toBe("统计周期：2026 年第 44 周（10 月 26 日—11 月 1 日）");
  expect(describeIsoWeek(2020, 53)).toBe("统计周期：2020 年第 53 周（12 月 28 日—1 月 3 日）");
  expect(isoWeekStart(2021, 53)).toBeNull();
});

it("uses current ISO weeks including year boundaries", () => {
 for (const [date,year,week] of [[new Date(2026,10,6),2026,45],[new Date(2026,10,16),2026,47],[new Date(2026,10,8,23,59),2026,45],[new Date(2026,10,9),2026,46],[new Date(2021,0,1),2020,53],[new Date(2025,11,29),2026,1]] as const) expect(currentIsoWeek(date)).toEqual({year,week});
 expect(describeIsoWeek(2026,45)).toContain("11 月 2 日—11 月 8 日");
});
