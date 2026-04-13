"""
處理管線 - 對提取的資料進行後處理、清洗、過濾。
"""

import re
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Pipeline:
    """資料處理管線，按順序執行一系列處理步驟。"""

    def __init__(self):
        self._steps: list[tuple[str, Callable]] = []

    def add_step(self, name: str, func: Callable) -> "Pipeline":
        self._steps.append((name, func))
        return self

    def process(self, data: dict) -> dict:
        for name, func in self._steps:
            try:
                data = func(data)
                if data is None:
                    logger.info("管線步驟 '%s' 過濾掉了此筆資料", name)
                    return None
            except Exception as e:
                logger.error("管線步驟 '%s' 出錯: %s", name, e)
        return data

    def process_many(self, items: list[dict]) -> list[dict]:
        results = []
        for item in items:
            result = self.process(item)
            if result is not None:
                results.append(result)
        return results


def strip_whitespace(data: dict) -> dict:
    """去除所有字串欄位的前後空白。"""
    return {
        k: v.strip() if isinstance(v, str) else v
        for k, v in data.items()
    }


def remove_empty_fields(data: dict) -> dict:
    """移除空值欄位。"""
    return {k: v for k, v in data.items() if v}


def clean_html_tags(data: dict) -> dict:
    """移除字串欄位中的 HTML 標籤。"""
    tag_re = re.compile(r"<[^>]+>")
    return {
        k: tag_re.sub("", v) if isinstance(v, str) else v
        for k, v in data.items()
    }


def deduplicate_by(field: str) -> Callable:
    """根據指定欄位去重（返回一個可用於管線的函式）。"""
    seen = set()

    def _dedup(data: dict) -> dict | None:
        val = data.get(field)
        if val in seen:
            return None
        seen.add(val)
        return data

    return _dedup


def build_pipeline_from_config(config: dict) -> Pipeline:
    """從設定檔建立處理管線。"""
    pipe = Pipeline()
    steps_cfg = config.get("pipeline", {}).get("steps", [])

    available = {
        "strip_whitespace": strip_whitespace,
        "remove_empty_fields": remove_empty_fields,
        "clean_html_tags": clean_html_tags,
    }

    for step in steps_cfg:
        if isinstance(step, str):
            if step in available:
                pipe.add_step(step, available[step])
            elif step.startswith("deduplicate_by:"):
                field = step.split(":", 1)[1]
                pipe.add_step(step, deduplicate_by(field))
            else:
                logger.warning("未知的管線步驟: %s", step)
        elif isinstance(step, dict):
            name = step.get("name", "")
            if name.startswith("deduplicate_by"):
                field = step.get("field", "url")
                pipe.add_step(name, deduplicate_by(field))

    return pipe
