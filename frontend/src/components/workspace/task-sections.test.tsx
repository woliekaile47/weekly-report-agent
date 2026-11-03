// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PauseForm, ReviewForm, TaskOutputs } from "./task-sections";
import { completedFromSnapshot } from "@/api/snapshot";
import type { StateSnapshot } from "@/api/types";

afterEach(cleanup);

it("lets a paused task remove an obsolete master workbook", () => {
  const onOperation = vi.fn().mockResolvedValue(undefined);
  render(
    <PauseForm
      state={{
        status: "paused",
        error_kind: "materials",
        inputs: { master: "inputs/master-old.xlsx" },
        spec: { title: "周报", year: 2026, week: 44, focus: "" },
      }}
      active={false}
      onOperation={onOperation}
    />,
  );
  fireEvent.click(screen.getByText("补充材料、调整周期或列映射"));
  fireEvent.click(screen.getByLabelText(/移除已有基础资料/));
  fireEvent.click(screen.getByRole("button", { name: "上传销售明细并继续" }));
  expect(onOperation).toHaveBeenCalled();
  const [path, data] = onOperation.mock.calls[0];
  expect(path).toBe("resume");
  expect(data.get("remove_master")).toBe("true");
});

it("shows an error instead of silently dropping a selected empty replacement file", () => {
  const onOperation = vi.fn().mockResolvedValue(undefined);
  render(
    <PauseForm
      state={{ status: "paused", error_kind: "materials", spec: { title: "周报", year: 2026, week: 44, focus: "" } }}
      active={false}
      onOperation={onOperation}
    />,
  );
  fireEvent.click(screen.getByText("补充材料、调整周期或列映射"));
  fireEvent.change(screen.getByLabelText("替换或补充销售明细"), {
    target: { files: [new File([], "empty.csv", { type: "text/csv" })] },
  });
  expect(screen.getByRole("alert").textContent).toContain("empty.csv");
  fireEvent.change(screen.getByLabelText("年份"), { target: { value: "2025" } });
  fireEvent.click(screen.getByRole("button", { name: "上传销售明细并继续" }));
  expect(screen.getByRole("alert").textContent).toContain("empty.csv");
  expect(onOperation).not.toHaveBeenCalled();
});

it("shows a direct next step and coverage for an out-of-range sales task", () => {
  render(<PauseForm
    state={{
      status: "paused", error_kind: "materials", resume_node: "calculate",
      reason: "第 46 周没有销售数据；上传资料实际覆盖 2026-10-19 至 2026-11-01",
      spec: { title: "周报", year: 2026, week: 46, focus: "" },
      inputs: { sales: "inputs/sales.xlsx" },
      sales: { sheet: "销售", rows: 2, raw_rows: 2, removed_duplicates: 0, mapping: {}, date_start: "2026-10-19", date_end: "2026-11-01" },
    }}
    active={false} onOperation={vi.fn()}
  />);
  expect(screen.getByText(/所选周期：2026 年第 46 周；销售覆盖：2026-10-19 至 2026-11-01/)).toBeTruthy();
  expect(screen.getByLabelText("ISO 周")).toBeTruthy();
  expect(screen.getByLabelText("替换或补充销售明细")).toBeTruthy();
});

it("keeps failed QA out of the awaiting-review label and shows Word quality notes", () => {
  render(<TaskOutputs id="test" tab="report" setTab={() => {}} events={[]} progress={null} workflow={null}
    state={{
      status: "paused", quality: { passed: false, checks: [{ name: "数字依据", passed: false, details: "待修正" }] },
      draft: { summary: "摘要", anomalies: [], conflicts: [], data_notes: [], actions: ["行动"], review_response: "" },
      report_quality_notes: ["本期退货 11 笔，合计 -260 元，已直接冲减系统实收。"],
    }} />);
  expect(screen.getByText("质检未通过，仅供查看")).toBeTruthy();
  expect(screen.getByText(/本期退货 11 笔/)).toBeTruthy();
  expect(screen.queryByText("待审核草稿")).toBeNull();
});

it("submits separate review items with the selected rework type and current version", () => {
  const onOperation = vi.fn().mockResolvedValue(undefined);
  render(
    <ReviewForm
      state={{ status: "awaiting_human", version: 3 }}
      active={false}
      onOperation={onOperation}
    />,
  );
  fireEvent.change(screen.getByLabelText("审核人"), {
    target: { value: "运营经理" },
  });
  fireEvent.change(screen.getByLabelText("修改类型"), {
    target: { value: "layout" },
  });
  fireEvent.change(screen.getByLabelText("审核意见"), {
    target: { value: "缩小段后间距\n改善表格排版" },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "提交审核决定" }).closest("form")!,
  );
  const payload = JSON.parse(onOperation.mock.calls[0][1]);
  expect(payload.version).toBe(3);
  expect(payload.items).toEqual([
    { text: "缩小段后间距", category: "layout" },
    { text: "改善表格排版", category: "layout" },
  ]);
});

it("shows unresolved review feedback and before/after content", () => {
  render(
    <TaskOutputs
      id="test"
      state={{
        revision_items: [
          {
            id: "R1-1",
            text: "补充摘要",
            categories: ["content"],
            sections: ["summary"],
            status: "open",
            before: { summary: "原摘要" },
            after: { summary: "未修改的摘要" },
            requested_version: 1,
            verification: "缺少逐项回应",
          },
        ],
      }}
      tab="revisions"
      setTab={() => {}}
      events={[]}
      progress={null}
      workflow={null}
    />,
  );
  expect(screen.getByText("R1-1 · 补充摘要")).toBeTruthy();
  expect(screen.getByText("缺少逐项回应")).toBeTruthy();
  fireEvent.click(screen.getByText("查看修改前后内容"));
  expect(screen.getByText("原摘要")).toBeTruthy();
  expect(screen.getByText("未修改的摘要")).toBeTruthy();
});

it("does not mark cleared outputs or waiting human approval as completed", () => {
  const done = completedFromSnapshot({
    status: "awaiting_human",
    quality: { passed: true, checks: [] },
    artifact: {},
    draft: {},
  } as unknown as StateSnapshot);
  expect(done).toEqual(["quality"]);
});
