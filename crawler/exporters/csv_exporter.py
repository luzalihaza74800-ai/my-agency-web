"""
CSV 資料匯出器。
"""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def export_csv(
    data: list[dict],
    output_dir: str = "./output",
    filename: str = "results",
    encoding: str = "utf-8-sig",
) -> str:
    """
    將資料匯出為 CSV 檔案。

    Args:
        data: 資料列表
        output_dir: 輸出目錄
        filename: 檔名（不含副檔名）
        encoding: 檔案編碼（預設 utf-8-sig 以支援 Excel 中文）

    Returns:
        輸出檔案路徑
    """
    if not data:
        logger.warning("沒有資料可匯出")
        return ""

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filepath = out_path / f"{filename}.csv"

    all_keys = []
    seen = set()
    for item in data:
        for key in item.keys():
            if key not in seen:
                all_keys.append(key)
                seen.add(key)

    with open(filepath, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for item in data:
            row = {}
            for k, v in item.items():
                if isinstance(v, list):
                    row[k] = ", ".join(str(i) for i in v)
                else:
                    row[k] = v
            writer.writerow(row)

    logger.info("已匯出 CSV: %s（%d 筆資料）", filepath, len(data))
    return str(filepath)
