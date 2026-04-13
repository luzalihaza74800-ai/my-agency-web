#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內政部實價登錄「預售屋建案備查」清單爬蟲。

重點：list.jsp 內 loadQueryPrice() / loadQueryPrice2() 會檢查
`navigator.webdriver`，若為 true 則不執行查詢，因此一般 Selenium
會永遠拿不到 tbody 資料。此腳本在頁面初始化前將 webdriver 設為 undefined，
並沿用網站既有的 localStorage「form-data」與 loadQueryPrice() 流程。

縣市／鄉鎮代碼可透過：
  GET https://lvr.land.moi.gov.tw/SERVICE/CITY
  GET https://lvr.land.moi.gov.tw/SERVICE/CITY/{縣市代碼}/
查得（例：臺中市 B、西屯區 B06）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


@dataclass
class ResolvedArea:
    city_code: str
    town_code: str
    city_title: str
    town_title: str


def _fetch_json(url: str) -> Any:
    req = urlopen(url, timeout=60)
    try:
        return json.loads(req.read().decode("utf-8"))
    finally:
        req.close()


def normalize_name(s: str) -> str:
    return s.strip().replace("台", "臺")


def resolve_area(city: str, district: str) -> ResolvedArea:
    city_n = normalize_name(city)
    dist_n = normalize_name(district)
    cities = _fetch_json("https://lvr.land.moi.gov.tw/SERVICE/CITY")
    city_code = None
    city_title = None
    for c in cities:
        if not c.get("use", True):
            continue
        title = c.get("title", "")
        if title == city_n or title == city:
            city_code = c["code"]
            city_title = title
            break
    if not city_code:
        raise ValueError(f"找不到縣市：{city}（已嘗試正規化為「{city_n}」）")

    towns = _fetch_json(f"https://lvr.land.moi.gov.tw/SERVICE/CITY/{city_code}/")
    town_code = None
    town_title = None
    for t in towns:
        if not t.get("use", True):
            continue
        title = t.get("title", "")
        if title == dist_n or title == district:
            town_code = t["code"]
            town_title = title
            break
    if not town_code:
        raise ValueError(f"找不到行政區：{district}（縣市 {city_title}）")

    return ResolvedArea(
        city_code=city_code,
        town_code=town_code,
        city_title=city_title or city,
        town_title=town_title or district,
    )


def build_form_data(
    area: ResolvedArea,
    starty: str,
    startm: str,
    endy: str,
    endm: str,
) -> dict[str, Any]:
    return {
        "qryType": "saleRemark",
        "city": area.city_code,
        "town": area.town_code,
        "ptype": "1,2",
        "starty": starty,
        "startm": startm,
        "endy": endy,
        "endm": endm,
        "tmoney_unit": "1",
        "pmoney_unit": "1",
        "unit": "2",
    }


def crawl_presale_cases(
    form_data: dict[str, Any],
    *,
    headless: bool = True,
    base_url: str = "https://lvr.land.moi.gov.tw/jsp/list.jsp",
    page_delay_ms: int = 400,
) -> tuple[list[list[str]], dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    rows_out: list[list[str]] = []
    table_info: dict[str, Any] = {}

    fd_json = json.dumps(form_data, ensure_ascii=False)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="zh-TW",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = context.new_page()
        page.add_init_script(f"localStorage.setItem('form-data', {json.dumps(fd_json)});")

        page.goto(base_url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2000)
        page.locator("a[href='#pills-saleremark']").first.click()
        page.wait_for_timeout(500)
        page.locator("#l_city").select_option(form_data["city"])
        page.wait_for_timeout(1500)
        page.locator("#l_town").select_option(form_data["town"])
        page.wait_for_timeout(500)
        page.evaluate("() => loadQueryPrice()")
        page.wait_for_selector("#table-item-tbody tr", timeout=120000)

        table_info = page.evaluate(
            """() => {
            const pi = table.page.info();
            return {
                recordsTotal: pi.recordsTotal,
                recordsDisplay: pi.recordsDisplay,
                pages: pi.pages,
                pageLen: table.page.len(),
            };
        }"""
        )

        total_pages = int(table_info.get("pages") or 1)
        for pi in range(total_pages):
            page.evaluate(f"() => {{ table.page({pi}).draw(false); }}")
            page.wait_for_timeout(page_delay_ms)
            batch = page.evaluate(
                """() => {
                const rows = [];
                document.querySelectorAll('#table-item-tbody tr').forEach((tr) => {
                    const cells = [];
                    tr.querySelectorAll('td').forEach((td) => {
                        cells.push((td.innerText || '').trim().replace(/\\s+/g, ' '));
                    });
                    if (cells.length) rows.push(cells);
                });
                return rows;
            }"""
            )
            rows_out.extend(batch)

        browser.close()

    return rows_out, table_info


# 與 list.jsp changeType('saleRemark') 之 table_head 欄位順序一致
SALE_REMARK_HEADERS = [
    "建案名稱",
    "坐落街道",
    "起造人",
    "層棟戶數",
    "使用分區",
    "主要用途",
    "主要建材",
    "申報備查期間",
    "自銷售期間",
    "代銷售期間",
    "坐落基地",
    "建照核發日期",
    "建造執照",
    "完成建物第一次登記日期",
    "詳細內容",
    "功能",
    "備註",
]


def write_csv(path: str, rows: list[list[str]], *, write_header: bool = True) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if write_header and rows:
            w.writerow(SALE_REMARK_HEADERS)
        for r in rows:
            w.writerow(r)


def main() -> int:
    parser = argparse.ArgumentParser(description="預售屋建案備查清單（內政部實價登錄）")
    parser.add_argument("--city", default="臺中市", help="縣市名稱（預設：臺中市）")
    parser.add_argument("--district", default="西屯區", help="鄉鎮市區（預設：西屯區）")
    parser.add_argument("--starty", default="110", help="申報備查期間：起始年（民國）")
    parser.add_argument("--startm", default="7", help="起始月")
    parser.add_argument("--endy", default="115", help="迄年（民國）")
    parser.add_argument("--endm", default="4", help="迄月")
    parser.add_argument(
        "--output",
        "-o",
        default="presale_cases.csv",
        help="輸出 CSV 路徑",
    )
    parser.add_argument("--no-header", action="store_true", help="CSV 不寫入欄位標題列")
    parser.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗（除錯用）")
    args = parser.parse_args()

    try:
        area = resolve_area(args.city, args.district)
    except (HTTPError, URLError, ValueError) as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1

    form = build_form_data(area, args.starty, args.startm, args.endy, args.endm)
    print(
        f"查詢：{area.city_title} {area.town_title} "
        f"({form['city']}/{form['town']}) "
        f"期間 {form['starty']}/{form['startm']}～{form['endy']}/{form['endm']}"
    )

    rows, info = crawl_presale_cases(form, headless=not args.headed)
    total = info.get("recordsTotal")
    print(
        f"DataTables：共 {total} 筆，"
        f"{info.get('pages', '?')} 頁，每頁 {info.get('pageLen', '?')} 筆；"
        f"匯出列數 {len(rows)}"
    )
    if total is not None and len(rows) != int(total):
        print(
            f"警告：匯出列數與伺服器筆數不一致（{len(rows)} != {total}）。",
            file=sys.stderr,
        )

    write_csv(args.output, rows, write_header=not args.no_header)
    print(f"已寫入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
