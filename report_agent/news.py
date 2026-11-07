"""Bounded public-keyword search. Search snippets are leads, never proof of a claim."""

import os
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


def search_news(spec):
    queries = list(dict.fromkeys(q.strip() for q in spec.get("news_queries", []) if q.strip()))[:3]
    start = date.fromisocalendar(spec["year"], spec["week"], 1)
    end = start + timedelta(days=6)
    result = {
        "status": "skipped",
        "message": "未填写公开检索关键词，未进行新闻核验。",
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
