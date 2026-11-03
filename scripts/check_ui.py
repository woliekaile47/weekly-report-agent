"""Read-only acceptance of the DeerFlow adaptation against real tasks and files."""

import json
import os
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8501"
OUT = Path(__file__).resolve().parents[1] / "runtime/ui-qa/deerflow"


def upload_sources():
    if os.environ.get("PUBLIC_DATA_DIR"):
        candidate = Path(os.environ["PUBLIC_DATA_DIR"])
        return candidate if (candidate / "销售明细.xlsx").is_file() else None
    for parent in OUT.parents:
        if parent.name == "比赛":
            source = next(parent.glob("赛题/**/销售明细.xlsx"), None)
            return source.parent if source else None
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = httpx.get(BASE + "/api/runs").json()["runs"]
    before = {r["id"]: httpx.get(BASE + "/api/runs/" + r["id"]).json() for r in runs}
    report_id = next((r["id"] for r in runs if r["week"] == 44 and r["status"] == "awaiting_human"), None)
    errors, checks, interactions = [], [], []
    source = upload_sources()
    with sync_playwright() as p:
        for channel in ("msedge", "chrome"):
            browser = p.chromium.launch(channel=channel, headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")
            blocked_writes = []

            def read_only(route):
                if route.request.method not in {"GET", "HEAD", "OPTIONS"}:
                    blocked_writes.append(route.request.method + " " + route.request.url)
                    route.abort()
                else:
                    route.continue_()

            context.route("**/api/**", read_only)
            page = context.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            routes = ["/", "/history", "/settings", "/settings/employee", "/settings/limits"]
            routes += ["/runs/" + r["id"] for r in runs]
            for width in (375, 760, 1024, 1600):
                page.set_viewport_size({"width": width, "height": 1000})
                for route in routes:
                    response = page.goto(BASE + route, wait_until="networkidle")
                    assert response.status == 200
                    assert response.headers["cache-control"] == "no-store"
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (
                        channel,
                        width,
                        route,
                        "horizontal overflow",
                    )
                    if route.startswith("/settings"):
                        dialog = page.get_by_role("dialog", name="设置", exact=True)
                        expect(dialog).to_be_visible()
                        if route.endswith("employee"):
                            expect(dialog.get_by_role("textbox").first).to_have_attribute(
                                "aria-label", "skills/weekly-report/SKILL.md"
                            )
                        if channel == "msedge" and width in (375, 1600):
                            page.screenshot(path=str(OUT / f"settings-{width}.png"))
                    else:
                        expect(
                            page.locator('[data-slot="sidebar-inset"] [data-sidebar="trigger"]')
                        ).to_be_visible()
                    if route.startswith("/runs/"):
                        task = before[route.rsplit("/", 1)[1]]
                        expect(
                            page.get_by_role("heading", name=task["spec"]["title"], exact=True)
                        ).to_be_visible()
                        if task["status"] == "paused" and not task.get("draft"):
                            expect(page.get_by_role("heading", name="等待周报成果")).to_be_attached()
                            page.get_by_text("补充材料、调整周期或列映射", exact=True).click()
                            expect(page.get_by_label("替换或补充销售明细", exact=True)).to_be_visible()
                            assert page.get_by_role("button", name="提交审核决定").count() == 0
                        if task["status"] == "awaiting_human":
                            expect(page.get_by_role("button", name="提交审核决定")).to_be_attached()
                            expect(page.get_by_role("combobox", name="审核决定", exact=True)).to_have_value(
                                "revise"
                            )
                        for tab in ("材料识别", "质检记录", "执行记录", "周报内容", "执行图谱", "工作进度"):
                            page.get_by_role("tab", name=tab, exact=True).click()
                            expect(page.get_by_role("tab", name=tab, exact=True)).to_have_attribute(
                                "aria-selected", "true"
                            )
                        page.locator("#task-scroll").evaluate("e => e.scrollTop = 0")
                        if channel == "msedge" and width in (375, 1600) and task["status"] == "paused":
                            page.screenshot(path=str(OUT / f"paused-{width}.png"))
                    checks.append({"browser": channel, "width": width, "route": route})
                page.goto(BASE, wait_until="networkidle")
                if channel == "msedge":
                    page.screenshot(path=str(OUT / f"home-{width}.png"))

            # Real PDF: render, paginate, resize, close and reopen. No approval is submitted.
            if report_id:
                page.goto(f"{BASE}/runs/{report_id}", wait_until="networkidle")
                expect(page.get_by_text("1 / 3 页", exact=True)).to_be_visible(timeout=15000)
                page.wait_for_function("""() => {
                    const canvas = document.querySelector('canvas[aria-label="周报 PDF 第 1 页"]');
                    if (!canvas || !canvas.width || !canvas.height) return false;
                    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
                    let colored = 0;
                    for (let i = 0; i < pixels.length; i += 16) if (pixels[i+3] > 0 && pixels[i] + pixels[i+1] + pixels[i+2] < 700) colored++;
                    return colored > 500;
                }""")
                page.get_by_role("button", name="下一页", exact=True).click()
                expect(page.get_by_text("2 / 3 页", exact=True)).to_be_visible()
                page.get_by_role("button", name="上一页", exact=True).click()
                expect(page.get_by_text("1 / 3 页", exact=True)).to_be_visible()
                page.get_by_role("button", name="前往人工审核", exact=True).click()
                expect(page.get_by_role("button", name="提交审核决定", exact=True)).to_be_visible()
                page.locator("#task-scroll").evaluate("e => e.scrollTop = 0")
                separator = page.get_by_role("separator", name="调整成果面板宽度")
                initial = page.get_by_role("complementary", name="任务成果面板").bounding_box()["width"]
                box = separator.bounding_box()
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.down()
                page.mouse.move(box["x"] + 80, box["y"] + box["height"] / 2, steps=8)
                page.mouse.up()
                resized = page.get_by_role("complementary", name="任务成果面板").bounding_box()["width"]
                assert abs(resized - initial) > 30
                page.get_by_role("button", name="关闭成果面板", exact=True).click()
                expect(page.get_by_role("button", name="打开任务文件")).to_have_attribute(
                    "aria-expanded", "false"
                )
                page.get_by_role("button", name="打开任务文件").click()
                reopened = page.get_by_role("complementary", name="任务成果面板").bounding_box()["width"]
                assert abs(reopened - resized) < 10
                page.set_viewport_size({"width": 760, "height": 1000})
                expect(page.get_by_role("button", name="打开任务文件")).to_have_attribute(
                    "aria-expanded", "false"
                )
                toggle = page.locator('[data-slot="sidebar-inset"] [data-sidebar="trigger"]')
                toggle.click()
                expect(page.get_by_role("dialog", name="工作空间导航", exact=True)).to_be_visible()
                page.keyboard.press("Escape")
                page.get_by_role("button", name="打开任务文件").click()
                expect(page.get_by_role("dialog", name="任务成果预览", exact=True)).to_be_visible()
                page.get_by_role("button", name="关闭成果面板", exact=True).click()
                page.set_viewport_size({"width": 1600, "height": 1000})
                expect(toggle).to_be_visible()
                toggle.click()
                expect(toggle).to_have_attribute("aria-expanded", "false")
                page.wait_for_timeout(250)
                page.get_by_role("link", name="任务历史", exact=True).first.hover()
                expect(page.get_by_role("tooltip")).to_be_visible()
                page.mouse.move(900, 20)
                expect(page.get_by_role("tooltip")).to_be_hidden(timeout=600)
                toggle.click()
                page.get_by_role("button", name="打开任务文件").click()
                page.wait_for_timeout(250)
                if channel == "msedge":
                    page.screenshot(path=str(OUT / "report-final.png"))
                interactions.append(
                    {
                        "browser": channel,
                        "pdf_rendered": True,
                        "pagination": True,
                        "panel_resize_persisted": True,
                        "split_fullscreen_sidebar": True,
                        "tooltip_dismissed": True,
                    }
                )

            # Footer menu opens the original settings layout and closes without stranding focus.
            page.get_by_role("button", name="设置与更多", exact=True).click()
            page.get_by_role("menuitem", name="员工配置", exact=True).click()
            dialog = page.get_by_role("dialog", name="设置", exact=True)
            expect(dialog).to_be_visible()
            expect(dialog.get_by_label("skills/weekly-report/SKILL.md")).to_be_visible()
            dialog.get_by_role("button", name="模型连接", exact=True).click()
            expect(dialog.locator('input[name="api_key"]')).to_have_value("")
            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
            page.get_by_role("button", name="搜索任务", exact=False).click()
            search = page.get_by_role("dialog", name="搜索任务", exact=True)
            expect(search).to_be_visible()
            search.get_by_role("textbox").fill("不存在的任务名称")
            expect(search.get_by_text("没有匹配的任务")).to_be_visible()
            page.keyboard.press("Escape")
            page.set_viewport_size({"width": 760, "height": 1000})
            page.locator('[data-slot="sidebar-inset"] [data-sidebar="trigger"]').click()
            navigation = page.get_by_role("dialog", name="工作空间导航", exact=True)
            expect(navigation).to_be_visible()
            navigation.get_by_role("button", name="设置与更多", exact=True).click()
            page.get_by_role("menuitem", name="员工配置", exact=True).click()
            expect(page.get_by_role("dialog", name="设置", exact=True)).to_be_visible()
            expect(navigation).to_be_hidden()
            page.keyboard.press("Escape")
            expect(page.locator('[data-slot="sidebar-inset"] [data-sidebar="trigger"]')).to_be_visible()
            page.set_viewport_size({"width": 1600, "height": 1000})
            # Exercise real file controls and multipart serialization, intercepting writes.
            if source:
                sales = source / "销售明细.xlsx"
                minutes = next(source.rglob("*2026W44*.docx"), None)
                if minutes:
                    writes = []

                    def intercept_create(route):
                        if route.request.method != "POST":
                            route.continue_()
                            return
                        body = route.request.post_data_buffer
                        has_sales = b'name="sales"; filename=' in body
                        has_minutes = b'name="minutes"; filename=' in body
                        assert b'"year":2026' in body
                        assert (has_sales, has_minutes) in {(False, True), (True, False), (True, True)}
                        assert (b'"week":46' if has_sales and not has_minutes else b'"week":44') in body
                        # CDP omits file bytes from multipart post_data_buffer.
                        writes.append((has_sales, has_minutes))
                        route.fulfill(
                            status=422,
                            content_type="application/json",
                            body=json.dumps(
                                {"detail": "浏览器验证已阻止写入，现有任务未修改"}, ensure_ascii=False
                            ),
                        )

                    page.route(BASE + "/api/runs", intercept_create)
                    page.add_init_script("""(() => {
                        const original = window.fetch;
                        window.fetch = function(input, options) {
                            if (String(input).endsWith('/api/runs') && options?.body instanceof FormData) {
                                window.uploadInspection = Object.fromEntries([...options.body.entries()].map(([key, value]) =>
                                    [key, value instanceof File ? {name: value.name, size: value.size} : value]));
                            }
                            return original.apply(this, arguments);
                        };
                    })();""")
                    page.goto(BASE, wait_until="networkidle")
                    page.get_by_label("本周周会纪要", exact=True).set_input_files(str(minutes))
                    page.get_by_role("button", name="发起任务", exact=True).click()
                    expect(page.get_by_role("alert")).to_contain_text("浏览器验证已阻止写入")
                    page.goto(BASE, wait_until="networkidle")
                    page.get_by_label("销售明细", exact=True).set_input_files(str(sales))
                    page.get_by_label("周次", exact=True).fill("46")
                    page.get_by_role("button", name="发起任务", exact=True).click()
                    expect(page.get_by_role("alert")).to_contain_text("浏览器验证已阻止写入")
                    page.goto(BASE, wait_until="networkidle")
                    page.get_by_label("销售明细", exact=True).set_input_files(str(sales))
                    page.get_by_label("本周周会纪要", exact=True).set_input_files(str(minutes))
                    page.get_by_role("button", name="发起任务", exact=True).click()
                    expect(page.get_by_role("alert")).to_contain_text("浏览器验证已阻止写入")
                    assert writes == [(False, True), (True, False), (True, True)], writes
                    sent = page.evaluate("window.uploadInspection")
                    assert sent["sales"]["size"] == sales.stat().st_size
                    assert sent["minutes"]["size"] == minutes.stat().st_size
                    page.unroute(BASE + "/api/runs", intercept_create)
                    interactions.append({"channel": channel, "single_and_two_file_multipart": True})
            assert not blocked_writes, blocked_writes
            context.close()
            # A failed entrypoint script still leaves a recovery link.
            recovery = browser.new_page()
            recovery.clock.install()
            recovery.route("**/assets/*.js", lambda route: route.abort())
            recovery.goto(BASE, wait_until="domcontentloaded")
            recovery.clock.fast_forward(11000)
            expect(recovery.get_by_text("工作空间加载未完成", exact=True)).to_be_visible()
            expect(recovery.get_by_role("link", name="重新加载工作空间")).to_be_visible()
            browser.close()
    assert not errors, errors
    for task_id, task in before.items():
        assert httpx.get(BASE + "/api/runs/" + task_id).json() == task, "UI verification changed a real task"
    assert len(httpx.get(BASE + "/api/runs").json()["runs"]) == len(runs)
    result = {
        "passed": True,
        "page_checks": len(checks),
        "render_errors": errors,
        "tasks_unchanged": True,
        "interactions": interactions,
        "checks": checks,
    }
    (OUT / "browser-acceptance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
