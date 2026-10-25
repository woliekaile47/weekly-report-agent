from __future__ import annotations

import asyncio
import hashlib
import shutil
import time
import uuid
import zipfile
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from weekly_report.model import generate
from weekly_report.schemas import EmployeeError, Review
from weekly_report.store import atomic_json, digest, task_path


class State(TypedDict, total=False):
    task_id: str
    spec: dict
    employee: dict
    mode: str
    inputs: dict
    status: str
    route: str
    resume_node: str
    resume_status: str
    reason: str
    error_kind: str
    sales: dict
    minutes: dict
    metrics: dict
    draft: dict
    artifact_id: str
    chart_file: str
    report_file: str
    report_hash: str
    quality: dict
    quality_history: list
    feedback: list
    review: dict
    version: int
    qc_repairs: int
    model_calls: int
    model_failures: int
    budget_id: str
    active_seconds: float
    delivery: str


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_graph(settings, store, gateway, checkpointer):
    def wrap(name, function):
        async def node(state):
            started = time.monotonic()
            limits = state["employee"]["limits"]
            budget_id = state.get("budget_id", state["task_id"])
            prior_events = store.events(state["task_id"])
            call_count = sum(
                e["kind"] == "model_started" and e["payload"].get("budget_id") == budget_id
                for e in prior_events
            )
            try:
                if state["status"] not in {"NEW", "RUNNING", "REWORK", "APPROVED"}:
                    raise EmployeeError("非法状态流转，执行已停止", "transition")
                if state.get("active_seconds", 0) >= limits["active_seconds"]:
                    raise EmployeeError("活动执行时间达到上限，需人工检查后恢复", "budget")
                if name == "draft":
                    if call_count >= limits["model_calls"]:
                        raise EmployeeError("模型调用轮次达到上限，需人工检查后恢复", "budget")
                    call_count += 1
                    store.event(
                        state["task_id"],
                        "model_started",
                        {
                            "round": call_count,
                            "mode": state["mode"],
                            "version": state["version"],
                            "budget_id": budget_id,
                        },
                    )
                remaining = limits["active_seconds"] - state.get("active_seconds", 0)
                deadline = min(remaining, limits["model_timeout_seconds"]) if name == "draft" else remaining
                update = await asyncio.wait_for(function(state), timeout=deadline)
                if update.get("status") != "PAUSED":
                    update.setdefault("reason", "")
                    update.setdefault("error_kind", "")
                if name == "draft":
                    store.event(state["task_id"], "model_completed", {"round": call_count})
                    update["model_failures"] = 0
            except Exception as exc:
                if isinstance(exc, asyncio.TimeoutError):
                    exc = (
                        EmployeeError("模型调用超时，已保存进度，可稍后重试")
                        if name == "draft" and remaining >= limits["model_timeout_seconds"]
                        else EmployeeError("执行达到时长上限，已暂停", "budget")
                    )
                message = (
                    str(exc)
                    if isinstance(exc, EmployeeError)
                    else f"步骤 {name} 执行失败（{type(exc).__name__}），请检查后重试"
                )
                update = {
                    "status": "PAUSED",
                    "route": "pause",
                    "resume_node": name,
                    "resume_status": "APPROVED" if name == "deliver" else "RUNNING",
                    "reason": message,
                    "error_kind": getattr(exc, "kind", "execution"),
                }
                store.event(state["task_id"], "step_failed", {"step": name, "message": message})
                if name == "draft" and getattr(exc, "kind", "execution") == "execution":
                    failures = state.get("model_failures", 0) + 1
                    update["model_failures"] = failures
                    if failures <= limits.get("model_retries", 2) and call_count < limits["model_calls"]:
                        update.update({"status": "RUNNING", "route": "draft"})
                        await asyncio.sleep(min(failures, 2))
            update["model_calls"] = call_count
            update["active_seconds"] = state.get("active_seconds", 0) + time.monotonic() - started
            store.event(
                state["task_id"],
                "state",
                {
                    "step": name,
                    "from": state["status"],
                    "to": update.get("status", state["status"]),
                    "version": state["version"],
                },
            )
            return update

        return node

    async def admit(s):
        missing = [
            label
            for key, label in [("sales", "销售数据"), ("minutes", "周会纪要")]
            if not s["inputs"].get(key)
        ]
        if missing:
            raise EmployeeError("请补充：" + "、".join(missing), "materials")
        return {"status": "RUNNING", "route": "read_sales", "reason": "", "error_kind": ""}

    async def sales(s):
        value = await gateway.call(
            "read_sales",
            {
                "task_id": s["task_id"],
                "file": s["inputs"]["sales"],
                "aliases": s["employee"]["column_aliases"],
            },
        )
        return {"sales": value, "route": "read_minutes"}

    async def minutes(s):
        value = await gateway.call("read_minutes", {"task_id": s["task_id"], "file": s["inputs"]["minutes"]})
        return {"minutes": value, "route": "metrics"}

    async def metrics(s):
        value = await gateway.call(
            "compute_metrics",
            {
                "sales": s["sales"],
                "spec": s["spec"],
                "threshold": s["employee"]["quality"]["anomaly_percent"],
            },
        )
        return {"metrics": value, "route": "draft"}

    async def draft(s):
        value = await generate(settings, s)
        artifact_id = f"v{s['version']}-{digest(value)[:12]}"
        atomic_json(task_path(settings.data_dir, s["task_id"], f"artifacts/{artifact_id}/draft.json"), value)
        return {"draft": value, "artifact_id": artifact_id, "status": "RUNNING", "route": "charts"}

    async def charts(s):
        result = await gateway.call(
            "render_charts",
            {"task_id": s["task_id"], "artifact_id": s["artifact_id"], "metrics": s["metrics"]},
        )
        return {"chart_file": result["file"], "route": "report"}

    async def report(s):
        args = {
            key: s[key]
            for key in (
                "task_id",
                "artifact_id",
                "chart_file",
                "spec",
                "metrics",
                "minutes",
                "draft",
                "version",
                "mode",
                "feedback",
            )
        }
        result = await gateway.call("build_report", args)
        return {"report_file": result["file"], "route": "quality"}

    async def quality(s):
        args = {key: s[key] for key in ("task_id", "report_file", "draft", "metrics", "minutes", "feedback")}
        args["quality"] = s["employee"]["quality"]
        result = await gateway.call("inspect_report", args)
        history = s.get("quality_history", []) + [
            {"version": s["version"], "artifact_id": s["artifact_id"], **result}
        ]
        store.event(s["task_id"], "quality", {"version": s["version"], **result})
        base = {"quality": result, "quality_history": history}
        if result["passed"]:
            return {
                **base,
                "status": "REVIEW",
                "route": "review",
                "report_hash": sha256_file(task_path(settings.data_dir, s["task_id"], s["report_file"])),
            }
        if s["qc_repairs"] < s["employee"]["limits"]["qc_repairs"]:
            return {**base, "qc_repairs": s["qc_repairs"] + 1, "route": "draft"}
        return {
            **base,
            "status": "PAUSED",
            "route": "pause",
            "resume_node": "draft",
            "resume_status": "RUNNING",
            "reason": "自动质检在修正后仍未通过，请检查质检记录并人工处理",
            "error_kind": "quality",
        }

    async def pause(s):
        reply = interrupt({"kind": "pause", "reason": s["reason"], "step": s["resume_node"]})
        inputs = reply.get("inputs", {})
        update = {
            "status": s.get("resume_status", "RUNNING"),
            "route": s["resume_node"],
            "model_calls": 0,
            "model_failures": 0,
            "budget_id": uuid.uuid4().hex,
            "active_seconds": 0.0,
            "qc_repairs": 0,
            "reason": "",
            "error_kind": "",
        }
        if inputs:
            update.update(
                {
                    "inputs": {**s["inputs"], **inputs},
                    "route": "admit",
                    "status": "RUNNING",
                    "sales": {},
                    "minutes": {},
                    "metrics": {},
                    "draft": {},
                    "quality": {},
                    "report_file": "",
                    "report_hash": "",
                    "review": {},
                    "version": s["version"] + (1 if s.get("report_file") else 0),
                }
            )
        store.event(s["task_id"], "resumed", {"step": update["route"], "inputs_replaced": list(inputs)})
        return update

    async def review(s):
        reply = interrupt(
            {
                "kind": "review",
                "version": s["version"],
                "report_file": s["report_file"],
                "quality": s["quality"],
            }
        )
        decision = Review.model_validate(reply).model_dump()
        if decision["version"] != s["version"] or not s["quality"]["passed"]:
            raise EmployeeError("审核版本不匹配或质检未通过", "transition")
        store.event(
            s["task_id"], "review", decision, key=f"review:{s['task_id']}:{s['version']}:{s['report_hash']}"
        )
        if decision["decision"] == "reject":
            return {
                "status": "REWORK",
                "route": "draft",
                "feedback": s["feedback"] + [decision],
                "version": s["version"] + 1,
                "qc_repairs": 0,
                "active_seconds": 0.0,
                "model_calls": 0,
                "model_failures": 0,
                "budget_id": uuid.uuid4().hex,
                "review": {},
                "report_hash": "",
            }
        return {
            "status": "APPROVED",
            "route": "deliver",
            "review": {**decision, "report_hash": s["report_hash"]},
            "active_seconds": 0.0,
            "model_calls": 0,
            "budget_id": uuid.uuid4().hex,
        }

    async def deliver(s):
        review_record = s.get("review", {})
        report_path = task_path(settings.data_dir, s["task_id"], s["report_file"])
        if (
            not s["quality"].get("passed")
            or review_record.get("decision") != "approve"
            or review_record.get("version") != s["version"]
            or review_record.get("report_hash") != sha256_file(report_path)
        ):
            raise EmployeeError("当前报告与已审核版本不一致，拒绝交付；请重新生成并审核", "transition")
        base = task_path(settings.data_dir, s["task_id"], f"delivery/v{s['version']}")
        base.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report_path, base / "经营周报.docx")
        atomic_json(base / "质检记录.json", s["quality_history"])
        atomic_json(base / "审核记录.json", {"history": s["feedback"], "approval": review_record})
        atomic_json(
            base / "交付清单.json",
            {
                "task_id": s["task_id"],
                "version": s["version"],
                "skill_version": s["employee"]["version"],
                "model_mode": s["mode"],
                "report_sha256": s["report_hash"],
                "inputs": s["inputs"],
            },
        )
        store.event(
            s["task_id"],
            "delivered",
            {"version": s["version"]},
            key=f"delivery:{s['task_id']}:{s['version']}",
        )
        atomic_json(base / "执行记录.json", store.events(s["task_id"]))
        target = base.parent / f"经营周报-v{s['version']}.zip"
        temporary = target.with_suffix(".tmp.zip")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as package:
            for file in sorted(base.iterdir()):
                package.write(file, file.name)
        temporary.replace(target)
        return {
            "status": "DELIVERED",
            "route": "end",
            "delivery": str(target.relative_to(task_path(settings.data_dir, s["task_id"]))).replace(
                "\\", "/"
            ),
        }

    graph = StateGraph(State)
    operations = {
        "admit": admit,
        "read_sales": sales,
        "read_minutes": minutes,
        "metrics": metrics,
        "draft": draft,
        "charts": charts,
        "report": report,
        "quality": quality,
        "deliver": deliver,
    }
    for name, operation in operations.items():
        graph.add_node(name, wrap(name, operation))
    graph.add_node("pause", pause)
    graph.add_node("review", review)
    routes = {name: name for name in [*operations, "pause", "review"]}
    routes["end"] = END
    for name in [*operations, "pause", "review"]:
        graph.add_conditional_edges(name, lambda state: state["route"], routes)
    graph.add_edge(START, "admit")
    return graph.compile(checkpointer=checkpointer)
