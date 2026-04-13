"""
JSON 資料匯出器。
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def export_json(
    data: list[dict],
    output_dir: str = "./output",
    filename: str = "results",
    indent: int = 2,
) -> str:
    """
    將資料匯出為 JSON 檔案。

    Args:
        data: 資料列表
        output_dir: 輸出目錄
        filename: 檔名（不含副檔名）
        indent: JSON 縮排

    Returns:
        輸出檔案路徑
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filepath = out_path / f"{filename}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

    logger.info("已匯出 JSON: %s（%d 筆資料）", filepath, len(data))
    return str(filepath)
