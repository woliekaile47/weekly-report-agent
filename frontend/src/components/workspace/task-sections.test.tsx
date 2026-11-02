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
  fireEvent.click(screen.getByRole("button", { name: "恢复执行" }));
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
  fireEvent.change(screen.getByLabelText("替换销售文件"), {
    target: { files: [new File([], "empty.csv", { type: "text/csv" })] },
  });
  expect(screen.getByRole("alert").textContent).toContain("empty.csv");
  fireEvent.change(screen.getByLabelText("年份"), { target: { value: "2025" } });
  fireEvent.click(screen.getByRole("button", { name: "恢复执行" }));
  expect(screen.getByRole("alert").textContent).toContain("empty.csv");
  expect(onOperation).not.toHaveBeenCalled();
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
