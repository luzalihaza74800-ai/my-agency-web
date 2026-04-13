"""
爬蟲執行器 - 根據設定檔執行對應的爬蟲模式。
"""

import logging
import sys
from pathlib import Path

from crawler.config.loader import load_config
from crawler.engine import CrawlerEngine
from crawler.pipeline import build_pipeline_from_config
from crawler.modes.single_page import crawl_single_page, crawl_multiple_pages
from crawler.modes.pagination import crawl_pagination
from crawler.modes.recursive import crawl_recursive
from crawler.modes.sitemap import crawl_sitemap
from crawler.exporters.json_exporter import export_json
from crawler.exporters.csv_exporter import export_csv

logger = logging.getLogger(__name__)


def setup_logging(config: dict):
    """根據設定初始化日誌。"""
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stdout)]

    log_file = log_cfg.get("file")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def run(config_path: str | None = None):
    """
    主執行函式。

    Args:
        config_path: 設定檔路徑（None 則使用預設）
    """
    config = load_config(config_path)
    setup_logging(config)

    name = config.get("name", "unnamed")
    mode = config.get("mode", "single_page")
    logger.info("啟動爬蟲 [%s]，模式: %s", name, mode)

    pipeline = build_pipeline_from_config(config)

    with CrawlerEngine(config) as engine:
        results = _dispatch_mode(mode, config, engine, pipeline)

    if results:
        _export_results(results, config)
    else:
        logger.warning("未取得任何資料")

    logger.info("爬蟲 [%s] 執行完成", name)
    return results


def _dispatch_mode(
    mode: str,
    config: dict,
    engine: CrawlerEngine,
    pipeline,
) -> list[dict]:
    """根據模式分發到對應的爬蟲函式。"""
    rules = config.get("rules", [])

    if mode == "single_page":
        urls = config.get("urls", [])
        if not urls:
            logger.error("single_page 模式需要設定 urls")
            return []
        if len(urls) == 1:
            result = crawl_single_page(urls[0], engine, rules, pipeline)
            return [result] if result else []
        return crawl_multiple_pages(urls, engine, rules, pipeline)

    elif mode == "pagination":
        pg = config.get("pagination", {})
        urls = config.get("urls", [])
        start_url = urls[0] if urls else ""
        if not start_url and not pg.get("url_template"):
            logger.error("pagination 模式需要設定 urls 或 url_template")
            return []
        return crawl_pagination(
            start_url=start_url,
            engine=engine,
            rules=rules,
            pipeline=pipeline,
            next_page_selector=pg.get("next_page_selector"),
            url_template=pg.get("url_template"),
            start_page=pg.get("start_page", 1),
            end_page=pg.get("end_page"),
            max_pages=pg.get("max_pages", 50),
            items_selector=pg.get("items_selector"),
            item_rules=pg.get("item_rules"),
        )

    elif mode == "recursive":
        rc = config.get("recursive", {})
        urls = config.get("urls", [])
        start_url = urls[0] if urls else ""
        if not start_url:
            logger.error("recursive 模式需要設定 urls")
            return []
        return crawl_recursive(
            start_url=start_url,
            engine=engine,
            rules=rules,
            pipeline=pipeline,
            max_depth=rc.get("max_depth", 3),
            max_pages=rc.get("max_pages", 100),
            same_domain=rc.get("same_domain", True),
            link_selector=rc.get("link_selector", "a"),
            url_pattern=rc.get("url_pattern"),
        )

    elif mode == "sitemap":
        sm = config.get("sitemap", {})
        sitemap_url = sm.get("sitemap_url", "")
        if not sitemap_url:
            logger.error("sitemap 模式需要設定 sitemap.sitemap_url")
            return []
        return crawl_sitemap(
            sitemap_url=sitemap_url,
            engine=engine,
            rules=rules,
            pipeline=pipeline,
            max_pages=sm.get("max_pages", 500),
            url_pattern=sm.get("url_pattern"),
            follow_sitemap_index=sm.get("follow_sitemap_index", True),
        )

    else:
        logger.error("不支援的爬蟲模式: %s", mode)
        return []


def _export_results(results: list[dict], config: dict):
    """根據設定匯出資料。"""
    export_cfg = config.get("export", {})
    fmt = export_cfg.get("format", "json")
    output_dir = export_cfg.get("output_dir", "./output")
    filename = export_cfg.get("filename", "results")

    if fmt in ("json", "both"):
        export_json(
            results,
            output_dir=output_dir,
            filename=filename,
            indent=export_cfg.get("json_indent", 2),
        )

    if fmt in ("csv", "both"):
        export_csv(
            results,
            output_dir=output_dir,
            filename=filename,
            encoding=export_cfg.get("csv_encoding", "utf-8-sig"),
        )
