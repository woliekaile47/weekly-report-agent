from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml
from dotenv import dotenv_values

ROOT = Path(os.environ.get("REPORT_AGENT_ROOT", Path(__file__).resolve().parents[1])).resolve()
DATA = Path(os.environ.get("REPORT_AGENT_DATA", ROOT / "runtime" / "v2")).resolve()
DATA.mkdir(parents=True, exist_ok=True)


def snapshot():
    paths = ["config/employee.yaml", "config/columns.yaml", "skills/weekly-report/SKILL.md"]
    files = {p: (ROOT / p).read_text(encoding="utf-8") for p in paths}
    employee = yaml.safe_load(files[paths[0]])
    for name, value in employee["limits"].items():
        if type(value) is not int or value < (0 if name in {"tool_retries", "quality_repairs"} else 1):
            raise ValueError(f"执行限制 {name} 必须是有效整数")
    rework = employee.get("rework", {})
    categories = {"data", "evidence", "content", "layout"}
    sections = {"summary", "anomalies", "conflicts", "data_notes", "actions"}
    if not set(rework.get("categories", {})).issubset(categories):
        raise ValueError("返工类别必须是 data、evidence、content 或 layout")
    for rule in [*rework.get("categories", {}).values(), *rework.get("quality_routes", {}).values()]:
        if not set(rule.get("sections", [])).issubset(sections):
            raise ValueError("返工章节包含不受支持的字段")
        if rule.get("category", "content") not in categories:
            raise ValueError("质检返工类别不受支持")
    return {
        "employee": employee,
        "columns": yaml.safe_load(files[paths[1]]),
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
