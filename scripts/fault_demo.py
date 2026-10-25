"""Demonstrate persistent MCP tool failure and recovery without losing successful steps."""

from weekly_report.schemas import TaskSpec
from weekly_report.service import EmployeeService
from weekly_report.settings import ROOT, Settings

settings = Settings(mode="mock")
service = EmployeeService(settings, faults={"compute_metrics": -1})
files = {
    "sales": ("sales.csv", (ROOT / "samples/sales.csv").read_bytes()),
    "minutes": ("minutes.md", (ROOT / "samples/minutes.md").read_bytes()),
}
task_id = service.create(
    TaskSpec(title="工具故障演示", start_date="2026-10-26", end_date="2026-11-01"), files
)
state = service.run(task_id)
print("任务：", task_id)
print("故障后：", state["status"], state.get("reason"))
restored = EmployeeService(settings)
state = restored.resume(task_id)
print("恢复后：", state["status"])
events = restored.store.events(task_id)
print("工具失败次数：", sum(e["kind"] == "tool_failed" for e in events))
print(
    "销售读取成功次数：",
    sum(e["kind"] == "tool_completed" and e["payload"]["tool"] == "read_sales" for e in events),
)
