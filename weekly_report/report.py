from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from weekly_report.analysis import money
from weekly_report.schemas import Draft
from weekly_report.store import atomic_json


def substitute(text: str, tokens: dict) -> str:
    return re.sub(r"\{\{([a-z0-9_]+)\}\}", lambda m: tokens.get(m[1], m[0]), text)


def chart(metrics: dict, path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    groups = [g for g in metrics["groups"] if g["dimension"] == "region"][:12]
    fig, ax = plt.subplots(figsize=(8.7, 3.6), layout="constrained")
    x = list(range(len(groups)))
    ax.bar(
        [v - 0.18 for v in x],
        [(g["previous_cents"] or 0) / 100 for g in groups],
        width=0.36,
        label="上期（无数据以零占位）",
        color="#BCCBD8",
    )
    ax.bar(
        [v + 0.18 for v in x],
        [g["current_cents"] / 100 for g in groups],
        width=0.36,
        label="本期",
        color="#237B88",
    )
    ax.set_xticks(x, [g["label"] for g in groups], rotation=15 if len(groups) > 5 else 0)
    ax.set_ylabel("销售额（元）")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", alpha=0.15)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp.png")
    fig.savefig(temp, dpi=160)
    plt.close(fig)
    temp.replace(path)


def build_document(
    path: Path,
    chart_path: Path,
    spec: dict,
    metrics: dict,
    minutes: dict,
    draft: dict,
    version: int,
    mode: str,
    feedback: list,
):
    content = Draft.model_validate(draft)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
    sec.left_margin, sec.right_margin = Cm(2.1), Cm(2.1)
    for style_name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[style_name]
        style.font.name = "Microsoft YaHei"
        style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "微软雅黑")
        for borders in list(style.element.iter(qn("w:pBdr"))):
            borders.getparent().remove(borders)
    doc.styles["Title"].font.color.rgb = RGBColor(0, 0, 0)
    doc.styles["Normal"].font.size = Pt(10)
    doc.styles["Normal"].paragraph_format.space_after = Pt(7)
    doc.styles["Normal"].paragraph_format.line_spacing = 1.2
    for heading in ("Heading 1", "Heading 2"):
        doc.styles[heading].font.color.rgb = RGBColor.from_string("194E61")
    doc.add_heading("经营周报", 0)
    doc.add_paragraph(spec["title"])
    doc.add_paragraph(
        f"{metrics['period']}　|　版本 {version}　|　{'离线模拟数据演示' if mode == 'mock' else 'Agnes AI 辅助分析'}"
    )
    doc.add_heading("经营概览", 1)
    doc.add_paragraph(substitute(content.summary, metrics["tokens"]))
    doc.add_heading("指标汇总", 1)
    doc.add_paragraph(
        f"本期销售额 {metrics['tokens']['total_current']}；上期 {metrics['tokens']['total_previous']}；"
        f"环比 {metrics['tokens']['total_change']}。"
    )
    doc.add_picture(str(chart_path), width=Cm(16.5))
    doc.add_paragraph("图示按区域比较销售额，最多展示前十二个区域；全部分组详见下表。")
    for dimension, title in [("region", "区域"), ("store", "门店"), ("category", "品类")]:
        doc.add_heading(f"按{title}汇总", 2)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Light Shading Accent 1"
        for cell, text in zip(table.rows[0].cells, [title, "本期（元）", "上期（元）", "环比"]):
            cell.text = text
        header = OxmlElement("w:tblHeader")
        table.rows[0]._tr.get_or_add_trPr().append(header)
        for group in [g for g in metrics["groups"] if g["dimension"] == dimension]:
            cells = table.add_row().cells
            values = [
                group["label"],
                money(group["current_cents"]),
                money(group["previous_cents"]) if group["previous_cents"] is not None else "无上期数据",
                group["change_text"],
            ]
            for cell, value in zip(cells, values):
                cell.text = value
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after = Pt(3)
                    paragraph.paragraph_format.space_before = Pt(3)
                    paragraph.paragraph_format.line_spacing = 1.05
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            border = OxmlElement(f"w:{edge}")
            for key, value in {"val": "single", "sz": "4", "color": "D9D9D9"}.items():
                border.set(qn(f"w:{key}"), value)
            borders.append(border)
        table._tbl.tblPr.append(borders)
    doc.add_heading("异常与原因", 1)
    for item in content.findings:
        doc.add_heading(substitute(item.title, metrics["tokens"]), 2)
        text = substitute(item.analysis, metrics["tokens"])
        if item.uncertain:
            text = "待核实：" + text
        if item.evidence:
            text += " " + " ".join(f"[{e.source_id}]" for e in item.evidence)
        doc.add_paragraph(text)
    doc.add_heading("行动建议", 1)
    for action in content.actions:
        doc.add_paragraph(substitute(action, metrics["tokens"]), style="List Bullet")
    doc.add_heading("数据与证据说明", 1)
    doc.add_paragraph(
        f"统计范围仅覆盖上传明细。本期 {metrics['current_rows']} 行，上期 {metrics['previous_rows']} 行。"
        "环比按金额差除以上期金额绝对值计算；上期为零时不计算增长率。"
    )
    for warning in metrics["warnings"]:
        doc.add_paragraph(warning, style="List Bullet")
    cited = {e.source_id for item in content.findings for e in item.evidence}
    for source in minutes["sources"]:
        if source["id"] in cited:
            doc.add_paragraph(f"[{source['id']}] {source['text']}")
    if feedback:
        doc.add_heading("审核修改说明", 1)
        for item in feedback:
            doc.add_paragraph(f"审核意见：{item['feedback']}")
        doc.add_paragraph(substitute(content.review_response, metrics["tokens"]))
    footer = sec.footer.paragraphs[0]
    footer.text = "经营周报员工 · 以交付包中的审核与质检记录为准"
    footer.runs[0].font.size = Pt(8)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.docx")
    doc.save(temporary)
    temporary.replace(path)


def inspect(path: Path, draft: dict, metrics: dict, minutes: dict, quality: dict, feedback: list) -> dict:
    checks = []

    def record(name, passed, details):
        checks.append({"name": name, "passed": bool(passed), "details": details})

    try:
        doc = Document(path)
    except Exception:
        return {
            "passed": False,
            "checks": [{"name": "文件完整性", "passed": False, "details": "Word 无法打开"}],
        }
    headings = {p.text for p in doc.paragraphs if p.style.name.startswith("Heading")}
    missing = [h for h in quality["required_sections"] if h not in headings]
    record("结构完整", not missing, "章节齐全" if not missing else f"缺少：{missing}")
    prose = "\n".join([draft["summary"], *(f["analysis"] for f in draft["findings"]), *draft["actions"]])
    count = len(substitute(prose, metrics["tokens"]))
    record("字数要求", quality["min_characters"] <= count <= quality["max_characters"], f"正文 {count} 字符")
    narrative = (
        prose
        + "\n"
        + draft.get("review_response", "")
        + "\n"
        + "\n".join(item["title"] for item in draft["findings"])
    )
    placeholders = re.findall(r"\{\{([^{}]+)\}\}", narrative)
    invalid = [token for token in placeholders if token not in metrics["tokens"]]
    known_sources = {source["id"] for source in minutes["sources"]}
    inline_sources = re.findall(r"M\d{3,}", narrative)
    invalid.extend(source for source in inline_sources if source not in known_sources)
    without_tokens = re.sub(r"\{\{[^{}]+\}\}|\[?M\d{3,}\]?", "", narrative)
    raw_numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)*%?", without_tokens)
    actual_rows = [tuple(c.text for c in row.cells) for table in doc.tables for row in list(table.rows)[1:]]
    expected_rows = [
        (
            g["label"],
            money(g["current_cents"]),
            money(g["previous_cents"]) if g["previous_cents"] is not None else "无上期数据",
            g["change_text"],
        )
        for g in metrics["groups"]
    ]
    tables_match = actual_rows == expected_rows
    rendered_text = "\n".join(p.text for p in doc.paragraphs)
    fragments = [
        draft["summary"],
        *draft["actions"],
        *(value for item in draft["findings"] for value in (item["title"], item["analysis"])),
    ]
    if draft.get("review_response"):
        fragments.append(draft["review_response"])
    prose_match = all(substitute(fragment, metrics["tokens"]) in rendered_text for fragment in fragments)
    record(
        "数据一致性",
        not invalid and not raw_numbers and tables_match and prose_match,
        f"未知指标 {invalid}；未通过指标引用的数字 {raw_numbers}；表格一致 {tables_match}；正文一致 {prose_match}",
    )
    sources = {s["id"]: s["text"] for s in minutes["sources"]}
    evidence_errors = []
    for item in draft["findings"]:
        if not item["uncertain"] and not item["evidence"]:
            evidence_errors.append(f"{item['title']}：确定原因没有证据")
        for citation in item["evidence"]:
            if citation["source_id"] not in sources or citation["quote"] not in sources.get(
                citation["source_id"], ""
            ):
                evidence_errors.append(f"{item['title']}：引用或原文不匹配")
    record(
        "证据覆盖",
        not evidence_errors,
        "引用原文可追溯；无证据原因标记待核实" if not evidence_errors else "；".join(evidence_errors),
    )
    record(
        "图表与文件完整",
        len(doc.inline_shapes) >= 1 and len(doc.tables) == 3,
        f"图表 {len(doc.inline_shapes)} 个，汇总表 {len(doc.tables)} 个",
    )
    forbidden = [word for word in quality.get("forbidden_words", []) if word in narrative]
    record("用语检查", not forbidden, f"禁用词：{forbidden}")
    record(
        "审核意见响应",
        not feedback or bool(draft.get("review_response", "").strip()),
        "修改说明存在；是否充分采纳由审核人复核" if feedback else "首次送审",
    )
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def save_quality(path, result):
    atomic_json(path, result)
