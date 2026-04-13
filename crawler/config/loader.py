"""
設定檔載入器 - 讀取 YAML 設定檔。
"""

import os
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "default.yaml"


def load_config(config_path: str | None = None) -> dict:
    """
    載入設定檔。

    如果未指定路徑，使用預設設定檔。
    支援環境變數覆寫：以 CRAWLER_ 為前綴的環境變數會覆蓋對應設定。

    Args:
        config_path: YAML 設定檔路徑

    Returns:
        設定字典
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"設定檔不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config = _apply_env_overrides(config)

    logger.info("已載入設定檔: %s", path)
    return config


def _apply_env_overrides(config: dict) -> dict:
    """
    套用環境變數覆寫。

    環境變數格式: CRAWLER_SECTION_KEY=value
    例如: CRAWLER_ENGINE_TIMEOUT=60
    """
    prefix = "CRAWLER_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        parts = key[len(prefix):].lower().split("_")
        _set_nested(config, parts, _cast_value(value))

    return config


def _set_nested(d: dict, keys: list[str], value: Any):
    """在巢狀字典中設定值。"""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _cast_value(value: str) -> Any:
    """嘗試將字串轉為適當的 Python 型別。"""
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
