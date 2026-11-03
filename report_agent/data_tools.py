"""Scenario-specific rules over pandas/openpyxl; no model-generated arithmetic."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

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


def parse_sales_day(value, excel_epoch=None):
    text = str(value).strip()
    if excel_epoch is not None and re.fullmatch(r"\d+(?:\.0+)?", text):
        from openpyxl.utils.datetime import from_excel

        try:
            result = from_excel(float(text), epoch=excel_epoch)
            if isinstance(result, datetime):
                return result.date()
        except (ValueError, OverflowError):
            pass
    match = re.fullmatch(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", text)
    if match:
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            pass
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if result.tzinfo is not None:
            return result.astimezone(ZoneInfo("Asia/Shanghai")).date()
        if re.match(r"^\d{4}-\d{2}-\d{2}[T ]", text):
            return result.date()
    except ValueError:
        pass
    raise WorkflowError(f"销售日期“{text}”无效或有歧义；请使用 YYYY-MM-DD、中文年月日或明确时区", "materials")


def inspect_office_archive(path, max_uncompressed=256 * 1024 * 1024):
    """Reject compressed Office files that can exhaust the parser before row limits apply."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(entry.file_size for entry in entries) > max_uncompressed or any(
                entry.file_size > 128 * 1024 * 1024
                or entry.file_size > max(1, entry.compress_size) * 1000
                for entry in entries
            ):
                raise WorkflowError("Office 文件展开后超过解析资源上限，请减少工作表或文件内容", "materials")
    except (zipfile.BadZipFile, OSError) as exc:
        raise WorkflowError("Office 文件压缩结构无效，请检查文件是否损坏", "materials") from exc


def read_excel_safely(path, *, nrows=None):
    """Apply the same archive and worksheet bounds to every Excel upload path."""
    from openpyxl import load_workbook

    inspect_office_archive(path)
    workbook = load_workbook(path, read_only=True)
    try:
        epoch = workbook.epoch
        if any(
            (sheet.max_row or 0) > 110_000 or (sheet.max_column or 0) > 200
            for sheet in workbook.worksheets
        ) or sum(
            (sheet.max_row or 0) * (sheet.max_column or 0)
            for sheet in workbook.worksheets
        ) > 4_000_000:
            raise WorkflowError("Excel 工作表行列规模超过解析上限", "materials")
    finally:
        workbook.close()
    return pd.read_excel(
        path, sheet_name=None, header=None, nrows=nrows, dtype=str, keep_default_na=False
    ), epoch


def read_csv_complete(path):
    """Stream to EOF; discarded blank rows must never hide valid trailing records."""
    def load(encoding):
        parts = []
        nonempty_count = 0
        reader = pd.read_csv(
            path, header=None, dtype=str, keep_default_na=False,
            encoding=encoding, chunksize=10_000,
        )
        try:
            for chunk in reader:
                nonempty = chunk.apply(lambda col: col.str.strip().ne("")).any(axis=1)
                useful = chunk.loc[nonempty]
                nonempty_count += len(useful)
                # Header plus up to 15 introductory rows and 100,000 sales records.
                if nonempty_count > 100_016:
                    raise WorkflowError("CSV 有效行数超过 100000 条明细上限，请拆分或精简文件", "materials")
                if not useful.empty:
                    parts.append(useful)
        finally:
            reader.close()
        # Preserve parser row indices so validation errors still identify the source row.
        return pd.concat(parts) if parts else pd.DataFrame()

    try:
        return load("utf-8-sig")
    except UnicodeDecodeError:
        return load("gb18030")


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


def workbook_has_catalogs(path, columns):
    """Check whether a replacement sales workbook contains all required master tables."""
    if path.suffix.lower() != ".xlsx":
        return False
    try:
        sheets, _ = read_excel_safely(path, nrows=16)
        return all(
            sum(
                bool(result and set(columns[role]).issubset(result[0].columns))
                for raw in sheets.values()
                for result in [mapped(raw, columns[role])]
            ) == 1
            for role in ("stores", "products", "targets")
        )
    except Exception:
        # This is only an early retirement hint. The normal ingest path reports malformed files.
        return False


def read_sales(task_id, file, columns, options=None, master_file=""):
    path = task_path(task_id, file)
    options = options or {}
    excel_epoch = None
    try:
        if path.suffix == ".xlsx":
            sheets, excel_epoch = read_excel_safely(path)
        elif path.suffix == ".csv":
            sheets = {"CSV": read_csv_complete(path)}
        else:
            raise WorkflowError("销售资料只支持 XLSX、CSV", "materials")
        if master_file:
            master_sheets, _ = read_excel_safely(task_path(task_id, master_file))
            sheets.update(
                {
                    f"基础资料/{k}": v
                    for k, v in master_sheets.items()
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
        if role == "targets":
            seen_periods = {}
            for index, row in table.iterrows():
                try:
                    if not re.fullmatch(r"\d{4}", row["year"]):
                        raise ValueError("年份须为四位数字")
                    if not re.fullmatch(r"[Ww]?\d{1,2}", row["week"]):
                        raise ValueError("周次须为 1 至 53 或 W01 至 W53")
                    year, week = int(row["year"]), int(row["week"].lstrip("Ww"))
                    date.fromisocalendar(year, week, 1)
                    if amount(row["target"]) < 0:
                        raise ValueError("实收目标不能为负数")
                    period_key = (row["region"], year, week)
                    if period_key in seen_periods:
                        raise ValueError(
                            f"与第 {seen_periods[period_key]} 行的区域、年份和周次重复；"
                            "44、W44 等写法按同一周处理，请核实目标"
                        )
                    seen_periods[period_key] = int(index) + 1
                except (ValueError, WorkflowError) as exc:
                    raise WorkflowError(
                        f"“{source}”第 {int(index) + 1} 行目标表字段无效："
                        f"年份={row['year']}，周次={row['week']}，实收目标={row['target']}；{exc}",
                        "materials",
                    ) from exc
        catalog[role] = table.to_dict("records")
        provenance.append({"role": role, "source": source, "rows": len(table)})
    stores = {r["store_id"]: r for r in catalog["stores"]}
    products = {r["product_id"]: r for r in catalog["products"]}
    allowed_channels = columns.get("allowed_channels", ["堂食自提", columns["delivery_channel"]])
    records = []
    for index, row in frame.iterrows():
        try:
            try:
                day = parse_sales_day(row["date"], excel_epoch)
            except WorkflowError as exc:
                raise WorkflowError(f"“{sheet}”第 {int(index) + 1} 行{exc}", "materials") from exc
            store = stores[str(row["store_id"]).strip()]
            product = products[str(row["product_id"]).strip()]
            q = Decimal(str(row["quantity"]))
            if not q.is_finite() or q != int(q):
                raise ValueError()
            channel = str(row["channel"]).strip()
            if not channel:
                raise ValueError()
            if channel not in allowed_channels:
                raise WorkflowError(
                    f"“{sheet}”第 {int(index) + 1} 行渠道“{channel}”不在允许值中："
                    f"{'、'.join(allowed_channels)}。请核实原始数据或修改字段映射配置。",
                    "materials",
                )
            records.append(
                {
                    "id": str(row["record_id"]),
                    "date": day.isoformat(),
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
        {"date": parse_sales_day(row["date"], excel_epoch).isoformat(),
         "cents": amount(row["amount"])}
        for _, row in removed.iterrows()
    ]
    normalized = {
        "records": records,
        "targets": catalog["targets"],
        "stores": catalog["stores"],
        "products": catalog["products"],
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
            inspect_office_archive(path)
            doc = Document(path)
            from docx.oxml.ns import qn
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            lines = []
            for element in doc.element.body.iterchildren():
                if element.tag == qn("w:p"):
                    lines.append(Paragraph(element, doc).text)
                elif element.tag == qn("w:tbl"):
                    lines.extend(" | ".join(c.text for c in row.cells) for row in Table(element, doc).rows)
        else:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        lines = [_normalize(line) for line in lines if line.strip()]
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError("周会纪要无法读取，请提供有效 Word 或 UTF-8 文本", "materials") from exc
    if not lines or sum(map(len, lines)) > 60000:
        raise WorkflowError("纪要为空或超过六万字", "materials")
    # Only the title and explicit period fields are metadata; incidental body dates are not.
    periods = []
    for index, line in enumerate(lines):
        # Markdown styling is presentation, while table cells and bold labels can hold period metadata.
        declaration = re.sub(r"^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[.)]\s+)", "", line)
        declaration = declaration.strip().strip("|｜ ")
        declaration = re.sub(r"[*_`]", "", declaration).strip()
        explicit = re.match(
            r"^\s*(?:统计周期|报告周期|会议周期|周报周期|周期|报告周次)\s*[:：|｜]", declaration
        )
        declared = index == 0 or explicit or (index < 8 and re.match(
            r"^\s*(?:\d{4}\s*年?\s*[-－]?\s*[Ww]\d{1,2}|\d{4}\s*年\s*第\s*\d{1,2}\s*周)", declaration
        ))
        if not declared:
            continue
        date_ranges = re.finditer(
            r"(?<!\d)(\d{4})\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})\s*日?\s*"
            r"(?:至|到|~|～|—|–|－)\s*"
            r"(?:(\d{4})\s*[年/-]\s*)?(\d{1,2})\s*[月/-]\s*(\d{1,2})\s*日?(?!\d)",
            declaration,
        )
        found_range = False
        for dates in date_ranges:
            found_range = True
            try:
                begin = date(int(dates[1]), int(dates[2]), int(dates[3]))
                finish = date(int(dates[4] or dates[1]), int(dates[5]), int(dates[6]))
                if begin.isoweekday() != 1 or finish != begin + timedelta(days=6):
                    raise ValueError("统计周期须为周一至周日的完整 ISO 周")
            except ValueError as exc:
                raise WorkflowError(f"纪要第 {index + 1} 行日期范围无效：{exc}", "materials") from exc
            periods.append((index + 1, begin.isocalendar().year, begin.isocalendar().week))
        year_weeks = list(re.finditer(
            r"(?<!\d)(\d{4})\s*(?:年\s*第\s*(\d{1,2})\s*周|年?\s*[-－]?\s*[Ww]\s*(\d{1,2}))(?!\d)",
            declaration,
        ))
        for bare_week in re.finditer(r"第\s*\d{1,2}\s*周", declaration):
            if not any(match.start() <= bare_week.start() and bare_week.end() <= match.end()
                       for match in year_weeks):
                raise WorkflowError(f"纪要第 {index + 1} 行只有周次，缺少年份", "materials")
        for match in year_weeks:
            year, week = int(match[1]), int(match[2] or match[3])
            try:
                date.fromisocalendar(year, week, 1)
            except ValueError as exc:
                raise WorkflowError(f"纪要第 {index + 1} 行 ISO 年周无效", "materials") from exc
            periods.append((index + 1, year, week))
        if explicit and not found_range and not year_weeks:
            raise WorkflowError(f"纪要第 {index + 1} 行统计周期无法识别，请写明 ISO 年周或完整日期范围", "materials")
    if not periods:
        raise WorkflowError("纪要缺少可确认的统计周期，请在标题或统计周期字段写明 ISO 年周", "materials")
    years = {year for _, year, _ in periods if year is not None}
    weeks = {week for _, _, week in periods if week is not None}
    if len(years) > 1 or len(weeks) > 1:
        raise WorkflowError(
            "纪要标题区的年份或周次相互冲突，请核对标题和统计周期："
            + "；".join(f"第{line}行 {year or '?'}年 第{week or '?'}周" for line, year, week in periods),
            "materials",
        )
    year, week = next(iter(years)), next(iter(weeks))
    start = date.fromisocalendar(year, week, 1)
    return {
        "week": week,
        "year": year,
        "period_start": start.isoformat(),
        "period_end": (start + timedelta(days=6)).isoformat(),
        "period_lines": sorted({line for line, _, _ in periods}),
        "sources": [{"id": f"M{i:03}", "text": line} for i, line in enumerate(lines, 1)],
    }


def money(cents):
    return f"{Decimal(cents) / 100:,.0f}"


def ratio(a, b):
    return None if not b else round(a / b * 100, 1)


def change_exceeds(value, previous, threshold):
    """Compare exact cent amounts; one-decimal ratios are only for display."""
    return previous != 0 and Decimal(abs(value - previous) * 100) > Decimal(str(threshold)) * abs(previous)


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
    targets = {}
    for index, row in enumerate(data["targets"], 2):
        try:
            year, week = int(row["year"]), int(str(row["week"]).lstrip("Ww"))
            date.fromisocalendar(year, week, 1)
            cents = amount(row["target"])
            if cents < 0:
                raise ValueError("实收目标不能为负数")
            key = (row["region"], year, week)
            if key in targets:
                raise ValueError("区域、年份和周次规范化后重复，不能覆盖目标")
            targets[key] = cents
        except (ValueError, WorkflowError) as exc:
            raise WorkflowError(
                f"目标表第 {index} 行字段无效：年份={row['year']}，"
                f"周次={row['week']}，实收目标={row['target']}；{exc}", "materials"
            ) from exc
    target_regions = {region for region, year, week in targets if (year, week) == (task.year, task.week)}
    observed_regions = {r["region"] for r in current + old}
    if missing := sorted(observed_regions - target_regions):
        raise WorkflowError("缺少本周实收目标：" + "、".join(missing), "materials")
    store_names = {r["store_id"]: r["store"] for r in data["stores"]}
    duplicate_store_names = {name for name, count in Counter(store_names.values()).items() if count > 1}
    product_names = {r["product_id"]: r["product"] for r in data.get("products", rows)}
    duplicate_product_names = {name for name, count in Counter(product_names.values()).items() if count > 1}

    def display_name(identifier, names, duplicates):
        name = names[identifier]
        return f"{name}（{identifier}）" if name in duplicates else name

    tokens = {}
    groups = []

    def aggregate(key, label, new, prior, dimension, region=None):
        value = sum(r["cents"] for r in new)
        previous = sum(r["cents"] for r in prior)
        cost = sum(r["cost_cents"] for r in new)
        no_current_records = dimension in {"region", "store"} and not new
        target = None
        if dimension == "total":
            target = sum(targets[(region, task.year, task.week)] for region in target_regions)
        elif dimension == "region":
            target = targets[(region, task.year, task.week)]
        change = None if no_current_records else ratio(value - previous, previous)
        crosses_change_threshold = not no_current_records and change_exceeds(value, previous, threshold)
        result = {
            "id": key,
            "label": label,
            "dimension": dimension,
            "cents": value,
            "previous_cents": previous,
            "change": change,
            "margin": ratio(value - cost, value),
            "target_rate": None if no_current_records else ratio(value, target),
            "delivery_share": ratio(sum(r["cents"] for r in new if r["channel"] == delivery_channel), value),
            "target_cents": target,
            "rows": len(new),
            "anomaly": crosses_change_threshold,
            "coverage_status": "本期无记录，待核实" if no_current_records else "有记录",
        }
        for field, val in (
            ("amount", money(value)),
            ("change", "本期无记录，待核实" if no_current_records else
             f"{change:+.1f}%" if change is not None else "上期为零，不适用"),
            ("margin", f"{result['margin']:.1f}%" if result["margin"] is not None else "不适用"),
            ("target", f"{result['target_rate']:.1f}%" if result["target_rate"] is not None else "不适用"),
        ):
            tokens[f"{key}_{field}"] = val
        return result

    total = aggregate("total", "全公司", current, old, "total")
    for dimension in ("region", "store", "category"):
        field = "store_id" if dimension == "store" else dimension
        labels = {r[field] for r in current + old}
        if dimension == "region":
            labels |= target_regions
        for identifier in sorted(labels):
            label = (display_name(identifier, store_names, duplicate_store_names)
                     if dimension == "store" else identifier)
            groups.append(
                aggregate(
                    f"g{len(groups)}",
                    label,
                    [r for r in current if r[field] == identifier],
                    [r for r in old if r[field] == identifier],
                    dimension,
                    region=identifier if dimension == "region" else None,
                )
            )
    top = {}
    for row in current:
        top[row["product_id"]] = top.get(row["product_id"], 0) + row["cents"]
    anomalies = [g for g in groups if g["dimension"] in {"region", "store"} and g["anomaly"]]
    removed = [r for r in data["removed"] if str(start) <= r["date"] <= str(end)]
    returns = [r for r in current if r["cents"] < 0]
    missing_days = []
    for store_id in sorted({r["store_id"] for r in current + old}):
        seen = {r["date"] for r in current if r["store_id"] == store_id}
        for n in range(7):
            day = (start + timedelta(days=n)).isoformat()
            if day not in seen:
                missing_days.append({
                    "store_id": store_id,
                    "store": display_name(store_id, store_names, duplicate_store_names),
                    "date": day,
                })
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
            profit_now = sales_now - sum(r["cost_cents"] for r in a)
            profit_old = sales_old - sum(r["cost_cents"] for r in b)
            now = ratio(profit_now, sales_now)
            before = ratio(profit_old, sales_old)
            raw_drop = (
                (Decimal(profit_old) / sales_old)
                - (Decimal(profit_now) / sales_now)
            ) * 100 if sales_now and sales_old else None
            if raw_drop is not None and raw_drop > Decimal(str(margin_drop_points)):
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
            {"product_id": p, "product": display_name(p, product_names, duplicate_product_names), "cents": v}
            for p, v in sorted(top.items(), key=lambda x: (-x[1], x[0]))[:5]
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
