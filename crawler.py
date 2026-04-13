#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣預售建案爬蟲
資料來源：內政部不動產交易實價查詢服務網（開放資料）
API：https://plvr.land.moi.gov.tw/Download?PayType=saleremark&fileName={city_code}_lvr_buildcase.csv

縣市代碼對照表：
  A = 臺北市     B = 臺中市     C = 基隆市
  D = 臺南市     E = 高雄市     F = 新北市
  G = 宜蘭縣     H = 桃園市     I = 嘉義市
  J = 新竹縣     K = 苗栗縣     M = 南投縣
  N = 彰化縣     O = 新竹市     P = 雲林縣
  Q = 嘉義縣     S = 屏東縣     T = 花蓮縣
  U = 臺東縣     V = 澎湖縣     W = 金門縣
  X = 連江縣
"""

import csv
import io
import sys
import time
import argparse
import logging
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 縣市名稱 → 英文代碼
CITY_CODE_MAP: dict[str, str] = {
    "臺北市": "A",
    "台北市": "A",
    "臺中市": "B",
    "台中市": "B",
    "基隆市": "C",
    "臺南市": "D",
    "台南市": "D",
    "高雄市": "E",
    "新北市": "F",
    "宜蘭縣": "G",
    "桃園市": "H",
    "嘉義市": "I",
    "新竹縣": "J",
    "苗栗縣": "K",
    "南投縣": "M",
    "彰化縣": "N",
    "新竹市": "O",
    "雲林縣": "P",
    "嘉義縣": "Q",
    "屏東縣": "S",
    "花蓮縣": "T",
    "臺東縣": "U",
    "台東縣": "U",
    "澎湖縣": "V",
    "金門縣": "W",
    "連江縣": "X",
}

BASE_URL = "https://plvr.land.moi.gov.tw"
DOWNLOAD_PATH = "/Download"


def fetch_presale_buildcase(city: str, timeout: int = 60) -> pd.DataFrame:
    """
    下載指定縣市的預售建案備查 CSV 資料。

    Parameters
    ----------
    city : str
        縣市名稱（中文），例如 '台中市'、'臺中市'
    timeout : int
        HTTP 請求逾時秒數

    Returns
    -------
    pd.DataFrame
        原始建案資料（未過濾）
    """
    city_code = CITY_CODE_MAP.get(city)
    if city_code is None:
        available = "、".join(sorted({k for k in CITY_CODE_MAP if not k.startswith("台")}))
        raise ValueError(
            f"不支援的縣市名稱：「{city}」。\n支援的縣市：{available}"
        )

    filename = f"{city_code.lower()}_lvr_buildcase.csv"
    url = f"{BASE_URL}{DOWNLOAD_PATH}"
    params = {"PayType": "saleremark", "fileName": filename}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://plvr.land.moi.gov.tw/DownloadOpenData",
    }

    logger.info("正在下載 %s 預售建案資料（縣市代碼：%s）...", city, city_code)

    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"下載失敗（已重試 3 次）：{exc}") from exc
            wait = 2 ** attempt
            logger.warning("第 %d 次請求失敗，%d 秒後重試：%s", attempt, wait, exc)
            time.sleep(wait)

    # 解碼並讀取 CSV
    content = resp.content.decode("utf-8-sig")  # 去除 BOM
    lines = content.splitlines()

    if len(lines) < 3:
        raise ValueError("回傳資料格式異常，行數不足")

    # 第 1 行為中文欄位名稱，第 2 行為英文欄位名稱，第 3 行起為資料
    reader_header = csv.reader([lines[0]])
    chinese_headers = next(reader_header)
    expected_cols = len(chinese_headers)

    # 讀取資料行（跳過英文標頭行），欄位數不符的行寬鬆處理
    data_buf = io.StringIO("\n".join(lines[2:]))
    df = pd.read_csv(
        data_buf,
        header=None,
        names=chinese_headers,
        on_bad_lines="skip",   # 欄位數不一致的行直接略過
        dtype=str,
        keep_default_na=False,
    )

    skipped = (len(lines) - 2) - len(df)
    if skipped > 0:
        logger.warning(
            "略過 %d 筆欄位數不一致的資料行（原始資料品質問題）", skipped
        )

    logger.info("成功取得 %s 全縣市資料：共 %d 筆建案", city, len(df))
    return df


def filter_by_district(df: pd.DataFrame, district: str) -> pd.DataFrame:
    """
    依鄉鎮市區過濾建案資料。

    Parameters
    ----------
    df : pd.DataFrame
        完整縣市資料
    district : str
        鄉鎮市區名稱，例如 '西屯區'

    Returns
    -------
    pd.DataFrame
        過濾後的資料
    """
    col = df.columns[0]  # 第一欄為鄉鎮市區
    mask = df[col].str.strip() == district.strip()
    result = df[mask].copy().reset_index(drop=True)
    return result


def crawl(
    city: str,
    district: str | None = None,
    output_path: str | None = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """
    爬取預售建案資料並可選擇性輸出為 CSV。

    Parameters
    ----------
    city : str
        縣市名稱
    district : str, optional
        鄉鎮市區名稱；若不指定則回傳整個縣市資料
    output_path : str, optional
        CSV 輸出路徑；若不指定則不寫檔
    timeout : int
        HTTP 逾時秒數

    Returns
    -------
    pd.DataFrame
        建案資料
    """
    df = fetch_presale_buildcase(city, timeout=timeout)

    if district:
        df = filter_by_district(df, district)
        logger.info("過濾後（%s %s）：共 %d 筆建案", city, district, len(df))

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        logger.info("資料已儲存至：%s", out.resolve())

    return df


def print_summary(df: pd.DataFrame, city: str, district: str | None) -> None:
    """在終端機顯示資料摘要。"""
    location = f"{city} {district}" if district else city
    print(f"\n{'=' * 60}")
    print(f"  台灣預售建案備查資料 ── {location}")
    print(f"{'=' * 60}")
    print(f"  共 {len(df)} 筆建案\n")

    if df.empty:
        print("  （查無資料）")
        return

    cols_to_show = ["建案名稱", "坐落街道", "起造人", "層棟戶數", "使用分區",
                    "主要用途", "主要建材", "申報備查日期", "銷售期間", "建造執照"]
    available = [c for c in cols_to_show if c in df.columns]
    display_df = df[available].copy()

    # 截斷過長的欄位，方便終端機顯示
    for col in ["坐落街道", "起造人", "銷售期間"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].str[:20]

    pd.set_option("display.max_rows", 20)
    pd.set_option("display.max_columns", 10)
    pd.set_option("display.width", 120)
    pd.set_option("display.max_colwidth", 18)
    print(display_df.to_string(index=True))
    print(f"\n{'=' * 60}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="台灣預售建案備查資料爬蟲（內政部開放資料）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python crawler.py                             # 預設：台中市西屯區
  python crawler.py --city 台中市 --district 西屯區
  python crawler.py --city 台北市 --output taipei_all.csv
  python crawler.py --city 台南市 --district 安平區 --output tainan_anping.csv
  python crawler.py --city 台中市 --no-filter   # 全台中市資料
        """,
    )
    parser.add_argument("--city", default="台中市", help="縣市名稱（預設：台中市）")
    parser.add_argument("--district", default="西屯區", help="鄉鎮市區（預設：西屯區）")
    parser.add_argument("--no-filter", action="store_true", help="不過濾區域，下載整個縣市資料")
    parser.add_argument("--output", "-o", default=None, help="輸出 CSV 路徑（預設：自動命名）")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP 逾時秒數（預設：60）")
    parser.add_argument("--no-print", action="store_true", help="不印出摘要表格")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    city = args.city
    district = None if args.no_filter else args.district

    # 自動產生輸出檔名
    if args.output is None:
        safe_city = city.replace("市", "").replace("縣", "")
        safe_district = f"_{district}" if district else "_全市"
        output_path = f"output/{safe_city}{safe_district}_presale_buildcase.csv"
    else:
        output_path = args.output

    try:
        df = crawl(city=city, district=district, output_path=output_path, timeout=args.timeout)
    except (ValueError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1

    if not args.no_print:
        print_summary(df, city, district)

    return 0


if __name__ == "__main__":
    sys.exit(main())
