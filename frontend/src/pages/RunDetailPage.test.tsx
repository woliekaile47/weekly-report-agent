// @vitest-environment jsdom
import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StateSnapshot } from "../api/types";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { RunDetailPage } from "./RunDetailPage";
import { SidebarProvider } from "@/components/ui/sidebar";

// Layout measurement is browser-only; the browser acceptance test covers React Flow itself.
vi.mock("../components/GraphView", () => ({
  GraphView: () => <div>任务执行流程图</div>,
}));

class EventSourceStub {
  addEventListener() {}
  close() {}
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const paused = {
  task_id: "task-missing-sales",
  spec: { title: "缺少材料的任务", year: 2026, week: 44, focus: "" },
  status: "paused",
  reason: "缺少销售明细，请补充 Excel 或 CSV",
  error_kind: "materials",
  current_node: "ingest",
  resume_node: "ingest",
  version: 1,
  // These empty objects are the real checkpoint representation that previously crashed the page.
  draft: {},
  metrics: {},
  sales: {},
  artifact: {},
  quality: {},
} as unknown as StateSnapshot;

function openTask(snapshot: StateSnapshot) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("1099"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.stubGlobal("EventSource", EventSourceStub);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }),
  );
  return render(
    <MemoryRouter initialEntries={["/runs/task-missing-sales"]}>
      <SidebarProvider>
        <Routes>
          <Route path="/runs/:id" element={<RunDetailPage />} />
        </Routes>
      </SidebarProvider>
    </MemoryRouter>,
  );
}

describe("checkpoint rendering regression", () => {
  it("renders a real missing-material checkpoint and its recovery form instead of a blank page", async () => {
    openTask(paused);
    await screen.findByRole("heading", { name: "缺少材料的任务" });
    expect(screen.getAllByText(paused.reason!).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "等待周报成果" })).toBeTruthy();
    fireEvent.click(screen.getByText("补充材料、调整周期或列映射"));
    expect(screen.getByLabelText("替换销售文件")).toBeTruthy();
    expect(screen.getByRole("button", { name: "恢复执行" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "提交审核决定" })).toBeNull();
  });

  it("supports material and quality tabs before their outputs have been generated", async () => {
    openTask(paused);
    await screen.findByRole("heading", { name: "缺少材料的任务" });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "材料识别" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(screen.getByText("读取材料后展示识别结果。")).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "质检记录" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(
      screen.getByText("生成 Word 后执行检查；当前没有质检记录。"),
    ).toBeTruthy();
  });

  it("keeps a failed operation message visible when background polling succeeds", async () => {
    openTask(paused);
    await screen.findByRole("heading", { name: "缺少材料的任务" });
    vi.mocked(fetch).mockImplementation(
      async (_input, init) =>
        ({
          ok: init?.method !== "POST",
          json: async () =>
            init?.method === "POST"
              ? { detail: "恢复请求未成功，请检查材料" }
              : paused,
        }) as Response,
    );
    fireEvent.click(screen.getByRole("button", { name: "恢复执行" }));
    await screen.findByRole("alert");
    const before = vi.mocked(fetch).mock.calls.length;
    await waitFor(
      () => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(before),
      { timeout: 3000 },
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "恢复请求未成功，请检查材料",
    );
  });
});

it("provides recovery links for an unexpected render failure", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  function Broken(): React.ReactNode {
    throw new Error("unexpected component error");
  }
  render(
    <ErrorBoundary>
      <Broken />
    </ErrorBoundary>,
  );
  expect(screen.getByRole("alert").textContent).toContain(
    "任务进度保存在服务端",
  );
  expect(
    screen.getByRole("link", { name: "返回任务历史" }).getAttribute("href"),
  ).toBe("/history");
});
