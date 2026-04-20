from __future__ import annotations

import csv
import datetime as dt
import math
import re
from pathlib import Path
from statistics import quantiles


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "data" / "taichung_presale_projects.csv"
OUTPUT_CSV = ROOT / "output" / "taichung_presale_strategy_table.csv"
OUTPUT_MD = ROOT / "output" / "taichung_presale_strategy_table.md"


def parse_price_to_wan(raw: str) -> float | None:
    if not raw:
        return None
    cleaned = raw.replace(",", "").strip()
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", cleaned)]
    if not nums:
        return None
    # e.g. 1550~2100萬/戶 -> take midpoint
    return sum(nums) / len(nums)


def parse_completion_date(raw: str) -> dt.date | None:
    if not raw:
        return None
    raw = raw.strip()
    year_match = re.search(r"(\d{4})年", raw)
    if not year_match:
        return None
    year = int(year_match.group(1))

    # 月份格式：2026年08月
    month_match = re.search(r"(\d{1,2})月", raw)
    if month_match and "季度" not in raw:
        month = int(month_match.group(1))
        if not 1 <= month <= 12:
            return None
        day = month_end_day(year, month)
        return dt.date(year, month, day)

    # 季度格式
    if "第一季度" in raw:
        return dt.date(year, 3, 31)
    if "第二季度" in raw:
        return dt.date(year, 6, 30)
    if "第三季度" in raw:
        return dt.date(year, 9, 30)
    if "第四季度" in raw:
        return dt.date(year, 12, 31)

    # 半年格式
    if "上半年" in raw:
        return dt.date(year, 6, 30)
    if "下半年" in raw:
        return dt.date(year, 12, 31)

    return None


def month_end_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    nxt = dt.date(year, month + 1, 1)
    return (nxt - dt.timedelta(days=1)).day


def pick_price_metric_wan(row: dict[str, str]) -> tuple[float | None, str]:
    list_price = parse_price_to_wan(row["list_total_price_raw"])
    if list_price is not None:
        return list_price, "建案總價"
    tx_price = parse_price_to_wan(row["recent_transaction_total_raw"])
    if tx_price is not None:
        return tx_price, "近期成交總價"
    return None, "待補件"


def compute_tier(value: float | None, cuts: tuple[float, float, float, float] | None) -> str:
    if value is None or cuts is None:
        return "待補件"
    q20, q40, q60, q80 = cuts
    if value <= q20:
        return "Tier 1"
    if value <= q40:
        return "Tier 2"
    if value <= q60:
        return "Tier 3"
    if value <= q80:
        return "Tier 4"
    return "Tier 5"


def fmt_date(d: dt.date | None) -> str:
    return d.isoformat() if d else ""


def main() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    enriched: list[dict[str, str | int | float | None]] = []
    numeric_prices: list[float] = []
    today = dt.date.today()

    for row in rows:
        completion_date = parse_completion_date(row["completion_raw"])
        price_metric_wan, price_source = pick_price_metric_wan(row)
        if price_metric_wan is not None:
            numeric_prices.append(price_metric_wan)

        days_to_completion: int | None = None
        focus_6m = "待補件"
        if completion_date is not None:
            days_to_completion = (completion_date - today).days
            if days_to_completion < 0:
                focus_6m = "已完工"
            elif days_to_completion <= 183:
                focus_6m = "★重點"
            else:
                focus_6m = "否"

        enriched.append(
            {
                "建案名稱": row["project_name"],
                "行政區": row["district"],
                "價格指標(萬/戶)": price_metric_wan,
                "價格來源": price_source,
                "預計完工日": completion_date,
                "距完工天數": days_to_completion,
                "半年內完工標注": focus_6m,
                "銷售狀態": row["sales_status"],
                "資料來源": row["source_url"],
            }
        )

    cuts: tuple[float, float, float, float] | None = None
    if len(numeric_prices) >= 5:
        q = quantiles(sorted(numeric_prices), n=5, method="inclusive")
        cuts = (q[0], q[1], q[2], q[3])

    for row in enriched:
        row["價格階段"] = compute_tier(
            row["價格指標(萬/戶)"] if isinstance(row["價格指標(萬/戶)"], float) else None,
            cuts,
        )

    def sort_key(r: dict[str, str | int | float | None]) -> tuple[int, dt.date, str]:
        d = r["預計完工日"]
        if isinstance(d, dt.date):
            return (0, d, str(r["建案名稱"]))
        return (1, dt.date.max, str(r["建案名稱"]))

    enriched.sort(key=sort_key)

    headers = [
        "建案名稱",
        "行政區",
        "價格指標(萬/戶)",
        "價格來源",
        "價格階段",
        "預計完工日",
        "距完工天數",
        "半年內完工標注",
        "銷售狀態",
        "資料來源",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in enriched:
            out = dict(r)
            out["預計完工日"] = fmt_date(r["預計完工日"] if isinstance(r["預計完工日"], dt.date) else None)
            price = r["價格指標(萬/戶)"]
            out["價格指標(萬/戶)"] = f"{price:.1f}" if isinstance(price, float) else ""
            days = r["距完工天數"]
            out["距完工天數"] = str(days) if isinstance(days, int) else ""
            writer.writerow(out)

    with OUTPUT_MD.open("w", encoding="utf-8") as f:
        f.write("# 台中市預售屋開發主表（含半年內完工重點）\n\n")
        f.write(f"- 產表日期：{today.isoformat()}\n")
        f.write("- 判定規則：0~183天為★重點，<0天為已完工。\n")
        f.write("- 價格指標優先順序：建案總價 > 近期成交總價。\n\n")
        f.write("| 建案名稱 | 行政區 | 價格指標(萬/戶) | 價格來源 | 價格階段 | 預計完工日 | 距完工天數 | 半年內完工標注 | 銷售狀態 |\n")
        f.write("|---|---|---:|---|---|---|---:|---|---|\n")
        for r in enriched:
            price = r["價格指標(萬/戶)"]
            price_str = f"{price:.1f}" if isinstance(price, float) else ""
            d = r["預計完工日"]
            d_str = d.isoformat() if isinstance(d, dt.date) else ""
            days = r["距完工天數"]
            days_str = str(days) if isinstance(days, int) else ""
            f.write(
                f"| {r['建案名稱']} | {r['行政區']} | {price_str} | {r['價格來源']} | "
                f"{r['價格階段']} | {d_str} | {days_str} | {r['半年內完工標注']} | {r['銷售狀態']} |\n"
            )


if __name__ == "__main__":
    main()
