"""Deterministic fictional 2025 retail fixtures; no real business or news claims."""

import csv
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/synthetic-2025"
OUT.mkdir(exist_ok=True)
rng = random.Random(2025)
stores = [
    ["S01", "模拟上海店", "华东"],
    ["S02", "模拟广州店", "华南"],
    ["S03", "模拟北京店", "华北"],
    ["S04", "模拟成都店", "西南"],
]
products = [
    ["P01", "模拟拿铁", "饮品"],
    ["P02", "模拟美式", "饮品"],
    ["P03", "模拟吐司", "面包"],
    ["P04", "模拟蛋糕", "蛋糕"],
    ["P05", "模拟曲奇", "点心"],
]
headers = ["record_id", "date", "store_id", "product_id", "channel", "quantity", "amount", "cost"]
rows = []
truth = defaultdict(lambda: {"cents": 0, "return_cents": 0, "returns": 0, "rows": 0})
day = date(2024, 12, 23)
while day <= date(2026, 1, 4):
    for i, store in enumerate(stores):
        if (store[0] == "S01" and date(2025, 3, 10) <= day <= date(2025, 3, 12)) or (
            store[0] == "S02" and day == date(2025, 6, 18)
        ):
            continue
        for j, product in enumerate(products):
            for channel in ["堂食自提", "外卖"]:
                qty = rng.randint(5, 20)
                price = [2600, 2000, 1200, 3800, 1800][j]
                if day.weekday() >= 5:
                    qty += 5
                if day.month == 10 and store[0] == "S03":
                    qty += 7
                if day.day == 15 and j == 3 and channel == "堂食自提":
                    qty = -2
                cents = qty * price
                cost = qty * (price // 3)
                row = [
                    f"SIM-{len(rows):06}",
                    str(day),
                    store[0],
                    product[0],
                    channel,
                    qty,
                    cents / 100,
                    cost / 100,
                ]
                rows.append(row)
                y, w, _ = day.isocalendar()
                t = truth[f"{y}W{w:02}"]
                t["cents"] += cents
                t["rows"] += 1
                if qty < 0:
                    t["returns"] += 1
                    t["return_cents"] += cents
    day += timedelta(days=1)
unique = len(rows)
rows.extend([r.copy() for r in rows if r[1] == "2025-09-09"][:29])
targets = [
    [s[2], y, w, 45000] for y, w in sorted({tuple(map(int, k.split("W"))) for k in truth}) for s in stores
]
sheets = {
    "销售明细": [headers] + rows,
    "门店资料": [["store_id", "store", "region"]] + stores,
    "商品资料": [["product_id", "product", "category"]] + products,
    "目标": [["region", "year", "week", "target"]] + targets,
}
(OUT / "workbook.json").write_text(json.dumps(sheets, ensure_ascii=False), encoding="utf-8")
(OUT / "expected.json").write_text(
    json.dumps(
        {"seed": 2025, "simulation": True, "unique_rows": unique, "duplicate_rows": 29, "weeks": truth},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
with (OUT / "模拟销售2025.csv").open("w", encoding="utf-8-sig", newline="") as f:
    csv.writer(f).writerows([headers] + rows)
for key in truth:
    y, w = map(int, key.split("W"))
    if y != 2025:
        continue
    start = date.fromisocalendar(y, w, 1)
    end = start + timedelta(days=6)
    text = f"{y}年第{w}周周会纪要\n统计周期：{start} 至 {end}\n本文件为模拟数据，不代表真实经营或新闻事件。\n门店波动为合成测试数据，原因待核实，不得凭空归因。\n"
    if w == 11:
        text += "模拟上海店3月10日至12日停业测试，无交易记录。\n"
    if w == 25:
        text += "模拟广州店6月18日采集失败，系统缺数，不得估算补账。\n"
    text += "退货以负数直接冲减当期实收。\n下周核对异常门店及缺失记录。\n"
    (OUT / f"纪要_{key}.txt").write_text(text, encoding="utf-8")
(OUT / "错误纪要_2025W11.txt").write_text(
    "2025年第12周周会纪要\n统计周期：2025-03-17 至 2025-03-23\n模拟测试：这是故意错误周次。", encoding="utf-8"
)
conflict = [r.copy() for r in rows[:2]]
conflict[1] = conflict[0].copy()
conflict[1][6] += 1
with (OUT / "冲突重复记录.csv").open("w", encoding="utf-8-sig", newline="") as f:
    csv.writer(f).writerows([headers] + conflict)
(OUT / "说明.txt").write_text(
    "全部为模拟数据。主年度2025-01-01至2025-12-31，另含2024-12-23至12-31及2026-01-01至01-04边界数据用于周环比。4家虚构门店，5种商品，2渠道，种子2025。包含29条相同重复、每月退货、3月停业、6月缺数、10月增长；错误纪要和冲突记录单独提供。CSV须同时上传模拟年度工作簿作为基础资料。不得作为真实新闻核验通过证据。",
    encoding="utf-8",
)
print("Prepared", unique, "unique rows and", len(truth), "ISO periods")
