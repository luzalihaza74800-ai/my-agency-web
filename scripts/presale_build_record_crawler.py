#!/usr/bin/env python3
"""爬取內政部實價登錄「預售屋建案備查」或「預售屋買賣」清單資料。

核心做法不是直接用 query string 打 list.jsp，也不是等待空的 tbody，
而是先把查詢條件寫進 localStorage['form-data']，再讓 list.jsp 依網站原生流程初始化。
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = "https://lvr.land.moi.gov.tw"
LIST_URL = f"{BASE_URL}/jsp/list.jsp"
CITY_API_URL = f"{BASE_URL}/SERVICE/CITY"


def normalize_region_name(value: str) -> str:
    return value.strip().replace("台", "臺")


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_city_code(city_name: str | None, city_code: str | None) -> str:
    if city_code:
        return city_code
    if not city_name:
        raise ValueError("請提供 --city-name 或 --city-code")

    normalized_target = normalize_region_name(city_name)
    for item in fetch_json(CITY_API_URL):
        if normalize_region_name(item["title"]) == normalized_target:
            return item["code"]

    raise ValueError(f"找不到縣市：{city_name}")


def resolve_town_code(city_code: str, town_name: str | None, town_code: str | None) -> str:
    if town_code:
        return town_code
    if not town_name:
        raise ValueError("請提供 --town-name 或 --town-code")

    normalized_target = normalize_region_name(town_name)
    for item in fetch_json(f"{CITY_API_URL}/{city_code}"):
        if normalize_region_name(item["title"]) == normalized_target:
            return item["code"]

    raise ValueError(f"找不到鄉鎮市區：{town_name}")


def current_roc_year() -> int:
    return date.today().year - 1911


def build_payload(args: argparse.Namespace, city_code: str, town_code: str) -> dict[str, str]:
    query_type = args.query_type
    payload: dict[str, str] = {
        "qryType": query_type,
        "city": city_code,
        "town": town_code,
        "ptype": "",
        "ftype": "",
        "p_build": "",
        "floor": "",
        "purpose": "",
        "urban": "",
        "nurban": "",
        "aa12": "",
        "QB41": "",
        "show_avg": "",
        "tmoney_unit": "1",
        "pmoney_unit": "1",
        "unit": "1",
        "starty": str(args.start_y),
        "startm": str(args.start_m),
        "endy": str(args.end_y),
        "endm": str(args.end_m),
        "price_s": "",
        "price_e": "",
        "unit_price_s": "",
        "unit_price_e": "",
        "area_s": "",
        "area_e": "",
        "house_age_s": "",
        "house_age_e": "",
        "buildarea_s": "",
        "buildarea_e": "",
        # list.jsp 初始化流程不依賴這個值，但保留欄位可更貼近網站原始資料結構。
        "token": "x",
    }
    return payload


def build_driver(chrome_binary: str | None, headless: bool) -> webdriver.Chrome:
    options = Options()
    binary = chrome_binary or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if binary:
        options.binary_location = binary
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,2200")
    return webdriver.Chrome(options=options)


def wait_for_table(driver: webdriver.Chrome, timeout: int) -> dict[str, Any]:
    wait = WebDriverWait(driver, timeout)
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    wait.until(
        lambda d: d.execute_script(
            "return typeof table !== 'undefined' && !!table.rows && !!table.page"
        )
    )

    deadline = time.time() + timeout
    last_signature: tuple[int, int] | None = None
    stable_rounds = 0
    latest_info: dict[str, Any] | None = None

    while time.time() < deadline:
        latest_info = driver.execute_script(
            """
            const info = table.page.info();
            return {
              rowsCount: table.rows().count(),
              recordsDisplay: info.recordsDisplay,
              recordsTotal: info.recordsTotal,
              page: info.page,
              pages: info.pages
            };
            """
        )
        signature = (latest_info["rowsCount"], latest_info["recordsDisplay"])
        if signature == last_signature:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_signature = signature

        if stable_rounds >= 2:
            return latest_info

        time.sleep(0.5)

    raise TimeoutError(f"等待資料表初始化逾時，最後狀態：{latest_info}")


def crawl_records(payload: dict[str, str], chrome_binary: str | None, headless: bool, timeout: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    driver = build_driver(chrome_binary=chrome_binary, headless=headless)
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
        driver.execute_script(
            "localStorage.setItem('form-data', arguments[0]);",
            json.dumps(payload, ensure_ascii=False),
        )
        driver.get(LIST_URL)
        info = wait_for_table(driver, timeout=timeout)
        rows = driver.execute_script("return table.rows().data().toArray();")
        return rows, info
    finally:
        driver.quit()


def flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames: list[str] = sorted({key for row in rows for key in row.keys()})
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: flatten_value(row.get(key)) for key in fieldnames})


def write_json(data: Any, output_path: Path) -> None:
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_default_output_prefix(args: argparse.Namespace, city_code: str, town_code: str) -> str:
    return f"{args.query_type}_{city_code}_{town_code}_{args.start_y}{int(args.start_m):02d}_{args.end_y}{int(args.end_m):02d}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="爬取內政部實價登錄預售屋建案備查清單資料"
    )
    parser.add_argument("--query-type", choices=["saleRemark"], default="saleRemark", help="目前僅支援 saleRemark（預售屋建案備查）")
    parser.add_argument("--city-name", default="臺中市", help="縣市名稱，例如：臺中市")
    parser.add_argument("--town-name", default="西屯區", help="鄉鎮市區名稱，例如：西屯區")
    parser.add_argument("--city-code", help="直接指定縣市代碼，例如：B")
    parser.add_argument("--town-code", help="直接指定行政區代碼，例如：B06")
    parser.add_argument("--start-y", type=int, default=110, help="起始民國年，預設 110")
    parser.add_argument("--start-m", type=int, default=7, help="起始月份，預設 7")
    parser.add_argument("--end-y", type=int, default=current_roc_year(), help="結束民國年，預設為今年民國年")
    parser.add_argument("--end-m", type=int, default=12, help="結束月份，預設 12")
    parser.add_argument("--output-dir", default="output", help="輸出資料夾，預設 output")
    parser.add_argument("--output-prefix", help="輸出檔名前綴")
    parser.add_argument("--chrome-binary", help="自訂 Chrome/Chromium 執行檔路徑")
    parser.add_argument("--timeout", type=int, default=30, help="等待網站初始化秒數，預設 30")
    parser.add_argument("--show-browser", action="store_true", help="不要使用 headless，方便人工觀察")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.query_type != "saleRemark":
        raise ValueError("目前僅支援 saleRemark（預售屋建案備查）")
    for name in ("start_m", "end_m"):
        value = getattr(args, name)
        if value < 1 or value > 12:
            raise ValueError(f"{name} 必須介於 1 到 12")
    if (args.start_y, args.start_m) > (args.end_y, args.end_m):
        raise ValueError("起始年月不可晚於結束年月")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        city_code = resolve_city_code(args.city_name, args.city_code)
        town_code = resolve_town_code(city_code, args.town_name, args.town_code)
        payload = build_payload(args, city_code=city_code, town_code=town_code)

        rows, table_info = crawl_records(
            payload=payload,
            chrome_binary=args.chrome_binary,
            headless=not args.show_browser,
            timeout=args.timeout,
        )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = args.output_prefix or make_default_output_prefix(args, city_code=city_code, town_code=town_code)

        raw_output_path = output_dir / f"{prefix}.json"
        csv_output_path = output_dir / f"{prefix}.csv"

        write_json(
            {
                "meta": {
                    "base_url": LIST_URL,
                    "query_type": args.query_type,
                    "city_name": args.city_name,
                    "town_name": args.town_name,
                    "city_code": city_code,
                    "town_code": town_code,
                    "table_info": table_info,
                    "payload": payload,
                },
                "rows": rows,
            },
            raw_output_path,
        )
        write_csv(rows, csv_output_path)

        print(f"查詢模式：{args.query_type}")
        print(f"行政區：{args.city_name} ({city_code}) / {args.town_name} ({town_code})")
        print(f"查詢區間：民國 {args.start_y}/{args.start_m} ~ {args.end_y}/{args.end_m}")
        print(f"總筆數：{table_info['recordsDisplay']}")
        print(f"JSON：{raw_output_path}")
        print(f"CSV：{csv_output_path}")
        if rows:
            sample_names = [
                row.get("name") or row.get("bname") or row.get("community") or row.get("addr", "")
                for row in rows[:10]
            ]
            print("前 10 筆名稱：")
            for index, name in enumerate(sample_names, start=1):
                print(f"  {index}. {name}")
        return 0
    except Exception as exc:
        print(f"執行失敗：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
