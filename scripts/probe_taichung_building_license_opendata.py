#!/usr/bin/env python3
"""
Probe 臺中市「建築執照存根」OpenData JSON API（Swagger 路徑 /Swagger/OpenData/<uuid>）。

官方 Swagger 彙總檔（含此資料集）：
  https://datacenter.taichung.gov.tw/swagger/yaml/387360000G

預設使用 JSON 資源 UUID（summary 內文標為「臺中市建築執照存根資料-Json」）：
  1799965e-f7b0-4ba2-a70b-2a419cba8540

環境變數：
  TAICHUNG_OPENDATA_BASE  完整 URL 前綴，預設為上述 JSON 端點（不含查詢字串）。

查詢參數（與 Swagger 一致）：offset, limit, sort, fields, filters, q

用法範例：
  python3 scripts/probe_taichung_building_license_opendata.py --limit 3
  python3 scripts/probe_taichung_building_license_opendata.py --q 西屯 --limit 5
  python3 scripts/probe_taichung_building_license_opendata.py --filters '行政區=西屯區' --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_RESOURCE_UUID = "1799965e-f7b0-4ba2-a70b-2a419cba8540"
DEFAULT_BASE = (
    f"https://datacenter.taichung.gov.tw/Swagger/OpenData/{DEFAULT_RESOURCE_UUID}"
)


def _guess_record_count(payload: Any) -> str:
    if payload is None:
        return "（無法解析）"
    if isinstance(payload, list):
        return str(len(payload))
    if isinstance(payload, dict):
        for k in ("data", "result", "records", "items", "rows"):
            v = payload.get(k)
            if isinstance(v, list):
                return f"payload['{k}'] 長度={len(v)}"
        return f"dict 鍵={list(payload.keys())[:12]}{'…' if len(payload) > 12 else ''}"
    return type(payload).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description="試打臺中建照存根 OpenData JSON API")
    parser.add_argument("--base-url", default=os.environ.get("TAICHUNG_OPENDATA_BASE", DEFAULT_BASE))
    parser.add_argument("--offset", type=int, default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--sort", default=None, help="排序欄位（依平台定義）")
    parser.add_argument("--fields", default=None, help="逗號分隔欄位，只取部分欄位")
    parser.add_argument("--filters", default=None, help="過濾條件字串（格式依平台；常見為 欄位=值）")
    parser.add_argument("--q", default=None, help="全文檢索字串")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP 逾時秒數",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="若回應為 JSON，美化輸出（可能很長）",
    )
    args = parser.parse_args()

    q: dict[str, str] = {}
    if args.offset is not None:
        q["offset"] = str(args.offset)
    if args.limit is not None:
        q["limit"] = str(args.limit)
    if args.sort:
        q["sort"] = args.sort
    if args.fields:
        q["fields"] = args.fields
    if args.filters:
        q["filters"] = args.filters
    if args.q:
        q["q"] = args.q

    url = args.base_url
    if q:
        url = f"{args.base_url}?{urllib.parse.urlencode(q)}"

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, */*;q=0.1",
            "User-Agent": "probe_taichung_building_license_opendata/1.0",
        },
        method="GET",
    )

    print("請求 URL:", url, flush=True)
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            status = resp.getcode()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print("HTTP 錯誤:", e.code, e.reason)
        body = e.read()
        if body:
            print("回應本文（前 2000 位元組）：")
            print(body[:2000].decode("utf-8", errors="replace"))
        return 1
    except OSError as e:
        print("連線失敗:", e, flush=True)
        print(
            "若在本機可連、此環境失敗，多半是網路或對方阻擋資料中心 IP；可改在本機執行同一指令。",
            flush=True,
        )
        return 2

    print("HTTP 狀態:", status)
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        print("回應本文為空（伺服器可能關閉連線或需不同路徑／標頭）。")
        return 3

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print("非 JSON 回應，前 800 字元：")
        print(text[:800])
        return 0

    print("粗略筆數／結構:", _guess_record_count(payload))
    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:50000])
    else:
        snippet = json.dumps(payload, ensure_ascii=False)
        if len(snippet) > 4000:
            print("JSON 摘要（前 4000 字元）：")
            print(snippet[:4000] + "…")
        else:
            print(snippet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
