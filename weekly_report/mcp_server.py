"""Official MCP Python SDK server. Run with python -m weekly_report.mcp_server."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from weekly_report.analysis import calculate, read_minutes_file, read_sales_file
from weekly_report.contracts import FileData, MetricsData, MinutesData, QualityData, SalesData, ToolResult
from weekly_report.report import build_document, chart, inspect, save_quality
from weekly_report.schemas import EmployeeError
from weekly_report.store import task_path

mcp = FastMCP("weekly-report-tools")


def root():
    return Path(os.environ["EMPLOYEE_DATA_DIR"]).resolve()


def invoke(function, *args, **kwargs):
    try:
        return {"ok": True, "data": function(*args, **kwargs)}
    except EmployeeError as exc:
        return {"ok": False, "error": str(exc), "kind": exc.kind}
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc), "kind": "execution"}


@mcp.tool()
def read_sales(task_id: str, file: str, aliases: dict[str, list[str]]) -> ToolResult[SalesData]:
    """Read validated Excel/CSV rows within a task directory; money is returned as integer cents."""
    return invoke(read_sales_file, task_path(root(), task_id, file), aliases)


@mcp.tool()
def read_minutes(task_id: str, file: str) -> ToolResult[MinutesData]:
    """Extract meeting paragraphs and assign stable evidence IDs."""
    return invoke(read_minutes_file, task_path(root(), task_id, file))


@mcp.tool()
def compute_metrics(sales: dict, spec: dict, threshold: float) -> ToolResult[MetricsData]:
    """Compute comparable-period sales, regional/store/category aggregates and anomaly flags."""
    return invoke(calculate, sales, spec, threshold)


@mcp.tool()
def render_charts(task_id: str, artifact_id: str, metrics: dict) -> ToolResult[FileData]:
    """Write an idempotent regional comparison chart and return its task-relative path."""
    file = f"artifacts/{artifact_id}/regions.png"
    result = invoke(chart, metrics, task_path(root(), task_id, file))
    if result["ok"]:
        result["data"] = {"file": file}
    return result


@mcp.tool()
def build_report(
    task_id: str,
    artifact_id: str,
    chart_file: str,
    spec: dict,
    metrics: dict,
    minutes: dict,
    draft: dict,
    version: int,
    mode: str,
    feedback: list[dict],
) -> ToolResult[FileData]:
    """Generate a Word report with metrics, chart, evidence and reviewer feedback."""
    file = f"artifacts/{artifact_id}/report.docx"
    result = invoke(
        build_document,
        task_path(root(), task_id, file),
        task_path(root(), task_id, chart_file),
        spec,
        metrics,
        minutes,
        draft,
        version,
        mode,
        feedback,
    )
    if result["ok"]:
        result["data"] = {"file": file}
    return result


@mcp.tool()
def inspect_report(
    task_id: str,
    report_file: str,
    draft: dict,
    metrics: dict,
    minutes: dict,
    quality: dict,
    feedback: list[dict],
) -> ToolResult[QualityData]:
    """Check report structure, length, numeric consistency, citations and artifact integrity."""
    result = invoke(
        inspect, task_path(root(), task_id, report_file), draft, metrics, minutes, quality, feedback
    )
    if result["ok"]:
        file = str(Path(report_file).with_name("quality.json")).replace("\\", "/")
        save_quality(task_path(root(), task_id, file), result["data"])
        result["data"]["file"] = file
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
