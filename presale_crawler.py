#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內政部實價登錄網 — 預售屋建案備查（saleRemark）列表爬蟲。

重點：官網在 loadQueryPrice / loadQueryPrice2 會檢查 navigator.webdriver，
Selenium 預設為 true 時會直接 return，永遠不發查詢。Playwright 一般不暴露
webdriver 旗標，並依使用者流程切換「預售屋建案備查」後再查詢。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://lvr.land.moi.gov.tw/jsp/list.jsp"
CITY_API = "https://lvr.land.moi.gov.tw/SERVICE/CITY"

# 官網縣市名稱為「臺中市」；常見別名對應
_CITY_ALIASES = {
    "台中市": "臺中市",
    "台北市": "臺北市",
    "台南市": "臺南市",
    "台東縣": "臺東縣",
}


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_city_town_codes(city: str, district: str) -> tuple[str, str]:
    """回傳 (city_code, town_code)，供 select value 使用。"""
    canon_city = _CITY_ALIASES.get(city, city)
    cities = _fetch_json(CITY_API)
    city_code = None
    for c in cities:
        if c.get("title") == canon_city and c.get("use"):
            city_code = c["code"]
            break
    if not city_code:
        raise ValueError(f"找不到縣市：{city}（請用與網站一致的名稱，例如「臺中市」）")

    towns = _fetch_json(f"https://lvr.land.moi.gov.tw/SERVICE/CITY/{city_code}/")
    town_code = None
    for t in towns:
        if t.get("title") == district and t.get("use"):
            town_code = t["code"]
            break
    if not town_code:
        raise ValueError(f"在 {canon_city} 找不到鄉鎮市區：{district}")

    return city_code, town_code


def _wait_query_result(page: Page, timeout_ms: int = 120_000) -> None:
    """等待預售建案列載入（至少一筆 a.a_link），或明確顯示查無資料。"""
    page.wait_for_function(
        """() => {
            const tb = document.querySelector('#table-item-tbody');
            if (!tb) return false;
            if (tb.innerText.includes('查無資料')) return true;
            return tb.querySelectorAll('a.a_link').length > 0;
        }""",
        timeout=timeout_ms,
    )


def _collect_current_page_rows(page: Page) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in page.locator("#table-item-tbody tr[role='row']").all():
        cells = [c.inner_text().strip().replace("\n", " ") for c in tr.locator("td").all()]
        if cells and cells[0] not in ("無資料", "查無資料"):
            rows.append(cells)
    return rows


def _click_next_if_any(page: Page) -> bool:
    """DataTables 下一頁；若無下一頁則回傳 False。"""
    nxt = page.locator("li.paginate_button.next:not(.disabled) a")
    if nxt.count() == 0:
        return False
    nxt.first.click()
    page.wait_for_timeout(600)
    return True


def crawl_presale_remark(
    city: str,
    district: str,
    *,
    headless: bool = True,
    out_csv: Path | None = None,
    out_json: Path | None = None,
) -> list[dict[str, Any]]:
    all_rows_matrix: list[list[str]] = []

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
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            try {
                if (!localStorage.getItem('form-data')) {
                    localStorage.setItem(
                        'form-data',
                        JSON.stringify({qryType: 'biz', ptype: '1,2,3,4,5'}),
                    );
                }
            } catch (e) {}
            """
        )
        page = context.new_page()
        page.set_default_timeout(120_000)
        page.set_viewport_size({"width": 1440, "height": 900})

        city_code, town_code = resolve_city_town_codes(city, district)

        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_function(
            """() => typeof window.$ !== 'undefined'
            && typeof window.changeType === 'function'
            && $.fn.DataTable
            && $.fn.DataTable.isDataTable('#price_table')
            && typeof window.table !== 'undefined'"""
        )

        # 與點「預售屋建案備查」分頁相同
        page.evaluate("changeType('saleRemark')")
        page.wait_for_timeout(500)

        page.wait_for_function(
            """() => {
                const s = document.querySelector('#l_city');
                return s && s.options && s.options.length > 1;
            }"""
        )

        with page.expect_response(
            lambda r: r.ok and f"/SERVICE/CITY/{city_code}/" in r.url,
            timeout=60_000,
        ):
            page.select_option("#l_city", value=city_code)

        page.wait_for_function(
            """() => {
                const s = document.querySelector('#l_town');
                return s && s.options && s.options.length > 1;
            }"""
        )
        page.select_option("#l_town", value=town_code)
        page.wait_for_timeout(400)

        # 「查詢」在側邊選單 #theMenu 內；點擊後以 AJAX 載入列表
        page.evaluate(
            """() => {
                const b = document.querySelector('#theMenu button.filter_button')
                    || document.querySelector('button.filter_button');
                if (b) b.click();
            }"""
        )

        _wait_query_result(page)

        for _ in range(500):
            all_rows_matrix.extend(_collect_current_page_rows(page))
            if not _click_next_if_any(page):
                break

        browser.close()

    # 預設表頭（與 saleRemark 模式一致，見官網 changeType）
    headers = [
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

    records: list[dict[str, Any]] = []
    for cells in all_rows_matrix:
        rec: dict[str, Any] = {}
        for i, h in enumerate(headers):
            rec[h] = cells[i] if i < len(cells) else ""
        records.append(rec)

    if out_csv:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            for r in records:
                w.writerow({k: r.get(k, "") for k in headers})

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="預售屋建案備查列表（內政部實價網）")
    parser.add_argument("--city", default="台中市", help="縣市名稱（與下拉選單一致）")
    parser.add_argument("--district", default="西屯區", help="鄉鎮市區（與下拉選單一致）")
    parser.add_argument("--csv", type=Path, default=Path("output/presale_xitun.csv"))
    parser.add_argument("--json", type=Path, default=Path("output/presale_xitun.json"))
    parser.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗（除錯用）")
    args = parser.parse_args()

    t0 = time.perf_counter()
    rows = crawl_presale_remark(
        args.city,
        args.district,
        headless=not args.headed,
        out_csv=args.csv,
        out_json=args.json,
    )
    elapsed = time.perf_counter() - t0

    print(f"筆數: {len(rows)}")
    print(f"已寫入: {args.csv} , {args.json}")
    print(f"耗時: {elapsed:.1f}s")
    for i, r in enumerate(rows[:5], 1):
        name = r.get("建案名稱", "")
        print(f"  {i}. {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
