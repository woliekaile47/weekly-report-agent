"""REST/background/SSE adapter derived from invoice assistant runs.py (a0a0fc5, MIT).

Changes: local SQLite instead of Postgres/SQLAlchemy; durable cursor replay instead
of a single-consumer queue; strict report-version guards; no demo/auto-approval API.
"""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import set_key
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictInt

from report_agent.config import ROOT, connection, snapshot, validate_files
from report_agent.models import Review, TaskSpec, WorkflowError
from report_agent.service import Service
from report_agent.store import task_path

app = FastAPI(title="经营周报员工", version="2.0")
service = Service()
tasks = {}


def _sse(event_type, data, seq=None):
    return (
        f"id: {seq}\n" if seq is not None else ""
    ) + f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def public(state):
    from report_agent.documents import report_quality_notes

    result = {k: v for k, v in state.items() if k not in {"bundle"}} | {
        "limits": state["bundle"]["employee"]["limits"],
        "config_version": state["bundle"]["version"],
        "model": connection()["LLM_MODEL"],
        "worker_active": state["task_id"] in tasks and not tasks[state["task_id"]].done(),
    }
    if state.get("metrics") and state.get("draft"):
        result["report_quality_notes"] = report_quality_notes(state["metrics"], state["draft"])
    return result


async def get_state(task_id):
    try:
        return await service.state(task_id)
    except (ValueError, WorkflowError) as exc:
        raise HTTPException(404, str(exc)) from exc


def start(task_id, **kwargs):
    if task_id in tasks and not tasks[task_id].done():
        raise HTTPException(409, "任务正在执行")

    async def worker():
        try:
            await service.operate(task_id, **kwargs)
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, (WorkflowError, ValueError))
                else f"执行进程中断（{type(exc).__name__}），可从已保存检查点继续"
            )
            service.store.event(task_id, "worker_error", {"message": message})

    tasks[task_id] = asyncio.create_task(worker())


async def read_uploads(**files):
    values = {}
    for role, file in files.items():
        if file is None:
            continue
        content = await file.read(20 * 1024 * 1024 + 1)
        service.validate_input(role, file.filename, len(content))
        values[role] = (file.filename, content)
    return values


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0"}


@app.get("/api/runs")
def list_runs():
    return {"runs": service.store.list()}


@app.post("/api/runs")
async def create(
    spec: str = Form(...),
    sales: UploadFile | None = File(None),
    minutes: UploadFile | None = File(None),
    master: UploadFile | None = File(None),
    import_options: str = Form("{}"),
):
    try:
        values = await read_uploads(sales=sales, minutes=minutes, master=master)
        task_id = service.create(TaskSpec.model_validate_json(spec), values, json.loads(import_options))
        start(task_id)
        return {"id": task_id, "status": "pending"}
    except (ValueError, WorkflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/runs/{task_id}")
async def detail(task_id: str):
    return public(await get_state(task_id))


@app.post("/api/runs/{task_id}/resume")
async def resume(
    task_id: str,
    spec: str = Form(""),
    import_options: str = Form(""),
    handler: str = Form(""),
    note: str = Form(""),
    sales: UploadFile | None = File(None),
    minutes: UploadFile | None = File(None),
    master: UploadFile | None = File(None),
    remove_master: bool = Form(False),
):
    state = await get_state(task_id)
    if state["status"] not in {"paused", "running", "pending", "approved"}:
        raise HTTPException(409, "当前状态不允许恢复")
    if state.get("error_kind") == "budget" and (not handler.strip() or not note.strip()):
        raise HTTPException(422, "超限恢复须填写处理人及意见")
    try:
        if remove_master and master is not None:
            raise WorkflowError("不能同时移除和上传基础资料，请只选择一种操作", "materials")
        revised = TaskSpec.model_validate_json(spec).model_dump() if spec else None
        options = json.loads(import_options) if import_options else None
        files = await read_uploads(sales=sales, minutes=minutes, master=master)
        start(
            task_id,
            action="resume" if state["status"] == "paused" else "run",
            spec=revised,
            import_options=options,
            handler=handler,
            note=note,
            files=files,
            remove_master=remove_master,
        )
        return {"id": task_id, "status": "running"}
    except (ValueError, WorkflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/runs/{task_id}/review")
async def review(task_id: str, decision: Review):
    state = await get_state(task_id)
    if state["status"] != "awaiting_human" or decision.version != state["version"]:
        raise HTTPException(409, "任务不在待审核状态或版本过期")
    if not state["quality"]["passed"]:
        raise HTTPException(409, "质检未通过")
    from report_agent.documents import sha256

    if (
        decision.decision == "approve"
        and sha256(task_path(task_id, state["artifact"]["file"])) != state["artifact"]["sha256"]
    ):
        raise HTTPException(409, "报告已改变，请退回重新生成")
    start(task_id, action="review", review=decision.model_dump())
    return {"id": task_id, "status": "running"}


@app.post("/api/runs/{task_id}/recheck")
async def recheck(task_id: str):
    state = await get_state(task_id)
    if (
        state["status"] not in {"paused", "awaiting_human"}
        or not state.get("draft")
        or state.get("error_kind") == "budget"
    ):
        raise HTTPException(409, "当前任务不可直接复检；超限请填写处理记录后恢复")
    start(task_id, action="recheck", note="用户明确复检现有草稿，不调用模型")
    return {"id": task_id, "status": "running"}


@app.get("/api/runs/{task_id}/events")
async def events(task_id: str, after: int = 0):
    await get_state(task_id)
    return {"events": service.store.events(task_id, after)}


@app.get("/api/runs/{task_id}/stream")
async def stream(task_id: str, request: Request):
    await get_state(task_id)

    async def event_source():
        cursor = int(request.headers.get("last-event-id", "0"))
        state = await get_state(task_id)
        yield _sse(
            "replay",
            {"status": state["status"], "state_snapshot": public(state), "trace": [], "final_status": None},
        )
        while not await request.is_disconnected():
            batch = service.store.events(task_id, cursor)
            for e in batch:
                cursor = e["seq"]
                yield _sse("audit", e, cursor)
                if e["kind"] == "node":
                    state = await get_state(task_id)
                    yield _sse(
                        "node",
                        {
                            "node": e["payload"]["node"],
                            "output": public(state),
                            "trace": [
                                {
                                    "node": e["payload"]["node"],
                                    "timestamp": e["time"],
                                    "summary": e["payload"]["status"],
                                }
                            ],
                        },
                    )
            state = await get_state(task_id)
            active = task_id in tasks and not tasks[task_id].done()
            if not active:
                if state["status"] == "awaiting_human":
                    yield _sse("interrupt", {"kind": "review", "version": state["version"]})
                yield _sse("done", {"status": state["status"], "final_status": None})
                return
            if not batch:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.6)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/runs/{task_id}/download/{kind}")
async def download(task_id: str, kind: str):
    state = await get_state(task_id)
    if kind == "package":
        if state["status"] != "completed":
            raise HTTPException(409, "审核通过并交付后才可下载正式交付包")
        file = state["delivery"]
    elif kind in {"docx", "pdf"}:
        if not state.get("artifact"):
            raise HTTPException(404, "暂无成果")
        file = state["artifact"]["file"]
        if kind == "pdf":
            file = str(Path(file).with_suffix(".pdf"))
    else:
        raise HTTPException(404, "未知文件")
    path = task_path(task_id, file)
    if not path.is_file():
        raise HTTPException(404, "文件尚未生成")
    return FileResponse(path, filename=path.name)


INPUT_LABELS = {"sales": "销售明细", "minutes": "周会纪要", "master": "基础资料"}


@app.get("/api/runs/{task_id}/files")
async def files(task_id: str):
    """Expose only files owned by this checkpoint, not an arbitrary directory listing."""
    state = await get_state(task_id)
    items = []
    for role, label in INPUT_LABELS.items():
        relative = state.get("inputs", {}).get(role)
        if not relative:
            continue
        path = task_path(task_id, relative)
        if path.is_file():
            items.append(
                {
                    "id": role,
                    "name": label + path.suffix,
                    "bytes": path.stat().st_size,
                    "kind": "input",
                    "url": f"/api/runs/{task_id}/input/{role}",
                }
            )
    artifact = state.get("artifact") or {}
    if artifact.get("file"):
        for kind, suffix in (("docx", ".docx"), ("pdf", ".pdf")):
            path = task_path(task_id, artifact["file"]).with_suffix(suffix)
            if path.is_file():
                items.append(
                    {
                        "id": kind,
                        "name": "经营周报" + suffix,
                        "bytes": path.stat().st_size,
                        "kind": "artifact",
                        "url": f"/api/runs/{task_id}/download/{kind}",
                    }
                )
    if state["status"] == "completed" and state.get("delivery"):
        path = task_path(task_id, state["delivery"])
        if path.is_file():
            items.append(
                {
                    "id": "package",
                    "name": "正式交付包.zip",
                    "bytes": path.stat().st_size,
                    "kind": "artifact",
                    "url": f"/api/runs/{task_id}/download/package",
                }
            )
    return {"files": items, "version": state["version"]}


@app.get("/api/runs/{task_id}/input/{role}")
async def download_input(task_id: str, role: str):
    state = await get_state(task_id)
    if role not in INPUT_LABELS or not state.get("inputs", {}).get(role):
        raise HTTPException(404, "材料不存在")
    path = task_path(task_id, state["inputs"][role])
    if not path.is_file():
        raise HTTPException(404, "材料文件不可用")
    return FileResponse(path, filename=INPUT_LABELS[role] + path.suffix)


@app.get("/api/config")
def get_config():
    bundle = snapshot()
    c = connection()
    return {
        "files": bundle["files"],
        "version": bundle["version"],
        "employee": bundle["employee"],
        "connection": {k: v for k, v in c.items() if k != "LLM_API_KEY"},
        "key_configured": bool(c["LLM_API_KEY"]),
    }


class ConfigUpdate(BaseModel):
    version: str
    files: dict[str, str]


class LimitsUpdate(BaseModel):
    version: str
    model_calls: StrictInt
    model_timeout_seconds: StrictInt
    active_seconds: StrictInt


@app.put("/api/limits")
def save_limits(body: LimitsUpdate):
    from filelock import FileLock

    values = {
        "model_calls": body.model_calls,
        "model_timeout_seconds": body.model_timeout_seconds,
        "active_seconds": body.active_seconds,
    }
    if any(type(value) is not int or value < 1 for value in values.values()):
        raise HTTPException(422, "执行上限须为大于零的整数")
    with FileLock(ROOT / "config/edit.lock", timeout=3):
        old = snapshot()
        if old["version"] != body.version:
            raise HTTPException(409, "配置已更新，请刷新再编辑")
        path = ROOT / "config/employee.yaml"
        original = old["files"]["config/employee.yaml"]
        head, marker, tail = original.partition("limits:\n")
        limits, next_marker, rest = tail.partition("limit_reasons:\n")
        if not marker or not next_marker:
            raise HTTPException(422, "限制配置格式无法识别，请在员工配置中编辑")
        for key, value in values.items():
            pattern = rf"(?m)^([ \t]+{re.escape(key)}:[ \t]*)\d+([ \t]*(?:#.*)?)$"
            limits, count = re.subn(pattern, lambda match: f"{match[1]}{value}{match[2]}", limits)
            if count != 1:
                raise HTTPException(422, f"限制配置 {key} 无法定位，请在员工配置中编辑")
        updated = head + marker + limits + next_marker + rest
        try:
            path.write_text(updated, encoding="utf-8")
            new = snapshot()
        except Exception as exc:
            path.write_text(original, encoding="utf-8")
            raise HTTPException(422, "执行上限无效，已还原") from exc
    return {"version": new["version"], "limits": new["employee"]["limits"]}


@app.put("/api/config")
def save_config(body: ConfigUpdate):
    from filelock import FileLock

    with FileLock(ROOT / "config/edit.lock", timeout=3):
        old = snapshot()
        if old["version"] != body.version:
            raise HTTPException(409, "配置已更新，请刷新再编辑")
        if set(body.files) != set(old["files"]):
            raise HTTPException(422, "只能修改已公开的配置文件")
        try:
            validate_files(body.files)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, f"配置无效：{exc}") from exc
        try:
            for name, content in body.files.items():
                (ROOT / name).write_text(content, encoding="utf-8")
            new = snapshot()
        except Exception as exc:
            for name, content in old["files"].items():
                (ROOT / name).write_text(content, encoding="utf-8")
            raise HTTPException(422, f"配置保存失败，已还原：{exc}") from exc
    return {"version": new["version"]}


class ConnectionUpdate(BaseModel):
    base_url: str
    model: str
    api_key: str = ""
    max_tokens: int = 6000
    reasoning_effort: str = ""


@app.put("/api/connection")
def save_connection(body: ConnectionUpdate):
    url = urlsplit(body.base_url)
    current = connection()
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not body.model.strip()
        or not 128 <= body.max_tokens <= 32000
        or body.reasoning_effort not in {"", "low", "medium", "high"}
    ):
        raise HTTPException(422, "接口地址或生成参数无效")
    if url.netloc != urlsplit(current["LLM_BASE_URL"]).netloc and not body.api_key.strip():
        raise HTTPException(422, "更换服务地址时请填写对应密钥")
    values = {
        "LLM_BASE_URL": body.base_url.rstrip("/"),
        "LLM_MODEL": body.model.strip(),
        "LLM_MAX_TOKENS": str(body.max_tokens),
        "LLM_REASONING_EFFORT": body.reasoning_effort,
    }
    if body.api_key.strip():
        values["LLM_API_KEY"] = body.api_key.strip()
    for key, val in values.items():
        set_key(str(ROOT / ".env"), key, val)
    return {"saved": True}


@app.post("/api/connection/test")
async def test_connection():
    c = connection()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                c["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + c["LLM_API_KEY"]},
                json={
                    "model": c["LLM_MODEL"],
                    "messages": [{"role": "user", "content": "请只回复：连接正常"}],
                    "max_tokens": 64,
                },
            )
        return {
            "ok": r.status_code == 200,
            "status_code": r.status_code,
            "message": "接口已返回响应" if r.status_code == 200 else "接口不可用，请检查额度、模型或网络",
        }
    except httpx.HTTPError:
        return {"ok": False, "message": "连接超时或网络不可用；未自动重试"}


dist = ROOT / "frontend/dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def index(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})
