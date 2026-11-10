import asyncio
import json
from pathlib import Path

import httpx
import pytest
from docx import Document
from langgraph.checkpoint.memory import InMemorySaver

from report_agent import documents, model
from report_agent.documents import anomaly_groups, reader_text
from report_agent.news import assign_regions, attendee_names, screen_queries
from report_agent.workflow import build_graph

MINUTES = {
    "sources": [
        {"id": "M001", "text": "参会人员：王某（运营总监，主持）、张伟（华东区域经理）；记录：吴某（行政）"},
        {"id": "M002", "text": "1. 华东（张伟）：杭州湖滨店停业三天，国庆放假七天。"},
        {"id": "M003", "text": "2. 华南（陈某）：活动结束。"},
        {"id": "M004", "text": "行政提醒：11 月上旬市场监管部门将开展消防检查。"},
        {"id": "M005", "text": "事项 | 负责人 | 截止日期"},
        {"id": "M006", "text": "活动方案 | 李娜 | 11/03"},
    ]
}
METRICS = {
    "week": 44,
    "tokens": {"g0_change": "-12.0%", "g0_change_abs": "12.0%", "g1_change_abs": "12.7%"},
    "groups": [
        {"id": "g0", "label": "华东", "dimension": "region", "region": "华东", "cents": 100, "change": -12.0, "target_rate": 84.1, "anomaly": True},
        {"id": "g1", "label": "华南", "dimension": "region", "region": "华南", "cents": 100, "change": -12.7, "target_rate": 92.3, "anomaly": True},
        {"id": "g4", "label": "杭州湖滨店", "dimension": "store", "region": "华东", "cents": 100, "change": -38.3, "anomaly": True},
    ],
}
METRICS["anomalies"] = list(METRICS["groups"])


def query(text, source="M004"):
    return {"query": text, "source_id": source, "claim": ""}


def test_screen_blocks_internal_terms_and_keeps_public_queries():
    plan = {
        "queries": [
            query("杭州湖滨店 消防改造"),
            query("杭州湖滨 商场 消防改造"),
            query("青禾烘焙 竞品"),
            query("张伟 华东"),
            query("李娜 活动"),
            query("王某 华东"),
            query("华东 实收 197618 元"),
            query("促销 12.7%"),
            query("公开事项", "M999"),
            query("2026 市场监管 消防检查 通知"),
        ]
    }
    result = screen_queries(plan, MINUTES, METRICS, ["青禾"])
    assert result["queries"] == ["2026 市场监管 消防检查 通知"]
    assert len(result["dropped"]) == 9


def test_screen_puts_manual_first_and_caps_total():
    plan = {"queries": [query(f"公开事项{i}") for i in "ABCD"]}
    result = screen_queries(plan, MINUTES, METRICS, manual=["手动 关键词", "手动 关键词"])
    assert result["queries"] == ["手动 关键词", "公开事项A", "公开事项B"]
    assert [i["origin"] for i in result["items"]] == ["manual", "auto", "auto"]


def test_attendee_names_reads_attendance_and_owner_column():
    assert {"王某", "张伟", "李娜"} <= attendee_names(MINUTES["sources"])


def test_regions_come_from_cited_minutes_line():
    draft = {"news_assessments": [{"source_id": "M002"}, {"source_id": "M004"}]}
    assign_regions(draft, MINUTES, METRICS)
    assert [i["region"] for i in draft["news_assessments"]] == ["华东", "全公司"]


def test_reader_text_hides_internal_codes():
    text = reader_text("华南（g1）：纪要 M003 称持平，下降 {{g1_change_abs}} [M003]。", METRICS["tokens"], 44)
    assert text == "华南：第44周纪要称持平，下降 12.7%（第44周纪要）。"
    kept = reader_text("纪要称持平 [M008]，系统实收下降 {{g1_change_abs}}。", METRICS["tokens"], 44)
    assert kept == "纪要称持平（第44周纪要），系统实收下降 12.7%。"
    merged = reader_text("李某提交方案 [M030]、[M031]。", {}, 44)
    assert merged == "李某提交方案（第44周纪要）。"


def test_external_finding_sits_under_its_region_and_never_carries_figures():
    draft = {
        "anomalies": [
            {"metric_id": "g4", "reason": "停业三天", "uncertain": False, "evidence": [{"source_id": "M002", "quote": "停业"}]},
            {"metric_id": "g0", "reason": "门店停业", "uncertain": False, "evidence": []},
            {"metric_id": "g1", "reason": "未提及", "uncertain": True, "evidence": []},
        ],
        "conflicts": ["华南：纪要称持平 [M003]，以系统数据为准。"],
        "news_assessments": [
            {"source_id": "M002", "region": "华东", "verdict": "conflict", "explanation": "通知写明放假8天", "citations": [{"source_id": "N001", "quote": "x"}]},
            {"source_id": "M004", "region": "全公司", "verdict": "support", "explanation": "公开通知提到消防检查", "citations": []},
            {"source_id": "M003", "region": "华南", "verdict": "unverified", "explanation": "无法核实", "citations": []},
        ],
    }
    news = {"sources": [{"id": "N001", "publisher": "gov.cn"}]}
    groups = {g["region"]: g["rows"] for g in anomaly_groups(METRICS, draft, news)}
    assert [r["label"] for r in groups["华东"]] == ["区域整体", "杭州湖滨店", "外部信息"]
    assert groups["华东"][1]["text"] == "停业三天（第44周纪要）。"
    external = groups["华东"][-1]["text"]
    assert external == "外部资料与纪要不符：详情见附录（来源：gov.cn）"
    assert [r["kind"] for r in groups["华南"]] == ["anomaly", "conflict"]
    assert groups["华南"][0]["text"].startswith("原因待核实：")
    assert groups["全公司"][0]["text"] == "外部资料与纪要相符：公开通知提到消防检查"


def test_plan_query_uses_budget_and_validates(monkeypatch):
    class Store:
        events_list = []

        def events(self, task_id):
            return self.events_list

        def event(self, task_id, kind, payload):
            self.events_list.append({"kind": kind, "payload": payload})

    captured = {}

    async def post(self, url, **kw):
        captured.update(kw["json"])
        body = {"queries": [{"query": "2026 消防检查 通知", "source_id": "M004", "claim": "检查是否存在"}]}
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(body, ensure_ascii=False)}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(
        model,
        "connection",
        lambda: {"LLM_API_KEY": "unit-test-only", "LLM_BASE_URL": "https://x", "LLM_MODEL": "m", "LLM_TEMPERATURE": "0", "LLM_MAX_TOKENS": "100"},
    )
    state = {
        "task_id": "t",
        "budget_id": "b",
        "spec": {"year": 2026, "week": 44},
        "minutes": MINUTES,
        "bundle": {"skill": "SKILL", "employee": {"limits": {"model_calls": 8, "model_timeout_seconds": 5}}},
    }
    store = Store()
    plan = asyncio.run(model.plan_queries(state, store))
    assert plan["queries"][0]["source_id"] == "M004"
    assert [e["kind"] for e in store.events_list] == ["model_started", "model_completed"]
    assert captured["messages"][0]["content"].startswith("SKILL")


class SearchGateway:
    def __init__(self):
        self.specs = []

    async def call(self, name, args):
        assert name == "search_news"
        self.specs.append(args["spec"])
        return {"status": "retrieved", "message": "ok", "sources": []}


def run_news(planner, state=None):
    """Run only the news node through the compiled graph's wrapped callable."""
    gateway = SearchGateway()
    events = []

    class Store:
        def events(self, task_id):
            return []

        def event(self, task_id, kind, payload):
            events.append((kind, payload))

    graph = build_graph(Store(), gateway, InMemorySaver(), planner=planner)
    base = {
        "task_id": "t",
        "version": 1,
        "status": "running",
        "budget_id": "b",
        "spec": {"year": 2026, "week": 44, "news_queries": []},
        "minutes": MINUTES,
        "metrics": METRICS,
        "bundle": {"employee": {"allowed_tools": ["search_news"], "limits": {"active_seconds": 60}, "search": {"blocked_terms": ["青禾"]}}},
        **(state or {}),
    }
    update = asyncio.run(graph.nodes["news"].bound.ainvoke(base))
    return update, gateway, events


def test_news_node_searches_only_screened_queries():
    async def planner(state, store):
        return {"queries": [query("2026 消防检查 通知"), query("青禾 活动")]}

    update, gateway, events = run_news(planner)
    assert gateway.specs[0]["news_queries"] == ["2026 消防检查 通知"]
    assert update["news"]["plan"]["dropped"][0]["reason"] == "包含门店或配置的内部词"
    assert update["route"] == "analyze"
    assert any(kind == "search_planned" for kind, _ in events)


def test_empty_plan_recovers_explicit_public_notice_without_internal_text():
    async def planner(state, store):
        return {"queries": []}

    update, gateway, _ = run_news(planner)
    assert gateway.specs[0]["news_queries"] == ["2026年11月 市场监管 消防检查 通知"]
    assert update["news"]["plan"]["items"][0]["source_id"] == "M004"
    assert "青禾" not in gateway.specs[0]["news_queries"][0]


def test_empty_plan_does_not_search_internal_operational_notes():
    async def planner(state, store):
        return {"queries": []}

    update, gateway, _ = run_news(planner, {"minutes": {"sources": [
        {"id": "M001", "text": "杭州湖滨店停业，店内消防检查已完成。"},
    ]}})
    assert gateway.specs[0]["news_queries"] == []


def test_public_notice_fallback_still_passes_privacy_screen():
    async def planner(state, store):
        return {"queries": []}

    update, gateway, _ = run_news(planner, {"metrics": {"groups": [
        {"dimension": "store", "label": "市场监管"},
    ]}})
    assert gateway.specs[0]["news_queries"] == []
    assert len(update["news"]["plan"]["dropped"]) == 1


def test_plan_failure_does_not_block_report():
    from report_agent.models import WorkflowError

    async def planner(state, store):
        raise WorkflowError("模型服务 HTTP 500，请检查设置或额度", "model")

    update, gateway, _ = run_news(planner)
    assert update.get("status") != "paused"
    assert update["route"] == "analyze"
    assert update["news"]["status"] == "plan_failed"
    assert gateway.specs[0]["news_queries"] == []


def test_unchanged_minutes_reuse_previous_search():
    async def planner(state, store):
        return {"queries": [query("2026 消防检查 通知")]}

    first, _, _ = run_news(planner)

    async def forbidden(state, store):
        raise AssertionError("must not plan again")

    second, gateway, _ = run_news(forbidden, {"news": first["news"]})
    assert gateway.specs == []
    assert second["route"] == "analyze" and "news" not in second


def test_template_has_required_sections_and_body_flow(tmp_path):
    path = Path(tmp_path) / "template.docx"
    documents.build_template(path)
    headings = [p.text for p in Document(path).paragraphs if p.style.name == "Heading 1"]
    assert headings == ["本周摘要", "核心指标", "品类与单品", "异常与原因", "数据质量说明", "下周关注事项", "附录：来源与审核记录"]


@pytest.mark.parametrize("kind", ["rate_limit", "budget", "configuration"])
def test_planning_hard_failure_pauses_without_search(kind):
    from report_agent.models import WorkflowError

    async def planner(state, store):
        raise WorkflowError("test hard failure", kind)

    update, gateway, _ = run_news(planner)
    assert update["status"] == "paused"
    assert update["error_kind"] == kind
    assert update["resume_node"] == "news"
    assert gateway.specs == []


@pytest.mark.parametrize("status", ["unavailable", "plan_failed", "partial"])
def test_failed_search_can_retry_on_resume(status):
    calls = []

    async def planner(state, store):
        calls.append(1)
        return {"queries": [query("2026 消防检查 通知")]}

    first, _, _ = run_news(planner)
    first["news"]["status"] = status
    _, gateway, _ = run_news(planner, {"news": first["news"]})
    assert len(calls) == 2 and len(gateway.specs) == 1
