"""Build the six-page technical report from repository documentation using ReportLab."""

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
normal = ParagraphStyle(
    "Chinese",
    fontName="STSong-Light",
    fontSize=10,
    leading=17,
    spaceAfter=8,
    wordWrap="CJK",
    alignment=TA_LEFT,
)
heading = ParagraphStyle(
    "Heading",
    parent=normal,
    fontSize=15,
    leading=22,
    spaceBefore=12,
    spaceAfter=13,
    textColor=colors.HexColor("#172b4d"),
)
title = ParagraphStyle("Title", parent=normal, fontSize=24, leading=32, spaceAfter=20)
small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=12, spaceAfter=4)
evidence = ParagraphStyle("Evidence", parent=normal, fontSize=9, leading=14, spaceAfter=6)


def p(text, style=normal):
    return Paragraph(escape(text).replace("`", ""), style)


def blocks(text):
    lines = text.strip().splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append([p(c, small) for c in cells])
                i += 1
            cols = len(rows[0])
            widths = [(170 * mm) / cols] * cols
            table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2fa")),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#dce2ed")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            out.extend([table, Spacer(1, 10)])
            continue
        if line.startswith("## "):
            out.append(p(line[3:], heading))
        elif not line.startswith("# "):
            out.append(p(line))
        i += 1
    return out


def architecture_diagram():
    diagram = Drawing(480, 140)
    nodes = [(10,90,"React 工作台"),(170,90,"FastAPI 与 SQLite"),(330,90,"LangGraph 编排"),
             (330,20,"MCP 工具与模型"),(170,20,"Word 与 PDF"),(10,20,"审核与交付")]
    for x,y,label in nodes:
        diagram.add(Rect(x,y,140,36,fillColor=colors.HexColor("#edf2fa"),strokeColor=colors.HexColor("#657c9e"),rx=4))
        diagram.add(String(x+70,y+13,label,fontName="STSong-Light",fontSize=11,textAnchor="middle"))
    for x1,y1,x2,y2 in [(150,108,170,108),(310,108,330,108),(400,90,400,56),(330,38,310,38),(170,38,150,38)]:
        diagram.add(Line(x1,y1,x2,y2,strokeColor=colors.HexColor("#657c9e")))
    return diagram


def main():
    text = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    sections = {}
    for section in text.split("\n## ")[1:]:
        name, body = section.split("\n", 1)
        sections[name] = body
    plan = [
        ("目标与架构", ["目标与验收", "架构"]),
        ("流程与状态控制", ["状态流转"]),
        ("岗位配置与工具契约", ["员工配置与执行预算", "数据与工具"]),
        ("程序质检与交付", ["质检与交付"]),
        ("开源复用与验证", ["复用与验证边界"]),
        ("复现与能力边界", ["复现与局限"]),
    ]
    story = []
    for i, (label, names) in enumerate(plan):
        if i:
            story.append(PageBreak())
        story.append(p("经营周报员工技术报告" if i == 0 else label, title if i == 0 else heading))
        story.append(p(f"场景 A  |  LangGraph / MCP / Agent Skills  |  2026-11-06  |  {i + 1}/6", small))
        for name in names:
            story.extend(blocks("## " + name + "\n" + sections[name]))
        if i == 0:
            story.extend(
                [
                    Spacer(1, 10),
                    architecture_diagram(),
                    p("工作流", heading),
                    p(
                        "识别材料 → 计算指标 → 核对纪要 → 模型分析 → Word生成 → 程序质检 → 人工审核 → 正式交付"
                    ),
                    p(
                        "质检不通过：有限修正或暂停。人工退回：同任务新版本重做。工具故障、缺材料和超限：持久化后等待明确恢复。"
                    ),
                ]
            )
        if i == 4:
            verification = ROOT / "docs/verification.md"
            if verification.exists():
                paragraphs = [item.strip() for item in verification.read_text(encoding="utf-8").split("\n\n")]
                story.append(p("验证摘要", heading))
                for prefix in ("本轮工程验证：", "本轮真实模型：", "本轮界面验证："):
                    paragraph = next((item for item in paragraphs if item.startswith(prefix)), "")
                    if paragraph:
                        story.append(p(paragraph, evidence))
    target = ROOT / "docs/技术报告.pdf"

    def footer(canvas, doc):
        canvas.setFont("STSong-Light", 8)
        canvas.setFillColor(colors.HexColor("#8b95a4"))
        canvas.drawString(20 * mm, 13 * mm, "经营周报员工 · 来源、复用与验证边界见项目文档")
        canvas.drawRightString(190 * mm, 13 * mm, str(doc.page))

    SimpleDocTemplate(
        str(target),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        title="经营周报员工技术报告",
        author="项目团队",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    print(target)


if __name__ == "__main__":
    main()
