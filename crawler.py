#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣內政部不動產交易實價查詢服務網 - 預售屋建案備查爬蟲

爬取目標：https://lvr.land.moi.gov.tw/jsp/list.jsp
資料類型：預售屋建案備查（saleRemark）
"""

import hashlib
import base64
import json
import os
import csv
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://lvr.land.moi.gov.tw"
ENCRYPT_KEY = "lvr.land.moi.gov.tw"

# 縣市代碼對照表
CITY_CODES = {
    "基隆市": "C", "臺北市": "A", "台北市": "A",
    "新北市": "F", "桃園市": "H", "新竹市": "O",
    "新竹縣": "J", "苗栗縣": "K", "臺中市": "B", "台中市": "B",
    "南投縣": "M", "彰化縣": "N", "雲林縣": "P", "嘉義市": "I",
    "嘉義縣": "Q", "臺南市": "D", "台南市": "D", "高雄市": "E",
    "屏東縣": "T", "宜蘭縣": "G", "花蓮縣": "U", "臺東縣": "V",
    "台東縣": "V", "澎湖縣": "X", "金門縣": "W", "連江縣": "Z",
}


def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int, iv_len: int):
    """OpenSSL EVP_BytesToKey 以 MD5 衍生金鑰，與 CryptoJS 相容。"""
    d = b""
    d_prev = b""
    while len(d) < key_len + iv_len:
        d_prev = hashlib.md5(d_prev + password + salt).digest()
        d += d_prev
    return d[:key_len], d[key_len : key_len + iv_len]


def _cryptojs_aes_encrypt(message: str, passphrase: str) -> str:
    """
    模擬 CryptoJS.AES.encrypt(message, passphrase) 行為：
    - 隨機產生 8 bytes salt
    - 以 MD5 衍生 AES-256-CBC 金鑰與 IV
    - 輸出格式：base64(base64("Salted__" + salt + ciphertext))
      （網站前端對加密結果再做一次 Base64 編碼）
    """
    salt = os.urandom(8)
    key, iv = _evp_bytes_to_key(passphrase.encode(), salt, 32, 16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(message.encode(), AES.block_size)
    ciphertext = cipher.encrypt(padded)
    inner_b64 = base64.b64encode(b"Salted__" + salt + ciphertext).decode()
    return base64.b64encode(inner_b64.encode()).decode()


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


class PresaleCrawler:
    """預售屋建案備查爬蟲。"""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": f"{BASE_URL}/jsp/list.jsp",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self._init_session()

    def _init_session(self):
        """初始化 Session，取得 JSESSIONID 與查詢 Token。"""
        logger.info("初始化 Session...")
        resp = self.session.get(f"{BASE_URL}/jsp/list.jsp", timeout=20)
        resp.raise_for_status()
        logger.debug("JSESSIONID: %s", self.session.cookies.get("JSESSIONID"))

    def _get_token(self) -> str:
        """向 setToken.jsp 取得一次性 Token。"""
        resp = self.session.get(f"{BASE_URL}/jsp/setToken.jsp", timeout=20)
        resp.raise_for_status()
        data = json.loads(resp.text.strip())
        token = data["token"]
        if token == "401":
            raise RuntimeError("Session 已過期，請重新初始化。")
        logger.debug("Token: %s", token)
        return token

    def get_cities(self) -> list[dict]:
        """取得所有縣市清單。"""
        resp = self.session.get(f"{BASE_URL}/SERVICE/CITY", timeout=20)
        resp.raise_for_status()
        return resp.json()

    def get_districts(self, city_code: str) -> list[dict]:
        """取得指定縣市的鄉鎮市區清單。"""
        resp = self.session.get(
            f"{BASE_URL}/SERVICE/CITY/{city_code}/", timeout=20
        )
        resp.raise_for_status()
        return resp.json()

    def resolve_city_code(self, city_name: str) -> str:
        """將縣市名稱轉換為代碼。"""
        code = CITY_CODES.get(city_name)
        if code:
            return code
        # 從 API 查詢
        cities = self.get_cities()
        for c in cities:
            if c["title"] in (city_name, city_name.replace("台", "臺")):
                return c["code"]
        raise ValueError(f"找不到縣市代碼：{city_name}")

    def resolve_district_code(self, city_code: str, district_name: str) -> str:
        """將鄉鎮市區名稱轉換為代碼。"""
        districts = self.get_districts(city_code)
        for d in districts:
            if d["title"] in (district_name, district_name.replace("台", "臺")):
                return d["code"]
        raise ValueError(
            f"在 {city_code} 找不到鄉鎮市區代碼：{district_name}"
        )

    def _build_api_url(self, params: dict, endpoint: str = "SaleData") -> str:
        """根據查詢參數建構 API URL（含加密）。"""
        params_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        encrypted = _cryptojs_aes_encrypt(params_json, ENCRYPT_KEY)
        hash_val = _md5(params_json)
        from urllib.parse import quote
        return (
            f"{BASE_URL}/SERVICE/QueryPrice/{endpoint}"
            f"/{hash_val}?q={quote(encrypted)}"
        )

    def fetch_presale_buildings(
        self,
        city: str,
        district: Optional[str] = None,
        start_year: int = 112,
        start_month: int = 1,
        end_year: int = 113,
        end_month: int = 12,
        p_builders: str = "",
        p_road: str = "",
    ) -> list[dict]:
        """
        爬取預售屋建案備查資料。

        Parameters
        ----------
        city:         縣市名稱（例如「臺中市」）或代碼（例如 "B"）
        district:     鄉鎮市區名稱（例如「西屯區」）或代碼（例如 "B06"），
                      留空表示查詢整個縣市
        start_year:   查詢起始民國年
        start_month:  查詢起始月
        end_year:     查詢結束民國年
        end_month:    查詢結束月
        p_builders:   建商名稱關鍵字（可留空）
        p_road:       路段關鍵字（可留空）

        Returns
        -------
        建案資料清單（每筆為 dict）
        """
        # 解析縣市代碼
        if len(city) <= 2 and city.isalpha():
            city_code = city.upper()
        else:
            city_code = self.resolve_city_code(city)

        # 解析鄉鎮市區代碼
        if district:
            if district.startswith(city_code) and len(district) == 3:
                town_code = district
            else:
                town_code = self.resolve_district_code(city_code, district)
        else:
            town_code = ""

        token = self._get_token()

        from urllib.parse import quote as urlquote

        params = {
            "qryType": "saleRemark",
            "city": city_code,
            "town": town_code,
            "ptype": "1,2,3,4,5",
            "starty": str(start_year),
            "startm": str(start_month),
            "endy": str(end_year),
            "endm": str(end_month),
            "p_build": "",
            "p_builders": urlquote(p_builders) if p_builders else "",
            "p_road": urlquote(p_road) if p_road else "",
            "p_land": "",
            "p_lnsy": "",
            "p_lnsno": "",
            "token": token,
        }

        url = self._build_api_url(params, endpoint="SaleData")
        logger.info(
            "查詢 %s %s（民國 %d/%02d ~ %d/%02d）...",
            city, district or "（全市）", start_year, start_month,
            end_year, end_month,
        )
        logger.debug("API URL: %s", url[:120] + "...")

        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        if not isinstance(data, list):
            logger.warning("意外的回應格式：%s", type(data))
            return []

        logger.info("取得 %d 筆建案資料", len(data))
        return data


def flatten_record(record: dict) -> dict:
    """將巢狀欄位攤平，方便寫入 CSV。"""
    flat = {}
    for k, v in record.items():
        if isinstance(v, list):
            flat[k] = "|".join(str(x) for x in v)
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}.{sub_k}"] = sub_v
        else:
            flat[k] = v
    return flat


FIELD_NAMES_ZH = {
    "id": "建案識別碼",
    "name": "建案名稱",
    "city": "縣市代碼",
    "town": "鄉鎮市區代碼",
    "addr": "地址",
    "apply": "申報建商",
    "applydate": "申報日期",
    "license": "建照號碼",
    "ldate": "建照日期",
    "chkdate": "最後查核日期",
    "house": "戶數",
    "pu": "使用分區",
    "AA11": "都市土地使用分區",
    "ma": "主要建材",
    "s": "銷售期間",
    "e": "完工期限",
    "f": "銷售截止",
    "b": "基地地號",
    "lat": "緯度",
    "lon": "經度",
    "mark": "備註",
    "pimg": "圖示",
    "sn": "序號",
    "subid": "子識別碼",
    "idlist": "備查紀錄清單",
}


def save_csv(records: list[dict], filepath: str):
    """將資料儲存為 CSV。"""
    if not records:
        logger.warning("無資料，跳過 CSV 輸出。")
        return

    flat_records = [flatten_record(r) for r in records]
    all_keys = []
    seen = set()
    for rec in flat_records:
        for k in rec:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_records)

    logger.info("CSV 已儲存：%s（%d 筆）", filepath, len(records))


def save_json(records: list[dict], filepath: str):
    """將資料儲存為 JSON。"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info("JSON 已儲存：%s（%d 筆）", filepath, len(records))


def parse_args():
    parser = argparse.ArgumentParser(
        description="台灣內政部實價登錄預售屋建案備查爬蟲",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  # 爬取臺中市西屯區（民國 112 年全年）
  python crawler.py --city 臺中市 --district 西屯區

  # 爬取臺北市（全市，民國 111-113 年）
  python crawler.py --city 臺北市 --start-year 111 --end-year 113

  # 搜尋特定建商
  python crawler.py --city 臺中市 --district 西屯區 --builders 遠雄

  # 指定輸出檔案
  python crawler.py --city 臺中市 --district 西屯區 --output result
        """,
    )
    parser.add_argument("--city", default="臺中市", help="縣市名稱（預設：臺中市）")
    parser.add_argument("--district", default="西屯區", help="鄉鎮市區名稱（留空查全市）")
    parser.add_argument("--start-year", type=int, default=112, help="起始民國年（預設：112）")
    parser.add_argument("--start-month", type=int, default=1, help="起始月（預設：1）")
    parser.add_argument("--end-year", type=int, default=113, help="結束民國年（預設：113）")
    parser.add_argument("--end-month", type=int, default=12, help="結束月（預設：12）")
    parser.add_argument("--builders", default="", help="建商名稱關鍵字")
    parser.add_argument("--road", default="", help="路段關鍵字")
    parser.add_argument("--output", default="", help="輸出檔案名稱（不含副檔名）")
    parser.add_argument("--format", choices=["csv", "json", "both"], default="both",
                        help="輸出格式（預設：both）")
    parser.add_argument("--delay", type=float, default=1.0, help="請求間隔秒數（預設：1.0）")
    parser.add_argument("--verbose", action="store_true", help="顯示詳細日誌")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    crawler = PresaleCrawler(delay=args.delay)

    records = crawler.fetch_presale_buildings(
        city=args.city,
        district=args.district,
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=args.end_year,
        end_month=args.end_month,
        p_builders=args.builders,
        p_road=args.road,
    )

    if not records:
        logger.warning("查無資料。")
        return

    # 決定輸出檔名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        base_name = args.output
    else:
        city_part = args.city.replace("市", "").replace("縣", "").replace("臺", "台")
        district_part = args.district.replace("區", "").replace("鄉", "").replace("鎮", "") if args.district else "全市"
        base_name = f"presale_{city_part}_{district_part}_{timestamp}"

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if args.format in ("csv", "both"):
        save_csv(records, str(output_dir / f"{base_name}.csv"))

    if args.format in ("json", "both"):
        save_json(records, str(output_dir / f"{base_name}.json"))

    # 印出摘要
    print(f"\n{'='*60}")
    print(f"查詢結果摘要")
    print(f"{'='*60}")
    print(f"縣市：{args.city}")
    print(f"鄉鎮市區：{args.district or '（全市）'}")
    print(f"查詢期間：民國 {args.start_year}/{args.start_month:02d} ~ {args.end_year}/{args.end_month:02d}")
    print(f"建案總數：{len(records)} 筆")
    print()

    # 印出前 10 筆建案名稱
    print("建案清單（前 10 筆）：")
    for i, r in enumerate(records[:10], 1):
        name = r.get("name", "（無名稱）")
        addr = r.get("addr", "")
        house = r.get("house", "?")
        apply_co = r.get("apply", "")
        print(f"  {i:2d}. {name}｜{addr}｜{house} 戶｜{apply_co}")

    if len(records) > 10:
        print(f"  ... 共 {len(records)} 筆，詳見輸出檔案。")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
