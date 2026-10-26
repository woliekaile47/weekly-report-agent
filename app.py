from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from weekly_report.report import substitute
from weekly_report.schemas import Review, TaskSpec
from weekly_report.service import EmployeeService
from weekly_report.settings import Settings
from weekly_report.store import task_path
from weekly_report.ui_chinese import STATUS, event_rows, friendly_error, localize_widgets, translate_details

st.set_page_config(page_title="经营周报员工", page_icon="📊", layout="wide")
st.markdown(
    """<style>
.block-container { max-width: 1200px; padding-top: 2rem; }
[data-testid="stMetric"] { background: #f0f6f7; border-radius: 10px; padding: 16px; }
h1,h2,h3 { color: #194e61; }
</style>""",
    unsafe_allow_html=True,
)

localize_widgets()

with st.sidebar:
    st.title("经营周报员工")
    st.caption("分析有依据 · 修改可追溯")
    service = EmployeeService(Settings())
    st.caption("使用 Agnes 模型分析上传的业务资料")
    st.divider()
    if st.button("新建任务", use_container_width=True):
        st.session_state.pop("task_id", None)
    tasks = service.store.tasks()
    if st.session_state.get("task_id") not in {task["id"] for task in tasks}:
        st.session_state.pop("task_id", None)
    selected = st.selectbox(
        "历史任务",
        [None] + [t["id"] for t in tasks],
        placeholder="选择任务",
        format_func=lambda x: (
            "选择任务" if x is None else next(f"{t['title']} · {x[:6]}" for t in tasks if t["id"] == x)
        ),
    )
    if st.button("打开任务", disabled=selected is None, use_container_width=True):
        st.session_state.task_id = selected
    st.caption("本地单用户应用。审核姓名用于留痕，不提供企业身份认证。")


def action(function, *args, **kwargs):
    try:
        with st.spinner("员工正在处理，完成后会显示结果…"):
            result = function(*args, **kwargs)
        return result
    except Exception as exc:
        st.error(friendly_error(exc))
        return None


if "task_id" not in st.session_state:
    st.title("把本周经营情况，整理成可交付的周报")
    st.write("上传门店销售明细与周会纪要。员工会计算指标、说明异常、生成图表，等待你审核后交付。")
    with st.form("new_task"):
        title = st.text_input("任务名称", "门店经营周报")
        left, right = st.columns(2)
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        last_week_end = today - timedelta(days=today.weekday() + 1)
        start = left.date_input("开始日期", last_week_end - timedelta(days=6))
        end = right.date_input("结束日期", last_week_end)
        compare = st.checkbox("需要与前一个同长度周期比较", True)
        focus = st.text_area("重点关注", placeholder="填写本次经营分析需要重点关注的问题")
        sales = st.file_uploader("销售明细", type=["xlsx", "csv"], max_upload_size=20)
        minutes = st.file_uploader("周会纪要", type=["docx", "md", "txt"], max_upload_size=20)
        st.caption("销售列：日期、门店、区域、品类、销售额。需要环比时，请在同一文件中包含上期数据。")
        submitted = st.form_submit_button("创建并执行", type="primary")
    if submitted:
        try:
            spec = TaskSpec(
                title=title, start_date=start, end_date=end, require_comparison=compare, focus=focus
            )
            files = {}
            for key, file in [("sales", sales), ("minutes", minutes)]:
                if file:
                    files[key] = (file.name, file.getvalue())
            task_id = service.create(spec, files)
            st.session_state.task_id = task_id
            action(service.run, task_id)
            st.rerun()
        except Exception as exc:
            st.error(friendly_error(exc))
    st.stop()

task_id = st.session_state.task_id
state = service.state(task_id)
st.title(state["spec"]["title"])
st.caption(
    f"任务 {task_id[:8]} · {state['spec']['start_date']} 至 {state['spec']['end_date']} · 版本 {state['version']}"
)
cols = st.columns(3)
cols[0].metric("任务状态", STATUS.get(state["status"], state["status"]))
cols[1].metric("分析模型", service.settings.model)
cols[2].metric("本轮模型调用", state.get("model_calls", 0))

if state["status"] == "PAUSED":
    st.warning(state["reason"])
    with st.form("resume"):
        st.write("可补充或替换材料后继续；服务故障解除后也可直接重试。")
        new_sales = st.file_uploader("补充销售数据", type=["csv", "xlsx"], max_upload_size=20)
        new_minutes = st.file_uploader("补充周会纪要", type=["docx", "txt", "md"], max_upload_size=20)
        if st.form_submit_button("恢复执行", type="primary"):
            files = {
                key: (value.name, value.getvalue())
                for key, value in [("sales", new_sales), ("minutes", new_minutes)]
                if value
            }
            if action(service.resume, task_id, files=files):
                st.rerun()
elif state["status"] in {"NEW", "RUNNING", "REWORK", "APPROVED"}:
    if st.button("继续执行 / 从中断处恢复", type="primary"):
        if action(service.run, task_id):
            st.rerun()

report_tab, quality_tab, events_tab = st.tabs(["周报与审核", "质检记录", "执行记录"])
with report_tab:
    if state.get("draft") and state.get("metrics"):
        draft, tokens = state["draft"], state["metrics"]["tokens"]
        st.subheader("经营概览")
        st.write(substitute(draft["summary"], tokens))
        if state.get("chart_file"):
            chart = task_path(service.settings.data_dir, task_id, state["chart_file"])
            if chart.exists():
                st.image(str(chart))
        for finding in draft["findings"]:
            st.subheader(substitute(finding["title"], tokens))
            st.write(("待核实：" if finding["uncertain"] else "") + substitute(finding["analysis"], tokens))
            for evidence in finding["evidence"]:
                st.caption(f"[{evidence['source_id']}] {evidence['quote']}")
        st.subheader("行动建议")
        for item in draft["actions"]:
            st.write("• " + substitute(item, tokens))
        if draft.get("review_response"):
            st.subheader("本次修改说明")
            st.write(substitute(draft["review_response"], tokens))
    if state.get("report_file"):
        path = task_path(service.settings.data_dir, task_id, state["report_file"])
        if path.exists():
            st.download_button(
                "下载周报文档供审核" if state["status"] != "DELIVERED" else "下载经营周报文档",
                path.read_bytes(),
                f"经营周报-v{state['version']}.docx",
            )
    if state["status"] == "REVIEW":
        st.divider()
        st.subheader("审核当前版本")
        with st.form("review"):
            reviewer = st.text_input("审核人")
            decision = st.radio("审核结果", ["通过并交付", "退回修改"], horizontal=True)
            feedback = st.text_area(
                "修改意见（退回时必填）", placeholder="例如：华东区下滑原因没说清楚，请结合周会纪要补充。"
            )
            if st.form_submit_button("提交审核结果", type="primary"):
                try:
                    review = Review(
                        decision="approve" if decision == "通过并交付" else "reject",
                        reviewer=reviewer,
                        feedback=feedback,
                        version=state["version"],
                    )
                    if action(service.review, task_id, review):
                        st.rerun()
                except Exception as exc:
                    st.error(friendly_error(exc))
    if state["status"] == "DELIVERED":
        st.success("当前版本已通过审核，周报、质检记录和审核记录已打包。")
        package = task_path(service.settings.data_dir, task_id, state["delivery"])
        st.download_button(
            "下载完整交付包", package.read_bytes(), package.name, mime="application/zip", type="primary"
        )
with quality_tab:
    for item in state.get("quality_history", []):
        st.write(f"版本 {item['version']} · {'通过' if item['passed'] else '未通过'}")
        st.table(
            [
                {
                    "检查项": check["name"],
                    "结果": "通过" if check["passed"] else "未通过",
                    "说明": translate_details(check["details"]),
                }
                for check in item["checks"]
            ]
        )
    if not state.get("quality_history"):
        st.info("尚无质检记录，周报生成后会显示检查结果。")
with events_tab:
    st.table(event_rows(service.store.events(task_id)))
