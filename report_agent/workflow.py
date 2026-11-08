"""Adapted from manuelbomi/Invoice-Receipt-Audit... graph.py and nodes.py (a0a0fc5, MIT).

Original explicit StateGraph + mandatory interrupt gate retained. Scenario nodes,
bounded repair/rework, illegal-transition rejection and persistent budgets added.
GenSlide's approve/revise routing is adapted to a strict versioned approval gate.
"""

from __future__ import annotations

import asyncio
import time
import uuid
import zipfile
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from report_agent.data_tools import change_exceeds
from report_agent.documents import sha256
from report_agent.model import generate, ground_dates, plan_queries
from report_agent.models import Review, WorkflowError
from report_agent.news import screen_queries
from report_agent.rework import changed_inputs, merge_revision, plan_rework, register_review, verify_revisions
from report_agent.store import atomic_json, digest, task_path


class ReportState(TypedDict, total=False):
    task_id: str
    spec: dict
    bundle: dict
    inputs: dict
    import_options: dict
    status: str
    route: str
    current_node: str
    resume_node: str
    reason: str
    error_kind: str
    sales: dict
    news: dict
    metrics: dict
    minutes: dict
    draft: dict
    artifact: dict
    quality: dict
    quality_history: list
    feedback: list
    approval: dict
    version: int
    repairs: int
    model_calls: int
    model_failures: int
    budget_id: str
    active_seconds: float
    delivery: str
    rework_plan: dict
    revision_items: list
    revision_ledger: dict
    draft_baseline: dict
    render_options: dict
    layout_attempts: int
    work_items: list


def build_graph(store, gateway, checkpointer, model=generate, planner=None):
    # Test model replacements must never reach the real planner.
    planner = planner or (plan_queries if model is generate else None)

    def wrap(name, fn):
        async def node(state):
            started = time.monotonic()
            limits = state["bundle"]["employee"]["limits"]
            startup = getattr(gateway, "startup_seconds", 0)
            if gateway is not None:
                gateway.startup_seconds = 0
            store.event(state["task_id"], "node_started", {"node": name, "version": state["version"]})
            try:
                if state.get("status") not in {"pending", "running", "approved"}:
                    raise WorkflowError("非法状态，拒绝继续执行", "transition")
                remaining = limits["active_seconds"] - state.get("active_seconds", 0) - startup
                if remaining <= 0:
                    raise WorkflowError("活动执行时长达到上限，已暂停转人工处理", "budget")
                update = await asyncio.wait_for(fn(state), timeout=remaining)
            except Exception as exc:
                if isinstance(exc, asyncio.TimeoutError):
                    exc = WorkflowError("活动执行时长达到上限，已暂停转人工处理", "budget")
                error = (
                    exc
                    if isinstance(exc, WorkflowError)
                    else WorkflowError(f"步骤 {name} 失败（{type(exc).__name__}），已保存进度")
                )
                update = {
                    "status": "paused",
                    "route": "pause",
                    "resume_node": name,
                    "reason": str(error),
                    "error_kind": error.kind,
                }
                if name == "analyze" and error.kind == "model":
                    failures = state.get("model_failures", 0) + 1
                    update["model_failures"] = failures
                    if failures <= limits["tool_retries"]:
                        update.update(status="running", route="analyze")
                store.event(
                    state["task_id"], "node_failed", {"node": name, "message": str(error), "kind": error.kind}
                )
            elapsed = state.get("active_seconds", 0) + startup + time.monotonic() - started
            calls = sum(
                e["kind"] == "model_started" and e["payload"].get("budget_id") == state["budget_id"]
                for e in store.events(state["task_id"])
            )
            update.update(active_seconds=elapsed, model_calls=calls, current_node=name)
            store.event(
                state["task_id"],
                "node_completed",
                {"node": name, "status": update.get("status", state["status"]), "version": state["version"], "duration_seconds": startup + time.monotonic() - started},
            )
            return update

        return node

    async def ingest(s):
        if not s["inputs"].get("sales"):
            raise WorkflowError("缺少销售明细，请补充 Excel 或 CSV", "materials")
        result = await gateway.call(
            "read_sales",
            {
                "task_id": s["task_id"],
                "file": s["inputs"]["sales"],
                "columns": s["bundle"]["columns"],
                "options": s.get("import_options", {}),
                "master_file": s["inputs"].get("master") or "",
            },
        )
        return {"sales": result, "status": "running", "route": "calculate"}

    async def calculate(s):
        business = s["bundle"]["employee"]["business"]
        metrics = await gateway.call(
            "compute_metrics",
            {
                "task_id": s["task_id"],
                "sales": s["sales"],
                "spec": s["spec"],
                "threshold": business["anomaly_percent"],
                "delivery_channel": s["bundle"]["columns"]["delivery_channel"],
                "margin_drop_points": business.get("margin_drop_points", 5),
            },
        )
        return {"metrics": metrics, "route": "evidence"}

    async def evidence(s):
        if not s["inputs"].get("minutes"):
            raise WorkflowError("缺少本周周会纪要，请补充后继续", "materials")
        minutes = await gateway.call(
            "read_minutes", {"task_id": s["task_id"], "file": s["inputs"]["minutes"]}
        )
        if minutes.get("year") != s["spec"]["year"] or minutes.get("week") != s["spec"]["week"]:
            raise WorkflowError(
                f"纪要为 {minutes.get('year') or '未知年份'} 年第 {minutes['week'] or '未知'} 周，"
                f"任务是 {s['spec']['year']} 年第 {s['spec']['week']} 周，请修正周期或替换纪要",
                "materials",
            )
        metrics = dict(s["metrics"])
        business = s["bundle"]["employee"]["business"]
        conflicts = []
        for g in metrics["groups"]:
            if g["dimension"] != "region" or g["change"] is None:
                continue
            for source in minutes["sources"]:
                if (
                    g["label"] in source["text"]
                    and any(p in source["text"] for p in business["flat_phrases"])
                    and change_exceeds(g["cents"], g["previous_cents"], business["flat_tolerance_percent"])
                ):
                    conflicts.append(
                        {
                            "region": g["label"],
                            "metric_id": g["id"],
                            "source_id": source["id"],
                            "claim": source["text"],
                            "instruction": "指出纪要与系统环比不一致，以数据为准",
                        }
                    )
        metrics["expected_conflicts"] = conflicts
        work_items = [
            {"id": "core", "label": "公司、区域核心指标及品类与前五单品", "kind": "metrics"},
            *(
                {"id": g["id"], "label": g["label"] + "异常原因与证据", "kind": "anomaly"}
                for g in metrics["anomalies"]
            ),
            *(
                {
                    "id": "conflict-" + c["metric_id"],
                    "label": c["region"] + "纪要与指标冲突",
                    "kind": "conflict",
                }
                for c in conflicts
            ),
            {"id": "data-quality", "label": "退货、重复记录及无记录日说明", "kind": "data_quality"},
        ]
        return {"minutes": minutes, "metrics": metrics, "work_items": work_items, "route": "news"}

    async def news(s):
        employee = s["bundle"]["employee"]
        if "search_news" not in employee["allowed_tools"]:
            result = {"status": "skipped", "message": "此任务旧配置未启用新闻工具，未进行外部核验", "sources": []}
            store.event(s["task_id"], "news_retrieved", {"status": result["status"], "count": 0})
            return {"news": result, "route": "analyze"}
        manual = s["spec"].get("news_queries", [])
        plan_key = digest({"sources": s["minutes"]["sources"], "manual": manual, "spec": [s["spec"]["year"], s["spec"]["week"]]})
        # Rework and resume reuse the same search: unchanged minutes mean no new provider calls.
        cached = s.get("news", {})
        if cached.get("plan_key") == plan_key and cached.get("status") in {"retrieved", "skipped"} and not cached.get("errors"):
            return {"route": "analyze"}
        candidates, plan_error = {"queries": []}, ""
        if planner:
            try:
                candidates = await planner(s, store)
            except WorkflowError as exc:
                if exc.kind in {"rate_limit", "budget", "configuration"}:
                    raise
                # Only recoverable planning failures may degrade to no external check.
                plan_error = str(exc)
        search = employee.get("search", {})
        screened = screen_queries(
            candidates, s["minutes"], s["metrics"], search.get("blocked_terms", []), manual, search.get("max_queries", 3)
        )
        store.event(s["task_id"], "search_planned", {**screened, "error": plan_error})
        result = await gateway.call("search_news", {"spec": {**s["spec"], "news_queries": screened["queries"]}})
        if plan_error and not screened["queries"]:
            result["status"] = "plan_failed"
            result["message"] = "未能自动生成检索词，本周未做外部核对；销售分析不受影响。原因：" + plan_error
        result = {**result, "plan": screened, "plan_key": plan_key}
        store.event(s["task_id"], "news_retrieved", {"status": result["status"], "count": len(result["sources"])})
        return {"news": result, "route": "analyze"}

    async def analyze(s):
        draft = await model(s, store)
        return {"draft": merge_revision(s, draft), "model_failures": 0, "route": "render"}

    async def rework(s):
        plan = plan_rework(s)
        store.event(s["task_id"], "rework_planned", plan)
        update = {
            "rework_plan": plan,
            "route": plan["route"],
            "approval": {},
            "artifact": {},
            "delivery": "",
            "draft_baseline": s.get("draft") or s.get("draft_baseline", {}),
        }
        if "layout" in plan["categories"]:
            update["render_options"] = s["bundle"]["employee"].get("rework", {}).get("compact_layout", {})
            update["layout_attempts"] = s.get("layout_attempts", 0) + 1
            if set(plan["categories"]) == {"layout"} and s.get("feedback"):
                update["draft"] = {
                    **s["draft"],
                    "review_response": "已按审核意见调整版式，逐项检查结果见修改台账。",
                }
        if plan["route"] == "ingest":
            update.update(
                status="paused",
                route="pause",
                resume_node="ingest",
                error_kind="materials",
                reason="数据或统计口径需核实，请补充销售材料、基础资料，或修正周期和字段映射后恢复",
            )
        return update

    async def render(s):
        from datetime import date, timedelta

        metrics = {**s["metrics"], "tokens": dict(s["metrics"]["tokens"])}
        if "category_margins" not in metrics:
            business = s["bundle"]["employee"]["business"]
            refreshed = await gateway.call(
                "compute_metrics",
                {
                    "task_id": s["task_id"],
                    "sales": s["sales"],
                    "spec": s["spec"],
                    "threshold": business["anomaly_percent"],
                    "delivery_channel": s["bundle"]["columns"]["delivery_channel"],
                    "margin_drop_points": business.get("margin_drop_points", 5),
                },
            )
            metrics = {**refreshed, "expected_conflicts": metrics.get("expected_conflicts", [])}
        metrics["tokens"].setdefault("year", str(s["spec"]["year"]))
        metrics["tokens"].setdefault(
            "next_week",
            f"第{(date.fromisocalendar(s['spec']['year'], s['spec']['week'], 1) + timedelta(days=7)).isocalendar().week}周",
        )
        s = {**s, "metrics": metrics}
        s = {**s, "draft": ground_dates(s["draft"], s)}
        artifact = await gateway.call(
            "generate_report",
            {
                **{
                    k: s[k]
                    for k in ("task_id", "version", "metrics", "minutes", "draft", "bundle", "feedback")
                },
                "render_options": s.get("render_options", {}),
                "news": s.get("news", {}),
            },
        )
        return {"artifact": artifact, "draft": s["draft"], "metrics": metrics, "route": "quality"}

    async def quality(s):
        result = await gateway.call(
            "inspect_report",
            {k: s[k] for k in ("task_id", "artifact", "metrics", "minutes", "draft", "bundle", "feedback")},
        )
        result = await page_inspection(s, result)
        items, ledger, revision_check = verify_revisions(s, result)
        result["checks"].append(revision_check)
        result["passed"] = all(c["passed"] for c in result["checks"])
        base = task_path(s["task_id"], s["artifact"]["file"]).parent
        atomic_json(base / "quality.json", result)
        atomic_json(base / "revisions.json", {"items": items, "ledger": ledger})
        history = s.get("quality_history", []) + [{"version": s["version"], **result}]
        store.event(s["task_id"], "quality", result)
        common = {
            "quality": result,
            "quality_history": history,
            "revision_items": items,
            "revision_ledger": ledger,
        }
        if result["passed"]:
            return {
                **common,
                "status": "awaiting_human",
                "route": "human_review",
                "reason": "",
                "error_kind": "",
            }
        if s.get("repairs", 0) < s["bundle"]["employee"]["limits"]["quality_repairs"]:
            return {
                **common,
                "repairs": s.get("repairs", 0) + 1,
                "route": "rework",
                "version": s["version"] + 1,
            }
        return {
            **common,
            "status": "paused",
            "route": "pause",
            "resume_node": "rework",
            "reason": "质检修正达到上限仍未通过，请核实记录后人工处理",
            "error_kind": "quality",
        }

    async def pause(s):
        reply = interrupt({"kind": "pause", "reason": s["reason"], "node": s["resume_node"]})
        update = {
            "status": "approved" if s["resume_node"] == "finalize" else "running",
            "route": s["resume_node"],
            "reason": "",
            "error_kind": "",
            "budget_id": uuid.uuid4().hex,
            "active_seconds": 0,
            "model_calls": 0,
            "repairs": 0,
            "model_failures": 0,
            "approval": s.get("approval", {}) if s["resume_node"] == "finalize" else {},
        }
        changes = {}
        if reply.get("recheck"):
            update.update(
                route="render",
                version=s["version"] + 1,
                repairs=s["bundle"]["employee"]["limits"]["quality_repairs"],
                approval={},
            )
        for key in ("spec", "import_options"):
            if key in reply and reply[key] != s.get(key):
                changes[key] = reply[key]
        update.update(changed_inputs(s, reply))
        if s.get("error_kind") == "quality" and not reply.get("recheck"):
            update.setdefault("version", s["version"] + 1)
        store.event(
            s["task_id"],
            "resumed",
            {
                "handler": reply.get("handler", ""),
                "note": reply.get("note", ""),
                "changed": changes,
                "inputs": list(reply.get("inputs", {})),
                "previous_reason": s.get("reason"),
                "previous_budget_id": s["budget_id"],
            },
        )
        return update

    async def human_review(s):
        reply = interrupt(
            {"kind": "review", "version": s["version"], "artifact": s["artifact"], "quality": s["quality"]}
        )
        if reply.get("recheck"):
            store.event(
                s["task_id"],
                "recheck_requested",
                {"previous_version": s["version"], "note": reply.get("note", "")},
            )
            return {
                "status": "running",
                "route": "render",
                "version": s["version"] + 1,
                "repairs": s["bundle"]["employee"]["limits"]["quality_repairs"],
                "approval": {},
                "budget_id": uuid.uuid4().hex,
                "active_seconds": 0,
                "model_calls": 0,
            }
        decision = Review.model_validate(reply).model_dump()
        if decision["version"] != s["version"] or not s["quality"]["passed"]:
            raise WorkflowError("审核版本过期或质检未通过", "transition")
        store.event(s["task_id"], "human_review", decision)
        if decision["decision"] == "revise":
            return {
                "status": "running",
                "route": "rework",
                "feedback": s["feedback"] + [decision],
                "revision_items": register_review(s, decision),
                "draft_baseline": s.get("draft", {}),
                "quality": {},
                "layout_attempts": 0,
                "version": s["version"] + 1,
                "repairs": 0,
                "budget_id": uuid.uuid4().hex,
                "active_seconds": 0,
                "model_calls": 0,
                "model_failures": 0,
                "approval": {},
            }
        return {
            "status": "approved",
            "route": "finalize",
            "approval": {**decision, "sha256": s["artifact"]["sha256"]},
            "budget_id": uuid.uuid4().hex,
            "active_seconds": 0,
            "model_calls": 0,
        }

    async def finalize(s):
        artifact = s["artifact"]
        path = task_path(s["task_id"], artifact["file"])
        if (
            not s["quality"]["passed"]
            or s.get("approval", {}).get("decision") != "approve"
            or s["approval"]["version"] != s["version"]
            or s["approval"]["sha256"] != sha256(path)
        ):
            raise WorkflowError("当前成果与批准版本不一致，拒绝交付", "transition")
        base = task_path(s["task_id"], f"delivery/v{s['version']}")
        base.mkdir(parents=True, exist_ok=True)
        atomic_json(base / "质检记录.json", s["quality_history"])
        atomic_json(base / "审核记录.json", {"feedback": s["feedback"], "approval": s["approval"]})
        atomic_json(
            base / "逐项修改记录.json",
            {"items": s.get("revision_items", []), "ledger": s.get("revision_ledger", {})},
        )
        atomic_json(base / "配置快照.json", s["bundle"])
        atomic_json(base / "指标与材料来源.json", s["metrics"])
        atomic_json(base / "完整纪要原文.json", s["minutes"])
        atomic_json(base / "新闻核验线索.json", {"search": s.get("news", {"status": "not_run"}), "model_assessments": s["draft"].get("news_assessments", []), "notice": "模型判断仅供人工核验"})
        atomic_json(base / "执行事件.json", store.events(s["task_id"]))
        atomic_json(
            base / "交付清单.json",
            {
                "task_id": s["task_id"],
                "version": s["version"],
                "report_sha256": artifact["sha256"],
                "inputs": s["inputs"],
            },
        )
        reasons = s["bundle"]["employee"]["limit_reasons"]
        (base / "执行限制说明.md").write_text(
            "# 执行限制与理由\n\n"
            + "\n".join(
                f"- {key}: {s['bundle']['employee']['limits'][key]}；{reason}"
                for key, reason in reasons.items()
            )
            + "\n\n每次请求含失败计数。超限暂停并需处理人和意见；人工等待不计时，明确恢复后开启新预算。",
            encoding="utf-8",
        )
        archive = base.parent / f"经营周报-v{s['version']}.zip"
        tmp = archive.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(path, "经营周报.docx")
            for p in sorted(base.iterdir()):
                z.write(p, p.name)
        tmp.replace(archive)
        return {
            "status": "completed",
            "route": "end",
            "delivery": str(archive.relative_to(task_path(s["task_id"]))).replace("\\", "/"),
        }

    builder = StateGraph(ReportState)
    operations = {
        "ingest": ingest,
        "calculate": calculate,
        "evidence": evidence,
        "news": news,
        "analyze": analyze,
        "render": render,
        "quality": quality,
        "rework": rework,
        "finalize": finalize,
    }
    for name, fn in operations.items():
        builder.add_node(name, wrap(name, fn))
    builder.add_node("pause", pause)
    builder.add_node("human_review", human_review)
    routes = {name: name for name in [*operations, "pause", "human_review"]}
    routes["end"] = END
    for name in [*operations, "pause", "human_review"]:
        builder.add_conditional_edges(name, lambda state: state["route"], routes)
    builder.add_edge(START, "ingest")
    return builder.compile(checkpointer=checkpointer)


async def page_inspection(state, result):
    from report_agent.render_worker import inspect_pages

    audit = await inspect_pages(
        task_path(state["task_id"], state["artifact"]["file"]),
        state["bundle"]["employee"]["limits"]["tool_timeout_seconds"],
    )
    quality = state["bundle"]["employee"]["quality"]
    result = {
        **result,
        "checks": [
            *result["checks"],
            {
                "name": "Word实际页数",
                "passed": audit.get("body_pages", audit.get("pages", 999)) <= quality["max_pages"]
                and audit.get("pages", 999) <= quality.get("max_total_pages", quality["max_pages"]),
                "details": audit.get("details", ""),
            },
        ],
        "page_audit": audit,
    }
    result["passed"] = all(c["passed"] for c in result["checks"])
    atomic_json(task_path(state["task_id"], state["artifact"]["file"]).parent / "quality.json", result)
    return result
