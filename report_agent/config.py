from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

import yaml
from dotenv import dotenv_values

ROOT = Path(os.environ.get("REPORT_AGENT_ROOT", Path(__file__).resolve().parents[1])).resolve()
DATA = Path(os.environ.get("REPORT_AGENT_DATA", ROOT / "runtime" / "v2")).resolve()
DATA.mkdir(parents=True, exist_ok=True)


def validate_files(files):
    try:
        employee = yaml.safe_load(files["config/employee.yaml"])
        columns = yaml.safe_load(files["config/columns.yaml"])
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 格式无效：{exc}") from exc
    if not isinstance(employee, dict) or not isinstance(columns, dict):
        raise ValueError("员工配置和字段映射必须是非空对象")
    limit_names = {
        "model_calls", "model_timeout_seconds", "active_seconds", "tool_timeout_seconds",
        "tool_retries", "quality_repairs",
    }
    limits = employee.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("执行限制必须是字段对象")
    if not limit_names.issubset(limits):
        raise ValueError("执行限制缺少必需字段：" + "、".join(sorted(limit_names - set(limits))))
    for name in limit_names:
        value = limits[name]
        if type(value) is not int or value < (0 if name in {"tool_retries", "quality_repairs"} else 1):
            raise ValueError(f"执行限制 {name} 必须是有效整数")
    reasons = employee.get("limit_reasons")
    if not isinstance(reasons, dict) or any(
        not isinstance(reasons.get(name), str) or not reasons[name].strip()
        for name in ("model_calls", "model_timeout_seconds", "active_seconds")
    ):
        raise ValueError("模型调用和时长上限必须保留文字说明")
    quality = employee.get("quality")
    required_quality = {"min_characters", "max_characters", "max_pages", "min_charts", "max_actions"}
    if not isinstance(quality, dict) or any(
        type(quality.get(name)) is not int or quality[name] < 1 for name in required_quality
    ):
        raise ValueError("质检规则的正文长度、页数、图表和行动项上限必须是正整数")
    if quality["min_characters"] > quality["max_characters"]:
        raise ValueError("质检规则的最小正文长度不能超过最大长度")
    for name in ("required_sections", "forbidden_words"):
        if not isinstance(quality.get(name), list) or not all(
            isinstance(value, str) and value.strip() for value in quality[name]
        ):
            raise ValueError(f"质检规则 {name} 必须是有效文字列表")
    if not quality["required_sections"]:
        raise ValueError("质检规则 required_sections 不能为空")
    if type(quality.get("max_summary_sentences")) is not int or quality["max_summary_sentences"] < 1:
        raise ValueError("质检规则 max_summary_sentences 必须是正整数")
    business = employee.get("business")
    if not isinstance(business, dict):
        raise ValueError("缺少业务规则")
    for name in ("anomaly_percent", "flat_tolerance_percent", "margin_drop_points"):
        value = business.get(name)
        if (type(value) not in {int, float} or not 0 <= value <= 100
                or (type(value) is float and not math.isfinite(value))):
            raise ValueError(f"业务阈值 {name} 必须是 0 至 100 的数字，不能写百分号")
    if not isinstance(business.get("flat_phrases"), list) or not all(
        isinstance(value, str) and value.strip() for value in business["flat_phrases"]
    ):
        raise ValueError("业务规则 flat_phrases 必须是文字列表")
    allowed_tools = employee.get("allowed_tools")
    if not isinstance(allowed_tools, list) or not all(
        isinstance(name, str) and name.strip() for name in allowed_tools
    ):
        raise ValueError("允许工具必须是非空工具名列表")
    required_tools = {"read_sales", "read_minutes", "compute_metrics", "generate_report", "inspect_report"}
    if not required_tools.issubset(allowed_tools):
        raise ValueError("允许工具缺少工作流所需工具：" + "、".join(sorted(required_tools - set(allowed_tools))))
    required_columns = {
        "sales": {"record_id", "date", "store_id", "product_id", "channel", "quantity", "amount", "cost"},
        "stores": {"store_id", "store", "region"},
        "products": {"product_id", "product", "category"},
        "targets": {"region", "year", "week", "target"},
    }
    for role, required in required_columns.items():
        mapping = columns.get(role)
        if not isinstance(mapping, dict) or not required.issubset(mapping):
            raise ValueError(f"字段映射 {role} 缺少必需字段：" + "、".join(sorted(required - set(mapping or {}))))
        for field, aliases in mapping.items():
            if not isinstance(aliases, list) or not aliases or not all(
                isinstance(alias, str) and alias.strip() for alias in aliases
            ):
                raise ValueError(f"字段映射 {role}.{field} 必须是非空列名列表")
    if not isinstance(columns.get("delivery_channel"), str) or not columns["delivery_channel"].strip():
        raise ValueError("字段映射 delivery_channel 必须填写渠道名称")
    allowed_channels = columns.get("allowed_channels")
    if not isinstance(allowed_channels, list) or not allowed_channels or not all(
        isinstance(channel, str) and channel.strip() for channel in allowed_channels
    ):
        raise ValueError("字段映射 allowed_channels 必须是非空渠道名称列表")
    if len(allowed_channels) != len(set(allowed_channels)) or columns["delivery_channel"] not in allowed_channels:
        raise ValueError("允许渠道不能重复，且必须包含外卖渠道 delivery_channel")
    rework = employee.get("rework", {})
    if not isinstance(rework, dict):
        raise ValueError("返工规则必须是字段对象")
    categories = {"data", "evidence", "content", "layout"}
    sections = {"summary", "anomalies", "conflicts", "data_notes", "actions"}
    rules = rework.get("categories", {})
    routes = rework.get("quality_routes", {})
    if not isinstance(rules, dict) or not isinstance(routes, dict):
        raise ValueError("返工类别和质检路由必须是字段对象")
    if not set(rules).issubset(categories):
        raise ValueError("返工类别必须是 data、evidence、content 或 layout")
    for rule in [*rules.values(), *routes.values()]:
        if not isinstance(rule, dict) or not isinstance(rule.get("sections", []), list) or not all(
            isinstance(section, str) for section in rule.get("sections", [])
        ):
            raise ValueError("返工规则必须包含有效章节列表")
        if not set(rule.get("sections", [])).issubset(sections):
            raise ValueError("返工章节包含不受支持的字段")
        if rule.get("category", "content") not in categories:
            raise ValueError("质检返工类别不受支持")
    for key in ["岗位职责", "工作步骤", "注意事项"]:
        if f"## {key}" not in files["skills/weekly-report/SKILL.md"]:
            raise ValueError(f"技能文件缺少 {key} 章节")
    return employee, columns


def snapshot():
    paths = ["config/employee.yaml", "config/columns.yaml", "skills/weekly-report/SKILL.md"]
    files = {p: (ROOT / p).read_text(encoding="utf-8") for p in paths}
    employee, columns = validate_files(files)
    return {
        "employee": employee,
        "columns": columns,
        "skill": files[paths[2]],
        "files": files,
        "version": hashlib.sha256(str(files).encode()).hexdigest()[:16],
    }


def connection():
    values = dotenv_values(ROOT / ".env", interpolate=False)
    return {
        k: values.get(k) or os.environ.get(k) or default
        for k, default in {
            "LLM_BASE_URL": "https://apihub.agnes-ai.com/v1",
            "LLM_MODEL": "agnes-3.0-flash",
            "LLM_API_KEY": "",
            "LLM_MAX_TOKENS": "6000",
            "LLM_TEMPERATURE": "0.2",
            "LLM_REASONING_EFFORT": "",
        }.items()
    }
