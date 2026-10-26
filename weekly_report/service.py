from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from filelock import FileLock, Timeout
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from weekly_report.graph import build_graph, sha256_file
from weekly_report.mcp_client import MCPGateway
from weekly_report.schemas import EmployeeError, Review, TaskSpec
from weekly_report.settings import Settings
from weekly_report.store import Store, atomic_json, task_path


class EmployeeService:
    def __init__(self, settings=None, faults=None):
        self.settings = settings or Settings()
        self.store = Store(self.settings.data_dir)
        self.faults = faults or {}

    def save_input(self, task_id: str, role: str, filename: str, data: bytes):
        suffix = Path(filename).suffix.lower()
        allowed = {"sales": {".csv", ".xlsx"}, "minutes": {".docx", ".md", ".txt"}}
        if role not in allowed or suffix not in allowed[role]:
            raise ValueError("输入文件类型不支持")
        if not 0 < len(data) <= 20 * 1024 * 1024:
            raise ValueError("上传文件必须非空且不超过 20 MB")
        file = f"inputs/{role}-{hashlib.sha256(data).hexdigest()[:16]}{suffix}"
        path = task_path(self.settings.data_dir, task_id, file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return file

    def create(self, spec: TaskSpec, files=None):
        task_id = uuid.uuid4().hex
        inputs = {}
        for role, (filename, data) in (files or {}).items():
            inputs[role] = self.save_input(task_id, role, filename, data)
        initial = {
            "task_id": task_id,
            "spec": spec.model_dump(mode="json"),
            "employee": self.settings.employee(),
            "mode": self.settings.mode,
            "inputs": inputs,
            "status": "NEW",
            "version": 1,
            "qc_repairs": 0,
            "model_calls": 0,
            "model_failures": 0,
            "budget_id": uuid.uuid4().hex,
            "active_seconds": 0.0,
            "feedback": [],
            "quality_history": [],
            "review": {},
        }
        self.store.add_task(task_id, initial)
        atomic_json(task_path(self.settings.data_dir, task_id, "employee-snapshot.json"), initial["employee"])
        self.store.event(task_id, "created", {"spec": initial["spec"], "mode": initial["mode"]})
        return task_id

    def run(self, task_id):
        return self._locked(task_id, "run")

    def resume(self, task_id, files=None):
        return self._locked(task_id, "resume", files=files)

    def review(self, task_id, decision: Review):
        return self._locked(task_id, "review", review=decision)

    def _locked(self, task_id, action, **kwargs):
        directory = task_path(self.settings.data_dir, task_id)
        self.store.initial(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(directory / "task.lock", timeout=0):
                return asyncio.run(self._operate(task_id, action, **kwargs))
        except Timeout as exc:
            raise EmployeeError("任务正在执行，请等待当前操作完成") from exc

    def state(self, task_id):
        return asyncio.run(self._operate(task_id, "state"))

    async def _operate(self, task_id, action, files=None, review=None):
        initial = self.store.initial(task_id)
        if initial.get("mode") != "live" or self.store.is_archived(task_id):
            raise EmployeeError("该历史演示任务已停用，请上传真实资料创建新任务", "transition")
        task_settings = Settings(root=self.settings.root, data_dir=self.settings.data_dir)
        async with AsyncSqliteSaver.from_conn_string(
            str(self.settings.data_dir / "checkpoints.sqlite")
        ) as saver:
            async with MCPGateway(
                task_settings, self.store, task_id, initial["employee"], self.faults
            ) as gateway:
                graph = build_graph(task_settings, self.store, gateway, saver)
                config = {"configurable": {"thread_id": task_id}, "recursion_limit": 150}
                snapshot = await graph.aget_state(config)
                state = dict(snapshot.values) if snapshot.values else initial
                if action == "state":
                    return state
                command = None
                if action == "run":
                    if state["status"] in {"PAUSED", "REVIEW", "DELIVERED"}:
                        return state
                    command = None if snapshot.values else initial
                elif action == "resume":
                    if state["status"] != "PAUSED":
                        self._reject(task_id, "只有暂停的任务才能恢复")
                    updates = {
                        role: self.save_input(task_id, role, filename, data)
                        for role, (filename, data) in (files or {}).items()
                    }
                    command = Command(resume={"inputs": updates})
                elif action == "review":
                    if state["status"] != "REVIEW" or review.version != state["version"]:
                        self._reject(task_id, "当前任务不在待审核状态，或审核版本已过期")
                    if not state["quality"].get("passed"):
                        self._reject(task_id, "质检未通过，不能审核")
                    if (
                        review.decision == "approve"
                        and sha256_file(task_path(task_settings.data_dir, task_id, state["report_file"]))
                        != state["report_hash"]
                    ):
                        self._reject(task_id, "报告文件已被修改，请退回重新生成后审核")
                    command = Command(resume=review.model_dump())
                else:
                    raise ValueError("不支持的操作")
                await graph.ainvoke(command, config)
                result = await graph.aget_state(config)
                return dict(result.values)

    def _reject(self, task_id, message):
        self.store.event(task_id, "transition_rejected", {"message": message})
        raise EmployeeError(message, "transition")
