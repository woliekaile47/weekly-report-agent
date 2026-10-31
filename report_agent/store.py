from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone

from report_agent.config import DATA


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def task_path(task_id, relative=""):
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise ValueError("无效任务编号")
    base = (DATA / "tasks" / task_id).resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValueError("文件路径越界")
    return target


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dumps(value), encoding="utf-8")
    tmp.replace(path)


class Store:
    def __init__(self):
        self.path = DATA / "tasks.sqlite"
        with self.db() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, created TEXT, state TEXT); CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,time TEXT,kind TEXT,payload TEXT); CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,value TEXT);"
            )

    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def save(self, task_id, state):
        with self.db() as db:
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (task_id, datetime.now(timezone.utc).isoformat(), dumps(state)),
            )

    def get(self, task_id):
        task_path(task_id)
        with self.db() as db:
            row = db.execute("SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("任务不存在")
        return json.loads(row[0])

    def list(self):
        with self.db() as db:
            return [
                {
                    "id": i,
                    "created": c,
                    "title": (s := json.loads(raw))["spec"]["title"],
                    "status": s["status"],
                    "week": s["spec"]["week"],
                }
                for i, c, raw in db.execute("SELECT id,created,state FROM tasks ORDER BY created DESC")
            ]

    def event(self, task_id, kind, payload):
        safe = re.sub(r"sk-[A-Za-z0-9_-]+", "[已隐藏]", dumps(payload))
        with self.db() as db:
            db.execute(
                "INSERT INTO events(task_id,time,kind,payload) VALUES(?,?,?,?)",
                (task_id, datetime.now(timezone.utc).isoformat(), kind, safe),
            )

    def events(self, task_id, after=0):
        with self.db() as db:
            return [
                {"seq": seq, "time": t, "kind": k, "payload": json.loads(p)}
                for seq, t, k, p in db.execute(
                    "SELECT seq,time,kind,payload FROM events WHERE task_id=? AND seq>? ORDER BY seq",
                    (task_id, after),
                )
            ]

    def cached(self, key):
        with self.db() as db:
            row = db.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES(?,?)", (key, dumps(value)))
