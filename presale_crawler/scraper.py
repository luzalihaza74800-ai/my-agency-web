"""
台灣預售建案爬蟲 — 核心抓取模組

透過 Playwright 操作內政部實價登錄網站 (lvr.land.moi.gov.tw)，
模擬使用者選擇縣市/區域後送出查詢，再攔截 SERVICE/QueryPrice
的 API 回應取得結構化資料。
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from datetime import datetime
from typing import Literal

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

QueryType = Literal["biz", "rent", "presale", "saleremark"]

QUERY_TYPE_TAB_IDS: dict[QueryType, str] = {
    "biz": "pills-sale-tab",
    "rent": "pills-rent-tab",
    "presale": "pills-presale-tab",
    "saleremark": "pills-saleremark-tab",
}

BASE_URL = "https://lvr.land.moi.gov.tw"


def _fetch_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def lookup_city(city_name: str) -> str:
    """將縣市名稱轉換為代碼（例如「台中市」→「B」）。"""
    cities = _fetch_json(f"{BASE_URL}/SERVICE/CITY")
    normalized = city_name.replace("台", "臺")
    for c in cities:
        if c["title"] == normalized or c["title"] == city_name:
            return c["code"]
    available = [c["title"] for c in cities]
    raise ValueError(f"找不到縣市「{city_name}」，可用：{available}")


def lookup_town(city_code: str, town_name: str) -> str:
    """將鄉鎮市區名稱轉換為代碼（例如「西屯區」→「B06」）。"""
    towns = _fetch_json(f"{BASE_URL}/SERVICE/CITY/{city_code}/")
    for t in towns:
        if t["title"] == town_name:
            return t["code"]
    available = [t["title"] for t in towns]
    raise ValueError(f"找不到鄉鎮市區「{town_name}」，可用：{available}")


def list_cities() -> list[dict]:
    """取得所有可查詢的縣市清單。"""
    return _fetch_json(f"{BASE_URL}/SERVICE/CITY")


def list_towns(city_code: str) -> list[dict]:
    """取得指定縣市下的所有鄉鎮市區清單。"""
    return _fetch_json(f"{BASE_URL}/SERVICE/CITY/{city_code}/")


async def query_presale_projects(
    city: str = "台中市",
    town: str = "西屯區",
    start_year: int | None = None,
    start_month: int = 1,
    end_year: int | None = None,
    end_month: int = 12,
    query_type: QueryType = "saleremark",
) -> list[dict]:
    """
    查詢預售建案資料。

    Args:
        city: 縣市名稱（例如「台中市」）
        town: 鄉鎮市區名稱（例如「西屯區」），留空則查全縣市
        start_year: 起始民國年（預設去年）
        start_month: 起始月份
        end_year: 結束民國年（預設今年）
        end_month: 結束月份
        query_type: 查詢類型（saleremark=預售屋建案, presale=預售屋買賣,
                    biz=不動產買賣, rent=不動產租賃）

    Returns:
        包含建案/交易資料的 dict 列表
    """
    if query_type not in QUERY_TYPE_TAB_IDS:
        raise ValueError(
            f"query_type 須為 {list(QUERY_TYPE_TAB_IDS)} 之一，"
            f"收到：{query_type!r}"
        )

    current_roc_year = datetime.now().year - 1911
    if end_year is None:
        end_year = current_roc_year
    if start_year is None:
        start_year = current_roc_year - 1

    city_code = await asyncio.to_thread(lookup_city, city)
    town_code = (
        await asyncio.to_thread(lookup_town, city_code, town) if town else ""
    )
    logger.info("查詢：%s（%s）%s [%s]", city, city_code, f"/ {town}" if town else "", query_type)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context()
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        page = await context.new_page()

        try:
            await page.goto(BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            frame = next(f for f in page.frames if "index.jsp" in f.url)

            tab_id = QUERY_TYPE_TAB_IDS[query_type]
            await frame.evaluate(
                "(tabId) => { document.querySelector('#' + tabId).click(); }",
                tab_id,
            )
            await page.wait_for_timeout(500)

            await frame.evaluate(
                """(cityCode) => {
                    var el = document.querySelector("#p_city");
                    el.value = cityCode;
                    el.dispatchEvent(new Event("change", {bubbles: true}));
                }""",
                city_code,
            )

            if town_code:
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

            async with page.expect_response(
                lambda r: "SERVICE/QueryPrice" in r.url and r.status == 200,
                timeout=30000,
            ) as response_info:
                await frame.evaluate("""() => {
                    var btn = document.querySelector(".form-button[go_type='list']");
                    if (btn) btn.click();
                }""")
                logger.info("已送出查詢，等待 API 回應…")

            response = await response_info.value
            data = await response.json()

        finally:
            await context.close()
            await browser.close()

    if not isinstance(data, list):
        raise RuntimeError(f"QueryPrice 回應格式非預期：{type(data).__name__}")

    logger.info("取得 %d 筆結果", len(data))
    return data
