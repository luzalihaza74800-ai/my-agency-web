"""
頁面解析器 - 從 HTML 中提取結構化資料。
支援：CSS 選擇器、XPath、正則表達式、JSON 路徑。
"""

import re
import json
import logging
from typing import Any, Optional

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)


class PageParser:
    """HTML 頁面解析器，支援多種選擇策略。"""

    def __init__(self, html: str, url: str = ""):
        self.html = html
        self.url = url
        self.tree = HTMLParser(html)

    def css(self, selector: str, attr: Optional[str] = None, first: bool = False) -> Any:
        """
        使用 CSS 選擇器提取資料。

        Args:
            selector: CSS 選擇器
            attr: 要提取的屬性名稱，None 則提取文字內容
            first: True 只返回第一個匹配

        Returns:
            匹配的文字或屬性值列表（或單一值）
        """
        nodes = self.tree.css(selector)
        if not nodes:
            return None if first else []

        results = []
        for node in nodes:
            if attr:
                val = node.attributes.get(attr, "")
            else:
                val = node.text(strip=True)
            results.append(val)

        return results[0] if first else results

    def css_html(self, selector: str, first: bool = False) -> Any:
        """提取匹配節點的 innerHTML。"""
        nodes = self.tree.css(selector)
        if not nodes:
            return None if first else []
        results = [node.html for node in nodes]
        return results[0] if first else results

    def regex(self, pattern: str, group: int = 0, first: bool = False) -> Any:
        """
        使用正則表達式提取資料。

        Args:
            pattern: 正則表達式
            group: 要返回的群組索引
            first: True 只返回第一個匹配
        """
        matches = re.findall(pattern, self.html)
        if not matches:
            return None if first else []

        if isinstance(matches[0], tuple):
            results = [m[group] if group < len(m) else m[0] for m in matches]
        else:
            results = matches

        return results[0] if first else results

    def extract_links(self, selector: str = "a", base_url: Optional[str] = None) -> list[str]:
        """提取所有連結 URL。"""
        from crawler.engine import CrawlerEngine

        base = base_url or self.url
        raw_links = self.css(selector, attr="href")
        links = []
        for link in raw_links:
            if link and not link.startswith(("javascript:", "mailto:", "tel:", "#")):
                absolute = CrawlerEngine.resolve_url(base, link)
                links.append(absolute)
        return links

    def extract_images(self, selector: str = "img", base_url: Optional[str] = None) -> list[dict]:
        """提取所有圖片資訊。"""
        from crawler.engine import CrawlerEngine

        base = base_url or self.url
        nodes = self.tree.css(selector)
        images = []
        for node in nodes:
            src = node.attributes.get("src", "")
            if src:
                images.append({
                    "src": CrawlerEngine.resolve_url(base, src),
                    "alt": node.attributes.get("alt", ""),
                    "title": node.attributes.get("title", ""),
                })
        return images

    def extract_by_rules(self, rules: list[dict]) -> dict:
        """
        根據設定檔中的規則批次提取資料。

        每條規則格式：
        {
            "field": "title",
            "selector": "h1.title",
            "type": "css",        # css / regex / css_html
            "attr": null,          # 可選
            "first": true,         # 可選
            "default": ""          # 可選預設值
        }
        """
        data = {}
        for rule in rules:
            field = rule["field"]
            sel_type = rule.get("type", "css")
            default = rule.get("default", None)

            try:
                if sel_type == "css":
                    val = self.css(
                        rule["selector"],
                        attr=rule.get("attr"),
                        first=rule.get("first", False),
                    )
                elif sel_type == "css_html":
                    val = self.css_html(
                        rule["selector"],
                        first=rule.get("first", False),
                    )
                elif sel_type == "regex":
                    val = self.regex(
                        rule["selector"],
                        group=rule.get("group", 0),
                        first=rule.get("first", False),
                    )
                else:
                    logger.warning("不支援的選擇器類型: %s", sel_type)
                    val = default

                data[field] = val if val is not None else default

            except Exception as e:
                logger.error("提取欄位 '%s' 時出錯: %s", field, e)
                data[field] = default

        return data

    @staticmethod
    def parse_json(text: str) -> Any:
        """解析 JSON 回應。"""
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("JSON 解析錯誤: %s", e)
            return None
