"""Record a read-only tour of the real local application. No model calls or approvals are issued."""

import json
import re
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/video"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    candidates = httpx.get("http://127.0.0.1:8501/api/runs").json()["runs"]
    task_id = next((r["id"] for r in candidates if r["week"] == 44 and r["status"] == "awaiting_human"), None)
    if not task_id:
        raise SystemExit("请先生成一份第44周真实待审核报告再录制。")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 960},
            record_video_dir=str(OUT),
            record_video_size={"width": 1440, "height": 960},
            device_scale_factor=1,
        )
        page = context.new_page()
        page.goto("http://127.0.0.1:8501", wait_until="networkidle")

        def chapter(title, detail, seconds=9):
            page.evaluate(
                """([title,detail])=>{let e=document.getElementById('recording-caption');if(!e){e=document.createElement('div');e.id='recording-caption';e.style='position:fixed;bottom:16px;left:50%;transform:translateX(-50%);width:780px;max-width:86vw;z-index:10000;background:#172b4df2;color:white;border-radius:12px;padding:15px 22px;box-shadow:0 5px 30px #0003;pointer-events:none;font-family:Microsoft YaHei,sans-serif';document.body.appendChild(e)} e.replaceChildren();let t=document.createElement('strong');t.textContent=title;t.style='font-size:16px;display:block;margin-bottom:7px';let d=document.createElement('div');d.textContent=detail;d.style='font-size:12px;color:#d4dfef;line-height:1.7';e.append(t,d)}""",
                [title, detail],
            )
            page.wait_for_timeout(seconds * 1000)

        page.get_by_role("link", name="上传与执行", exact=True).click()
        chapter(
            "经营周报员工｜真实应用巡览",
            "LangGraph 编排 · MCP 官方 SDK · 可配置岗位技能 · Word 交付。画面展示实际应用与真实模型生成成果，不使用模拟对话。",
            10,
        )
        page.goto(f"http://127.0.0.1:8501/runs/{task_id}", wait_until="networkidle")
        chapter(
            "第 44 周｜系统数据与模型解释",
            "实收 573,635 元，环比 -9.3%。程序计算指标；模型结合第 44 周纪要逐项解释异常。此任务经过真实模型生成及质检修正。",
            10,
        )
        page.get_by_role("tab", name="材料识别").click()
        chapter(
            "多工作表识别与按 ID 去重",
            "读取销售、门店、商品和目标表。44,820 条原始记录，按记录 ID 剔除 29 条相同重复上传；冲突记录暂停核实。",
            9,
        )
        page.get_by_role("tab", name="周报与审核").click()
        page.get_by_role("heading", name="异常与原因", exact=True).scroll_into_view_if_needed()
        chapter(
            "异常、原文证据与纪要冲突",
            "超过 ±10% 的区域和门店逐项列出；无直接证据的原因标为待核实。纪要说法与系统指标不一致时，以数据为准。",
            10,
        )
        page.get_by_role("tab", name="质检记录").click()
        page.evaluate("window.scrollTo(0,0)")
        chapter(
            "程序质检｜三页、两图及可追溯数字",
            "检查结构、数字来源、异常覆盖、原文、Word 表格、图表与真实页数。本周 Word 已经 Microsoft Word 实际排版验证为 3 页。",
            10,
        )
        page.get_by_role("tab", name="执行记录").click()
        chapter(
            "完整事件与持久化恢复",
            "模型请求、工具调用、质检及恢复均有记录。后台中断后从检查点继续，事件回放不会重新提交任务。",
            9,
        )
        page.goto("http://127.0.0.1:8501/settings/employee", wait_until="networkidle")
        chapter(
            "业务人员可以修改员工做法",
            "职责、步骤、注意事项、阈值与质检以技能或 YAML 文件维护。新任务保存配置快照；已受理任务保持原配置。",
            10,
        )
        page.get_by_role("link", name="执行限制与人工处理", exact=True).click()
        chapter(
            "有界执行与人工处理",
            "每轮 8 次模型请求，单次 90 秒，活动执行 600 秒。超限暂停，填写处理人和处理意见后明确恢复。限制理由随交付包保存。",
            9,
        )
        page.goto(f"http://127.0.0.1:8501/runs/{task_id}", wait_until="networkidle")
        page.get_by_role("tab", name="周报与审核").click()
        page.get_by_role("heading", name=re.compile("^人工审核")).scroll_into_view_if_needed()
        chapter(
            "交付前人工审核｜支持同任务返工",
            "审核人可通过或填写意见退回，退回后生成新版本、重新质检和送审。本视频只浏览待审核成果，不替业务人员批准；正式交付包需通过当前版本后生成。",
            12,
        )
        page.get_by_text("关于工作空间", exact=True).click()
        chapter(
            "开源复用与验证边界",
            "界面和流程复用 Invoice Audit Assistant，文本处理复用 GenSlide，Word 使用 docxtpl。来源、版本与许可均已保留；企业盲测与业务审核仍需现场完成。",
            10,
        )
        video = page.video
        context.close()
        browser.close()
        path = video.path()
        (OUT / "recording.json").write_text(
            json.dumps(
                {
                    "source": str(path),
                    "kind": "read-only real-application tour",
                    "automatic_approvals": False,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(path)


if __name__ == "__main__":
    main()
