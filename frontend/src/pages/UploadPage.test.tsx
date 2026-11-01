// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { request } from "@/api/client";
import { UploadPage } from "./UploadPage";

vi.mock("@/api/client", () => ({ request: vi.fn() }));
// The workspace header is outside the form and has its own sidebar tests.
vi.mock("@/components/workspace/workspace-header", () => ({
  WorkspaceHeader: () => null,
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function openForm() {
  vi.mocked(request).mockImplementation(async (path) =>
    path === "/config"
      ? { connection: { LLM_MODEL: "test-model" } }
      : { id: "submitted" },
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/runs/submitted" element={<p>任务已提交</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

it("keeps focus on year and week while clicking, typing and using arrow keys", async () => {
  const user = openForm();
  const title = screen.getByLabelText("任务名称") as HTMLInputElement;
  const year = screen.getByLabelText("年份") as HTMLInputElement;
  const week = screen.getByLabelText("周次") as HTMLInputElement;
  await user.click(year);
  expect(document.activeElement).toBe(year);
  await user.clear(year);
  await user.type(year, "2025");
  expect(year.value).toBe("2025");
  await user.click(week);
  expect(document.activeElement).toBe(week);
  await user.clear(week);
  await user.type(week, "42");
  await user.keyboard("{ArrowUp}");
  expect(document.activeElement).toBe(week);
  expect(title.value).toBe("门店经营周报");
  expect(week.value).toBe("42"); // jsdom does not implement native number stepping.
  await user.click(title);
  await user.tab();
  expect(document.activeElement).toBe(year);
  await user.tab();
  expect(document.activeElement).toBe(week);
});

it("serializes the edited period with the unchanged task title", async () => {
  const user = openForm();
  await user.clear(screen.getByLabelText("年份"));
  await user.type(screen.getByLabelText("年份"), "2025");
  await user.clear(screen.getByLabelText("周次"));
  await user.type(screen.getByLabelText("周次"), "12");
  // Check the period payload here; native file selection and validated form
  // submission are exercised in Edge/Chrome against the built workspace.
  fireEvent.submit(
    screen.getByRole("button", { name: "开始生成" }).closest("form")!,
  );
  await screen.findByText("任务已提交");
  const call = vi.mocked(request).mock.calls.find(([path]) => path === "/runs");
  const body = call?.[1]?.body as FormData;
  expect(JSON.parse(String(body.get("spec")))).toMatchObject({
    title: "门店经营周报",
    year: 2025,
    week: 12,
  });
});
