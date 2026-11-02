"""Adapted from invoice assistant's durable background-run / checkpoint approach (MIT)."""

from __future__ import annotations

import hashlib
import uuid

from filelock import FileLock, Timeout
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from report_agent.config import DATA, snapshot
from report_agent.documents import sha256
from report_agent.mcp_client import Gateway
from report_agent.model import generate
from report_agent.models import Review, TaskSpec, WorkflowError
from report_agent.store import Store, atomic_json, task_path
from report_agent.workflow import build_graph


class Service:
    def __init__(self, model=generate, faults=None):
        self.store = Store()
        self.model = model
        self.faults = faults or {}

    @staticmethod
    def validate_input(role, filename, size):
        from pathlib import Path

        suffix = Path(filename or "").suffix.lower()
        allowed = {"sales": {".xlsx", ".csv"}, "minutes": {".docx", ".md", ".txt"}, "master": {".xlsx"}}
        labels = {"sales": "销售明细", "minutes": "周会纪要", "master": "基础资料"}
        if role not in allowed or suffix not in allowed[role]:
            raise WorkflowError(f"{labels.get(role, '上传')}文件类型不支持", "materials")
        if size <= 0:
            raise WorkflowError(f"{labels[role]}文件为空", "materials")
        if size > 20 * 1024 * 1024:
            raise WorkflowError(f"{labels[role]}文件超过20MB，请选择更小的文件", "materials")

    def save_input(self, task_id, role, filename, content):
        from pathlib import Path

        self.validate_input(role, filename, len(content))
        suffix = Path(filename).suffix.lower()
        relative = f"inputs/{role}-{hashlib.sha256(content).hexdigest()[:16]}{suffix}"
        target = task_path(task_id, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return relative

    def create(self, spec, files=None, import_options=None):
        spec = TaskSpec.model_validate(spec).model_dump()
        task_id = uuid.uuid4().hex
        inputs = {
            role: self.save_input(task_id, role, name, data) for role, (name, data) in (files or {}).items()
        }
        state = {
            "task_id": task_id,
            "spec": spec,
            "bundle": snapshot(),
            "inputs": inputs,
            "import_options": import_options or {},
            "status": "pending",
            "route": "ingest",
            "version": 1,
            "repairs": 0,
            "model_calls": 0,
            "model_failures": 0,
            "budget_id": uuid.uuid4().hex,
            "active_seconds": 0,
            "feedback": [],
            "quality_history": [],
            "approval": {},
        }
        self.store.save(task_id, state)
        atomic_json(task_path(task_id, "configuration.json"), state["bundle"])
        self.store.event(task_id, "created", {"spec": spec, "configuration": state["bundle"]["version"]})
        return task_id

    async def state(self, task_id):
        initial = self.store.get(task_id)
        async with AsyncSqliteSaver.from_conn_string(str(DATA / "checkpoints.sqlite")) as saver:
            graph = build_graph(self.store, None, saver, self.model)
            checkpoint = await graph.aget_state({"configurable": {"thread_id": task_id}})
            result = dict(checkpoint.values) if checkpoint.values else initial
            result["next_nodes"] = list(checkpoint.next)
            return result

    async def operate(
        self,
        task_id,
        action="run",
        review=None,
        files=None,
        handler="",
        note="",
        spec=None,
        import_options=None,
    ):
        directory = task_path(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        lock = FileLock(directory / "run.lock", timeout=0)
        try:
            lock.acquire()
        except Timeout as exc:
            raise WorkflowError("任务正在执行，请等待当前操作完成", "transition") from exc
        try:
            state = await self.state(task_id)
            if action == "run":
                if state["status"] in {"paused", "awaiting_human", "completed"}:
                    return state
                command = state if not state.get("next_nodes") else None
            elif action in {"resume", "recheck"}:
                if state["status"] != "paused" and not (
                    action == "recheck" and state["status"] == "awaiting_human"
                ):
                    raise WorkflowError("只有已暂停任务可以恢复", "transition")
                if state.get("error_kind") == "budget" and (not handler.strip() or not note.strip()):
                    raise WorkflowError("超限恢复必须填写处理人和处理意见", "transition")
                updates = {
                    role: self.save_input(task_id, role, name, data)
                    for role, (name, data) in (files or {}).items()
                }
                if action == "recheck" and not state.get("draft"):
                    raise WorkflowError("没有可复检的草稿", "transition")
                payload = {
                    "inputs": updates,
                    "handler": handler.strip(),
                    "note": note.strip(),
                    "recheck": action == "recheck",
                }
                if spec is not None:
                    payload["spec"] = TaskSpec.model_validate(spec).model_dump()
                if import_options is not None:
                    payload["import_options"] = import_options
                command = Command(resume=payload)
            elif action == "review":
                decision = Review.model_validate(review)
                if (
                    state["status"] != "awaiting_human"
                    or state["version"] != decision.version
                    or not state["quality"]["passed"]
                ):
                    raise WorkflowError("任务不在待审核状态或审核版本已过期", "transition")
                if (
                    decision.decision == "approve"
                    and sha256(task_path(task_id, state["artifact"]["file"])) != state["artifact"]["sha256"]
                ):
                    raise WorkflowError("报告文件已修改，请退回重新生成后审核", "transition")
                command = Command(resume=decision.model_dump())
            else:
                raise ValueError("未知操作")
            self.store.event(task_id, "operation_started", {"action": action})
            async with AsyncSqliteSaver.from_conn_string(str(DATA / "checkpoints.sqlite")) as saver:
                async with Gateway(self.store, task_id, state["bundle"], self.faults) as gateway:
                    # Own all AnyIO contexts in this parent task, not individual LangGraph node tasks.
                    await gateway.connect()
                    graph = build_graph(self.store, gateway, saver, self.model)
                    config = {"configurable": {"thread_id": task_id}, "recursion_limit": 120}
                    async for event in graph.astream(command, config, stream_mode="updates"):
                        checkpoint = await graph.aget_state(config)
                        current = dict(checkpoint.values) if checkpoint.values else state
                        self.store.save(task_id, current)
                        for node, output in event.items():
                            if node == "__interrupt__":
                                self.store.event(task_id, "interrupt", {"status": current["status"]})
                            elif isinstance(output, dict):
                                self.store.event(
                                    task_id,
                                    "node",
                                    {
                                        "node": node,
                                        "status": current["status"],
                                        "version": current["version"],
                                    },
                                )
                    result = await graph.aget_state(config)
                    values = dict(result.values)
                    self.store.save(task_id, values)
                    return values
        except WorkflowError as exc:
            self.store.event(task_id, "operation_rejected", {"message": str(exc), "kind": exc.kind})
            raise
        finally:
            lock.release()
