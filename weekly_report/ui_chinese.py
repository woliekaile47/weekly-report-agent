"""Chinese presentation for widgets and audit records; persisted data stays unchanged."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from pydantic import ValidationError

STATUS = {
    "NEW": "待执行",
    "RUNNING": "执行中 / 可恢复",
    "PAUSED": "已暂停",
    "REVIEW": "等待审核",
    "REWORK": "修改中 / 可恢复",
    "APPROVED": "审核通过 / 待交付",
    "DELIVERED": "已交付",
}
TOOLS = {
    "admit": "准入检查",
    "read_sales": "读取销售数据",
    "read_minutes": "读取周会纪要",
    "metrics": "计算经营指标",
    "compute_metrics": "计算经营指标",
    "draft": "撰写周报",
    "charts": "生成图表",
    "render_charts": "生成图表",
    "report": "生成周报文档",
    "build_report": "生成周报文档",
    "quality": "自动质检",
    "inspect_report": "检查周报",
    "review": "人工审核",
    "deliver": "交付成果",
    "pause": "暂停等待",
}
EVENTS = {
    "created": "任务创建",
    "state": "流程进度",
    "tool_started": "工具开始执行",
    "tool_completed": "工具执行完成",
    "tool_cached": "复用已有结果",
    "tool_failed": "工具执行失败",
    "tool_denied": "已拒绝越权调用",
    "model_started": "模型开始分析",
    "model_completed": "模型分析完成",
    "step_failed": "步骤执行失败",
    "quality": "自动质检",
    "review": "人工审核",
    "resumed": "任务恢复",
    "delivered": "成果交付",
    "transition_rejected": "已拒绝无效操作",
}
FIELDS = {
    "task_id": "任务编号",
    "title": "任务名称",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "require_comparison": "需要环比",
    "focus": "重点关注",
    "spec": "任务要求",
    "mode": "分析模式",
    "tool": "工具",
    "attempt": "尝试次数",
    "step": "当前步骤",
    "from": "原状态",
    "to": "新状态",
    "version": "报告版本",
    "round": "调用轮次",
    "message": "说明",
    "reason": "原因",
    "decision": "审核结果",
    "reviewer": "审核人",
    "feedback": "审核意见",
    "passed": "检查通过",
    "name": "检查项",
    "details": "检查说明",
    "inputs_replaced": "已补充材料",
    "sales": "销售数据",
    "minutes": "周会纪要",
    "checks": "检查明细",
}


def translate_details(text):
    return str(text).replace("True", "是").replace("False", "否").replace("Word 无法打开", "周报文档无法打开")


def readable(value, key=""):
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return "无"
    if isinstance(value, dict):
        return "；".join(
            f"{FIELDS.get(k, '补充信息')}：{readable(v, k)}"
            for k, v in value.items()
            if k not in {"budget_id", "artifact_id", "file", "report_hash"}
        )
    if isinstance(value, list):
        return "、".join(readable(item, key) for item in value) or "无"
    if key in {"from", "to", "status"}:
        return STATUS.get(value, "未知状态")
    if key in {"tool", "step"}:
        return TOOLS.get(value, "未开放的工具")
    if key == "mode":
        return "真实模型" if value == "live" else "离线演示"
    if key == "decision":
        return "通过" if value == "approve" else "退回修改"
    if key == "inputs_replaced":
        return FIELDS.get(value, "附件")
    return translate_details(value)


def event_rows(events):
    return [
        {
            "序号": event["seq"],
            "时间（北京时间）": datetime.fromisoformat(event["time"])
            .astimezone(ZoneInfo("Asia/Shanghai"))
            .strftime("%Y年%m月%d日 %H:%M:%S"),
            "操作": EVENTS.get(event["kind"], "执行记录"),
            "详情": readable(event["payload"]),
        }
        for event in events
    ]


def friendly_error(error):
    if not isinstance(error, ValidationError):
        return translate_details(error)
    messages = []
    for item in error.errors():
        label = FIELDS.get(str(item["loc"][-1]), "填写内容") if item["loc"] else "填写内容"
        reason = item.get("ctx", {}).get("error")
        if reason:
            messages.append(str(reason))
        elif item["type"] == "string_too_short":
            messages.append(f"{label}不能为空")
        elif item["type"] == "string_too_long":
            messages.append(f"{label}过长，请缩短后重试")
        else:
            messages.append(f"请检查{label}是否填写正确")
    return "；".join(messages)


_localize_widgets = st.components.v2.component(
    "chinese_widgets",
    js=Path(__file__).with_name("ui_chinese.js").read_text(encoding="utf-8"),
)


def localize_widgets():
    _localize_widgets(key="chinese_widgets", height=0)
