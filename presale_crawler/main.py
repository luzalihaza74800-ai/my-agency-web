#!/usr/bin/env python3
"""
台灣預售建案爬蟲 — 命令列介面

用法範例:
    # 查詢台中市西屯區預售建案備查（預設）
    python -m presale_crawler

    # 查詢台北市信義區預售屋買賣
    python -m presale_crawler --city 台北市 --district 信義區 --type presale

    # 查詢所有可用縣市
    python -m presale_crawler --list-cities

    # 查詢台中市所有區域
    python -m presale_crawler --list-towns --city 台中市
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from presale_crawler.adapter import normalize, get_csv_headers
from presale_crawler.exporter import to_csv, to_json
from presale_crawler.scraper import (
    list_cities,
    list_towns,
    lookup_city,
    query_presale_projects,
)

logger = logging.getLogger("presale_crawler")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="presale_crawler",
        description="台灣預售建案爬蟲 — 爬取內政部實價登錄網站資料",
    )
    p.add_argument("--city", default="台中市", help="縣市名稱（預設：台中市）")
    p.add_argument("--district", default="西屯區", help="鄉鎮市區名稱（預設：西屯區）")
    p.add_argument(
        "--type",
        dest="query_type",
        default="saleremark",
        choices=["saleremark", "presale", "biz", "rent"],
        help="查詢類型: saleremark=預售屋建案備查, presale=預售屋買賣, biz=不動產買賣, rent=不動產租賃",
    )
    p.add_argument("--start-year", type=int, default=None, help="起始民國年（預設：去年）")
    p.add_argument("--start-month", type=int, default=1, help="起始月份（預設：1）")
    p.add_argument("--end-year", type=int, default=None, help="結束民國年（預設：今年）")
    p.add_argument("--end-month", type=int, default=12, help="結束月份（預設：12）")
    p.add_argument("--output", "-o", default=None, help="輸出檔案路徑（.csv 或 .json）")
    p.add_argument("--format", choices=["csv", "json", "both"], default="both", help="輸出格式")
    p.add_argument("--raw", action="store_true", help="輸出原始 API 欄位（不轉換）")
    p.add_argument("--list-cities", action="store_true", help="列出所有可查詢的縣市")
    p.add_argument("--list-towns", action="store_true", help="列出指定縣市下的鄉鎮市區")
    p.add_argument("-v", "--verbose", action="store_true", help="顯示詳細日誌")
    return p


def _run_list_cities() -> None:
    cities = list_cities()
    print(f"\n可查詢的縣市（共 {len(cities)} 個）：")
    for c in cities:
        print(f"  {c['title']}（代碼：{c['code']}）")


def _run_list_towns(city: str) -> None:
    city_code = lookup_city(city)
    towns = list_towns(city_code)
    print(f"\n{city} 的鄉鎮市區（共 {len(towns)} 個）：")
    for t in towns:
        print(f"  {t['title']}（代碼：{t['code']}）")


def _default_output_name(city: str, district: str, query_type: str) -> str:
    safe_city = city.replace("臺", "台")
    return f"presale_{safe_city}_{district}_{query_type}"


async def _run_query(args: argparse.Namespace) -> None:
    data = await query_presale_projects(
        city=args.city,
        town=args.district,
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=args.end_year,
        end_month=args.end_month,
        query_type=args.query_type,
    )

    if not data:
        print("\n查無資料。請確認縣市/區域名稱是否正確，或調整查詢期間。")
        return

    print(f"\n共取得 {len(data)} 筆資料")

    if args.raw:
        records = data
    else:
        records = normalize(data, args.query_type)

    _print_summary(records, args.query_type)

    base_name = args.output or _default_output_name(
        args.city, args.district, args.query_type
    )

    if args.format in ("csv", "both"):
        csv_path = base_name if base_name.endswith(".csv") else f"{base_name}.csv"
        to_csv(records, csv_path)
        print(f"已匯出 CSV：{csv_path}")

    if args.format in ("json", "both"):
        json_path = base_name if base_name.endswith(".json") else f"{base_name}.json"
        to_json(records, json_path)
        print(f"已匯出 JSON：{json_path}")


def _print_summary(records: list[dict], query_type: str) -> None:
    """印出前幾筆資料的摘要。"""
    print("\n" + "=" * 70)
    type_names = {
        "saleremark": "預售屋建案備查",
        "presale": "預售屋買賣",
        "biz": "不動產買賣",
        "rent": "不動產租賃",
    }
    print(f"查詢類型：{type_names.get(query_type, query_type)}")
    print(f"資料筆數：{len(records)}")
    print("=" * 70)

    preview_count = min(10, len(records))
    print(f"\n前 {preview_count} 筆資料預覽：")
    print("-" * 70)

    if query_type == "saleremark":
        for i, r in enumerate(records[:preview_count], 1):
            name = r.get("建案名稱", r.get("project_name", ""))
            addr = r.get("基地位置", r.get("address", ""))
            company = r.get("申報人/公司", r.get("applicant_company", ""))
            houses = r.get("戶數", r.get("house_count", ""))
            material = r.get("主要建材", r.get("construction_type", ""))
            print(f"  {i:3d}. {name}")
            print(f"       位置：{addr}")
            print(f"       建商：{company}　戶數：{houses}　建材：{material}")
            print()
    elif query_type == "presale":
        for i, r in enumerate(records[:preview_count], 1):
            addr = r.get("建物區段門牌", r.get("address", ""))
            name = r.get("建案名稱", r.get("building_name", ""))
            price = r.get("總價(元)", r.get("total_price", ""))
            unit_price = r.get("單價(元/坪)", r.get("unit_price", ""))
            area = r.get("總面積(坪)", r.get("area", ""))
            print(f"  {i:3d}. {name} — {addr}")
            print(f"       總價：{price} 元　單價：{unit_price} 元/坪　面積：{area} 坪")
            print()
    else:
        for i, r in enumerate(records[:preview_count], 1):
            first_key = list(r.keys())[0]
            second_key = list(r.keys())[1] if len(r) > 1 else first_key
            print(f"  {i:3d}. {r[first_key]} — {r[second_key]}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_cities:
        _run_list_cities()
        return

    if args.list_towns:
        _run_list_towns(args.city)
        return

    asyncio.run(_run_query(args))


if __name__ == "__main__":
    main()
