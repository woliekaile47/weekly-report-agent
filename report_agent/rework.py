"""Scenario routing around LangGraph and the reused AgentOps revision ledger.

Business keywords/scopes live in employee.yaml. Code only enforces dependency
order, allowed targets, immutable sections and objective revision evidence.
"""

import re
from copy import deepcopy

from report_agent.store import digest
from report_agent.third_party.agentops_ledger import update_revision_ledger

SECTIONS = ("summary", "anomalies", "conflicts", "data_notes", "actions")
CATEGORIES = ("data", "evidence", "content", "layout")


def policy(state):
    return state["bundle"]["employee"].get("rework", {})


def normalized_options(options):
    """HTML's empty auto-detection fields and omitted fields have identical meaning."""
    result = {k: v for k, v in (options or {}).items() if v not in (None, "", {})}
    if "fields" in result:
        fields = {k: v for k, v in result["fields"].items() if v not in (None, "")}
        if fields:
            result["fields"] = fields
        else:
            result.pop("fields")
    return result


def classify(state, text, category="auto", sections=None):
    rules = policy(state)
    categories = (
        [category]
        if category != "auto"
        else [
            name
            for name, rule in rules.get("categories", {}).items()
            if any(word in text for word in rule.get("keywords", []))
        ]
    )
    categories = [c for c in CATEGORIES if c in categories] or ["content"]
    selected = sections or [
        name
        for name, words in rules.get("section_keywords", {}).items()
        if any(word in text for word in words)
    ]
    if not selected:
        selected = [
            section
            for c in categories
            for section in rules.get("categories", {})
            .get(c, {})
            .get("sections", [] if c == "layout" else list(SECTIONS))
        ]
    return categories, [s for s in SECTIONS if s in selected]


def register_review(state, decision):
    # Structured entries are preferred; legacy text remains usable, one line per item.
    requested = decision.get("items") or [
        {"text": re.sub(r"^\s*(?:[-•]|\d+[.、)])\s*", "", line).strip()}
        for line in decision["feedback"].splitlines()
        if line.strip()
    ]
    items = deepcopy(state.get("revision_items", []))
    for i, request in enumerate(requested, 1):
        categories, sections = classify(
            state, request["text"], request.get("category", "auto"), request.get("sections")
        )
        items.append(
            {
                "id": f"R{state['version']}-{i}",
                "text": request["text"],
                "categories": categories,
                "sections": sections,
                "requested_version": state["version"],
                "reviewer": decision["reviewer"],
                "before": {k: deepcopy(state.get("draft", {}).get(k)) for k in sections},
                "before_tokens": dict(state.get("metrics", {}).get("tokens", {})),
                "before_inputs": dict(state["inputs"]),
                "before_spec": dict(state["spec"]),
                "before_import_options": state.get("import_options", {}),
                "before_artifact": state.get("artifact", {}).get("sha256", ""),
                "before_layout": state.get("render_options", {}),
                "status": "open",
                "attempts": [],
            }
        )
    return items


def plan_rework(state):
    categories, sections, reasons = set(), set(), []
    for item in state.get("revision_items", []):
        if item["status"] == "open":
            categories.update(item["categories"])
            sections.update(item["sections"])
            reasons.append(item["id"] + "：" + item["text"])
    for check in state.get("quality", {}).get("checks", []):
        if check["passed"]:
            continue
        if check["name"] == "审核意见逐项回应":
            # Use the unresolved item scopes above instead of rewriting the entire report.
            continue
        rule = policy(state).get("quality_routes", {}).get(check["name"], {})
        categories.add(rule.get("category", "content"))
        sections.update(rule.get("sections", list(SECTIONS)))
        reasons.append(check["name"] + "：" + check["details"])
    categories = categories or {"content"}
    # A second page-count failure needs shorter prose, after a bounded layout attempt.
    if state.get("layout_attempts", 0) and any(
        c["name"] == "Word实际页数" and not c["passed"] for c in state.get("quality", {}).get("checks", [])
    ):
        categories.add("content")
        sections.update(SECTIONS)
        reasons.append("紧凑排版后页数仍超限，缩短正文并保留必需业务内容")
    if categories - {"layout"} and not sections:
        sections.update(SECTIONS)
    route = next(
        (
            node
            for category, node in (
                ("data", "ingest"),
                ("evidence", "evidence"),
                ("content", "analyze"),
                ("layout", "render"),
            )
            if category in categories
        ),
        "analyze",
    )
    return {
        "route": route,
        "categories": sorted(categories),
        "sections": [s for s in SECTIONS if s in sections],
        "reasons": reasons,
        "version": state["version"],
    }


def merge_revision(state, candidate):
    previous = state.get("draft") or state.get("draft_baseline")
    scope = state.get("rework_plan", {}).get("sections", list(SECTIONS))
    if previous and state.get("rework_plan"):
        candidate = deepcopy(candidate)
        for section in SECTIONS:
            if section not in scope:
                candidate[section] = deepcopy(previous[section])
    return candidate


def verify_revisions(state, quality):
    items = deepcopy(state.get("revision_items", []))
    responses = state.get("draft", {}).get("revision_responses", [])
    sources = {s["id"] for s in state.get("minutes", {}).get("sources", [])}
    open_ids, verified_ids = [], []
    for item in items:
        matches = [r for r in responses if r["item_id"] == item["id"]]
        after = {k: deepcopy(state.get("draft", {}).get(k)) for k in item["sections"]}
        changes = [k for k in item["sections"] if after[k] != item["before"].get(k)]
        issues = []
        layout_only = set(item["categories"]) == {"layout"}
        if "layout" in item["categories"]:
            layout_checks = [
                c
                for c in quality["checks"]
                if policy(state).get("quality_routes", {}).get(c["name"], {}).get("category") == "layout"
            ]
            changed = state.get("render_options", {}) != item["before_layout"]
            if not (changed and bool(layout_checks) and all(c["passed"] for c in layout_checks)):
                issues.append("尚无有效版式变更或文件质检未通过")
        if layout_only:
            passed = not issues
            response = "已使用配置中的紧凑版式重新生成文件，版式检查结果见质检记录。"
        else:
            response = matches[0]["response"] if len(matches) == 1 else item.get("response", "")
            record = matches[0] if len(matches) == 1 else item.get("response_record", {})
            if len(matches) > 1 or not record or not response.strip():
                issues.append("缺少唯一的逐项回应")
            claimed = record.get("sections", [])
            if (
                not claimed
                or not set(claimed).issubset(item["sections"])
                or not set(claimed).issubset(changes)
            ):
                issues.append("回应所列章节没有实际修改或超出影响范围")
            if not set(record.get("source_ids", [])).issubset(sources):
                issues.append("回应引用了不存在的纪要来源")
            if "data" in item["categories"] and (
                all(state["inputs"].get(k) == item["before_inputs"].get(k) for k in ("sales", "master"))
                and all(state["spec"][k] == item["before_spec"][k] for k in ("year", "week"))
                and normalized_options(state.get("import_options"))
                == normalized_options(item.get("before_import_options"))
            ):
                issues.append("数据类意见尚未补充材料或修正周期")
            item["response_record"] = record
            passed = not issues
        item.update(
            status="verified" if passed else "open",
            after=after,
            after_tokens=dict(state.get("metrics", {}).get("tokens", {})),
            after_layout=dict(state.get("render_options", {})),
            after_artifact=state.get("artifact", {}).get("sha256", ""),
            changed_sections=changes,
            response=response,
            verification="程序差异核验通过，内容充分性待人工确认" if passed else "；".join(issues),
            verified_version=state["version"] if passed else None,
        )
        item["attempts"].append(
            {
                "version": state["version"],
                "passed": passed,
                "details": item["verification"],
                "after_hash": digest(after),
            }
        )
        (verified_ids if passed else open_ids).append(item["id"])
    ledger = update_revision_ledger(state.get("revision_ledger", {}), open_ids, verified_ids)
    check = {
        "name": "审核意见逐项回应",
        "passed": not open_ids,
        "details": "待处理：" + "、".join(open_ids)
        if open_ids
        else "所有已登记意见均有回应与程序差异记录；最终由人工确认",
    }
    return items, ledger, check


def changed_inputs(state, reply):
    inputs = {k: v for k, v in reply.get("inputs", {}).items() if v != state["inputs"].get(k)}
    spec = reply.get("spec", state["spec"])
    options = normalized_options(reply.get("import_options", state.get("import_options", {})))
    old_options = normalized_options(state.get("import_options", {}))
    if not inputs and spec == state["spec"] and options == old_options:
        return {}
    reset = {
        "inputs": {**state["inputs"], **inputs},
        "spec": spec,
        "import_options": options,
        "status": "running",
        "draft": {},
        "artifact": {},
        "quality": {},
        "approval": {},
        "delivery": "",
        "draft_baseline": {},
        "render_options": {},
        "layout_attempts": 0,
        "work_items": [],
        "version": state["version"] + (1 if state.get("artifact") else 0),
    }
    if set(inputs) & {"sales", "master"} or options != old_options:
        reset.update(route="ingest", sales={}, metrics={}, minutes={})
        scope = list(SECTIONS)
    elif any(spec[k] != state["spec"][k] for k in ("year", "week")):
        reset.update(route="calculate" if state.get("sales") else "ingest", metrics={}, minutes={})
        scope = list(SECTIONS)
    elif "minutes" in inputs:
        reset.update(route="evidence" if state.get("metrics") else "ingest", minutes={})
        scope = list(SECTIONS)  # A replacement source may invalidate citations in any section.
    else:
        reset.update(route="analyze" if state.get("minutes") else "ingest")
        scope = list(SECTIONS)
    reset["rework_plan"] = {
        "route": reset["route"],
        "sections": scope,
        "categories": ["data"] if reset["route"] in {"ingest", "calculate"} else ["evidence"],
        "reasons": ["材料或任务参数变化，保留未受影响的上游结果"],
        "version": reset["version"],
    }
    return reset
