"""Read-only browser acceptance against the real running app; never submits tasks or reviews."""

import json
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8501"
OUT = Path(__file__).resolve().parents[1] / "runtime/ui-qa"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = httpx.get(BASE + "/api/runs").json()["runs"]
    before = {r["id"]: httpx.get(BASE + "/api/runs/" + r["id"]).json() for r in runs}
    errors, checks = [], []
    with sync_playwright() as p:
        for channel in ("msedge", "chrome"):
            browser = p.chromium.launch(channel=channel, headless=True)
            page = browser.new_page(viewport={"width": 1900, "height": 950}, locale="zh-CN")
            page.on("pageerror", lambda e: errors.append(str(e)))
            routes = ["/", "/history", "/settings", "/settings/employee", "/settings/limits"]
            routes += ["/runs/" + r["id"] for r in runs]
            for width in (375, 760, 1900):
                page.set_viewport_size({"width": width, "height": 950})
                for route in routes:
                    response = page.goto(BASE + route, wait_until="networkidle")
                    assert response.status == 200
                    assert response.headers["cache-control"] == "no-store"
                    expect(page.get_by_role("navigation", name="主导航")).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (channel, width, route, "horizontal overflow")
                    if route.startswith("/runs/"):
                        task = before[route.rsplit("/", 1)[1]]
                        if task["status"] == "paused" and not task.get("draft"):
                            expect(page.get_by_role("heading", name="等待周报成果")).to_be_attached()
                            page.get_by_text("补充材料、调整周期或列映射", exact=True).click()
                            expect(page.get_by_label("替换销售文件", exact=True)).to_be_visible()
                            assert page.get_by_role("button", name="提交审核决定").count() == 0
                        if task["status"] == "awaiting_human":
                            expect(page.get_by_role("button", name="提交审核决定")).to_be_attached()
                            if width == 1900:
                                boxes = page.locator("[aria-label='任务执行流程图']").bounding_box(), page.get_by_role("heading", name="实时节点输出").locator("..").bounding_box()
                                assert abs(boxes[0]["y"] - boxes[1]["y"]) < 1
                                assert abs(boxes[0]["height"] - boxes[1]["height"]) < 1
                        for tab in ("材料识别", "质检记录", "执行记录", "周报与审核"):
                            page.get_by_role("tab", name=tab, exact=True).click()
                            expect(page.get_by_role("tab", name=tab, exact=True)).to_have_attribute("aria-selected", "true")
                        if channel == "msedge" and width == 1900:
                            page.evaluate("window.scrollTo(0,0)")
                            page.screenshot(path=str(OUT / ("reference-" + route.rsplit("/", 1)[1] + ".png")))
                    checks.append({"browser": channel, "width": width, "route": route})
                if channel == "msedge":
                    page.goto(BASE, wait_until="networkidle")
                    page.screenshot(path=str(OUT / f"reference-upload-{width}.png"), full_page=True)
            # Resource-loading failures must leave a readable recovery entrypoint.
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
        after = httpx.get(BASE + "/api/runs/" + task_id).json()
        assert after == task, "Browser verification must not change real tasks"
    result = {"passed": True, "page_checks": len(checks), "render_errors": errors, "tasks_unchanged": True, "checks": checks}
    (OUT / "browser-acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
