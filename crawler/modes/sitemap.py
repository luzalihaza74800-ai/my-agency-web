"""
Sitemap 模式 - 從 sitemap.xml 取得所有 URL 後逐一爬取。
適合：需要全站覆蓋的情況。
"""

import re
import logging
from xml.etree import ElementTree

from crawler.engine import CrawlerEngine
from crawler.parser import PageParser
from crawler.pipeline import Pipeline

logger = logging.getLogger(__name__)

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_sitemap_urls(xml_text: str) -> list[str]:
    """從 sitemap XML 提取所有 URL。"""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as e:
        logger.error("Sitemap XML 解析錯誤: %s", e)
        return []

    urls = []

    sitemapindex = root.findall("sm:sitemap", SITEMAP_NS)
    if sitemapindex:
        for sitemap in sitemapindex:
            loc = sitemap.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
        return urls

    for url_elem in root.findall("sm:url", SITEMAP_NS):
        loc = url_elem.find("sm:loc", SITEMAP_NS)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    return urls


def crawl_sitemap(
    sitemap_url: str,
    engine: CrawlerEngine,
    rules: list[dict],
    pipeline: Pipeline | None = None,
    max_pages: int = 500,
    url_pattern: str | None = None,
    follow_sitemap_index: bool = True,
) -> list[dict]:
    """
    Sitemap 爬取模式。

    Args:
        sitemap_url: sitemap.xml 的 URL
        engine: 爬蟲引擎
        rules: 提取規則
        pipeline: 資料處理管線
        max_pages: 最大爬取頁數
        url_pattern: URL 過濾正則（僅爬取匹配的）
        follow_sitemap_index: 是否遞迴展開 sitemap index

    Returns:
        所有提取的資料列表
    """
    url_re = re.compile(url_pattern) if url_pattern else None

    all_urls = _collect_urls(sitemap_url, engine, follow_sitemap_index)
    logger.info("Sitemap 共找到 %d 個 URL", len(all_urls))

    if url_re:
        all_urls = [u for u in all_urls if url_re.search(u)]
        logger.info("URL 過濾後剩 %d 個", len(all_urls))

    all_urls = all_urls[:max_pages]

    results = []
    for i, url in enumerate(all_urls, 1):
        logger.info("Sitemap 爬取 [%d/%d]: %s", i, len(all_urls), url)

        response = engine.fetch(url)
        if not response:
            continue

        parser = PageParser(response.text, url)
        data = parser.extract_by_rules(rules)
        data["_url"] = url
        data["_status_code"] = response.status_code

        if pipeline:
            data = pipeline.process(data)
        if data:
            results.append(data)

    logger.info("Sitemap 爬取完成：共 %d 筆資料", len(results))
    return results


def _collect_urls(
    sitemap_url: str,
    engine: CrawlerEngine,
    follow_index: bool,
) -> list[str]:
    """遞迴收集 sitemap 中所有頁面 URL。"""
    response = engine.fetch(sitemap_url)
    if not response:
        return []

    urls = parse_sitemap_urls(response.text)

    if follow_index and any(u.endswith(".xml") for u in urls):
        page_urls = []
        xml_urls = [u for u in urls if u.endswith(".xml")]
        non_xml = [u for u in urls if not u.endswith(".xml")]
        page_urls.extend(non_xml)

        for xml_url in xml_urls:
            page_urls.extend(_collect_urls(xml_url, engine, follow_index))

        return page_urls

    return urls
