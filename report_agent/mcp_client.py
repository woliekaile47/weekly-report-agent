import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from datetime import timedelta

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from report_agent.config import DATA, ROOT
from report_agent.models import WorkflowError
from report_agent.store import digest, task_path

TOOLS = {"read_sales", "read_minutes", "compute_metrics", "generate_report", "inspect_report"}


class Gateway:
    def __init__(self, store, task_id, bundle, faults=None):
        self.store, self.task_id, self.bundle = store, task_id, bundle
        self.allowed = TOOLS.intersection(bundle["employee"]["allowed_tools"])
        self.faults = faults or {}
        self.stack = AsyncExitStack()
        self.session = None
        self.connection_error = None
        self.startup_seconds = 0

    async def __aenter__(self):
        return self

    async def connect(self):
        """Own SDK cancel scopes in the parent task; failed setup is raised by graph tools."""
        started = time.monotonic()
        limits = self.bundle["employee"]["limits"]
        for attempt in range(limits["tool_retries"] + 1):
            self.store.event(self.task_id, "mcp_connect_started", {"attempt": attempt + 1})
            try:
                if self.faults.get("connect", 0):
                    if self.faults["connect"] > 0:
                        self.faults["connect"] -= 1
                    raise WorkflowError("测试注入：MCP 连接暂时不可用")
                await self._connect_once()
                self.connection_error = None
                return
            except Exception as exc:
                await self.stack.aclose()
                self.stack = AsyncExitStack()
                self.session = None
                self.connection_error = WorkflowError(
                    f"MCP 工具服务连接失败（{type(exc).__name__}），已保存进度，请检查服务后恢复", "execution"
                )
                self.store.event(
                    self.task_id,
                    "mcp_connect_failed",
                    {"attempt": attempt + 1, "message": str(self.connection_error)},
                )
                if time.monotonic() - started >= limits["active_seconds"]:
                    self.connection_error = WorkflowError(
                        "MCP 连接耗时达到活动执行上限，已暂停转人工", "budget"
                    )
                    break
                if attempt < limits["tool_retries"]:
                    await asyncio.sleep(min(attempt + 1, 2))
            finally:
                self.startup_seconds = time.monotonic() - started

    async def _connect_once(self):
        if self.session:
            return
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
        }
        env.update(
            {
                "REPORT_AGENT_ROOT": str(ROOT),
                "REPORT_AGENT_DATA": str(DATA),
                "PYTHONPATH": str(ROOT),
                "PYTHONUTF8": "1",
                "MPLBACKEND": "Agg",
            }
        )
        log = self.stack.enter_context((DATA / "mcp.log").open("a", encoding="utf-8"))
        streams = await self.stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=sys.executable, args=["-m", "report_agent.mcp_server"], cwd=str(ROOT), env=env
                ),
                errlog=log,
            )
        )
        self.session = await self.stack.enter_async_context(
            ClientSession(
                *streams,
                read_timeout_seconds=timedelta(
                    seconds=self.bundle["employee"]["limits"]["tool_timeout_seconds"]
                ),
            )
        )
        with anyio.fail_after(self.bundle["employee"]["limits"]["tool_timeout_seconds"]):
            await self.session.initialize()
            discovered = {t.name for t in (await self.session.list_tools()).tools}
        if not self.allowed.issubset(discovered):
            raise WorkflowError("MCP 服务缺少允许工具")

    async def __aexit__(self, *args):
        await self.stack.aclose()

    async def call(self, name, args):
        if name not in self.allowed or ("task_id" in args and args["task_id"] != self.task_id):
            self.store.event(self.task_id, "tool_denied", {"tool": name})
            raise WorkflowError("拒绝越权工具调用", "permission")
        if self.connection_error:
            raise self.connection_error
        key = digest(
            {
                "revision": 3,
                "task": self.task_id,
                "name": name,
                "args": args,
                "bundle": self.bundle["version"],
            }
        )
        # Generated files and their inspection are mutable; never reuse an existence-only cache.
        cacheable = name not in {"generate_report", "inspect_report"}
        cached = self.store.cached(key) if cacheable else None
        if cached is not None and (
            not cached.get("file") or task_path(self.task_id, cached["file"]).exists()
        ):
            self.store.event(self.task_id, "tool_cached", {"tool": name})
            return cached
        limits = self.bundle["employee"]["limits"]
        for attempt in range(limits["tool_retries"] + 1):
            self.store.event(self.task_id, "tool_started", {"tool": name, "attempt": attempt + 1})
            try:
                if self.faults.get(name, 0):
                    if self.faults[name] > 0:
                        self.faults[name] -= 1
                    raise WorkflowError("测试注入：工具暂时不可用")
                if self.session is None:
                    raise WorkflowError("MCP 连接未建立，请恢复任务重试")
                response = await self.session.call_tool(name, args)
                if response.isError:
                    raise WorkflowError("MCP 工具参数或执行错误，请检查输入")
                payload = response.structuredContent or json.loads(
                    next(c.text for c in response.content if c.type == "text")
                )
                if not payload["ok"]:
                    raise WorkflowError(payload["error"], payload["kind"])
                if cacheable:
                    self.store.cache(key, payload["data"])
                self.store.event(self.task_id, "tool_completed", {"tool": name, "attempt": attempt + 1})
                return payload["data"]
            except Exception as exc:
                error = (
                    exc
                    if isinstance(exc, WorkflowError)
                    else WorkflowError(f"工具通信失败（{type(exc).__name__}）")
                )
                self.store.event(
                    self.task_id, "tool_failed", {"tool": name, "message": str(error), "attempt": attempt + 1}
                )
                if error.kind in {"materials", "permission"} or attempt == limits["tool_retries"]:
                    raise error
                await asyncio.sleep(min(attempt + 1, 2))
