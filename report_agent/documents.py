"""Reuse docxtpl/Jinja2 for business-editable Word templates; python-docx only builds the initial template."""

from __future__ import annotations

import hashlib
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docxtpl import DocxTemplate, InlineImage

from report_agent.config import ROOT
from report_agent.data_tools import money
from report_agent.store import atomic_json, digest, task_path


def substitute(text, tokens):
    return re.sub(r"\{\{([^{}]+)\}\}", lambda m: str(tokens.get(m[1], m[0])), str(text))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_table(doc, headers, items):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Shading Accent 1"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = text
    for row in items:
        cells = table.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = text
    return table


def build_template(path):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(1.45)
    sec.left_margin = sec.right_margin = Cm(1.5)
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(8.5)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.paragraph_format.space_after = Pt(3)
    style.paragraph_format.line_spacing = 1.05
    for name in ["Title", "Heading 1", "Heading 2"]:
        doc.styles[name].font.name = "Microsoft YaHei"
        doc.styles[name]._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
        doc.styles[name].font.size = Pt(20 if name == "Title" else 12)
    doc.add_paragraph("{{ title }}", style="Title")
    doc.add_paragraph("{{ period }} · {{ week }} · 版本 {{ version }}")
    doc.add_heading("本周摘要", 1)
    doc.add_paragraph("{{ summary }}")
    doc.add_heading("核心指标", 1)
    add_table(
        doc,
        ["区域", "实收（元）", "环比", "毛利率", "目标达成率"],
        [
            ["{%tr for row in core %}"],
            ["{{row.label}}", "{{row.amount}}", "{{row.change}}", "{{row.margin}}", "{{row.target}}"],
            ["{%tr endfor %}"],
        ],
    )
    charts = doc.add_table(rows=1, cols=2)
    charts.cell(0, 0).text = "{{ regions_chart }}"
    charts.cell(0, 1).text = "{{ trend_chart }}"
    doc.add_heading("品类与单品", 1)
    doc.add_paragraph("{{ categories }}")
    doc.add_paragraph("{{ category_margins }}")
    doc.add_paragraph("{{ top_products }}")
    doc.add_page_break()
    doc.add_heading("异常与原因", 1)
    doc.add_paragraph("{{ anomaly_intro }}")
    add_table(
        doc,
        ["对象／环比", "原因与依据"],
        [
            ["{%tr for row in anomalies %}"],
            ["{{row.label}}\n{{row.change}}", "{{row.reason}}"],
            ["{%tr endfor %}"],
        ],
    )
    doc.add_page_break()
    doc.add_heading("数据质量说明", 1)
    doc.add_paragraph("{{ quality_notes }}")
    doc.add_heading("下周关注事项", 1)
    doc.add_paragraph("{{ actions }}")
    doc.add_heading("证据与审核说明", 1)
    doc.add_paragraph("{{ evidence }}")
    doc.add_paragraph("{{ review_response }}")
    doc.add_paragraph("{{ provenance }}")
    footer = sec.footer.paragraphs[0]
    footer.text = "经营周报员工 · 审核状态以交付包为准  |  "
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def chart(metrics, base):
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    files = []
    regions = [g for g in metrics["groups"] if g["dimension"] == "region"]
    fig, ax = plt.subplots(figsize=(5, 2.35), layout="constrained")
    ax.bar([r["label"] for r in regions], [r["cents"] / 100 for r in regions], color="#3d68d9")
    ax.set_title("区域实收对比", fontsize=11)
    ax.set_ylabel("元", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    p = base / "regions.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    files.append(p)
    fig, ax = plt.subplots(figsize=(5, 2.35), layout="constrained")
    ax.plot(
        [f"W{r['week']}" for r in metrics["trend"]],
        [r["cents"] / 100 if r["covered"] else float("nan") for r in metrics["trend"]],
        marker="o",
        color="#3d68d9",
    )
    ax.set_title("近四周实收趋势", fontsize=11)
    ax.set_ylabel("元", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    p = base / "trend.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    files.append(p)
    return files


def percent(value, sign=False):
    return (f"{value:+.1f}%" if sign else f"{value:.1f}%") if value is not None else "不适用"


def generate_report(task_id, version, metrics, minutes, draft, bundle, feedback, render_options=None):
    template = ROOT / "templates/weekly-report.docx"
    if not template.exists():
        build_template(template)
    artifact_id = f"v{version}-{digest({'draft': draft, 'metrics': metrics, 'template': sha256(template), 'layout': render_options})[:12]}"
    base = task_path(task_id, f"artifacts/{artifact_id}")
    base.mkdir(parents=True, exist_ok=True)
    pictures = chart(metrics, base)
    tpl = DocxTemplate(template)
    tokens = metrics["tokens"]
    by_id = {g["id"]: g for g in metrics["anomalies"]}
    anomalies = []
    used = set()
    for item in draft["anomalies"]:
        g = by_id.get(item["metric_id"], {"label": item["metric_id"], "change": None})
        used.update(e["source_id"] for e in item["evidence"])
        reason = ("原因待核实：" if item["uncertain"] else "") + substitute(item["reason"], tokens)
        reason += " " + " ".join(f"[{e['source_id']}]" for e in item["evidence"])
        anomalies.append({"label": g["label"], "change": percent(g["change"], True), "reason": reason})
    q = metrics["quality"]
    notes = [
        f"本期按记录ID剔除 {q['removed_count']} 条相同重复上传记录，实收合计 {money(q['removed_cents'])} 元；全文件共剔除 {metrics['import_summary']['removed_duplicates']} 条，冲突记录不会自动合并。",
        f"本期退货 {q['return_count']} 笔，合计 {money(q['return_cents'])} 元，已直接冲减系统实收。",
    ]
    if q["missing_days"]:
        grouped = {}
        for r in q["missing_days"]:
            grouped.setdefault(r["store"], []).append(r["date"][5:])
        notes.append(
            "无系统记录日期："
            + "；".join(f"{k} {'、'.join(v)}" for k, v in grouped.items())
            + "。停业、未开业与系统缺失需结合纪要区分，未用估计金额补账。"
        )
    notes.extend(substitute(x, tokens) for x in draft.get("data_notes", []))
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
    # Quote evidence is preserved verbatim in the JSON appendix; concise excerpts keep the business Word within three pages.
    evidence = []
    for sid in sorted(used):
        if sid in sources:
            evidence.append(
                f"[{sid}] 第{metrics['week']}周纪要：{sources[sid][:130]}"
                + ("…（完整原文见证据记录）" if len(sources[sid]) > 130 else "")
            )
    core = [metrics["total"], *[g for g in metrics["groups"] if g["dimension"] == "region"]]
    context = {
        "title": "门店经营周报",
        "period": metrics["period"],
        "week": f"{metrics['tokens'].get('year', metrics['start'][:4])}年第{metrics['week']}周",
        "version": version,
        "summary": substitute(draft["summary"], tokens)
        + "\n"
        + "\n".join(substitute(x, tokens) for x in draft.get("conflicts", [])),
        "core": [
            {
                "label": r["label"],
                "amount": money(r["cents"]),
                "change": percent(r["change"], True),
                "margin": percent(r["margin"]),
                "target": percent(r["target_rate"]),
            }
            for r in core
        ],
        "regions_chart": InlineImage(tpl, str(pictures[0]), width=Cm(8.6)),
        "trend_chart": InlineImage(tpl, str(pictures[1]), width=Cm(8.6)),
        "categories": "品类实收／环比："
        + "；".join(
            f"{g['label']} {money(g['cents'])}元／{percent(g['change'], True)}"
            for g in metrics["groups"]
            if g["dimension"] == "category"
        ),
        "top_products": "实收前五单品："
        + "；".join(f"{r['product']} {money(r['cents'])}元" for r in metrics["top_products"]),
        "category_margins": "区域品类毛利率下降："
        + "；".join(
            f"{r['region']}{r['category']} {r['previous_margin']:.1f}% → {r['margin']:.1f}%"
            for r in metrics.get("category_margins", [])
        )
        if metrics.get("category_margins")
        else "",
        "anomaly_intro": f"按实收环比超过 ±{bundle['employee']['business']['anomaly_percent']:g}% 逐项检查。"
        if anomalies
        else "本周无超过阈值的区域或门店。",
        "anomalies": anomalies,
        "quality_notes": "\n".join(notes),
        "actions": "\n".join("• " + substitute(x, tokens) for x in draft["actions"]),
        "evidence": "\n".join(evidence),
        "review_response": substitute(draft.get("review_response", ""), tokens)
        if feedback
        else "首次送审；待人工审核。",
        "provenance": f"口径：{metrics['import_summary']['sheet']} 的实收金额；按ISO周统计。完整指标、原文、质检与配置快照见交付包。",
    }
    tpl.render(context, autoescape=True)
    if render_options:
        style = tpl.docx.styles["Normal"]
        style.font.size = Pt(max(8, min(12, render_options.get("font_points", 8.5))))
        style.paragraph_format.space_after = Pt(max(0, min(12, render_options.get("space_after_points", 3))))
        style.paragraph_format.line_spacing = max(1, min(1.5, render_options.get("line_spacing", 1.05)))
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
        nums = re.findall(r"\d+(?:[.,]\d+)*", clean)
        source_nums = set(re.findall(r"\d+(?:[.,]\d+)*", source_text))
        raw_numbers.extend(n for n in nums if n not in source_nums)
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
