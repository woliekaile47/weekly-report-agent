const DAY = 24 * 60 * 60 * 1000;
const WEEK = 7 * DAY;

function mondayOf(date: Date) {
  const monday = new Date(date.getTime());
  monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
  return monday;
}

export function isoWeekStart(year: number, week: number): Date | null {
  if (!Number.isInteger(year) || year < 2000 || year > 2100 || !Number.isInteger(week) || week < 1 || week > 53) {
    return null;
  }
  const first = mondayOf(new Date(Date.UTC(year, 0, 4)));
  const start = new Date(first.getTime() + (week - 1) * WEEK);
  const thursday = new Date(start.getTime() + 3 * DAY);
  return thursday.getUTCFullYear() === year ? start : null;
}

export function currentIsoWeek(now = new Date()) {
  // Use the browser's local calendar date, then UTC arithmetic to avoid DST shifts.
  const today = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  const start = mondayOf(today);
  const year = new Date(start.getTime() + 3 * DAY).getUTCFullYear();
  const first = isoWeekStart(year, 1)!;
  return { year, week: Math.round((start.getTime() - first.getTime()) / WEEK) + 1 };
}

export function describeIsoWeek(year: number, week: number) {
  const start = isoWeekStart(year, week);
  if (!start) return "请输入有效的 ISO 年份和周次。";
  const end = new Date(start.getTime() + 6 * DAY);
  const shortDate = (date: Date) => `${date.getUTCMonth() + 1} 月 ${date.getUTCDate()} 日`;
  return `统计周期：${year} 年第 ${week} 周（${shortDate(start)}—${shortDate(end)}）`;
}

export function lastCompleteIsoWeek(now = new Date()) {
 const previous = new Date(now);
 previous.setDate(previous.getDate() - 7);
 return currentIsoWeek(previous);
}
