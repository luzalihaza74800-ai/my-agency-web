"""
遞迴模式 - 自動跟隨連結深度爬取。
適合：網站全站抓取、多級分類頁面。
"""

import logging
from collections import deque
from urllib.parse import urlparse

from crawler.engine import CrawlerEngine
from crawler.parser import PageParser
from crawler.pipeline import Pipeline

logger = logging.getLogger(__name__)


def crawl_recursive(
    start_url: str,
    engine: CrawlerEngine,
    rules: list[dict],
    pipeline: Pipeline | None = None,
    max_depth: int = 3,
    max_pages: int = 100,
    same_domain: bool = True,
    link_selector: str = "a",
    url_pattern: str | None = None,
) -> list[dict]:
    """
    遞迴爬取，從起始 URL 自動跟隨連結。

    Args:
        start_url: 起始 URL
        engine: 爬蟲引擎
        rules: 提取規則
        pipeline: 資料處理管線
        max_depth: 最大爬取深度
        max_pages: 最大爬取頁數
        same_domain: 是否限制同網域
        link_selector: 連結選擇器
        url_pattern: URL 正則過濾（僅爬取匹配的 URL）

    Returns:
        所有提取的資料列表
    """
    import re

    visited: set[str] = set()
    results: list[dict] = []
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    start_domain = urlparse(start_url).netloc

    url_re = re.compile(url_pattern) if url_pattern else None

    while queue and len(results) < max_pages:
        url, depth = queue.popleft()

        if url in visited:
            continue
        visited.add(url)

        if url_re and not url_re.search(url):
            continue

        logger.info("遞迴爬取 [深度=%d, 已爬=%d]: %s", depth, len(results), url)

        response = engine.fetch(url)
        if not response:
            continue

        parser = PageParser(response.text, url)

        data = parser.extract_by_rules(rules)
        data["_url"] = url
        data["_depth"] = depth
        data["_status_code"] = response.status_code

        if pipeline:
            data = pipeline.process(data)

        if data:
            results.append(data)

        if depth < max_depth:
            links = parser.extract_links(link_selector, base_url=url)
            for link in links:
                if link not in visited:
                    if same_domain and urlparse(link).netloc != start_domain:
                        continue
                    queue.append((link, depth + 1))

    logger.info("遞迴爬取完成：共 %d 頁", len(results))
    return results
