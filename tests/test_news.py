import httpx
import pytest

from report_agent import news
from report_agent.models import TaskSpec, WorkflowError


def test_no_keywords_never_search(monkeypatch):
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **k: pytest.fail("unexpected external request"))
    assert news.search_news({"year": 2025, "week": 1})["status"] == "skipped"


def test_missing_key(monkeypatch):
    monkeypatch.setattr(news, "dotenv_values", lambda *a, **k: {})
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert (
        news.search_news({"year": 2025, "week": 1, "news_queries": ["公开新闻"]})["status"] == "unavailable"
    )


def test_news_dates_and_bounds(monkeypatch):
    monkeypatch.setattr(news, "dotenv_values", lambda *a, **k: {"TAVILY_API_KEY": "unit-test-only"})
    calls = []

    def post(self, url, **kw):
        calls.append(kw["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "results": [
                    {
                        "url": "https://example.com/one",
                        "content": "原始摘录",
                        "published_date": "2025-01-01",
                        "title": "测试",
                    },
                    {
                        "url": "https://example.com/future",
                        "content": "future",
                        "published_date": "2026-01-01",
                    },
                    {"url": "https://example.com/unknown", "content": "unknown"},
                    {"url": "javascript:alert(1)", "content": "bad"},
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    r = news.search_news({"year": 2025, "week": 1, "news_queries": ["公开新闻", "公开新闻"]})
    assert len(calls) == 1 and calls[0]["end_date"] == "2025-01-05"
    assert [s["time_status"] for s in r["sources"]] == ["in_range", "out_of_range", "unknown"]
    assert all(s["verdict"] == "待人工核验" for s in r["sources"])
    state = {"minutes": {"sources": [{"id": "M001"}]}, "news": r}
    item = {
        "source_id": "M001",
        "verdict": "support",
        "citations": [{"source_id": "N001", "quote": "原始摘录"}],
    }
    news.validate_assessments({"news_assessments": [item]}, state)
    item["citations"][0]["quote"] = "编造"
    with pytest.raises(WorkflowError):
        news.validate_assessments({"news_assessments": [item]}, state)
    item["citations"] = [{"source_id": "N002", "quote": "future"}]
    with pytest.raises(WorkflowError):
        news.validate_assessments({"news_assessments": [item]}, state)
    item["citations"] = []
    with pytest.raises(WorkflowError):
        news.validate_assessments({"news_assessments": [item]}, state)


def test_search_failure_is_not_false_verdict(monkeypatch):
    monkeypatch.setattr(news, "dotenv_values", lambda *a, **k: {"TAVILY_API_KEY": "unit-test-only"})

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("private response")

    monkeypatch.setattr(httpx.Client, "post", fail)
    r = news.search_news({"year": 2025, "week": 1, "news_queries": ["公开新闻"]})
    assert r["status"] == "unavailable" and not r["sources"] and "private" not in str(r)


def test_query_limits():
    with pytest.raises(ValueError):
        TaskSpec(news_queries=["x"] * 4)
    with pytest.raises(ValueError):
        TaskSpec(news_queries=["x" * 161])


def test_bocha_response_mapping(monkeypatch):
    monkeypatch.setattr(
        news, "dotenv_values", lambda *a, **k: {"BOCHA_API_KEY": "unit-test-only", "NEWS_PROVIDER": "bocha"}
    )

    def post(self, url, **kw):
        assert url == "https://api.bocha.cn/v1/web-search"
        assert kw["json"]["freshness"] == "2024-11-30..2025-01-05"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "code": 200,
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "url": "https://example.com/a",
                                "name": "title",
                                "summary": "extract",
                                "datePublished": "2025-01-01T10:00:00+08:00",
                            }
                        ]
                    }
                },
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    r = news.search_news({"year": 2025, "week": 1, "news_queries": ["公开新闻"]})
    assert (
        r["provider"] == "bocha"
        and r["sources"][0]["excerpt"] == "extract"
        and r["sources"][0]["time_status"] == "in_range"
    )
