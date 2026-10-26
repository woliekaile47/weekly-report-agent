"""仅供自动化测试使用，业务应用不导入本模块。"""

from weekly_report.schemas import Draft


def mock_draft(state):
    sources = state["minutes"]["sources"]
    findings = []
    groups = [g for g in state["metrics"]["groups"] if g["dimension"] == "region"]
    for group in groups:
        relevant = [s for s in sources if group["label"] in s["text"]]
        evidence = [{"source_id": s["id"], "quote": s["text"]} for s in relevant[:2]]
        text = (
            f"{group['label']}本期销售额为 {{{{{group['key']}_current}}}}，"
            f"环比为 {{{{{group['key']}_change}}}}。"
        )
        if evidence:
            text += "周会记录提供了该区域的业务背景，建议负责人结合所引原文核查影响范围，避免将时间相关性直接视为因果关系。"
        else:
            text += "现有纪要未提供可核实的原因，需要区域负责人补充库存、客流和活动执行记录后进一步判断。"
        findings.append(
            {
                "title": group["label"] + "经营表现",
                "analysis": text,
                "uncertain": not evidence,
                "evidence": evidence,
            }
        )
    feedback = state.get("feedback", [])
    response = ""
    if feedback:
        response = "已结合审核意见重新检查区域表现及纪要引用，并补充核实步骤。"
        # Mock mode is explicitly a workflow fixture, not a claim of semantic model quality.
        findings[0]["analysis"] += (
            "本次返工补充：逐项检查纪要提及事项，并由区域负责人核实原因与销售波动的对应关系。"
        )
    return Draft.model_validate(
        {
            "summary": "本期整体销售额为 {{total_current}}，与上期相比为 {{total_change}}。"
            "本周经营分析按区域、门店和品类分别汇总，重点关注下降区域及数据覆盖情况。"
            "经营判断应结合周会记录与实际业务核实；缺少证据的原因已标记待核实。"
            "建议管理者优先检查异常区域的供货、活动执行及门店反馈，再安排下一周期跟进。",
            "findings": findings,
            "actions": [
                "区域负责人复核波动门店的明细和周会事项，补充可追溯的原因证据，并在下次周会报告处理进展。",
                "运营岗位核实缺记录日期及可能的重复明细，与门店确认数据覆盖后再扩大分析结论的适用范围。",
                "门店负责人将已确认问题转化为具体整改事项，记录负责人和完成情况，供下一周期对照检查。",
            ],
            "review_response": response,
        }
    ).model_dump()


async def fake_generate(settings, state):
    return mock_draft(state)
