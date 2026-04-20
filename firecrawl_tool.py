#!/usr/bin/env python3
"""
Firecrawl 網站爬取工具

提供以下功能：
- scrape: 抓取單一頁面，回傳 Markdown 內容
- crawl: 爬取整個網站（依深度與頁數限制）
- map: 取得網站的所有 URL 地圖
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from firecrawl import FirecrawlApp

load_dotenv()

API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not API_KEY:
    print("錯誤：請在 .env 檔案中設定 FIRECRAWL_API_KEY")
    print("可參考 .env.example 檔案")
    sys.exit(1)

app = FirecrawlApp(api_key=API_KEY)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def scrape_url(url: str, formats: list[str] | None = None):
    """抓取單一頁面，回傳 Markdown 內容"""
    kwargs = {}
    if formats:
        kwargs["formats"] = formats
    else:
        kwargs["formats"] = ["markdown"]

    result = app.scrape(url, **kwargs)
    return result


def crawl_url(url: str, limit: int = 10, max_depth: int = 2):
    """爬取整個網站"""
    result = app.crawl(
        url,
        limit=limit,
        max_discovery_depth=max_depth,
    )
    return result


def map_url(url: str):
    """取得網站的 URL 地圖"""
    result = app.map(url)
    return result


def to_serializable(obj):
    """將 Firecrawl 回傳的物件轉為可序列化的 dict/list"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    if isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    return obj


def save_result(data, filename: str):
    """將結果儲存到 output 資料夾"""
    filepath = OUTPUT_DIR / filename
    serializable = to_serializable(data)
    with open(filepath, "w", encoding="utf-8") as f:
        if isinstance(serializable, (dict, list)):
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        else:
            f.write(str(serializable))
    print(f"結果已儲存至：{filepath}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Firecrawl 網站爬取工具")
    subparsers = parser.add_subparsers(dest="command", help="可用指令")

    scrape_parser = subparsers.add_parser("scrape", help="抓取單一頁面")
    scrape_parser.add_argument("url", help="目標 URL")
    scrape_parser.add_argument(
        "--formats",
        nargs="+",
        default=["markdown"],
        help="輸出格式（預設：markdown）",
    )
    scrape_parser.add_argument("-o", "--output", help="輸出檔名")

    crawl_parser = subparsers.add_parser("crawl", help="爬取整個網站")
    crawl_parser.add_argument("url", help="目標 URL")
    crawl_parser.add_argument(
        "--limit", type=int, default=10, help="最大頁面數（預設：10）"
    )
    crawl_parser.add_argument(
        "--depth", type=int, default=2, help="最大深度（預設：2）"
    )
    crawl_parser.add_argument("-o", "--output", help="輸出檔名")

    map_parser = subparsers.add_parser("map", help="取得網站 URL 地圖")
    map_parser.add_argument("url", help="目標 URL")
    map_parser.add_argument("-o", "--output", help="輸出檔名")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "scrape":
        print(f"正在抓取：{args.url}")
        result = scrape_url(args.url, formats=args.formats)
        serializable = to_serializable(result)
        if args.output:
            save_result(result, args.output)
        else:
            print(json.dumps(serializable, ensure_ascii=False, indent=2))

    elif args.command == "crawl":
        print(f"正在爬取：{args.url}（上限 {args.limit} 頁，深度 {args.depth}）")
        result = crawl_url(args.url, limit=args.limit, max_depth=args.depth)
        serializable = to_serializable(result)
        if args.output:
            save_result(result, args.output)
        else:
            print(json.dumps(serializable, ensure_ascii=False, indent=2))

    elif args.command == "map":
        print(f"正在取得網站地圖：{args.url}")
        result = map_url(args.url)
        serializable = to_serializable(result)
        if args.output:
            save_result(result, args.output)
        else:
            print(json.dumps(serializable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
