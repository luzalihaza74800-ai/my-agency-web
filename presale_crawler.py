#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣內政部實價登錄 - 預售建案爬蟲

支援兩種查詢模式：
  1. saleremark - 預售屋建案備查（建案清單，含建案名稱、地址、建商等）
  2. presale    - 預售屋買賣交易（個別交易紀錄，含成交價、坪數等）

使用 Playwright 自動化瀏覽器操作，攔截底層 QueryPrice API 回應取得結構化資料。
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Literal

from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

QueryType = Literal["biz", "rent", "presale", "saleremark"]

QUERY_TAB_IDS: dict[QueryType, str] = {
    "biz": "pills-sale-tab",
    "rent": "pills-rent-tab",
    "presale": "pills-presale-tab",
    "saleremark": "pills-saleremark-tab",
}

SALEREMARK_FIELDS = {
    "name": "建案名稱",
    "addr": "地址",
    "apply": "申報公司",
    "applydate": "申報日期",
    "license": "建造執照",
    "ldate": "執照日期",
    "house": "戶數",
    "ma": "建材",
    "mark": "履約擔保",
    "e": "銷售期間",
    "s": "工程進度",
    "AA11": "使用分區",
    "city": "縣市代碼",
    "town": "鄉鎮代碼",
    "lat": "緯度",
    "lon": "經度",
}

PRESALE_FIELDS = {
    "a": "地址",
    "bn": "建案名稱",
    "bu": "棟號",
    "b": "建物型態",
    "e": "交易日期",
    "tp": "總價_元",
    "p": "單價_元_坪",
    "s": "面積_坪",
    "f": "樓別",
    "j": "房",
    "k": "廳",
    "l": "衛",
    "v": "格局",
    "ma": "建材",
    "cp": "車位總價",
    "t": "交易標的",
    "pu": "用途",
    "m": "管理組織",
    "lat": "緯度",
    "lon": "經度",
    "note": "備註",
}

BIZ_FIELDS = {
    "a": "地址",
    "bn": "社區名稱",
    "b": "建物型態",
    "e": "交易日期",
    "tp": "總價_元",
    "p": "單價_元_坪",
    "s": "面積_坪",
    "bs": "主建物佔比",
    "f": "樓別",
    "j": "房",
    "k": "廳",
    "l": "衛",
    "v": "格局",
    "m": "管理組織",
    "el": "有無電梯",
    "t": "交易標的",
    "note": "備註",
    "lat": "緯度",
    "lon": "經度",
}

RENT_FIELDS = {
    "a": "地址",
    "bn": "社區名稱",
    "b": "建物型態",
    "e": "交易日期",
    "tp": "租金_元",
    "p": "單價_元_坪",
    "s": "面積_坪",
    "f": "樓別",
    "v": "格局",
    "rperiod": "租賃期間",
    "rtype": "租賃型態",
    "fn": "附屬設備",
    "lat": "緯度",
    "lon": "經度",
    "note": "備註",
}

FIELD_MAPS: dict[QueryType, dict] = {
    "saleremark": SALEREMARK_FIELDS,
    "presale": PRESALE_FIELDS,
    "biz": BIZ_FIELDS,
    "rent": RENT_FIELDS,
}

QUERY_TYPE_NAMES: dict[QueryType, str] = {
    "saleremark": "預售屋建案備查",
    "presale": "預售屋買賣",
    "biz": "不動產買賣",
    "rent": "不動產租賃",
}


def fetch_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def lookup_city(city_name: str) -> str:
    cities = fetch_json("https://lvr.land.moi.gov.tw/SERVICE/CITY")
    normalized = city_name.replace("台", "臺")
    for c in cities:
        if c["title"] == normalized or c["title"] == city_name:
            return c["code"]
    available = [c["title"] for c in cities]
    raise ValueError(f"找不到縣市「{city_name}」，可用的有：{available}")


def lookup_town(city_code: str, town_name: str) -> str:
    towns = fetch_json(f"https://lvr.land.moi.gov.tw/SERVICE/CITY/{city_code}/")
    for t in towns:
        if t["title"] == town_name:
            return t["code"]
    available = [t["title"] for t in towns]
    raise ValueError(f"找不到鄉鎮市區「{town_name}」，可用的有：{available}")


async def crawl(
    city: str = "台中市",
    town: str = "西屯區",
    query_type: QueryType = "saleremark",
    start_year: int | None = None,
    start_month: int = 1,
    end_year: int | None = None,
    end_month: int = 12,
) -> list[dict]:
    """
    使用 Playwright 操作瀏覽器查詢實價登錄，
    攔截 SERVICE/QueryPrice API 回應取得原始 JSON 資料。
    """
    current_roc_year = datetime.now().year - 1911
    if end_year is None:
        end_year = current_roc_year
    if start_year is None:
        start_year = current_roc_year - 1

    type_name = QUERY_TYPE_NAMES.get(query_type, query_type)
    logger.info(f"查詢類型：{type_name}")
    logger.info(f"目標區域：{city} {town}")
    logger.info(f"查詢期間：民國 {start_year} 年 {start_month} 月 ～ {end_year} 年 {end_month} 月")

    logger.info("正在查詢縣市/鄉鎮代碼...")
    city_code = await asyncio.to_thread(lookup_city, city)
    town_code = await asyncio.to_thread(lookup_town, city_code, town) if town else ""
    logger.info(f"縣市代碼：{city_code}，鄉鎮代碼：{town_code}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        page = await context.new_page()

        logger.info("正在載入實價登錄首頁...")
        await page.goto("https://lvr.land.moi.gov.tw/", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        frame = None
        for f in page.frames:
            if "index.jsp" in f.url:
                frame = f
                break
        if frame is None:
            raise RuntimeError("找不到 index.jsp iframe，頁面結構可能已變更")

        logger.info(f"切換到「{type_name}」查詢標籤...")
        tab_id = QUERY_TAB_IDS[query_type]
        await frame.evaluate(
            "(tabId) => { document.querySelector('#' + tabId).click(); }",
            tab_id,
        )
        await page.wait_for_timeout(500)

        logger.info("設定縣市...")
        await frame.evaluate(
            """(cityCode) => {
                var el = document.querySelector("#p_city");
                el.value = cityCode;
                el.dispatchEvent(new Event("change", {bubbles: true}));
            }""",
            city_code,
        )

        if town_code:
            logger.info("設定鄉鎮市區...")
            await frame.wait_for_function(
                'document.querySelector("#p_town").options.length > 1'
            )
            await frame.evaluate(
                """(townCode) => {
                    var el = document.querySelector("#p_town");
                    el.value = townCode;
                    el.dispatchEvent(new Event("change", {bubbles: true}));
                }""",
                town_code,
            )

        logger.info("設定查詢期間...")
        await frame.evaluate(
            """(args) => {
                document.querySelector("#p_startY").value = String(args.startYear);
                document.querySelector("#p_startM").value = String(args.startMonth);
                document.querySelector("#p_endY").value = String(args.endYear);
                document.querySelector("#p_endM").value = String(args.endMonth);
            }""",
            {
                "startYear": start_year,
                "startMonth": start_month,
                "endYear": end_year,
                "endMonth": end_month,
            },
        )

        logger.info("送出查詢，等待 API 回應...")
        try:
            async with page.expect_response(
                lambda r: "SERVICE/QueryPrice" in r.url and r.status == 200,
                timeout=45000,
            ) as response_info:
                await frame.evaluate("""() => {
                    var btn = document.querySelector(".form-button[go_type='list']");
                    if (btn) btn.click();
                }""")

            response = await response_info.value
            data = await response.json()
        except Exception as e:
            logger.error(f"查詢失敗：{e}")
            await context.close()
            await browser.close()
            raise

        await context.close()
        await browser.close()

    if not isinstance(data, list):
        raise RuntimeError(f"API 回應格式非預期：{type(data).__name__}")

    logger.info(f"成功取得 {len(data)} 筆資料")
    return data


def to_friendly(records: list[dict], query_type: QueryType) -> list[dict]:
    """將 API 原始 key 轉為中文欄位名稱。"""
    mapping = FIELD_MAPS.get(query_type, {})
    results = []
    for rec in records:
        row = {}
        for raw_key, friendly_name in mapping.items():
            row[friendly_name] = rec.get(raw_key, "")
        results.append(row)
    return results


def save_csv(records: list[dict], filepath: str) -> None:
    if not records:
        logger.warning("沒有資料可儲存")
        return
    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    logger.info(f"已儲存 CSV：{filepath}（{len(records)} 筆）")


def save_json(records: list[dict], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"已儲存 JSON：{filepath}（{len(records)} 筆）")


def print_summary(records: list[dict], query_type: QueryType) -> None:
    """在終端機印出簡要摘要。"""
    if not records:
        print("\n（無資料）")
        return

    type_name = QUERY_TYPE_NAMES.get(query_type, query_type)
    print(f"\n{'='*60}")
    print(f"  {type_name} 查詢結果：共 {len(records)} 筆")
    print(f"{'='*60}")

    if query_type == "saleremark":
        for i, r in enumerate(records, 1):
            name = r.get("建案名稱", "N/A")
            addr = r.get("地址", "N/A")
            company = r.get("申報公司", "N/A")
            houses = r.get("戶數", "N/A")
            material = r.get("建材", "N/A")
            period = r.get("銷售期間", "N/A")
            print(f"\n  [{i:3d}] {name}")
            print(f"        地址：{addr}")
            print(f"        建商：{company}")
            print(f"        戶數：{houses}　建材：{material}")
            print(f"        銷售期間：{period}")

    elif query_type == "presale":
        for i, r in enumerate(records[:20], 1):
            addr = r.get("地址", "N/A")
            bn = r.get("建案名稱", "N/A")
            tp = r.get("總價_元", "N/A")
            p = r.get("單價_元_坪", "N/A")
            area = r.get("面積_坪", "N/A")
            layout = r.get("格局", "N/A")
            print(f"  [{i:3d}] {bn} | {addr}")
            print(f"        總價：{tp} 元　單價：{p} 元/坪　面積：{area} 坪　格局：{layout}")
        if len(records) > 20:
            print(f"\n  ... 還有 {len(records) - 20} 筆（完整資料請查看 CSV/JSON 檔案）")

    elif query_type == "biz":
        for i, r in enumerate(records[:20], 1):
            addr = r.get("地址", "N/A")
            tp = r.get("總價_元", "N/A")
            p = r.get("單價_元_坪", "N/A")
            layout = r.get("格局", "N/A")
            print(f"  [{i:3d}] {addr} | 總價：{tp} | 單價：{p} | {layout}")
        if len(records) > 20:
            print(f"\n  ... 還有 {len(records) - 20} 筆")

    elif query_type == "rent":
        for i, r in enumerate(records[:20], 1):
            addr = r.get("地址", "N/A")
            tp = r.get("租金_元", "N/A")
            layout = r.get("格局", "N/A")
            print(f"  [{i:3d}] {addr} | 租金：{tp} 元 | {layout}")
        if len(records) > 20:
            print(f"\n  ... 還有 {len(records) - 20} 筆")

    print(f"\n{'='*60}\n")


async def main():
    parser = argparse.ArgumentParser(
        description="台灣內政部實價登錄 - 預售建案爬蟲",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  # 查詢台中市西屯區的預售建案備查清單
  python presale_crawler.py --city 台中市 --district 西屯區 --type saleremark

  # 查詢台中市西屯區的預售屋買賣交易
  python presale_crawler.py --city 台中市 --district 西屯區 --type presale

  # 查詢高雄市鹽埕區的買賣案件
  python presale_crawler.py --city 高雄市 --district 鹽埕區 --type biz

  # 指定查詢期間（民國年）
  python presale_crawler.py --city 台中市 --district 西屯區 --type saleremark \\
      --start-year 110 --end-year 115

查詢類型說明：
  saleremark  預售屋建案備查（建案清單）
  presale     預售屋買賣（個別交易紀錄）
  biz         不動產買賣
  rent        不動產租賃
        """,
    )
    parser.add_argument("--city", default="台中市", help="縣市名稱（預設：台中市）")
    parser.add_argument("--district", default="西屯區", help="鄉鎮市區名稱（預設：西屯區）")
    parser.add_argument(
        "--type",
        default="saleremark",
        choices=["saleremark", "presale", "biz", "rent"],
        help="查詢類型（預設：saleremark）",
    )
    parser.add_argument("--start-year", type=int, default=None, help="起始年（民國年，預設：去年）")
    parser.add_argument("--start-month", type=int, default=1, help="起始月（預設：1）")
    parser.add_argument("--end-year", type=int, default=None, help="結束年（民國年，預設：今年）")
    parser.add_argument("--end-month", type=int, default=12, help="結束月（預設：12）")
    parser.add_argument("--output", default=None, help="輸出檔名前綴（預設自動產生）")
    parser.add_argument("--json-only", action="store_true", help="只輸出 JSON")
    parser.add_argument("--csv-only", action="store_true", help="只輸出 CSV")

    args = parser.parse_args()

    raw_data = await crawl(
        city=args.city,
        town=args.district,
        query_type=args.type,
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=args.end_year,
        end_month=args.end_month,
    )

    if not raw_data:
        logger.warning("查詢結果為空，沒有符合條件的資料")
        sys.exit(0)

    friendly_data = to_friendly(raw_data, args.type)
    print_summary(friendly_data, args.type)

    prefix = args.output or f"{args.city}_{args.district}_{args.type}"
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if not args.csv_only:
        save_json(raw_data, str(output_dir / f"{prefix}_raw.json"))
        save_json(friendly_data, str(output_dir / f"{prefix}.json"))

    if not args.json_only:
        save_csv(friendly_data, str(output_dir / f"{prefix}.csv"))

    logger.info("完成！")


if __name__ == "__main__":
    asyncio.run(main())
