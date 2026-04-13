"""
分頁模式 - 自動翻頁爬取列表。
適合：搜尋結果、商品列表、文章列表。
"""

import re
import logging

from crawler.engine import CrawlerEngine
from crawler.parser import PageParser
from crawler.pipeline import Pipeline

logger = logging.getLogger(__name__)


def crawl_pagination(
    start_url: str,
    engine: CrawlerEngine,
    rules: list[dict],
    pipeline: Pipeline | None = None,
    next_page_selector: str | None = None,
    url_template: str | None = None,
    start_page: int = 1,
    end_page: int | None = None,
    max_pages: int = 50,
    items_selector: str | None = None,
    item_rules: list[dict] | None = None,
) -> list[dict]:
    """
    分頁爬取。

    支援兩種翻頁策略：
    1. next_page_selector：從頁面中找「下一頁」連結
    2. url_template：URL 模板（如 https://example.com/list?page={page}）

    Args:
        start_url: 起始 URL（策略 1）或第一頁 URL
        engine: 爬蟲引擎
        rules: 頁面級提取規則
        pipeline: 資料處理管線
        next_page_selector: 「下一頁」按鈕的 CSS 選擇器
        url_template: URL 模板，包含 {page} 佔位符
        start_page: 起始頁碼（搭配 url_template）
        end_page: 結束頁碼（搭配 url_template）
        max_pages: 最大翻頁數
        items_selector: 列表項的 CSS 選擇器（提取多項）
        item_rules: 每個列表項的提取規則

    Returns:
        所有頁面提取的資料列表
    """
    results = []
    current_url = start_url
    page_num = start_page

    for page_count in range(max_pages):
        if url_template:
            current_url = url_template.format(page=page_num)

        logger.info("爬取分頁 [第 %d 頁]: %s", page_num, current_url)

        response = engine.fetch(current_url)
        if not response:
            break

        parser = PageParser(response.text, current_url)

        if items_selector and item_rules:
            items_html = parser.css_html(items_selector)
            if isinstance(items_html, str):
                items_html = [items_html]

            for item_html in items_html:
                item_parser = PageParser(item_html, current_url)
                item_data = item_parser.extract_by_rules(item_rules)
                item_data["_page"] = page_num
                item_data["_url"] = current_url
                if pipeline:
                    item_data = pipeline.process(item_data)
                if item_data:
                    results.append(item_data)
        else:
            data = parser.extract_by_rules(rules)
            data["_page"] = page_num
            data["_url"] = current_url
            if pipeline:
                data = pipeline.process(data)
            if data:
                results.append(data)

        if url_template:
            page_num += 1
            if end_page and page_num > end_page:
                break
        elif next_page_selector:
            next_link = parser.css(next_page_selector, attr="href", first=True)
            if not next_link:
                logger.info("找不到下一頁連結，停止翻頁")
                break
            current_url = CrawlerEngine.resolve_url(current_url, next_link)
            page_num += 1
        else:
            break

    logger.info("分頁爬取完成：共 %d 頁, %d 筆資料", page_count + 1, len(results))
    return results
