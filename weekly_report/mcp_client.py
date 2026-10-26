from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from weekly_report.schemas import EmployeeError
from weekly_report.store import digest, task_path

TOOL_POLICY = {
    "read_sales",
    "read_minutes",
    "compute_metrics",
    "render_charts",
    "build_report",
    "inspect_report",
}


class MCPGateway:
    def __init__(self, settings, store, task_id, employee, faults=None):
        self.settings, self.store, self.task_id = settings, store, task_id
        self.employee, self.faults = employee, faults or {}
        self.allowed = TOOL_POLICY.intersection(employee["allowed_tools"])
        self.session = None
        self.worker = None
        self.queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self.worker is not None and not self.worker.done():
            await self.queue.put(None)
            await self.worker

    async def connect(self):
        if self.worker is None or self.worker.done():
            self.ready = asyncio.get_running_loop().create_future()
            self.worker = asyncio.create_task(self.serve())
        await self.ready

    async def serve(self):
        # MCP/AnyIO enter and exit must run in the same asyncio task.
        try:
            async with AsyncExitStack() as stack:
                await self.open_session(stack)
                self.ready.set_result(True)
                while True:
                    request = await self.queue.get()
                    if request is None:
                        break
                    name, arguments, future = request
                    try:
                        result = await self.session.call_tool(name, arguments)
                        if not future.done():
                            future.set_result(result)
                    except Exception as exc:
                        if not future.done():
                            future.set_exception(exc)
        except Exception as exc:
            if not self.ready.done():
                self.ready.set_exception(EmployeeError(f"MCP 服务连接失败（{type(exc).__name__}）"))
        finally:
            self.session = None

    async def open_session(self, stack):
        # Do not send model credentials to the tool process.
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
        }
        env.update(
            {
                "EMPLOYEE_DATA_DIR": str(self.settings.data_dir),
                "PYTHONUTF8": "1",
                "PYTHONPATH": str(self.settings.root),
                "MPLBACKEND": "Agg",
            }
        )
        stderr = stack.enter_context((self.settings.data_dir / "mcp-stderr.log").open("a", encoding="utf-8"))
        streams = await stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "weekly_report.mcp_server"],
                    env=env,
                    cwd=str(self.settings.root),
                ),
                errlog=stderr,
            )
        )
        session = await stack.enter_async_context(
            ClientSession(
                streams[0],
                streams[1],
                read_timeout_seconds=timedelta(seconds=self.employee["limits"]["tool_timeout_seconds"]),
            )
        )
        await session.initialize()
        discovered = {tool.name for tool in (await session.list_tools()).tools}
        if not self.allowed.issubset(discovered):
            raise EmployeeError("MCP 服务缺少配置要求的工具")
        self.session = session

    async def call(self, name, arguments):
        if name not in self.allowed:
            self.store.event(self.task_id, "tool_denied", {"tool": name})
            raise EmployeeError(f"员工无权调用工具：{name}", "permission")
        if "task_id" in arguments and arguments["task_id"] != self.task_id:
            raise EmployeeError("拒绝访问其他任务", "permission")
        key = digest(
            {"task": self.task_id, "tool": name, "args": arguments, "skill": self.employee["version"]}
        )
        cached = self.store.cached(key)
        if cached is not None:
            file = cached.get("file") if isinstance(cached, dict) else None
            if not file or task_path(self.settings.data_dir, self.task_id, file).exists():
                self.store.event(self.task_id, "tool_cached", {"tool": name})
                return cached
        for attempt in range(self.employee["limits"]["tool_retries"] + 1):
            self.store.event(self.task_id, "tool_started", {"tool": name, "attempt": attempt + 1})
            try:
                fault = self.faults.get(name, 0)
                if fault:
                    if isinstance(fault, int) and fault > 0:
                        self.faults[name] -= 1
                    raise EmployeeError("测试注入：工具暂时不可用")
                await self.connect()
                future = asyncio.get_running_loop().create_future()
                await self.queue.put((name, arguments, future))
                result = await future
                if result.isError:
                    raise EmployeeError("MCP 工具返回错误，请查看本地工具日志")
                payload = result.structuredContent
                if payload is None:
                    payload = json.loads(next(c.text for c in result.content if c.type == "text"))
                if not isinstance(payload, dict) or "ok" not in payload:
                    raise EmployeeError("MCP 工具返回格式不正确")
                if not payload["ok"]:
                    raise EmployeeError(payload.get("error", "工具失败"), payload.get("kind", "execution"))
                self.store.cache(key, payload["data"])
                self.store.event(
                    self.task_id, "tool_completed", {"tool": name, "attempt": attempt + 1}, key="tool:" + key
                )
                return payload["data"]
            except Exception as exc:
                error = (
                    exc
                    if isinstance(exc, EmployeeError)
                    else EmployeeError(f"工具 {name} 通信失败（{type(exc).__name__}）")
                )
                self.store.event(
                    self.task_id, "tool_failed", {"tool": name, "attempt": attempt + 1, "message": str(error)}
                )
                if (
                    error.kind in {"materials", "permission"}
                    or attempt == self.employee["limits"]["tool_retries"]
                ):
                    raise error
                await asyncio.sleep(min(0.5 * (2**attempt), 2))
        raise EmployeeError("工具调用失败")
