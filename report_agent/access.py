"""Public deployment access boundary; disabled for the local desktop workflow."""

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse, RedirectResponse

from report_agent.config import DATA

ENABLED = os.getenv("REPORT_PUBLIC") == "1"
KEY = os.getenv("REPORT_SESSION_SECRET", "")
PASSWORD = os.getenv("REPORT_ADMIN_PASSWORD", "")
COOKIE = "report_session"


@contextmanager
def db():
    c = sqlite3.connect(DATA / "access.sqlite", timeout=10)
    c.executescript(
        "CREATE TABLE IF NOT EXISTS owners(task TEXT PRIMARY KEY, owner TEXT); CREATE TABLE IF NOT EXISTS quota(day TEXT, bucket TEXT, count INTEGER, PRIMARY KEY(day,bucket));"
    )
    try:
        with c:
            yield c
    finally:
        c.close()


def sign(identity):
    value = f"{identity}.{int(time.time())}"
    return value + "." + hmac.new(KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def identity(token):
    try:
        who, stamp, signature = token.split(".")
        expected = hmac.new(KEY.encode(), f"{who}.{stamp}".encode(), hashlib.sha256).hexdigest()
        age = time.time() - int(stamp)
        if hmac.compare_digest(expected, signature) and 0 <= age < (28800 if who == "admin" else 2592000):
            return who
    except (ValueError, AttributeError):
        pass
    return None


def claim(task, owner):
    if ENABLED:
        with db() as c:
            c.execute("INSERT INTO owners VALUES (?,?)", (task, owner))


def owned(task, owner):
    with db() as c:
        return bool(c.execute("SELECT 1 FROM owners WHERE task=? AND owner=?", (task, owner)).fetchone())


def consume(buckets):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        day = time.strftime("%Y-%m-%d", time.gmtime())
        for bucket, limit in buckets:
            row = c.execute("SELECT count FROM quota WHERE day=? AND bucket=?", (day, bucket)).fetchone()
            if row and row[0] >= limit:
                return False
        for bucket, _ in buckets:
            c.execute(
                "INSERT INTO quota VALUES (?,?,1) ON CONFLICT(day,bucket) DO UPDATE SET count=count+1",
                (day, bucket),
            )
    return True


def install(app):
    if not ENABLED:
        return
    if len(KEY) < 32 or len(PASSWORD) < 16:
        raise RuntimeError("Public deployment requires a session secret (32+ characters) and admin password (16+ characters)")

    mutation_lock = asyncio.Lock()

    @app.middleware("http")
    async def access(request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/runs"):
            async with mutation_lock:
                return await dispatch(request, call_next)
        return await dispatch(request, call_next)

    async def dispatch(request, call_next):
        path = request.url.path
        who = identity(request.cookies.get(COOKIE))
        fresh = who is None
        who = who or secrets.token_hex(24)
        request.state.owner = who
        admin = who == "admin"

        def error(code, message):
            return JSONResponse({"detail": message}, status_code=code)

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and urlsplit(origin).netloc != request.headers.get("host")) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return error(403, "不允许跨站操作")
        if path == "/admin":
            try:
                scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
                user, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
                valid = scheme.lower() == "basic" and user == "admin" and secrets.compare_digest(password.encode(), PASSWORD.encode())
            except (ValueError, UnicodeError):
                valid = False
            if not valid:
                return JSONResponse({"detail": "需要管理员登录"}, status_code=401, headers={"WWW-Authenticate": 'Basic realm="Report admin"'})
            response = RedirectResponse("/")
            response.set_cookie(COOKIE, sign("admin"), httponly=True, secure=True, samesite="strict", max_age=28800)
            return response
        if path in {"/docs", "/redoc", "/openapi.json"} and not admin:
            return error(404, "页面不存在")
        if path == "/api/session":
            response = JSONResponse({"admin": admin, "public": True})
        else:
            if path.startswith(("/api/config", "/api/connection", "/api/limits")) and not admin:
                return error(403, "仅管理员可修改全局配置")
            if path.startswith("/api/runs/"):
                parts = path.split("/")
                task = parts[3]
                if not admin and not owned(task, who):
                    return error(404, "任务不存在")
            if request.method == "POST" and path.startswith("/api/runs"):
                from report_agent.api import tasks

                if sum(not t.done() for t in tasks.values()) >= 1:
                    return error(429, "服务器正在处理一份周报，请稍后重试")
            response = await call_next(request)
        if fresh:
            response.set_cookie(
                COOKIE, sign(who), httponly=True, secure=True, samesite="strict", max_age=2592000
            )
        return response
