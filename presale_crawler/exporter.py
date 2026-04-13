"""
匯出模組 — 將爬取結果寫入 CSV 或 JSON。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def to_csv(
    records: list[dict],
    output_path: str | Path,
    encoding: str = "utf-8-sig",
) -> Path:
    """
    將紀錄列表寫入 CSV 檔案。

    使用 utf-8-sig 編碼，確保 Excel 開啟時中文正常顯示。
    """
    path = Path(output_path)
    if not records:
        path.write_text("（無資料）\n", encoding=encoding)
        return path

    fieldnames = list(records[0].keys())
    with open(path, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return path


def to_json(
    records: list[dict],
    output_path: str | Path,
    encoding: str = "utf-8",
) -> Path:
    """將紀錄列表寫入 JSON 檔案。"""
    path = Path(output_path)
    with open(path, "w", encoding=encoding) as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return path
