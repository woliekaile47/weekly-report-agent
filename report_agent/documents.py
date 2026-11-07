"""Reuse docxtpl/Jinja2 for business-editable Word templates; python-docx only builds the initial template."""

from __future__ import annotations

import hashlib
import re
from itertools import zip_longest

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docxtpl import DocxTemplate, InlineImage, RichText

from report_agent.config import ROOT
from report_agent.data_tools import money
from report_agent.store import atomic_json, digest, task_path


def substitute(text, tokens):
    return re.sub(r"\{\{([^{}]+)\}\}", lambda m: str(tokens.get(m[1], m[0])), str(text))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


INK = "1F2933"
MUTED = "6B7280"
ACCENT = "0F5C63"
RULE = "D5DAE1"
SHADE = "F3F5F7"
BAND = "E4EEEF"
WARM = "FDF3E7"
NEGATIVE = "B42318"
POSITIVE = "1B7F4C"
CONTENT_WIDTH_CM = 17.4


def shade(cell, fill):
    props = cell._tc.get_or_add_tcPr()
    element = OxmlElement("w:shd")
    element.set(qn("w:val"), "clear")
    element.set(qn("w:color"), "auto")
    element.set(qn("w:fill"), fill)
    props.append(element)


def table_frame(table, widths, rules=True):
    """Horizontal rules only: fixed column widths so Word and LibreOffice lay out alike."""
    table.autofit = False
    props = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        visible = rules and edge in {"top", "bottom", "insideH"}
        element.set(qn("w:val"), "single" if visible else "nil")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), RULE)
        borders.append(element)
    props.append(borders)
    margins = OxmlElement("w:tblCellMar")
    for edge, value in (("top", "40"), ("left", "70"), ("bottom", "40"), ("right", "70")):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:w"), value)
        element.set(qn("w:type"), "dxa")
        margins.append(element)
    props.append(margins)
    for column, width in zip(table.columns, widths):
        column.width = Cm(width)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = Cm(width)


def add_table(doc, widths, rows, numeric=(), rules=True):
    table = doc.add_table(rows=len(rows), cols=len(widths))
    table_frame(table, widths, rules)
    for row, values in zip(table.rows, rows):
        # A row that splits across pages is hard to read; keep each one whole.
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for index, (cell, text) in enumerate(zip(row.cells, values)):
            paragraph = cell.paragraphs[0]
            paragraph.style = "Report Table"
            paragraph.add_run(text)
            if index in numeric:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return table


def header_row(row, fill=SHADE):
    row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for cell in row.cells:
        shade(cell, fill)
        for run in cell.paragraphs[0].runs:
            run.bold = True


def style_font(style, size, bold=None, color=None):
    style.font.name = "Microsoft YaHei"
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color:
        style.font.color.rgb = RGBColor.from_string(color)


def build_template(path):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(1.8)
    sec.bottom_margin = Cm(1.6)
    sec.left_margin = sec.right_margin = Cm(1.8)
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    styles = doc.styles
    style_font(styles["Normal"], 10, color=INK)
    styles["Normal"].paragraph_format.space_after = Pt(4)
    styles["Normal"].paragraph_format.line_spacing = 1.2
    style_font(styles["Title"], 20, bold=True, color=INK)
    border = styles["Title"].element.pPr.find(qn("w:pBdr"))
    if border is not None:
        styles["Title"].element.pPr.remove(border)
    styles["Title"].paragraph_format.space_after = Pt(0)
    style_font(styles["Heading 1"], 12, bold=True, color=ACCENT)
    styles["Heading 1"].paragraph_format.space_before = Pt(12)
    styles["Heading 1"].paragraph_format.space_after = Pt(4)
    style_font(styles["Heading 2"], 10, bold=True, color=INK)
    styles["Heading 2"].paragraph_format.space_before = Pt(8)
    styles["Heading 2"].paragraph_format.space_after = Pt(2)
    for name, size, bold, color in (
        ("Report Table", 9, None, None),
        ("Report Lead", 11, True, None),
        ("Report Note", 8.5, None, MUTED),
        ("Report KPI", 15, True, None),
    ):
        style = styles.add_style(name, 1)
        style.base_style = styles["Normal"]
        style_font(style, size, bold, color)
        style.paragraph_format.space_after = Pt(0 if name in {"Report Table", "Report KPI"} else 3)
        style.paragraph_format.line_spacing = 1.1

    doc.add_paragraph("{{ title }}", style="Title")
    doc.add_paragraph("{{ week }}（{{ period }}）", style="Report Note")
    doc.add_heading("本周摘要", 1)
    doc.add_paragraph("{{ lead }}", style="Report Lead")
    doc.add_paragraph("{%p if summary %}")
    doc.add_paragraph("{{ summary }}")
    doc.add_paragraph("{%p endif %}")

    kpis = doc.add_table(rows=1, cols=5)
    table_frame(kpis, [CONTENT_WIDTH_CM / 5] * 5, rules=False)
    for cell, (label, value) in zip(
        kpis.rows[0].cells,
        (
            ("实收（元）", "{{r kpi.amount}}"),
            ("环比", "{{r kpi.change}}"),
            ("毛利率", "{{r kpi.margin}}"),
            ("目标达成率", "{{r kpi.target}}"),
            ("外卖占比", "{{r kpi.delivery}}"),
        ),
    ):
        shade(cell, SHADE)
        cell.paragraphs[0].style = "Report Note"
        cell.paragraphs[0].add_run(label)
        cell.add_paragraph(value, style="Report KPI")

    doc.add_heading("核心指标", 1)
    core = add_table(
        doc,
        [3.0, 3.2, 2.6, 2.6, 3.2, 2.8],
        [
            ["区域", "实收（元）", "环比", "毛利率", "目标达成率", "外卖占比"],
            ["{{r total.label}}", "{{r total.amount}}", "{{r total.change}}", "{{r total.margin}}", "{{r total.target}}", "{{r total.delivery}}"],
            ["{%tr for row in regions %}"],
            ["{{row.label}}", "{{row.amount}}", "{{r row.change}}", "{{row.margin}}", "{{row.target}}", "{{row.delivery}}"],
            ["{%tr endfor %}"],
        ],
        numeric=(1, 2, 3, 4, 5),
    )
    header_row(core.rows[0])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    charts = doc.add_table(rows=1, cols=2)
    table_frame(charts, [CONTENT_WIDTH_CM / 2] * 2, rules=False)
    charts.cell(0, 0).text = "{{ regions_chart }}"
    charts.cell(0, 1).text = "{{ trend_chart }}"

    doc.add_heading("品类与单品", 1)
    products = add_table(
        doc,
        [2.8, 2.5, 2.0, 0.4, 6.8, 2.9],
        [
            ["品类", "实收（元）", "环比", "", "实收前五单品", "实收（元）"],
            ["{%tr for row in product_rows %}"],
            ["{{row.category}}", "{{row.category_amount}}", "{{r row.category_change}}", "", "{{row.product}}", "{{row.product_amount}}"],
            ["{%tr endfor %}"],
        ],
        numeric=(1, 2, 5),
    )
    header_row(products.rows[0])
    doc.add_paragraph("{%p if margin_alert %}")
    doc.add_paragraph("{{ margin_alert }}", style="Report Note")
    doc.add_paragraph("{%p endif %}")

    doc.add_heading("异常与原因", 1)
    doc.add_paragraph("{{ anomaly_intro }}")
    anomalies = add_table(
        doc,
        [3.3, 14.1],
        [
            ["对象／环比", "原因与依据"],
            ["{%tr for group in anomaly_groups %}"],
            ["{{ group.header }}", ""],
            ["{%tr for row in group.rows %}"],
            ["{% cellbg row.fill %}{{ row.label }}\n{{ row.change }}", "{% cellbg row.fill %}{{ row.text }}"],
            ["{%tr endfor %}"],
            ["{%tr endfor %}"],
        ],
    )
    header_row(anomalies.rows[0])
    band = anomalies.rows[2].cells[0].merge(anomalies.rows[2].cells[1])
    shade(band, BAND)
    for run in band.paragraphs[0].runs:
        run.bold = True

    doc.add_heading("数据质量说明", 1)
    doc.add_paragraph("{%p for note in quality_notes %}")
    doc.add_paragraph("{{ note }}")
    doc.add_paragraph("{%p endfor %}")
    doc.add_heading("下周关注事项", 1)
    doc.add_paragraph("{%p for action in actions %}")
    doc.add_paragraph("{{ action }}")
    doc.add_paragraph("{%p endfor %}")

    appendix = doc.add_heading("附录：来源与审核记录", 1)
    appendix.paragraph_format.page_break_before = True
    doc.add_heading("纪要原文摘录", 2)
    doc.add_paragraph("{%p for line in evidence %}")
    doc.add_paragraph("{{ line }}", style="Report Note")
    doc.add_paragraph("{%p endfor %}")
    doc.add_heading("外部信息核对", 2)
    doc.add_paragraph("{%p for line in external_notes %}")
    doc.add_paragraph("{{ line }}", style="Report Note")
    doc.add_paragraph("{%p endfor %}")
    doc.add_heading("口径与审核", 2)
    doc.add_paragraph("{{ provenance }}", style="Report Note")
    doc.add_paragraph("{{ review_response }}", style="Report Note")

    footer = sec.footer.paragraphs[0]
    footer.style = "Report Note"
    footer.text = "{{ title }}  ·  {{ week }}  ·  第 "
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    footer.add_run(" 页")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def chart(metrics, base):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    files = []
    regions = [g for g in metrics["groups"] if g["dimension"] == "region"]

    def frame(ax, title):
        ax.set_title(title, fontsize=10, fontweight="bold", loc="left", color="#" + INK)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#" + RULE)
        ax.set_yticks([])
        ax.tick_params(axis="x", length=0, labelsize=9, colors="#" + INK)

    fig, ax = plt.subplots(figsize=(4.6, 2.3), layout="constrained")
    amounts = [r["cents"] / 100 for r in regions]
    positions = range(len(regions))
    ax.bar(
        positions,
        amounts,
        width=0.55,
        color=["#" + (ACCENT if r["anomaly"] else "A9BEC1") for r in regions],
    )
    ax.set_xticks(list(positions), [r["label"] for r in regions])
    targets = [(i, r["target_cents"] / 100) for i, r in enumerate(regions) if r.get("target_cents")]
    if targets:
        ax.hlines(
            [v for _, v in targets],
            [i - 0.36 for i, _ in targets],
            [i + 0.36 for i, _ in targets],
            color="#" + INK,
            linewidth=1.4,
            label="目标",
        )
        ax.legend(frameon=False, fontsize=8, loc="upper right")
    top = max(amounts + [v for _, v in targets]) if amounts else 0
    for i, value in enumerate(amounts):
        ax.text(i, value + top * 0.02, f"{value:,.0f}", ha="center", va="bottom", fontsize=8, color="#" + INK)
    ax.set_ylim(0, top * 1.22 or 1)
    moved = "、".join(r["label"] for r in regions if r["anomaly"])
    frame(ax, "区域实收与目标" + (f"：{moved}波动超阈值" if moved else ""))
    p = base / "regions.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    files.append(p)

    fig, ax = plt.subplots(figsize=(4.6, 2.3), layout="constrained")
    weeks = [f"第{r['week']}周" for r in metrics["trend"]]
    values = [r["cents"] / 100 if r["covered"] else float("nan") for r in metrics["trend"]]
    ax.plot(range(len(weeks)), values, marker="o", markersize=4.5, linewidth=1.8, color="#" + ACCENT)
    ax.set_xticks(range(len(weeks)), weeks)
    known = [v for v in values if v == v]
    if known:
        span = (max(known) - min(known)) or max(known) or 1
        ax.set_ylim(min(known) - span * 0.35, max(known) + span * 0.45)
        for i, value in enumerate(values):
            if value == value:
                ax.text(i, value + span * 0.1, f"{value:,.0f}", ha="center", va="bottom", fontsize=8, color="#" + INK)
    ax.set_xlim(-0.35, len(weeks) - 0.65)
    frame(ax, "近四周实收" + (f"：本周环比 {percent(metrics['total']['change'], True)}"))
    p = base / "trend.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    files.append(p)
    return files


def percent(value, sign=False):
    return (f"{value:+.1f}%" if sign else f"{value:.1f}%") if value is not None else "不适用"


def reader_text(text, tokens, week):
    """Readers see metric values and the minutes week, never internal g/M identifiers."""
    source = f"第{week}周纪要"
    code = r"\[?M\d{3,}\]?"
    text = substitute(text, tokens)
    text = re.sub(r"\s*[（(]\s*g\d+\s*[）)]|\bg\d+\b", "", text)
    text = re.sub(rf"(?:第\s*\d+\s*周)?(?:周会)?纪要\s*{code}[ \t]*", source, text)
    text = re.sub(rf"\s*{code}(?:[\s、，,]*{code})*[ \t]*", f"（{source}）", text)
    text = re.sub(rf"([。；])（{source}）", rf"（{source}）\1", text)
    return text.strip()


def report_quality_notes(metrics, draft):
    """One source for Word data-quality prose and the review workspace."""
    q = metrics["quality"]
    notes = [
        f"重复上传：按记录ID剔除 {q['removed_count']} 条完全相同的记录（实收合计 {money(q['removed_cents'])} 元），未计入本周实收。"
        if q["removed_count"]
        else "重复上传：本周未发现记录ID重复的数据。",
        f"退货：{q['return_count']} 笔，合计 {money(q['return_cents'])} 元，已冲减实收。"
        if q["return_count"]
        else "退货：本周没有退货记录。",
    ]
    if q["missing_days"]:
        grouped = {}
        for row in q["missing_days"]:
            grouped.setdefault(row["store"], []).append(row["date"][5:])
        notes.append(
            "无系统记录："
            + "；".join(f"{store} {'、'.join(days)}" for store, days in grouped.items())
            + "。未用估算金额补账，是否停业、未开业或系统缺失以纪要和门店核实为准。"
        )
    notes.extend(reader_text(item, metrics["tokens"], metrics["week"]) for item in draft.get("data_notes", []))
    return notes


VERDICTS = {"support": "外部资料与纪要相符", "conflict": "外部资料与纪要不符"}


def external_row(item, news):
    """External findings stay in their own labelled row; they never become a cause or a sales figure."""
    sources = {s["id"]: s for s in (news or {}).get("sources", [])}
    publishers = list(dict.fromkeys(
        sources[c["source_id"]]["publisher"] for c in item.get("citations", []) if c["source_id"] in sources
    ))
    explanation = item.get("explanation", "").strip()
    # The report only states numbers computable from sales data; figures stay in the appendix.
    body = explanation if explanation and len(explanation) <= 90 and not re.search(r"\d", explanation) else "详情见附录"
    return {
        "kind": "external",
        "label": "外部信息",
        "change": "待人工确认",
        "text": f"{VERDICTS[item['verdict']]}：{body}" + (f"（来源：{'、'.join(publishers)}）" if publishers else ""),
        "fill": SHADE,
        "evidence": [],
    }


def anomaly_groups(metrics, draft, news=None):
    """Anomalies grouped by region for Word and the workspace, each followed by its external check."""
    tokens, week = metrics["tokens"], metrics["week"]
    source = f"第{week}周纪要"
    regions = [g for g in metrics["groups"] if g["dimension"] == "region"]
    by_id = {g["id"]: g for g in metrics.get("anomalies", [])}
    groups = {g["label"]: [] for g in regions}
    extra = {}
    for item in draft.get("anomalies", []):
        metric = by_id.get(item["metric_id"], {"label": item["metric_id"], "change": None})
        reason = reader_text(item["reason"], tokens, week)
        if item.get("evidence") and source not in reason:
            reason = reason.rstrip("。") + f"（{source}）。"
        row = {
            "kind": "anomaly",
            "metric_id": item["metric_id"],
            "label": "区域整体" if metric.get("dimension") == "region" else metric["label"],
            "change": percent(metric.get("change"), True),
            "sort": (metric.get("dimension") != "region", -abs(metric.get("change") or 0)),
            "text": ("原因待核实：" if item.get("uncertain") else "") + reason,
            "uncertain": bool(item.get("uncertain")),
            "evidence": item.get("evidence", []),
            "fill": "FFFFFF",
        }
        region = metric.get("region")
        (groups[region] if region in groups else extra.setdefault("其他", [])).append(row)
    for text in draft.get("conflicts", []):
        region = next((g["label"] for g in regions if g["label"] in text), None)
        row = {
            "kind": "conflict",
            "label": "纪要与数据不一致",
            "change": "以数据为准",
            "text": reader_text(text, tokens, week),
            "fill": WARM,
            "evidence": [],
        }
        (groups[region] if region else extra.setdefault("全公司", [])).append(row)
    for item in draft.get("news_assessments", []):
        if item.get("verdict") not in VERDICTS:
            continue
        region = item.get("region")
        (groups[region] if region in groups else extra.setdefault("全公司", [])).append(external_row(item, news))

    def weight(row):
        return row.get("sort", (True, 0)) if row["kind"] == "anomaly" else (True, 1)

    result = []
    for g in sorted(regions, key=lambda r: -abs(r["change"] or 0)):
        rows = sorted(groups[g["label"]], key=weight)
        if rows:
            result.append(
                {
                    "region": g["label"],
                    "header": f"{g['label']}　实收 {money(g['cents'])} 元　环比 {percent(g['change'], True)}　目标达成率 {percent(g['target_rate'])}",
                    "rows": rows,
                }
            )
    for name, rows in extra.items():
        result.append({"region": name, "header": name, "rows": sorted(rows, key=weight)})
    for group in result:
        for row in group["rows"]:
            row.pop("sort", None)
    return result


def change_text(metric, bold=False):
    value = percent(metric["change"], True)
    color = None
    if metric.get("anomaly"):
        color = NEGATIVE if (metric["change"] or 0) < 0 else POSITIVE
    return RichText(value, color=color, bold=bold)


def external_notes(draft, news):
    news = news or {}
    notes = [news.get("message") or "本任务未进行外部检索。"]
    queries = news.get("queries") or []
    if queries:
        notes.append("检索词：" + "；".join(queries) + f"。检索范围 {news.get('start_date', '')} 至 {news.get('end_date', '')}。")
    sources = {s["id"]: s for s in news.get("sources", [])}
    for item in draft.get("news_assessments", []):
        cited = [sources[c["source_id"]] for c in item.get("citations", []) if c["source_id"] in sources]
        label = VERDICTS.get(item.get("verdict"), "无法核实")
        notes.append(f"[{item['source_id']}] {label}：{item.get('explanation', '')}")
        notes.extend(f"　[{s['id']}] {s['title']}｜{s['publisher']}｜{s['published_at'] or '发布日期不明'}｜{s['url']}" for s in cited)
    return notes


def generate_report(task_id, version, metrics, minutes, draft, bundle, feedback, render_options=None, news=None):
    template = ROOT / "templates/weekly-report.docx"
    if not template.exists():
        build_template(template)
    artifact_id = f"v{version}-{digest({'draft': draft, 'metrics': metrics, 'template': sha256(template), 'layout': render_options, 'news': news})[:12]}"
    base = task_path(task_id, f"artifacts/{artifact_id}")
    base.mkdir(parents=True, exist_ok=True)
    pictures = chart(metrics, base)
    tpl = DocxTemplate(template)
    tokens = metrics["tokens"]
    week_no = metrics["week"]
    used = {e["source_id"] for item in draft["anomalies"] for e in item["evidence"]}
    groups = anomaly_groups(metrics, draft, news) or [
        {
            "region": "全公司",
            "header": "全公司",
            "rows": [{"label": "无异常", "change": "", "text": "本周没有超过阈值的区域或门店。", "fill": "FFFFFF"}],
        }
    ]
    notes = report_quality_notes(metrics, draft)
    prose = "\n".join(
        [
            draft["summary"],
            *draft.get("conflicts", []),
            *draft.get("data_notes", []),
            *draft["actions"],
            draft.get("review_response", ""),
        ]
    )
    used.update(re.findall(r"M\d{3,}", prose))
    sources = {r["id"]: r["text"] for r in minutes["sources"]}
    # Quote evidence is preserved verbatim in the JSON appendix; concise excerpts keep the appendix short.
    evidence = []
    for sid in sorted(used):
        if sid in sources:
            evidence.append(
                f"[{sid}] {sources[sid][:130]}" + ("…（完整原文见交付包）" if len(sources[sid]) > 130 else "")
            )
    total = metrics["total"]
    regions = [g for g in metrics["groups"] if g["dimension"] == "region"]
    summary = reader_text(draft["summary"], tokens, week_no)
    match = re.match(r"(.+?[。！？!?])\s*(.*)", summary, re.DOTALL)
    lead, rest = match.groups() if match else (summary, "")
    categories = [g for g in metrics["groups"] if g["dimension"] == "category"]
    product_rows = [
        {
            "category": c["label"] if c else "",
            "category_amount": money(c["cents"]) if c else "",
            "category_change": change_text(c) if c else "",
            "product": p["product"] if p else "",
            "product_amount": money(p["cents"]) if p else "",
        }
        for c, p in zip_longest(categories, metrics["top_products"])
    ]

    def strong(value):
        return RichText(value, bold=True)

    context = {
        "title": "门店经营周报",
        "period": metrics["period"],
        "week": f"{metrics['tokens'].get('year', metrics['start'][:4])}年第{metrics['week']}周",
        "lead": lead,
        "summary": rest,
        "kpi": {
            "amount": RichText(money(total["cents"])),
            "change": change_text(total),
            "margin": RichText(percent(total["margin"])),
            "target": RichText(percent(total["target_rate"])),
            "delivery": RichText(percent(total.get("delivery_share"))),
        },
        "total": {
            "label": strong(total["label"]),
            "amount": strong(money(total["cents"])),
            "change": change_text(total, bold=True),
            "margin": strong(percent(total["margin"])),
            "target": strong(percent(total["target_rate"])),
            "delivery": strong(percent(total.get("delivery_share"))),
        },
        "regions": [
            {
                "label": r["label"],
                "amount": money(r["cents"]),
                "change": change_text(r),
                "margin": percent(r["margin"]),
                "target": percent(r["target_rate"]),
                "delivery": percent(r.get("delivery_share")),
            }
            for r in regions
        ],
        "regions_chart": InlineImage(tpl, str(pictures[0]), width=Cm(8.5)),
        "trend_chart": InlineImage(tpl, str(pictures[1]), width=Cm(8.5)),
        "product_rows": product_rows,
        "margin_alert": "毛利率下降较多："
        + "；".join(
            f"{r['region']}{r['category']} {r['previous_margin']:.1f}% → {r['margin']:.1f}%"
            for r in metrics.get("category_margins", [])
        )
        if metrics.get("category_margins")
        else "",
        "anomaly_intro": f"实收环比波动超过 ±{bundle['employee']['business']['anomaly_percent']:g}% 的区域和门店如下。原因来自周会纪要，纪要没有提到的标为待核实。"
        if draft["anomalies"]
        else "本周没有超过阈值的区域或门店。",
        "anomaly_groups": groups,
        "quality_notes": notes,
        "actions": [f"{i}. {reader_text(x, tokens, week_no)}" for i, x in enumerate(draft["actions"], 1)],
        "evidence": evidence or ["本周正文未引用纪要原文。"],
        "external_notes": external_notes(draft, news),
        "review_response": "修改说明：" + reader_text(draft.get("review_response", ""), tokens, week_no)
        if feedback
        else "首次送审，审核状态以交付包记录为准。",
        "provenance": f"版本 v{version}。实收取自 {metrics['import_summary']['sheet']} 的实收金额，按 ISO 周统计。外部信息只用于核对纪要说法，不计入经营数据。完整指标、原文和质检记录见交付包。",
    }
    tpl.render(context, autoescape=True)
    if render_options:
        size = max(8, min(12, render_options.get("font_points", 10)))
        style = tpl.docx.styles["Normal"]
        style.font.size = Pt(size)
        style.paragraph_format.space_after = Pt(max(0, min(12, render_options.get("space_after_points", 4))))
        style.paragraph_format.line_spacing = max(1, min(1.5, render_options.get("line_spacing", 1.2)))
        tpl.docx.styles["Report Table"].font.size = Pt(max(8, size - 0.5))
    path = base / "经营周报.docx"
    tmp = base / "report.tmp.docx"
    tpl.save(tmp)
    tmp.replace(path)
    atomic_json(base / "draft.json", draft)
    atomic_json(base / "metrics.json", metrics)
    atomic_json(base / "evidence.json", minutes)
    artifact = {
        "file": str(path.relative_to(task_path(task_id))).replace("\\", "/"),
        "artifact_id": artifact_id,
        "sha256": sha256(path),
        "chart_files": [str(p.relative_to(task_path(task_id))).replace("\\", "/") for p in pictures],
    }
    return artifact


def inspect_report(task_id, artifact, metrics, minutes, draft, bundle, feedback):
    path = task_path(task_id, artifact["file"])
    doc = Document(path)
    checks = []

    def check(name, passed, details):
        checks.append({"name": name, "passed": bool(passed), "details": details})

    quality = bundle["employee"]["quality"]
    tokens = metrics["tokens"]
    headings = {p.text for p in doc.paragraphs if p.style.name.startswith("Heading")}
    check("结构完整", set(quality["required_sections"]).issubset(headings), "六类业务章节必须齐全")
    content_errors = []
    if len(substitute(draft.get("summary", "").strip(), tokens)) < quality.get("min_summary_characters", 30):
        content_errors.append("本周摘要为空或过短")
    if not draft.get("actions"):
        content_errors.append("缺少行动项")
    for i, action in enumerate(draft.get("actions", []), 1):
        if len(substitute(action.strip(), tokens)) < quality.get("min_action_characters", 12):
            content_errors.append(f"第{i}条行动项为空或过短")
    for item in draft.get("anomalies", []):
        if len(substitute(item.get("reason", "").strip(), tokens)) < quality.get("min_reason_characters", 8):
            content_errors.append(f"异常 {item.get('metric_id', '?')} 原因为空或过短")
    for name in ("conflicts", "data_notes"):
        if any(not entry.strip() for entry in draft.get(name, [])):
            content_errors.append(f"{name} 包含空条目")
    check("章节内容有效", not content_errors, "；".join(content_errors) or "摘要、异常原因和行动项均有内容")
    sentences = [part for part in re.split(r"[。！？!?]+|(?<!\d)\.(?!\d)", draft["summary"]) if part.strip()]
    maximum = quality.get("max_summary_sentences", 5)
    check("摘要句数", len(sentences) <= maximum, f"摘要 {len(sentences)} 句；上限 {maximum} 句")
    prose = "\n".join(
        [
            draft["summary"],
            *(a["reason"] for a in draft["anomalies"]),
            *draft["actions"],
            *draft.get("data_notes", []),
            *draft.get("conflicts", []),
            draft.get("review_response", ""),
        ]
    )
    length = len(substitute(prose, tokens))
    check(
        "正文长度",
        quality["min_characters"] <= length <= quality["max_characters"],
        f"正文 {length} 字符；上限 {quality['max_characters']}",
    )
    unknown = [k for k in re.findall(r"\{\{([^{}]+)\}\}", prose) if k not in tokens]
    check("指标引用", not unknown, "未知占位符：" + str(unknown))
    raw_numbers = []
    semantic_errors = []
    source_map = {s["id"]: s["text"] for s in minutes["sources"]}
    fragments = [
        (draft["summary"], []),
        *(
            (
                a["reason"],
                [e["source_id"] for e in a["evidence"] if e["quote"] in source_map.get(e["source_id"], "")],
            )
            for a in draft["anomalies"]
        ),
        *(
            (x, [])
            for x in [
                *draft["actions"],
                *draft.get("data_notes", []),
                *draft.get("conflicts", []),
                draft.get("review_response", ""),
            ]
        ),
    ]
    for text, cited in fragments:
        cited = set(cited) | set(re.findall(r"M\d{3,}", text))
        clean = re.sub(r"\{\{[^{}]+\}\}|\[?M\d{3,}\]?", "", text)
        known_ids = {g["id"] for g in metrics["groups"]}
        clean = re.sub(r"\bg\d+\b", lambda m: "" if m[0] in known_ids else m[0], clean)
        # Source-derived dates/manual estimates must be explicitly attributed; all KPI numbers use tokens.
        source_text = " ".join(source_map.get(sid, "") for sid in cited)
        source_nums = set(re.findall(r"\d+(?:[.,]\d+)*", source_text))
        kpi_words = r"实收|销售额|环比|毛利率|目标达成率|外卖占比"
        for match in re.finditer(r"\d+(?:[.,]\d+)*", clean):
            clause = re.split(r"[。；，,\n]", clean[:match.start()])[-1]
            if match[0] not in source_nums or re.search(kpi_words, clause):
                raw_numbers.append(match[0])
        for match in re.finditer(r"(?P<label>实收|销售额|环比|毛利率|目标达成率|外卖占比)\s*[:：为约]?(?:本周)?\s*\{\{(?P<token>[^{}]+)\}\}", text):
            expected = {
                "实收": "amount", "销售额": "amount", "环比": "change", "毛利率": "margin",
                "目标达成率": "target", "外卖占比": "delivery",
            }[match["label"]]
            if not match["token"].removesuffix("_abs").endswith("_" + expected):
                semantic_errors.append(f"{match['label']} 引用了不匹配的指标 {match['token']}")
        for match in re.finditer(r"(增长|上升|下降|减少|下滑)\s*\{\{([^{}]+_change)\}\}", text):
            value = str(tokens.get(match[2], ""))
            if (value.startswith("-") and match[1] in {"增长", "上升"}) or (
                value.startswith("+") and match[1] in {"下降", "减少", "下滑"}
            ):
                semantic_errors.append(f"{match[2]} 的方向与“{match[1]}”不一致")
        for match in re.finditer(r"(增长|上升|下降|减少|下滑)\s*\{\{([^{}]+_change)_abs\}\}", text):
            value = str(tokens.get(match[2], ""))
            if (value.startswith("-") and match[1] in {"增长", "上升"}) or (
                value.startswith("+") and match[1] in {"下降", "减少", "下滑"}
            ):
                semantic_errors.append(f"{match[2]}_abs 的方向与“{match[1]}”不一致")
    check("指标语义一致", not semantic_errors, "；".join(semantic_errors) or "指标名称与占位符类型一致")
    check("正文数字依据", not raw_numbers, "无指标占位符或所引原文依据的数字：" + str(raw_numbers))
    required = {g["id"] for g in metrics["anomalies"]}
    got = [g["metric_id"] for g in draft["anomalies"]]
    check(
        "异常逐项覆盖",
        set(got) == required and len(got) == len(required),
        f"应覆盖 {len(required)} 项，实际 {len(got)} 项；缺失 {sorted(required - set(got))}",
    )
    sources = {s["id"]: s["text"] for s in minutes["sources"]}
    errors = []
    for item in draft["anomalies"]:
        if not item["uncertain"] and not item["evidence"]:
            errors.append(item["metric_id"] + "确定原因缺少证据")
        for evidence in item["evidence"]:
            if evidence["source_id"] not in sources or evidence["quote"] not in sources.get(
                evidence["source_id"], ""
            ):
                errors.append(item["metric_id"] + "引用非原文")
    errors.extend("未知来源 " + sid for sid in re.findall(r"M\d{3,}", prose) if sid not in sources)
    check("证据原文可追溯", not errors, "；".join(errors) or "来源编号和连续原文匹配；无证据原因标为待核实")
    check(
        "图表完整", len(doc.inline_shapes) >= quality["min_charts"], f"文档图表 {len(doc.inline_shapes)} 张"
    )
    check(
        "行动项与反馈",
        1 <= len(draft["actions"]) <= quality["max_actions"]
        and (not feedback or bool(draft.get("review_response", "").strip())),
        "行动项不超过五条；退回任务必须有修改说明，充分性由人工复核",
    )
    conflicts = metrics.get("expected_conflicts", [])
    conflict_text = "\n".join(draft.get("conflicts", []))
    missing_conflicts = [
        c["region"]
        for c in conflicts
        if c["region"] not in conflict_text or c["source_id"] not in conflict_text
    ]
    check("纪要与数据冲突提示", not missing_conflicts, "未说明的持平说法冲突：" + str(missing_conflicts))
    check("敏感用语", not any(w in prose for w in quality["forbidden_words"]), "检查配置中的禁用词")
    tables = [[c.text for c in row.cells] for t in doc.tables for row in t.rows]
    expected = [metrics["total"], *[g for g in metrics["groups"] if g["dimension"] == "region"]]
    check(
        "表格数值一致",
        all(
            any(
                row[:5]
                == [
                    r["label"],
                    money(r["cents"]),
                    percent(r["change"], True),
                    percent(r["margin"]),
                    percent(r["target_rate"]),
                ]
                for row in tables
            )
            for r in expected
        ),
        "Word核心指标与程序计算逐项比对",
    )
    # Optional renderer audit is performed by the main process using a bounded Word/LibreOffice worker.
    check("文件完整", sha256(path) == artifact["sha256"], "文件摘要与生成版本一致")
    result = {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "artifact_id": artifact["artifact_id"],
    }
    atomic_json(path.parent / "quality.json", result)
    return result
