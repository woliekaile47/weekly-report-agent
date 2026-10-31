"""Scenario-specific rules over pandas/openpyxl; no model-generated arithmetic."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd
from docx import Document

from report_agent.config import ROOT
from report_agent.models import TaskSpec, WorkflowError
from report_agent.store import atomic_json, digest, task_path
from report_agent.third_party.genslide_text import _normalize


def norm(value):
    return "".join(unicodedata.normalize("NFKC", str(value)).split()).casefold()


def amount(value):
    try:
        v = Decimal(str(value).replace(",", "").strip())
        if not v.is_finite() or abs(v) > 10**12:
            raise ValueError()
        return int((v * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as exc:
        raise WorkflowError("金额为空、非数字或超出合理范围，请核实原始数据", "materials") from exc


def mapped(raw, aliases, overrides=None):
    overrides = overrides or {}
    for offset in range(min(15, len(raw))):
        cols = [str(c).strip() for c in raw.iloc[offset]]
        mapping = {}
        for key, choices in aliases.items():
            names = [overrides[key]] if overrides.get(key) else choices
            found = [c for c in cols if norm(c) in {norm(a) for a in names}]
            if len(found) > 1:
                raise WorkflowError(
                    f"字段 {key} 存在多个候选列：{'、'.join(found)}。请在导入映射中指定列名。", "materials"
                )
            if found:
                mapping[found[0]] = key
        if {"date", "amount"}.issubset(mapping.values()) or len(mapping) == len(aliases):
            if len([c for c in cols if c]) != len(set(norm(c) for c in cols if c)):
                raise WorkflowError("工作表存在重复列名", "materials")
            frame = raw.iloc[offset + 1 :].copy()
            frame.columns = cols
            frame = frame.loc[frame.apply(lambda row: any(str(v).strip() for v in row), axis=1)]
            frame = frame.rename(columns=mapping)
            return frame, offset + 1, {v: k for k, v in mapping.items()}
    return None


def read_sales(task_id, file, columns, options=None, master_file=""):
    path = task_path(task_id, file)
    options = options or {}
    try:
        if path.suffix == ".xlsx":
            sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str, keep_default_na=False)
        elif path.suffix == ".csv":
            try:
                frame = pd.read_csv(path, header=None, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            except UnicodeDecodeError:
                frame = pd.read_csv(path, header=None, dtype=str, keep_default_na=False, encoding="gb18030")
            sheets = {"CSV": frame}
        else:
            raise WorkflowError("销售资料只支持 XLSX、CSV", "materials")
        if master_file:
            sheets.update(
                {
                    f"基础资料/{k}": v
                    for k, v in pd.read_excel(
                        task_path(task_id, master_file),
                        sheet_name=None,
                        header=None,
                        dtype=str,
                        keep_default_na=False,
                    ).items()
                }
            )
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError("销售文件读取失败，请检查格式或是否损坏", "materials") from exc
    candidates = []
    for name, raw in sheets.items():
        if options.get("sheet") and name != options["sheet"]:
            continue
        result = mapped(raw, columns["sales"], options.get("fields"))
        if result and {"date", "amount"}.issubset(result[0].columns):
            candidates.append((name, *result))
    if len(candidates) != 1:
        raise WorkflowError(
            "无法唯一识别销售明细表，请指定工作表及字段映射。现有工作表：" + "、".join(sheets), "materials"
        )
    sheet, frame, header, mapping = candidates[0]
    required = {"record_id", "date", "store_id", "product_id", "channel", "quantity", "amount", "cost"}
    if missing := required - set(frame.columns):
        raise WorkflowError(
            f"缺少必需字段：{'、'.join(sorted(missing))}；实际列名：{'、'.join(mapping.values())}",
            "materials",
        )
    if not 1 <= len(frame) <= 100000:
        raise WorkflowError("明细须包含 1 至 100000 行", "materials")
    raw_count = len(frame)
    ids = frame["record_id"].astype(str).str.strip()
    if (ids == "").any():
        raise WorkflowError("记录ID为空，请补齐后重试", "materials")
    frame["record_id"] = ids
    duplicates = frame[ids.duplicated(keep=False)]
    for identifier, group in duplicates.groupby("record_id"):
        if len(group.drop_duplicates()) != 1:
            raise WorkflowError(f"记录ID {identifier} 对应多个不同内容，不能自动去重，请核实", "materials")
    removed = frame[frame["record_id"].duplicated()].copy()
    frame = frame.drop_duplicates("record_id").copy()
    catalog = {}
    provenance = []
    for role, key in (("stores", "store_id"), ("products", "product_id"), ("targets", "region")):
        matches = []
        for name, raw in sheets.items():
            result = mapped(raw, columns[role])
            if result and set(columns[role]).issubset(result[0].columns):
                matches.append((name, result[0]))
        if len(matches) > 1:
            raise WorkflowError(f"存在多份 {role} 基础表，请保留唯一版本", "materials")
        if matches:
            source, table = matches[0]
        elif path.suffix == ".csv":
            source = f"已配置基础资料/{role}.csv"
            table = pd.read_csv(ROOT / f"config/reference/{role}.csv", dtype=str, keep_default_na=False)
        else:
            raise WorkflowError(f"Excel 缺少 {role} 基础表，请补充同一工作簿或上传基础资料", "materials")
        table = table[list(columns[role])].copy()
        for c in table:
            table[c] = table[c].astype(str).str.strip()
        unique = ["region", "year", "week"] if role == "targets" else [key]
        if table[unique].eq("").any().any() or table.duplicated(unique).any():
            raise WorkflowError(f"{role} 基础表的关联键为空或不唯一", "materials")
        catalog[role] = table.to_dict("records")
        provenance.append({"role": role, "source": source, "rows": len(table)})
    stores = {r["store_id"]: r for r in catalog["stores"]}
    products = {r["product_id"]: r for r in catalog["products"]}
    records = []
    for index, row in frame.iterrows():
        try:
            day = pd.Timestamp(row["date"])
            if pd.isna(day):
                raise ValueError()
            store = stores[str(row["store_id"]).strip()]
            product = products[str(row["product_id"]).strip()]
            q = Decimal(str(row["quantity"]))
            if not q.is_finite() or q != int(q):
                raise ValueError()
            channel = str(row["channel"]).strip()
            if not channel:
                raise ValueError()
            records.append(
                {
                    "id": str(row["record_id"]),
                    "date": day.date().isoformat(),
                    "store_id": store["store_id"],
                    "store": store["store"],
                    "region": store["region"],
                    "product_id": product["product_id"],
                    "product": product["product"],
                    "category": product["category"],
                    "channel": channel,
                    "quantity": int(q),
                    "cents": amount(row["amount"]),
                    "cost_cents": amount(row["cost"]),
                    "source_row": int(index) + 1,
                }
            )
        except (ValueError, KeyError, InvalidOperation) as exc:
            raise WorkflowError(
                f"“{sheet}”第 {int(index) + 1} 行日期/数量无效或门店/商品编码无法关联", "materials"
            ) from exc
    removed_rows = [
        {"date": str(row["date"])[:10], "cents": amount(row["amount"])} for _, row in removed.iterrows()
    ]
    normalized = {
        "records": records,
        "targets": catalog["targets"],
        "stores": catalog["stores"],
        "removed": removed_rows,
    }
    result_file = f"materials/{digest({'file': file, 'columns': columns, 'options': options, 'master': master_file})[:16]}.json"
    atomic_json(task_path(task_id, result_file), normalized)
    return {
        "file": result_file,
        "sheet": sheet,
        "header_row": header,
        "mapping": mapping,
        "raw_rows": raw_count,
        "rows": len(records),
        "removed_duplicates": len(removed),
        "date_start": min(r["date"] for r in records),
        "date_end": max(r["date"] for r in records),
        "references": provenance,
    }


def read_minutes(task_id, file):
    path = task_path(task_id, file)
    try:
        if path.suffix == ".docx":
            doc = Document(path)
            lines = [p.text for p in doc.paragraphs] + [
                " | ".join(c.text for c in row.cells) for t in doc.tables for row in t.rows
            ]
        else:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        lines = [_normalize(line) for line in lines if line.strip()]
    except Exception as exc:
        raise WorkflowError("周会纪要无法读取，请提供有效 Word 或 UTF-8 文本", "materials") from exc
    if not lines or sum(map(len, lines)) > 60000:
        raise WorkflowError("纪要为空或超过六万字", "materials")
    # Weekly labels are evidence metadata; detect a clear mismatch, not arbitrary dates in prose.
    week_match = re.search(r"第\s*(\d{1,2})\s*周", lines[0])
    return {
        "week": int(week_match[1]) if week_match else None,
        "sources": [{"id": f"M{i:03}", "text": line} for i, line in enumerate(lines, 1)],
    }


def money(cents):
    return f"{Decimal(cents) / 100:,.0f}"


def ratio(a, b):
    return None if not b else round(a / b * 100, 1)


def compute_metrics(task_id, sales, spec, threshold=10, delivery_channel="外卖", margin_drop_points=5):
    import json

    task = TaskSpec.model_validate(spec)
    data = json.loads(task_path(task_id, sales["file"]).read_text(encoding="utf-8"))
    start = date.fromisocalendar(task.year, task.week, 1)
    end = start + timedelta(days=6)
    prev = start - timedelta(days=7)
    rows = data["records"]
    current = [r for r in rows if str(start) <= r["date"] <= str(end)]
    old = [r for r in rows if str(prev) <= r["date"] < str(start)]
    if not current:
        raise WorkflowError(
            f"第 {task.week} 周没有销售数据；上传资料实际覆盖 {sales['date_start']} 至 {sales['date_end']}，请补充对应周期资料",
            "materials",
        )
    if not old:
        raise WorkflowError(
            f"缺少上期 {prev} 至 {start - timedelta(days=1)} 的销售数据，无法计算环比", "materials"
        )
    targets = {
        (r["region"], int(r["year"]), int(str(r["week"]).lstrip("Ww"))): amount(r["target"])
        for r in data["targets"]
    }
    tokens = {}
    groups = []

    def aggregate(key, label, new, prior, dimension):
        value = sum(r["cents"] for r in new)
        previous = sum(r["cents"] for r in prior)
        cost = sum(r["cost_cents"] for r in new)
        regions = {r["region"] for r in new}
        target = None
        if dimension in {"total", "region"}:
            missing = [region for region in regions if (region, task.year, task.week) not in targets]
            if missing:
                raise WorkflowError("缺少本周实收目标：" + "、".join(missing), "materials")
            target = sum(targets[(region, task.year, task.week)] for region in regions)
        change = ratio(value - previous, previous)
        result = {
            "id": key,
            "label": label,
            "dimension": dimension,
            "cents": value,
            "previous_cents": previous,
            "change": change,
            "margin": ratio(value - cost, value),
            "target_rate": ratio(value, target),
            "delivery_share": ratio(sum(r["cents"] for r in new if r["channel"] == delivery_channel), value),
            "target_cents": target,
            "rows": len(new),
            "anomaly": change is not None and abs(change) > threshold,
        }
        for field, val in (
            ("amount", money(value)),
            ("change", f"{change:+.1f}%" if change is not None else "上期为零，不适用"),
            ("margin", f"{result['margin']:.1f}%" if result["margin"] is not None else "不适用"),
            ("target", f"{result['target_rate']:.1f}%" if result["target_rate"] is not None else "不适用"),
        ):
            tokens[f"{key}_{field}"] = val
        return result

    total = aggregate("total", "全公司", current, old, "total")
    for dimension in ("region", "store", "category"):
        for label in sorted({r[dimension] for r in current + old}):
            groups.append(
                aggregate(
                    f"g{len(groups)}",
                    label,
                    [r for r in current if r[dimension] == label],
                    [r for r in old if r[dimension] == label],
                    dimension,
                )
            )
    top = {}
    for row in current:
        top[row["product"]] = top.get(row["product"], 0) + row["cents"]
    anomalies = [g for g in groups if g["dimension"] in {"region", "store"} and g["anomaly"]]
    removed = [r for r in data["removed"] if str(start) <= r["date"] <= str(end)]
    returns = [r for r in current if r["cents"] < 0]
    missing_days = []
    for store in sorted({r["store"] for r in current}):
        seen = {r["date"] for r in current if r["store"] == store}
        for n in range(7):
            day = (start + timedelta(days=n)).isoformat()
            if day not in seen:
                missing_days.append({"store": store, "date": day})
    tokens.update(
        {
            "period": f"{start} 至 {end}",
            "year": str(task.year),
            "week": f"第{task.week}周",
            "total_delivery": f"{total['delivery_share']:.1f}%"
            if total["delivery_share"] is not None
            else "不适用",
            "duplicate_count": str(len(removed)),
            "duplicate_amount": money(sum(r["cents"] for r in removed)),
            "return_count": str(len(returns)),
            "return_amount": money(sum(r["cents"] for r in returns)),
            "file_duplicate_count": str(sales["removed_duplicates"]),
            "next_week": f"第{(start + timedelta(days=7)).isocalendar().week}周",
        }
    )
    trend = []
    for n in range(3, -1, -1):
        s = start - timedelta(days=7 * n)
        e = s + timedelta(days=6)
        rr = [r for r in rows if str(s) <= r["date"] <= str(e)]
        trend.append(
            {"week": s.isocalendar().week, "cents": sum(r["cents"] for r in rr), "covered": bool(rr)}
        )
    category_margins = []
    for region in sorted({r["region"] for r in current}):
        for category in sorted({r["category"] for r in current}):
            a = [r for r in current if r["region"] == region and r["category"] == category]
            b = [r for r in old if r["region"] == region and r["category"] == category]
            sales_now = sum(r["cents"] for r in a)
            sales_old = sum(r["cents"] for r in b)
            now = ratio(sales_now - sum(r["cost_cents"] for r in a), sales_now)
            before = ratio(sales_old - sum(r["cost_cents"] for r in b), sales_old)
            if now is not None and before is not None and before - now > margin_drop_points:
                key = f"margin{len(category_margins)}"
                category_margins.append(
                    {
                        "id": key,
                        "region": region,
                        "category": category,
                        "margin": now,
                        "previous_margin": before,
                    }
                )
                tokens[key + "_current"] = f"{now:.1f}%"
                tokens[key + "_previous"] = f"{before:.1f}%"
    return {
        "total": total,
        "groups": groups,
        "anomalies": anomalies,
        "top_products": [
            {"product": p, "cents": v} for p, v in sorted(top.items(), key=lambda x: x[1], reverse=True)[:5]
        ],
        "tokens": tokens,
        "period": tokens["period"],
        "week": task.week,
        "start": str(start),
        "end": str(end),
        "quality": {
            "removed_count": len(removed),
            "removed_cents": sum(r["cents"] for r in removed),
            "return_count": len(returns),
            "return_cents": sum(r["cents"] for r in returns),
            "missing_days": missing_days,
        },
        "trend": trend,
        "category_margins": category_margins,
        "import_summary": sales,
    }
