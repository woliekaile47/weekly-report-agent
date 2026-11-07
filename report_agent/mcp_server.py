"""Only official MCP SDK. Tool schemas are published by FastMCP."""

from mcp.server.fastmcp import FastMCP

from report_agent import data_tools
from report_agent.contracts import (
    ArtifactResult,
    ImportResult,
    MetricsResult,
    MinutesResult,
    QualityResult,
    ToolResult,
)
from report_agent.models import WorkflowError

mcp = FastMCP("weekly-report-employee")


def invoke(fn, *args, **kwargs):
    try:
        return {"ok": True, "data": fn(*args, **kwargs)}
    except WorkflowError as exc:
        return {"ok": False, "error": str(exc), "kind": exc.kind}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"工具执行失败（{type(exc).__name__}），请检查材料或本地日志",
            "kind": "execution",
        }


@mcp.tool()
def read_sales(
    task_id: str, file: str, columns: dict, options: dict | None = None, master_file: str = ""
) -> ToolResult[ImportResult]:
    """Read workbook/CSV, join unique dimension keys, dedupe identical record IDs, persist normalized rows."""
    return invoke(data_tools.read_sales, task_id, file, columns, options, master_file)


@mcp.tool()
def read_minutes(task_id: str, file: str) -> ToolResult[MinutesResult]:
    """Read business meeting sources with stable identifiers."""
    return invoke(data_tools.read_minutes, task_id, file)


@mcp.tool()
def compute_metrics(
    task_id: str,
    sales: dict,
    spec: dict,
    threshold: float = 10,
    delivery_channel: str = "外卖",
    margin_drop_points: float = 5,
) -> ToolResult[MetricsResult]:
    """Calculate exact sales, margins, targets, delivery share, top products and anomalies."""
    return invoke(
        data_tools.compute_metrics, task_id, sales, spec, threshold, delivery_channel, margin_drop_points
    )


@mcp.tool()
def generate_report(
    task_id: str,
    version: int,
    metrics: dict,
    minutes: dict,
    draft: dict,
    bundle: dict,
    feedback: list,
    render_options: dict | None = None,
) -> ToolResult[ArtifactResult]:
    """Render a versioned Word report from a business-editable docxtpl template, with two charts."""
    from report_agent.documents import generate_report as render

    return invoke(render, task_id, version, metrics, minutes, draft, bundle, feedback, render_options)


@mcp.tool()
def inspect_report(
    task_id: str, artifact: dict, metrics: dict, minutes: dict, draft: dict, bundle: dict, feedback: list
) -> ToolResult[QualityResult]:
    """Run deterministic document, evidence, numeric and coverage checks; return inspection records."""
    from report_agent.documents import inspect_report as inspect

    return invoke(inspect, task_id, artifact, metrics, minutes, draft, bundle, feedback)


@mcp.tool()
def search_news(spec: dict) -> dict:
    """Retrieve bounded public news leads with URLs and publication dates; no truth certification."""
    from report_agent.news import search_news as search
    return invoke(search, spec)


if __name__ == "__main__":
    mcp.run(transport="stdio")
