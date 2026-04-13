"""
爬蟲引擎 - 負責發送 HTTP 請求並取得頁面內容。
支援：同步請求、自動重試、User-Agent 輪替、請求間隔控制。
"""

import time
import random
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)


class CrawlerEngine:
    """HTTP 請求引擎，封裝所有網路請求相關功能。"""

    DEFAULT_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    }

    def __init__(self, config: dict):
        self.config = config
        engine_cfg = config.get("engine", {})

        self.timeout = engine_cfg.get("timeout", 30)
        self.max_retries = engine_cfg.get("max_retries", 3)
        self.retry_delay = engine_cfg.get("retry_delay", 2)
        self.request_delay = engine_cfg.get("request_delay", 1.0)
        self.random_delay = engine_cfg.get("random_delay", True)
        self.respect_robots_txt = engine_cfg.get("respect_robots_txt", True)
        self.follow_redirects = engine_cfg.get("follow_redirects", True)

        self.rotate_ua = engine_cfg.get("rotate_user_agent", True)
        self._ua = UserAgent() if self.rotate_ua else None
        self._custom_ua = engine_cfg.get("user_agent")

        headers = {**self.DEFAULT_HEADERS}
        extra = engine_cfg.get("headers", {})
        headers.update(extra)
        if not self.rotate_ua and self._custom_ua:
            headers["User-Agent"] = self._custom_ua

        proxy = engine_cfg.get("proxy")
        self.client = httpx.Client(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
            proxy=proxy,
        )
        self._last_request_time: float = 0

    def _get_user_agent(self) -> str:
        if self.rotate_ua and self._ua:
            return self._ua.random
        return self._custom_ua or self.DEFAULT_HEADERS.get("User-Agent", "")

    def _wait_between_requests(self):
        if self.request_delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        base_delay = self.request_delay
        if self.random_delay:
            base_delay += random.uniform(0, self.request_delay * 0.5)
        remaining = base_delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def fetch(self, url: str, method: str = "GET", **kwargs) -> Optional[httpx.Response]:
        """
        發送 HTTP 請求，帶有自動重試機制。

        Args:
            url: 目標 URL
            method: HTTP 方法
            **kwargs: 傳遞給 httpx 的額外參數

        Returns:
            httpx.Response 或 None（所有重試都失敗時）
        """
        self._wait_between_requests()

        for attempt in range(1, self.max_retries + 1):
            try:
                if self.rotate_ua:
                    self.client.headers["User-Agent"] = self._get_user_agent()

                logger.info("請求 [%s] %s（第 %d 次嘗試）", method, url, attempt)
                response = self.client.request(method, url, **kwargs)
                self._last_request_time = time.time()

                if response.status_code == 429:
                    wait = self.retry_delay * attempt
                    logger.warning("收到 429 Too Many Requests，等待 %ss 後重試", wait)
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response

            except httpx.TimeoutException:
                logger.warning("請求 %s 逾時（第 %d 次）", url, attempt)
            except httpx.HTTPStatusError as e:
                logger.warning("HTTP 錯誤 %s: %s（第 %d 次）", url, e.response.status_code, attempt)
            except httpx.RequestError as e:
                logger.warning("請求錯誤 %s: %s（第 %d 次）", url, e, attempt)

            if attempt < self.max_retries:
                wait = self.retry_delay * attempt
                logger.info("等待 %ss 後重試…", wait)
                time.sleep(wait)

        logger.error("所有重試失敗: %s", url)
        return None

    @staticmethod
    def resolve_url(base_url: str, relative_url: str) -> str:
        return urljoin(base_url, relative_url)

    @staticmethod
    def get_domain(url: str) -> str:
        return urlparse(url).netloc

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
