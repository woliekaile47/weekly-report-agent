from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from docx import Document

from weekly_report.schemas import EmployeeError, TaskSpec


def read_sales_file(path: Path, aliases: dict) -> dict:
    if not path.is_file():
        raise EmployeeError("销售文件不存在，请补充材料", "materials")
    try:
        if path.suffix.lower() == ".csv":
            try:
                frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
            except UnicodeDecodeError:
                frame = pd.read_csv(path, dtype=str, encoding="gb18030", keep_default_na=False)
        elif path.suffix.lower() == ".xlsx":
            frame = pd.read_excel(path, dtype=str, keep_default_na=False)
        else:
            raise EmployeeError("销售文件仅支持 .xlsx 或 .csv", "materials")
    except EmployeeError:
        raise
    except Exception as exc:
        raise EmployeeError("无法读取销售文件，请检查格式和文件是否损坏", "materials") from exc
    if frame.empty or len(frame) > 100000:
        raise EmployeeError("销售数据必须包含 1 至 100000 行", "materials")
    frame.columns = [str(c).strip() for c in frame.columns]
    rename = {}
    for key, choices in aliases.items():
        found = [c for c in frame.columns if c in choices]
        if len(found) != 1:
            raise EmployeeError(
                f"字段 {key} 缺失或存在多个候选列，可用列名：{'、'.join(choices)}", "materials"
            )
        rename[found[0]] = key
    frame = frame.rename(columns=rename)
    records = []
    for number, row in enumerate(frame.to_dict("records"), start=2):
        try:
            parsed = pd.Timestamp(row["date"])
            if pd.isna(parsed):
                raise ValueError("日期为空")
            amount = Decimal(str(row["amount"]).replace(",", "").strip())
            if not amount.is_finite() or abs(amount) > Decimal("1000000000000"):
                raise ValueError("金额范围无效")
            for key in ("store", "region", "category"):
                if not str(row[key]).strip() or len(str(row[key])) > 100:
                    raise ValueError(f"{key} 为空或过长")
            records.append(
                {
                    "date": parsed.date().isoformat(),
                    "store": str(row["store"]).strip(),
                    "region": str(row["region"]).strip(),
                    "category": str(row["category"]).strip(),
                    "cents": int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                    "source_row": number,
                }
            )
        except (ValueError, InvalidOperation, OverflowError) as exc:
            raise EmployeeError(
                f"销售文件第 {number} 行无效：日期、金额或分组字段不正确", "materials"
            ) from exc
    duplicates = int(frame.duplicated(subset=list(aliases)).sum())
    warnings = [f"发现 {duplicates} 行完全相同的明细，已保留，需核实是否重复记账。"] if duplicates else []
    return {"records": records, "warnings": warnings, "row_count": len(records)}


def read_minutes_file(path: Path) -> dict:
    if not path.is_file():
        raise EmployeeError("周会纪要不存在，请补充材料", "materials")
    try:
        if path.suffix.lower() == ".docx":
            document = Document(path)
            paragraphs = [p.text for p in document.paragraphs]
            paragraphs += [
                " | ".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows
            ]
        elif path.suffix.lower() in {".txt", ".md"}:
            paragraphs = path.read_text(encoding="utf-8-sig").splitlines()
        else:
            raise EmployeeError("周会纪要仅支持 .docx、.txt 或 .md", "materials")
    except EmployeeError:
        raise
    except Exception as exc:
        raise EmployeeError("纪要读取失败，请提供未损坏的 Word 或 UTF-8 文本", "materials") from exc
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if not paragraphs:
        raise EmployeeError("周会纪要为空", "materials")
    if sum(map(len, paragraphs)) > 60000:
        raise EmployeeError("纪要超过六万字，请提供本周相关内容", "materials")
    return {"sources": [{"id": f"M{i:03d}", "text": text} for i, text in enumerate(paragraphs, 1)]}


def money(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def percentage(current: int, previous: int | None):
    if previous is None:
        return None
    if previous == 0:
        return None
    return float(
        (Decimal(current - previous) / abs(previous) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def calculate(sales: dict, spec: dict, threshold: float) -> dict:
    task = TaskSpec.model_validate(spec)
    duration = (task.end_date - task.start_date).days + 1
    prior_start, prior_end = task.start_date - timedelta(days=duration), task.start_date - timedelta(days=1)
    current = [
        r for r in sales["records"] if task.start_date <= date.fromisoformat(r["date"]) <= task.end_date
    ]
    previous = [r for r in sales["records"] if prior_start <= date.fromisoformat(r["date"]) <= prior_end]
    if not current:
        raise EmployeeError("统计周期内没有销售明细，请补充对应日期的数据", "materials")
    if task.require_comparison and not previous:
        raise EmployeeError(f"缺少上期数据（{prior_start} 至 {prior_end}），无法按要求计算环比", "materials")
    tokens, groups, warnings = {}, [], list(sales["warnings"])

    def aggregate(key, label, rows, old, dimension):
        amount = sum(r["cents"] for r in rows)
        prior = sum(r["cents"] for r in old) if old else None
        change = percentage(amount, prior)
        change_text = (
            f"{change:+.2f}%" if change is not None else ("上期为零，不适用" if prior == 0 else "无上期数据")
        )
        tokens.update(
            {
                f"{key}_current": money(amount) + " 元",
                f"{key}_previous": money(prior) + " 元" if prior is not None else "无上期数据",
                f"{key}_change": change_text,
            }
        )
        return {
            "key": key,
            "label": label,
            "dimension": dimension,
            "current_cents": amount,
            "previous_cents": prior,
            "change_percent": change,
            "change_text": change_text,
            "current_rows": len(rows),
            "previous_rows": len(old),
            "anomaly": change is not None and abs(change) >= threshold,
        }

    total = aggregate("total", "全部门店", current, previous, "total")
    for dimension in ("region", "store", "category"):
        names = sorted({r[dimension] for r in current + previous})
        for name in names:
            groups.append(
                aggregate(
                    f"g{len(groups)}",
                    name,
                    [r for r in current if r[dimension] == name],
                    [r for r in previous if r[dimension] == name],
                    dimension,
                )
            )
    if any(r["cents"] < 0 for r in current):
        warnings.append("本期包含负金额，已作为退货或冲减保留，请核实业务口径。")
    if len({r["date"] for r in current}) < duration:
        warnings.append("本期部分日期没有记录；缺记录不代表当日零销售，请核实数据覆盖。")
    if previous and len({r["date"] for r in previous}) < duration:
        warnings.append("上期部分日期没有记录，环比仅基于上传范围。")
    if any(g["current_rows"] == 0 for g in groups):
        warnings.append("部分分组仅在上期出现，本期汇总为零但可能存在缺记录，请核实。")
    tokens.update(
        {
            "period": f"{task.start_date} 至 {task.end_date}",
            "previous_period": f"{prior_start} 至 {prior_end}",
            "current_rows": str(len(current)),
            "previous_rows": str(len(previous)),
            "anomaly_threshold": f"{threshold:g}%",
        }
    )
    return {
        "total": total,
        "groups": groups,
        "tokens": tokens,
        "warnings": warnings,
        "period": f"{task.start_date} 至 {task.end_date}",
        "previous_period": f"{prior_start} 至 {prior_end}",
        "current_rows": len(current),
        "previous_rows": len(previous),
        "threshold": threshold,
    }
