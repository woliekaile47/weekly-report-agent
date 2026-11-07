"""Bounded public-keyword search. Search snippets are leads, never proof of a claim."""

import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

from report_agent.config import ROOT


def validate_assessments(draft, state):
    """Citation/date integrity, not a semantic truth guarantee."""
    from report_agent.models import WorkflowError

    minutes = {s["id"] for s in state["minutes"]["sources"]}
    news = {s["id"]: s for s in state.get("news", {}).get("sources", [])}
    for item in draft.get("news_assessments", []):
        if item["source_id"] not in minutes:
            raise WorkflowError("新闻核验引用了不存在的纪要编号", "model")
        if item["verdict"] != "unverified" and not item["citations"]:
            raise WorkflowError("新闻核验结论缺少引用，不得认定支持或冲突", "model")
        for citation in item["citations"]:
            source = news.get(citation["source_id"])
            if not source or citation["quote"] not in source["excerpt"]:
                raise WorkflowError("新闻引用不存在或摘录不匹配", "model")
            if item["verdict"] != "unverified" and source["time_status"] != "in_range":
                raise WorkflowError("新闻日期不明或超出范围，只能标记无法核实", "model")


def attendee_names(sources):
    """Names listed in the attendance line and owner column of the minutes action table."""
    names, owner_column = set(), None
    for source in sources:
        text = source["text"]
        if re.match(r"\s*(参会人员|参会人|出席人员|出席)\s*[:：]", text):
            for part in re.split(r"[、，,；;：:]", re.sub(r"（[^）]*）|\([^)]*\)", "", text)):
                part = part.strip()
                if 2 <= len(part) <= 4 and part not in {"参会人员", "参会人", "出席人员", "出席", "记录"}:
                    names.add(part)
        cells = [c.strip() for c in text.split("|")]
        if "负责人" in cells:
            owner_column = cells.index("负责人")
        elif owner_column is not None and len(cells) > owner_column:
            names.update(n.strip() for n in re.split(r"[、，,/]", cells[owner_column]) if 2 <= len(n.strip()) <= 4)
    return names


def screen_queries(plan, minutes, metrics, blocked_terms=(), manual=(), limit=3):
    """Program gate for model-written queries: internal names and figures never reach the search provider."""
    sources = {s["id"]: s["text"] for s in minutes["sources"]}
    stores = [g["label"] for g in metrics["groups"] if g["dimension"] == "store"]
    terms = {*blocked_terms, *stores, *(s[:-1] for s in stores if s.endswith("店") and len(s) > 3)}
    names = attendee_names(minutes["sources"])
    items = [{"query": q.strip(), "source_id": "", "claim": "", "origin": "manual"} for q in manual if q.strip()]
    dropped = []
    for item in plan.get("queries", []):
        query = item["query"].strip()
        if item["source_id"] not in sources:
            reason = "引用了不存在的纪要编号"
        elif any(term and term in query for term in terms):
            reason = "包含门店或配置的内部词"
        elif any(name in query for name in names) or re.search(r"[\u4e00-\u9fff]某", query):
            reason = "包含人名"
        elif re.search(r"\d[\d,.]*\s*(?:元|万|%|％|笔|份)|\b[A-Z]{1,3}\d{2,}\b", query):
            reason = "包含金额、比例或内部编码"
        else:
            items.append({**item, "query": query, "origin": "auto"})
            continue
        dropped.append({"source_id": item["source_id"], "reason": reason})
    unique = list({item["query"]: item for item in items}.values())[:limit]
    return {"queries": [item["query"] for item in unique], "items": unique, "dropped": dropped}


def assign_regions(draft, minutes, metrics):
    """Attach each assessment to a report region using the cited minutes line, not the model's guess."""
    sources = {s["id"]: s["text"] for s in minutes["sources"]}
    regions = [g["label"] for g in metrics["groups"] if g["dimension"] == "region"]
    stores = {g["label"]: g.get("region") for g in metrics["groups"] if g["dimension"] == "store"}
    for item in draft.get("news_assessments", []):
        text = sources.get(item["source_id"], "")
        found = {r for r in regions if r in text} | {r for s, r in stores.items() if r and s in text}
        item["region"] = found.pop() if len(found) == 1 else "全公司"


def search_news(spec):
    queries = list(dict.fromkeys(q.strip() for q in spec.get("news_queries", []) if q.strip()))[:3]
    start = date.fromisocalendar(spec["year"], spec["week"], 1)
    end = start + timedelta(days=6)
    result = {
        "status": "skipped",
        "message": "本周纪要没有可对外核实的公开事项，未进行外部检索。",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "start_date": str(start - timedelta(days=30)),
        "end_date": str(end),
        "queries": queries,
        "sources": [],
        "errors": [],
    }
    if not queries:
        return result
    settings = dotenv_values(ROOT / ".env", interpolate=False)
    provider = settings.get("NEWS_PROVIDER") or os.getenv("NEWS_PROVIDER", "tavily")
    key_name = "BOCHA_API_KEY" if provider == "bocha" else "TAVILY_API_KEY"
    key = settings.get(key_name) or os.getenv(key_name)
    result["provider"] = provider
    if not key:
        return result | {"status": "unavailable", "message": "未配置新闻搜索密钥；纪要外部事实尚未核实。"}
    seen = set()
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        for query in queries:
            try:
                if provider == "bocha":
                    if query != queries[0]:
                        time.sleep(2.1)  # Tier 0: QPS 1, QPM 30; single task worker.
                    response = client.post(
                        "https://api.bocha.cn/v1/web-search",
                        headers={"Authorization": "Bearer " + key},
                        json={
                            "query": query,
                            "freshness": result["start_date"] + ".." + result["end_date"],
                            "summary": True,
                            "count": 5,
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
                    if body.get("code") not in (None, 200):
                        raise ValueError("provider rejected request")
                    rows = [
                        {
                            "url": r.get("url"),
                            "title": r.get("name"),
                            "content": r.get("summary") or r.get("snippet"),
                            "published_date": r.get("datePublished") or "",
                        }
                        for r in (body.get("data") or {}).get("webPages", {}).get("value", [])[:5]
                    ]
                else:
                    response = client.post(
                        "https://api.tavily.com/search",
                        headers={"Authorization": "Bearer " + key},
                        json={
                            "query": query,
                            "topic": "news",
                            "search_depth": "basic",
                            "max_results": 5,
                            "start_date": result["start_date"],
                            "end_date": result["end_date"],
                            "include_answer": False,
                            "include_raw_content": False,
                        },
                    )
                    response.raise_for_status()
                    rows = response.json().get("results", [])[:5]
                for row in rows:
                    url = row.get("url", "")
                    parsed = urlsplit(url)
                    if parsed.scheme not in {"http", "https"} or not parsed.hostname or url in seen:
                        continue
                    published = row.get("published_date") or ""
                    try:
                        try:
                            published_day = datetime.fromisoformat(published.replace("Z", "+00:00")).date()
                        except ValueError:
                            published_day = parsedate_to_datetime(published).date()
                        temporal = (
                            "in_range"
                            if start - timedelta(days=30) <= published_day <= end
                            else "out_of_range"
                        )
                    except (ValueError, TypeError, OverflowError):
                        temporal = "unknown"
                    seen.add(url)
                    result["sources"].append(
                        {
                            "id": f"N{len(seen):03}",
                            "query": query,
                            "title": str(row.get("title", ""))[:300],
                            "url": url,
                            "publisher": parsed.hostname,
                            "published_at": published,
                            "time_status": temporal,
                            "excerpt": str(row.get("content", ""))[:1500],
                            "verdict": "待人工核验",
                        }
                    )
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                result["errors"].append(
                    {"query": query, "message": "搜索失败或返回格式异常；未核实，不代表纪要错误。"}
                )
    result["status"] = "partial" if result["errors"] else "retrieved"
    if result["errors"] and not result["sources"]:
        result["status"] = "unavailable"
    result["message"] = (
        "搜索结果仅为待核验线索；须核对主体、事件和日期。未找到结果不代表纪要错误，新闻不能证明内部销售额或经营因果。"
    )
    return result
