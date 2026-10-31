import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import timedelta

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

    async def __aenter__(self):
        return self

    async def connect(self):
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
        key = digest(
            {
                "revision": 2,
                "task": self.task_id,
                "name": name,
                "args": args,
                "bundle": self.bundle["version"],
            }
        )
        cached = self.store.cached(key)
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
                await self.connect()
                response = await self.session.call_tool(name, args)
                if response.isError:
                    raise WorkflowError("MCP 工具参数或执行错误，请检查输入")
                payload = response.structuredContent or json.loads(
                    next(c.text for c in response.content if c.type == "text")
                )
                if not payload["ok"]:
                    raise WorkflowError(payload["error"], payload["kind"])
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
