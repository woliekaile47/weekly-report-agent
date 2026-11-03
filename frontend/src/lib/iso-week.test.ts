import { expect, it } from "vitest";
import { describeIsoWeek, isoWeekStart, lastCompleteIsoWeek } from "./iso-week";

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
