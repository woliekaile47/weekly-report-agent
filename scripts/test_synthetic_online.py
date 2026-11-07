import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/synthetic-2025"
results = []
with httpx.Client(base_url="https://wlklqnz.xyz", timeout=45) as c:
    c.get("/api/session")
    for week in [40, 11, 25]:
        folder = OUT / f"live-W{week}"
        folder.mkdir(exist_ok=True)
        minutes = (OUT / f"纪要_2025W{week:02}.txt").read_text(encoding="utf-8")
        if week == 40:
            minutes += "\n待核验公开说法（故意错误测试）：2025年国庆中秋全国放假从10月1日至7日，共7天。\n"
        spec = {
            "year": 2025,
            "week": week,
            "title": f"模拟年度W{week}联网验收",
            "news_queries": ["2025 国庆 中秋 放假 通知 国务院"] if week == 40 else [],
        }
        r = c.post(
            "/api/runs",
            data={"spec": json.dumps(spec)},
            files={
                "sales": ("sim.xlsx", (OUT / "模拟年度2025.xlsx").read_bytes()),
                "minutes": ("minutes.txt", minutes.encode()),
            },
        )
        r.raise_for_status()
        tid = r.json()["id"]
        print("Created", week, tid, flush=True)
        for i in range(150):
            s = c.get("/api/runs/" + tid).json()
            if i % 12 == 0:
                print(week, s.get("status"), s.get("current_node"), flush=True)
            if not s.get("worker_active") and s.get("status") in ["paused", "awaiting_human", "completed"]:
                break
            time.sleep(4)
        else:
            raise TimeoutError(tid)
        (folder / "state.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "events.json").write_text(
            json.dumps(c.get("/api/runs/" + tid + "/events").json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if s["status"] == "awaiting_human":
            c.post(
                "/api/runs/" + tid + "/review",
                json={
                    "decision": "approve",
                    "reviewer": "模拟数据自动化验收（非业务审批）",
                    "version": s["version"],
                    "feedback": "仅用于验证测试交付",
                },
            ).raise_for_status()
            for _ in range(30):
                s = c.get("/api/runs/" + tid).json()
                if not s.get("worker_active"):
                    break
                time.sleep(2)
        for f in c.get("/api/runs/" + tid + "/files").json()["files"]:
            resp = c.get(f["url"])
            resp.raise_for_status()
            (folder / f["name"]).write_bytes(resp.content)
        item = {
            "week": week,
            "id": tid,
            "status": s["status"],
            "reason": s.get("reason"),
            "news_status": s.get("news", {}).get("status"),
            "news_sources": len(s.get("news", {}).get("sources", [])),
            "assessments": s.get("draft", {}).get("news_assessments", []),
        }
        results.append(item)
        print(item, flush=True)
        (OUT / "live-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
