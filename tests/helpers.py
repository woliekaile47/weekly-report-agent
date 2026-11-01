"""Deterministic model replacement for engineering tests only. Not imported by the product."""


async def test_model(state, store):
    metrics = state["metrics"]
    sources = state["minutes"]["sources"]
    result = {
        "summary": "本周全公司实收 {{total_amount}} 元，环比 {{total_change}}，毛利率 {{total_margin}}，目标达成率 {{total_target}}，外卖占比 {{total_delivery}}。区域与门店异常均已列入下表，建议管理层结合纪要和数据质量说明安排核实，避免把缺记录等同于零销售。",
        "anomalies": [],
        "conflicts": [],
        "data_notes": [],
        "actions": [
            "区域负责人核查各异常门店的经营记录，对无直接证据的原因补充可追溯资料，并在下次周会反馈。",
            "财务核对退货冲减及重复上传处理，运营持续跟踪整改效果，确认本周指标与可用系统记录一致。",
        ],
        "review_response": "已根据审核意见重新核对异常、原因和原文引用，并在相应内容中补充核实步骤。"
        if state.get("feedback")
        else "",
    }
    for metric in metrics["anomalies"]:
        relevant = [s for s in sources if metric["label"] in s["text"]]
        ev = [{"source_id": s["id"], "quote": s["text"][:80]} for s in relevant[:1]]
        result["anomalies"].append(
            {
                "metric_id": metric["id"],
                "reason": f"本周环比 {{{{{metric['id']}_change}}}}。"
                + (
                    "纪要提供经营背景，相关影响范围需由负责人结合门店记录核实。"
                    if ev
                    else "纪要未直接说明原因，需补充门店客流、活动及运营记录。"
                ),
                "uncertain": True,
                "evidence": ev,
            }
        )
    for c in metrics.get("expected_conflicts", []):
        result["conflicts"].append(
            f"{c['region']}纪要所述基本持平（{c['source_id']}）与系统环比 {{{{{c['metric_id']}_change}}}} 不一致，以系统数据为准。"
        )
    result["revision_responses"] = []
    for item in state.get("revision_items", []):
        if item["status"] != "open" or set(item["categories"]) == {"layout"}:
            continue
        for section in item["sections"]:
            addition = "复核时由责任人逐项登记原文与系统记录的差异，核实后再确认结论。"
            if section == "summary":
                result[section] += addition
            elif section == "anomalies" and result[section]:
                result[section][0]["reason"] += addition
            elif section in {"actions", "data_notes", "conflicts"}:
                if result[section]:
                    result[section][0] += addition
                else:
                    result[section].append(addition)
        result["revision_responses"].append(
            {
                "item_id": item["id"],
                "response": "已补充责任人核对步骤与差异登记说明。",
                "sections": item["sections"],
                "source_ids": [],
            }
        )
    return result
