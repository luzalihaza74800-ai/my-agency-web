"""
單頁模式 - 爬取單一頁面並提取資料。
適合：產品頁面、文章詳情頁等。
"""

import logging

from crawler.engine import CrawlerEngine
from crawler.parser import PageParser
from crawler.pipeline import Pipeline

logger = logging.getLogger(__name__)


def crawl_single_page(
    url: str,
    engine: CrawlerEngine,
    rules: list[dict],
    pipeline: Pipeline | None = None,
) -> dict | None:
    """
    爬取單一頁面。

    Args:
        url: 目標 URL
        engine: 爬蟲引擎實例
        rules: 提取規則列表
        pipeline: 資料處理管線（可選）

    Returns:
        提取的資料字典，或 None
    """
    response = engine.fetch(url)
    if not response:
        return None

    parser = PageParser(response.text, url)
    data = parser.extract_by_rules(rules)
    data["_url"] = url
    data["_status_code"] = response.status_code

    if pipeline:
        data = pipeline.process(data)

    return data


def crawl_multiple_pages(
    urls: list[str],
    engine: CrawlerEngine,
    rules: list[dict],
    pipeline: Pipeline | None = None,
) -> list[dict]:
    """批次爬取多個頁面。"""
    results = []
    for i, url in enumerate(urls, 1):
        logger.info("爬取頁面 [%d/%d]: %s", i, len(urls), url)
        data = crawl_single_page(url, engine, rules, pipeline)
        if data:
            results.append(data)
    return results
