from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import requests
from playwright.sync_api import Page, Response, TimeoutError, sync_playwright
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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

NORMALIZED_FIELD_ORDER = [
    "city",
    "district",
    "city_code",
    "district_code",
    "project_id",
    "project_name",
    "address",
    "applicant",
    "household_count",
    "zoning",
    "primary_usage",
    "main_material",
    "license",
    "filing_date",
    "apply_date",
    "sale_period",
    "completion_deadline",
    "latitude",
    "longitude",
    "source_url",
]


@dataclass(frozen=True)
class RegionCode:
    city_code: str
    district_code: str
    city_title: str
    district_title: str


@dataclass(frozen=True)
class CrawlQuery:
    start_year: int
    start_month: int
    end_year: int
    end_month: int


@dataclass
class CrawlResult:
    region: RegionCode
    raw_rows: list[dict[str, Any]]
    normalized_rows: list[dict[str, Any]]
    sale_data_url: str

    @property
    def count(self) -> int:
        return len(self.raw_rows)


class PresaleCrawlerError(RuntimeError):
    pass


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("台", "臺")


def validate_query(query: CrawlQuery) -> None:
    for month in (query.start_month, query.end_month):
        if month < 1 or month > 12:
            raise PresaleCrawlerError("月份必須介於 1 到 12 之間。")

    start_value = query.start_year * 100 + query.start_month
    end_value = query.end_year * 100 + query.end_month
    if start_value > end_value:
        raise PresaleCrawlerError("起始年月不可晚於結束年月。")


def build_retry_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            )
        }
    )
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        allowed_methods=frozenset({"GET"}),
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_json(session: requests.Session, url: str) -> Any:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_city_item(session: requests.Session, city: str) -> dict[str, Any]:
    city_items = get_json(session, CITY_API)
    normalized_city = normalize_name(city)
    matched_city = next(
        (item for item in city_items if normalize_name(item["title"]) == normalized_city),
        None,
    )
    if not matched_city:
        raise PresaleCrawlerError(f"找不到縣市代碼：{city}")
    return matched_city


def fetch_regions_for_city(session: requests.Session, city: str) -> list[RegionCode]:
    matched_city = fetch_city_item(session, city)
    district_items = get_json(session, f"{CITY_API}/{matched_city['code']}/")
    return [
        RegionCode(
            city_code=matched_city["code"],
            district_code=item["code"],
            city_title=matched_city["title"],
            district_title=item["title"],
        )
        for item in district_items
        if item.get("use", True)
    ]


def fetch_region_code(session: requests.Session, city: str, district: str) -> RegionCode:
    regions = fetch_regions_for_city(session, city)
    normalized_district = normalize_name(district)
    matched_region = next(
        (region for region in regions if normalize_name(region.district_title) == normalized_district),
        None,
    )
    if not matched_region:
        raise PresaleCrawlerError(f"找不到行政區代碼：{district}")
    return matched_region


def resolve_target_regions(
    session: requests.Session,
    city: str,
    districts: Sequence[str] | None,
    all_districts: bool,
    district_limit: int | None,
) -> list[RegionCode]:
    if all_districts:
        regions = fetch_regions_for_city(session, city)
    else:
        district_names = list(districts or ["西屯區"])
        regions = [fetch_region_code(session, city, district_name) for district_name in district_names]

    if district_limit is not None:
        return regions[:district_limit]
    return regions


def build_form_data(region: RegionCode, query: CrawlQuery) -> dict[str, str]:
    data = dict(DEFAULT_FORM_DATA)
    data.update(
        {
            "city": region.city_code,
            "town": region.district_code,
            "starty": str(query.start_year),
            "startm": str(query.start_month),
            "endy": str(query.end_year),
            "endm": str(query.end_month),
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
    page.wait_for_timeout(2_000)
    return response


def replay_sale_data_url(session: requests.Session, url: str) -> list[dict[str, Any]]:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def extract_sale_rows(session: requests.Session, response: Response) -> list[dict[str, Any]]:
    try:
        payload = response.json()
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return replay_sale_data_url(session, response.url)


def normalize_project_row(row: dict[str, Any], region: RegionCode, source_url: str) -> dict[str, Any]:
    return {
        "city": region.city_title,
        "district": region.district_title,
        "city_code": region.city_code,
        "district_code": region.district_code,
        "project_id": row.get("id", ""),
        "project_name": row.get("name", ""),
        "address": row.get("addr", ""),
        "applicant": row.get("apply", ""),
        "household_count": row.get("house", ""),
        "zoning": row.get("AA11", ""),
        "primary_usage": row.get("pu", ""),
        "main_material": row.get("ma", ""),
        "license": row.get("license", ""),
        "filing_date": row.get("chkdate", ""),
        "apply_date": row.get("applydate", ""),
        "sale_period": row.get("s", ""),
        "completion_deadline": row.get("f", ""),
        "latitude": row.get("lat", ""),
        "longitude": row.get("lon", ""),
        "source_url": source_url,
    }


def crawl_region(
    session: requests.Session,
    page: Page,
    region: RegionCode,
    query: CrawlQuery,
    save_debug_html: Path | None = None,
) -> CrawlResult:
    form_data = build_form_data(region, query)
    seed_form_data(page, form_data)

    try:
        response = wait_for_sale_data(page)
    except TimeoutError as exc:
        raise PresaleCrawlerError(
            f"等待 {region.city_title}{region.district_title} 的 SaleData 回應逾時。"
        ) from exc

    if save_debug_html is not None:
        ensure_output_dir(save_debug_html.parent)
        save_debug_html.write_text(page.content(), encoding="utf-8")

    rows = extract_sale_rows(session, response)
    normalized_rows = [
        normalize_project_row(row, region=region, source_url=response.url) for row in rows
    ]
    return CrawlResult(
        region=region,
        raw_rows=rows,
        normalized_rows=normalized_rows,
        sale_data_url=response.url,
    )


def crawl_single_region(
    session: requests.Session,
    region: RegionCode,
    query: CrawlQuery,
    headless: bool,
    save_debug_html: Path | None,
) -> CrawlResult:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            return crawl_region(
                session=session,
                page=page,
                region=region,
                query=query,
                save_debug_html=save_debug_html,
            )
        finally:
            browser.close()


def crawl_regions(
    session: requests.Session,
    regions: Sequence[RegionCode],
    query: CrawlQuery,
    headless: bool,
    debug_dir: Path | None,
    delay_seconds: float,
    fail_fast: bool,
) -> tuple[list[CrawlResult], list[dict[str, str]]]:
    results: list[CrawlResult] = []
    errors: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            for index, region in enumerate(regions):
                debug_path = None
                if debug_dir is not None:
                    debug_path = debug_dir / f"{region.district_code}.html"
                try:
                    results.append(
                        crawl_region(
                            session=session,
                            page=page,
                            region=region,
                            query=query,
                            save_debug_html=debug_path,
                        )
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "city": region.city_title,
                            "district": region.district_title,
                            "district_code": region.district_code,
                            "error": str(exc),
                        }
                    )
                    if fail_fast:
                        raise

                if delay_seconds > 0 and index < len(regions) - 1:
                    time.sleep(delay_seconds)
        finally:
            browser.close()

    return results, errors


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_output_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    ensure_output_dir(path.parent)
    if not rows:
        header = ",".join(fieldnames or [])
        path.write_text(f"{header}\n" if header else "", encoding="utf-8")
        return

    ordered_fieldnames = list(fieldnames or [])
    for row in rows:
        for key in row.keys():
            if key not in ordered_fieldnames:
                ordered_fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_result_metadata(result: CrawlResult, query: CrawlQuery) -> dict[str, Any]:
    return {
        "city": result.region.city_title,
        "district": result.region.district_title,
        "city_code": result.region.city_code,
        "district_code": result.region.district_code,
        "query": asdict(query),
        "count": result.count,
        "sale_data_url": result.sale_data_url,
        "sample_projects": [row.get("name", "") for row in result.raw_rows[:10]],
    }


def write_result_bundle(base_dir: Path, result: CrawlResult, query: CrawlQuery) -> None:
    ensure_output_dir(base_dir)
    write_json(base_dir / "presale_projects.json", result.raw_rows)
    write_csv(base_dir / "presale_projects.csv", result.raw_rows)
    write_json(base_dir / "presale_projects_normalized.json", result.normalized_rows)
    write_csv(
        base_dir / "presale_projects_normalized.csv",
        result.normalized_rows,
        fieldnames=NORMALIZED_FIELD_ORDER,
    )
    write_json(base_dir / "metadata.json", build_result_metadata(result, query))


def build_city_summary(results: Sequence[CrawlResult], query: CrawlQuery) -> list[dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []
    for result in results:
        summary_rows.append(
            {
                "city": result.region.city_title,
                "district": result.region.district_title,
                "city_code": result.region.city_code,
                "district_code": result.region.district_code,
                "count": result.count,
                "query_start": f"{query.start_year:03d}/{query.start_month:02d}",
                "query_end": f"{query.end_year:03d}/{query.end_month:02d}",
                "first_project": result.raw_rows[0].get("name", "") if result.raw_rows else "",
                "sample_projects": " | ".join(row.get("name", "") for row in result.raw_rows[:5]),
                "sale_data_url": result.sale_data_url,
            }
        )
    return summary_rows


def write_city_bundle(
    output_dir: Path,
    results: Sequence[CrawlResult],
    errors: Sequence[dict[str, str]],
    query: CrawlQuery,
) -> None:
    all_raw_rows = [row for result in results for row in result.raw_rows]
    all_normalized_rows = [row for result in results for row in result.normalized_rows]
    summary_rows = build_city_summary(results, query)

    write_json(output_dir / "all_presale_projects.json", all_raw_rows)
    write_csv(output_dir / "all_presale_projects.csv", all_raw_rows)
    write_json(output_dir / "all_presale_projects_normalized.json", all_normalized_rows)
    write_csv(
        output_dir / "all_presale_projects_normalized.csv",
        all_normalized_rows,
        fieldnames=NORMALIZED_FIELD_ORDER,
    )
    write_json(output_dir / "city_summary.json", summary_rows)
    write_csv(output_dir / "city_summary.csv", summary_rows)
    write_json(
        output_dir / "run_metadata.json",
        {
            "query": asdict(query),
            "districts_succeeded": len(results),
            "districts_failed": len(errors),
            "total_projects": len(all_raw_rows),
        },
    )
    if errors:
        write_json(output_dir / "errors.json", list(errors))


def print_single_result(result: CrawlResult) -> None:
    print(f"查詢地區：{result.region.city_title}{result.region.district_title}")
    print(f"取得筆數：{result.count}")
    print("前 15 筆建案：")
    for index, row in enumerate(result.raw_rows[:15], start=1):
        print(f"{index:>2}. {row.get('name', '')}")
    print(f"SaleData URL：{result.sale_data_url}")


def print_batch_summary(results: Sequence[CrawlResult], errors: Sequence[dict[str, str]]) -> None:
    total_projects = sum(result.count for result in results)
    print(f"成功行政區數：{len(results)}")
    print(f"失敗行政區數：{len(errors)}")
    print(f"總建案筆數：{total_projects}")
    for result in results:
        print(f"- {result.region.city_title}{result.region.district_title}: {result.count} 筆")
    if errors:
        print("失敗清單：")
        for item in errors:
            print(f"- {item['city']}{item['district']}: {item['error']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取內政部實價登錄預售屋建案備查資料")
    parser.add_argument("--city", default="臺中市", help="縣市名稱，例如：臺中市")
    parser.add_argument(
        "--district",
        action="append",
        help="行政區名稱，可重複傳入；若未指定且未啟用 --all-districts，預設抓西屯區",
    )
    parser.add_argument("--all-districts", action="store_true", help="抓取指定縣市的全部行政區")
    parser.add_argument("--district-limit", type=int, help="限制實際抓取的行政區數量")
    parser.add_argument("--start-year", type=int, default=110, help="起始民國年")
    parser.add_argument("--start-month", type=int, default=7, help="起始月份")
    parser.add_argument("--end-year", type=int, default=115, help="結束民國年")
    parser.add_argument("--end-month", type=int, default=12, help="結束月份")
    parser.add_argument("--output-dir", default="output", help="輸出目錄")
    parser.add_argument("--show-browser", action="store_true", help="顯示瀏覽器，方便人工除錯")
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="批次抓取時各行政區之間的等待秒數")
    parser.add_argument("--fail-fast", action="store_true", help="批次模式遇到錯誤時立即停止")
    parser.add_argument(
        "--save-debug-html",
        help="單區模式時，保存觸發查詢後的 HTML，例如 output/debug.html",
    )
    parser.add_argument(
        "--save-debug-dir",
        help="批次模式時，依行政區保存 HTML，例如 output/debug-html/",
    )
    parser.add_argument(
        "--save-debug-json",
        help="單區模式時，保存 SaleData 原始 JSON，例如 output/raw.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    query = CrawlQuery(
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=args.end_year,
        end_month=args.end_month,
    )
    validate_query(query)
    if args.delay_seconds < 0:
        raise PresaleCrawlerError("--delay-seconds 不可為負數。")
    if args.district_limit is not None and args.district_limit <= 0:
        raise PresaleCrawlerError("--district-limit 必須大於 0。")
    output_dir = Path(args.output_dir)
    ensure_output_dir(output_dir)

    debug_html_path = Path(args.save_debug_html) if args.save_debug_html else None
    debug_dir = Path(args.save_debug_dir) if args.save_debug_dir else None
    debug_json_path = Path(args.save_debug_json) if args.save_debug_json else None

    session = build_retry_session()
    regions = resolve_target_regions(
        session=session,
        city=args.city,
        districts=args.district,
        all_districts=args.all_districts,
        district_limit=args.district_limit,
    )

    if len(regions) == 1 and not args.all_districts:
        result = crawl_single_region(
            session=session,
            region=regions[0],
            query=query,
            headless=not args.show_browser,
            save_debug_html=debug_html_path,
        )
        write_result_bundle(output_dir, result, query)
        if debug_json_path is not None:
            write_json(debug_json_path, result.raw_rows)
        print_single_result(result)
        return

    results, errors = crawl_regions(
        session=session,
        regions=regions,
        query=query,
        headless=not args.show_browser,
        debug_dir=debug_dir,
        delay_seconds=args.delay_seconds,
        fail_fast=args.fail_fast,
    )

    if not results and errors:
        raise PresaleCrawlerError(f"全部行政區查詢失敗：{errors[0]['error']}")

    districts_dir = output_dir / "districts"
    for result in results:
        write_result_bundle(districts_dir / result.region.district_code, result, query)

    write_city_bundle(output_dir, results, errors, query)
    print_batch_summary(results, errors)


if __name__ == "__main__":
    main()
