from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def json_text(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def digest(value):
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def redact(value):
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", json_text(value))


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "tasks.sqlite"
        directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, initial TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    time TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    event_key TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS tool_cache (
                    key TEXT PRIMARY KEY, result TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS archived_tasks (
                    task_id TEXT PRIMARY KEY, reason TEXT NOT NULL
                );
            """)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def add_task(self, task_id, initial):
        with self.connect() as db:
            db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?)",
                (task_id, datetime.now(timezone.utc).isoformat(), json_text(initial)),
            )

    def initial(self, task_id):
        with self.connect() as db:
            row = db.execute("SELECT initial FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("任务不存在")
        return json.loads(row[0])

    def tasks(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, created, initial FROM tasks WHERE id NOT IN "
                "(SELECT task_id FROM archived_tasks) ORDER BY created DESC"
            ).fetchall()
        return [
            {"id": i, "created": c, "title": json.loads(s)["spec"]["title"]}
            for i, c, s in rows
            if json.loads(s).get("mode") == "live"
        ]

    def archive(self, task_id, reason):
        self.initial(task_id)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO archived_tasks VALUES(?,?)", (task_id, reason))

    def is_archived(self, task_id):
        with self.connect() as db:
            return (
                db.execute("SELECT 1 FROM archived_tasks WHERE task_id=?", (task_id,)).fetchone() is not None
            )

    def event(self, task_id, kind, payload, key=None):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO events(task_id,time,kind,payload,event_key) VALUES(?,?,?,?,?)",
                (task_id, datetime.now(timezone.utc).isoformat(), kind, redact(payload), key),
            )

    def events(self, task_id):
        with self.connect() as db:
            rows = db.execute(
                "SELECT seq,time,kind,payload FROM events WHERE task_id=? ORDER BY seq", (task_id,)
            ).fetchall()
        return [{"seq": i, "time": t, "kind": k, "payload": json.loads(p)} for i, t, k, p in rows]

    def cached(self, key):
        with self.connect() as db:
            row = db.execute("SELECT result FROM tool_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key, result):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO tool_cache VALUES(?,?)", (key, json_text(result)))


def task_path(directory: Path, task_id: str, relative="") -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise ValueError("非法任务标识")
    base = (directory / "tasks" / task_id).resolve()
    result = (base / relative).resolve()
    if not result.is_relative_to(base):
        raise ValueError("文件路径超出当前任务范围")
    return result


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json_text(value), encoding="utf-8")
    temp.replace(path)
