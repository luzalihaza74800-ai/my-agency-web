from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Page, Response, TimeoutError, sync_playwright


BASE_URL = "https://lvr.land.moi.gov.tw"
CITY_API = f"{BASE_URL}/SERVICE/CITY"
LIST_PAGE_URL = f"{BASE_URL}/jsp/list.jsp"

DEFAULT_FORM_DATA = {
    "qryType": "saleRemark",
    "ptype": "",
    "p_build": "",
    "ftype": "",
    "price_s": "",
    "price_e": "",
    "unit_price_s": "",
    "unit_price_e": "",
    "area_s": "",
    "area_e": "",
    "build_s": "",
    "build_e": "",
    "buildyear_s": "",
    "buildyear_e": "",
    "doorno": "",
    "pattern": "",
    "community": "",
    "floor": "",
    "rent_type": "",
    "rent_order": "",
    "urban": "",
    "urbantext": "",
    "nurban": "",
    "aa12": "",
    "p_purpose": "",
    "p_unusual_yn": "",
    "p_unusualcode": "",
    "QB41": "",
    "show_avg": "1",
    "tmoney_unit": "1",
    "pmoney_unit": "1",
    "unit": "2",
}


@dataclass(frozen=True)
class RegionCode:
    city_code: str
    district_code: str
    city_title: str
    district_title: str


class PresaleCrawlerError(RuntimeError):
    pass


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("台", "臺")


def fetch_region_code(city: str, district: str) -> RegionCode:
    city_response = requests.get(CITY_API, timeout=30)
    city_response.raise_for_status()
    city_items = city_response.json()

    normalized_city = normalize_name(city)
    matched_city = next(
        (item for item in city_items if normalize_name(item["title"]) == normalized_city),
        None,
    )
    if not matched_city:
        raise PresaleCrawlerError(f"找不到縣市代碼：{city}")

    district_response = requests.get(f"{CITY_API}/{matched_city['code']}/", timeout=30)
    district_response.raise_for_status()
    district_items = district_response.json()

    normalized_district = normalize_name(district)
    matched_district = next(
        (item for item in district_items if normalize_name(item["title"]) == normalized_district),
        None,
    )
    if not matched_district:
        raise PresaleCrawlerError(f"找不到行政區代碼：{district}")

    return RegionCode(
        city_code=matched_city["code"],
        district_code=matched_district["code"],
        city_title=matched_city["title"],
        district_title=matched_district["title"],
    )


def build_form_data(
    region: RegionCode,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> dict[str, str]:
    data = dict(DEFAULT_FORM_DATA)
    data.update(
        {
            "city": region.city_code,
            "town": region.district_code,
            "starty": str(start_year),
            "startm": str(start_month),
            "endy": str(end_year),
            "endm": str(end_month),
        }
    )
    return data


def seed_form_data(page: Page, form_data: dict[str, str]) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=120_000)
    page.evaluate(
        "(data) => localStorage.setItem('form-data', JSON.stringify(data))",
        form_data,
    )


def wait_for_sale_data(page: Page) -> Response:
    with page.expect_response(
        lambda resp: "/SERVICE/QueryPrice/SaleData/" in resp.url and resp.status == 200,
        timeout=120_000,
    ) as response_info:
        page.goto(LIST_PAGE_URL, wait_until="domcontentloaded", timeout=120_000)
    response = response_info.value
    page.wait_for_timeout(2000)
    return response


def replay_sale_data_url(url: str) -> list[dict[str, Any]]:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def crawl_presale_projects(
    city: str,
    district: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    headless: bool = True,
    save_debug_html: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    region = fetch_region_code(city, district)
    form_data = build_form_data(region, start_year, start_month, end_year, end_month)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()

        seed_form_data(page, form_data)
        try:
            response = wait_for_sale_data(page)
        except TimeoutError as exc:
            browser.close()
            raise PresaleCrawlerError("等待 SaleData 回應逾時，官方網站可能變更或暫時異常。") from exc

        if save_debug_html is not None:
            save_debug_html.write_text(page.content(), encoding="utf-8")

        sale_data_url = response.url
        data = replay_sale_data_url(sale_data_url)
        browser.close()
        return data, sale_data_url


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]], city: str, district: str, sale_data_url: str) -> None:
    names = [row.get("name", "") for row in rows[:15]]
    print(f"查詢地區：{city}{district}")
    print(f"取得筆數：{len(rows)}")
    print("前 15 筆建案：")
    for index, name in enumerate(names, start=1):
        print(f"{index:>2}. {name}")
    print(f"SaleData URL：{sale_data_url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取內政部實價登錄預售屋建案備查資料")
    parser.add_argument("--city", default="臺中市", help="縣市名稱，例如：臺中市")
    parser.add_argument("--district", default="西屯區", help="行政區名稱，例如：西屯區")
    parser.add_argument("--start-year", type=int, default=110, help="起始民國年")
    parser.add_argument("--start-month", type=int, default=7, help="起始月份")
    parser.add_argument("--end-year", type=int, default=115, help="結束民國年")
    parser.add_argument("--end-month", type=int, default=12, help="結束月份")
    parser.add_argument("--output-dir", default="output", help="輸出目錄")
    parser.add_argument("--show-browser", action="store_true", help="顯示瀏覽器，方便人工除錯")
    parser.add_argument(
        "--save-debug-html",
        help="保存觸發查詢後的 HTML，例如 output/debug.html",
    )
    parser.add_argument(
        "--save-debug-json",
        help="保存 SaleData 原始 JSON，例如 output/raw.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    ensure_output_dir(output_dir)

    debug_html_path = Path(args.save_debug_html) if args.save_debug_html else None
    debug_json_path = Path(args.save_debug_json) if args.save_debug_json else None
    if debug_html_path is not None:
        ensure_output_dir(debug_html_path.parent)
    if debug_json_path is not None:
        ensure_output_dir(debug_json_path.parent)

    rows, sale_data_url = crawl_presale_projects(
        city=args.city,
        district=args.district,
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=args.end_year,
        end_month=args.end_month,
        headless=not args.show_browser,
        save_debug_html=debug_html_path,
    )

    json_path = output_dir / "presale_projects.json"
    csv_path = output_dir / "presale_projects.csv"
    meta_path = output_dir / "metadata.json"

    write_json(json_path, rows)
    write_csv(csv_path, rows)
    write_json(
        meta_path,
        {
            "city": args.city,
            "district": args.district,
            "start_year": args.start_year,
            "start_month": args.start_month,
            "end_year": args.end_year,
            "end_month": args.end_month,
            "count": len(rows),
            "sale_data_url": sale_data_url,
        },
    )
    if debug_json_path is not None:
        write_json(debug_json_path, rows)
    print_summary(rows, args.city, args.district, sale_data_url)


if __name__ == "__main__":
    main()
