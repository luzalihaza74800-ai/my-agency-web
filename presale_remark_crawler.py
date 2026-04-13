#!/usr/bin/env python3
"""抓取內政部實價登錄「預售屋建案備查」清單資料。"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select


DEFAULT_QUERY = {
    "qryType": "saleRemark",
    "city": "",
    "town": "",
    "starty": "110",
    "startm": "7",
    "endy": "115",
    "endm": "12",
    "tmoney_unit": "1",
    "pmoney_unit": "1",
    "unit": "2",
    "ptype": "1,2,4,5",
}

TABLE_COLUMNS = [
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


@dataclass
class QueryTarget:
    city: str
    district: str
    city_code: str
    district_code: str


class PresaleRemarkCrawler:
    def __init__(self, headless: bool = True) -> None:
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=zh-TW")
        options.binary_location = "/usr/local/bin/google-chrome"
        self.driver = webdriver.Chrome(options=options)

    def close(self) -> None:
        self.driver.quit()

    def _sleep(self, seconds: float = 1.0) -> None:
        # 站方頁面靠多段前端初始化，固定短暫等待比顯式條件更穩。
        self.driver.implicitly_wait(0)
        time.sleep(seconds)

    def _wait_for_table_count(self, timeout: float = 30.0) -> int:
        deadline = time.time() + timeout
        last_count = 0
        while time.time() < deadline:
            last_count = self.driver.execute_script(
                "return (typeof table !== 'undefined' && table && table.data) "
                "? table.data().count() : 0"
            )
            if last_count > 0:
                return last_count
            time.sleep(1)
        raise RuntimeError(f"查詢逾時，資料表筆數仍為 {last_count}")

    def _bootstrap_page(self, query: dict[str, str]) -> None:
        self.driver.get("https://lvr.land.moi.gov.tw/")
        self.driver.execute_script(
            "window.localStorage.setItem('form-data', arguments[0]);",
            json.dumps(query, ensure_ascii=False),
        )
        self.driver.get("https://lvr.land.moi.gov.tw/jsp/list.jsp")
        self._sleep(5)

    def resolve_target(self, city: str, district: str) -> QueryTarget:
        self._bootstrap_page(DEFAULT_QUERY.copy())

        city_select = Select(self.driver.find_element("id", "l_city"))
        city_select.select_by_visible_text(city)
        city_code = city_select.first_selected_option.get_attribute("value")

        self._sleep(1)
        district_select = Select(self.driver.find_element("id", "l_town"))
        district_select.select_by_visible_text(district)
        district_code = district_select.first_selected_option.get_attribute("value")

        return QueryTarget(
            city=city,
            district=district,
            city_code=city_code,
            district_code=district_code,
        )

    def fetch_rows(self, target: QueryTarget) -> list[dict[str, str]]:
        query = DEFAULT_QUERY.copy()
        query["city"] = target.city_code
        query["town"] = target.district_code
        self._bootstrap_page(query)

        count = self._wait_for_table_count()
        self.driver.execute_script("table.page.len(-1).draw(false);")
        self._sleep(2)

        headers = self.driver.execute_script(
            "return Array.from(document.querySelectorAll('#table-item-head th'))"
            ".map(x => x.innerText.trim())"
        )
        if headers != TABLE_COLUMNS:
            raise RuntimeError(f"表頭與預期不符：{headers}")

        rows = self.driver.execute_script(
            """
            return Array.from(document.querySelectorAll('#table-item-tbody tr')).map(
              (tr) => Array.from(tr.querySelectorAll('td')).map((td) => td.innerText.trim())
            );
            """
        )
        if len(rows) != count:
            raise RuntimeError(f"渲染列數 {len(rows)} 與表格筆數 {count} 不一致")

        query_url = (
            "https://lvr.land.moi.gov.tw/jsp/list.jsp"
            f"?city={target.city}&district={target.district}"
        )
        fetched_at = datetime.now(timezone.utc).astimezone().isoformat()

        result: list[dict[str, str]] = []
        for values in rows:
            row = dict(zip(TABLE_COLUMNS, values, strict=True))
            row["city"] = target.city
            row["district"] = target.district
            row["query_url"] = query_url
            row["fetched_at"] = fetched_at
            result.append(row)
        return result


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = TABLE_COLUMNS + ["city", "district", "query_url", "fetched_at"]
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, city: str, district: str, rows: list[dict[str, str]]) -> None:
    payload: dict[str, Any] = {
        "city": city,
        "district": district,
        "count": len(rows),
        "query_url": (
            "https://lvr.land.moi.gov.tw/jsp/list.jsp"
            f"?city={city}&district={district}"
        ),
        "fetched_at": rows[0]["fetched_at"] if rows else None,
        "columns": TABLE_COLUMNS,
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取預售屋建案備查資料")
    parser.add_argument("--city", required=True, help="縣市名稱，例如：臺中市")
    parser.add_argument("--district", required=True, help="行政區名稱，例如：西屯區")
    parser.add_argument(
        "--output-dir",
        default="results",
        help="輸出目錄，預設為 results",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="顯示瀏覽器視窗，預設使用 headless 模式",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    crawler = PresaleRemarkCrawler(headless=not args.show_browser)
    try:
        target = crawler.resolve_target(args.city, args.district)
        rows = crawler.fetch_rows(target)
    finally:
        crawler.close()

    stem = f"presale_remark_{args.city}_{args.district}"
    csv_path = output_dir / f"{stem}.csv"
    json_path = output_dir / f"{stem}.json"

    write_csv(csv_path, rows)
    write_json(json_path, args.city, args.district, rows)

    print(f"抓取完成：{args.city}{args.district}")
    print(f"筆數：{len(rows)}")
    print(f"CSV：{csv_path}")
    print(f"JSON：{json_path}")


if __name__ == "__main__":
    main()
