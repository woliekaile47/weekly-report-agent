import asyncio
import json
import re

import httpx

from report_agent.config import connection
from report_agent.models import Draft, WorkflowError


async def generate(state, store):
    settings = connection()
    limits = state["bundle"]["employee"]["limits"]
    if not settings["LLM_API_KEY"]:
        raise WorkflowError("请先在设置中填写模型密钥", "configuration")
    budget = state["budget_id"]
    used = sum(
        e["kind"] == "model_started" and e["payload"].get("budget_id") == budget
        for e in store.events(state["task_id"])
    )
    if used >= limits["model_calls"]:
        raise WorkflowError("本轮模型调用已达到上限，已暂停转人工处理", "budget")
    system = (
        state["bundle"]["skill"]
        + "\n必须只输出符合以下Schema的JSON：\n"
        + json.dumps(Draft.model_json_schema(), ensure_ascii=False)
    )
    metrics = state["metrics"]
    payload = {
        "task": state["spec"],
        "metrics": metrics,
        "meeting_sources": state["minutes"]["sources"],
        "feedback": state.get("feedback", []),
        "quality_issues": state.get("quality", {}),
        "previous_draft": state.get("draft"),
        "rework_scope": state.get("rework_plan", {}),
        "revision_items": [
            {k: item.get(k) for k in ("id", "text", "sections", "verification")}
            for item in state.get("revision_items", [])
            if item["status"] == "open"
        ],
        "requirements": state["bundle"]["employee"]["quality"],
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    if len(system) + len(user_content) > limits.get("model_input_characters", 160000):
        raise WorkflowError("模型输入超过配置的字符预算，请缩短纪要或处理未解决反馈后恢复", "budget")
    store.event(
        state["task_id"],
        "model_started",
        {"budget_id": budget, "model": settings["LLM_MODEL"], "attempt": used + 1},
    )
    try:
        async with httpx.AsyncClient(timeout=limits["model_timeout_seconds"]) as client:
            response = await client.post(
                settings["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + settings["LLM_API_KEY"]},
                json={
                    **(
                        {"reasoning_effort": settings["LLM_REASONING_EFFORT"]}
                        if settings.get("LLM_REASONING_EFFORT")
                        else {}
                    ),
                    "response_format": {"type": "json_object"},
                    "model": settings["LLM_MODEL"],
                    "temperature": float(settings["LLM_TEMPERATURE"]),
                    "max_tokens": int(settings["LLM_MAX_TOKENS"]),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                },
            )
        if response.status_code == 429:
            raise WorkflowError(
                "模型服务限流或额度不足（HTTP 429），已保存进度。请稍后恢复或检查额度。", "rate_limit"
            )
        if response.status_code >= 400:
            raise WorkflowError(f"模型服务 HTTP {response.status_code}，请检查设置或额度", "model")
        response_data = response.json()
        choice = response_data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise WorkflowError("模型输出被截断，请调整最大输出长度或推理强度后恢复", "configuration")
        content = choice["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        result = ground_dates(Draft.model_validate_json(content).model_dump(), state)
        usage = response_data.get("usage") or {}
        store.event(state["task_id"], "model_completed", {
            "budget_id": budget, "attempt": used + 1,
            "input_characters": len(user_content),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        })
        return result
    except WorkflowError:
        raise
    except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
        raise WorkflowError("单次模型调用超时，已暂停转人工处理", "budget") from exc
    except httpx.HTTPError as exc:
        raise WorkflowError("模型网络连接失败，已保存进度，可恢复重试", "model") from exc
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise WorkflowError("模型返回结构无效，已保存进度，请重试", "model") from exc


def ground_dates(draft, state):
    """Add explicit provenance for unambiguously sourced deadlines; never invent a date or KPI."""
    import copy

    result = copy.deepcopy(draft)
    year = str(state["spec"]["year"])
    for key in ("summary", "review_response"):
        result[key] = re.sub(r"(?<!\d)" + year + r"(?=\s*年)", "{{year}}", result.get(key, ""))
    for key in ("conflicts", "data_notes", "actions"):
        result[key] = [
            re.sub(r"(?<!\d)" + year + r"(?=\s*年)", "{{year}}", text) for text in result.get(key, [])
        ]
    for i, action in enumerate(result["actions"]):
        refs = set(re.findall(r"M\d{3,}", action))
        for date_text in re.findall(r"(?<!\d)(?:1[0-2]|0?[1-9])/(?:3[01]|[12]\d|0?[1-9])(?!\d)", action):
            matches = [s for s in state["minutes"]["sources"] if date_text in s["text"]]
            if len(matches) == 1:
                refs.add(matches[0]["id"])
        if refs:
            action += " " + " ".join(
                f"[{r}]" for r in sorted(refs) if r not in re.findall(r"M\d{3,}", action)
            )
        next_week = state["metrics"]["tokens"].get("next_week", "")
        if "建议时间" in action and next_week:
            action = re.sub(
                r"第\s*" + str(int(re.search(r"\d+", next_week)[0])) + r"\s*周", "{{next_week}}", action
            )
        result["actions"][i] = action.strip()
    if not state.get("feedback"):
        result["review_response"] = ""
    return result
