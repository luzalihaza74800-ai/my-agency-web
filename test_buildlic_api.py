#!/usr/bin/env python3
"""
臺中市建築執照存根 OpenData API 測試腳本
=========================================
目的：驗證 mcgbm.taichung.gov.tw 的 OpenDataSearchUrl.do (BUILDLIC) 端點
      在不同查詢條件下的回傳格式、資料內容與資料時效性。

API 規格（全國建管系統標準）：
  端點：https://mcgbm.taichung.gov.tw/opendata/OpenDataSearchUrl.do
  固定參數：d=OPENDATA, c=BUILDLIC
  Start：起始筆數（每批最多 100 筆）
  欄位查詢：直接附加於 URL，例如 &執照類別=建造執照
  雙層欄位：用點號，例如 &地號.行政區=西屯區

注意事項（網路環境）：
  mcgbm.taichung.gov.tw 伺服器在 TLS 握手階段即會對非台灣 IP 重置連線
  （Connection reset by peer），這是台灣政府機關常見的 IP 白名單機制。
  若在 Cloud Agent / 海外伺服器執行，可透過以下方式解決：
    1. 使用台灣境內的機器執行
    2. 設定台灣出口的 VPN 或代理伺服器（見下方 PROXY 設定）
    3. 在腳本中設定環境變數 HTTPS_PROXY=socks5://your-proxy:port

使用方式：
  python3 test_buildlic_api.py              # 標準執行
  python3 test_buildlic_api.py --dry-run    # 僅顯示將發送的 URL，不實際發送請求
  HTTPS_PROXY=http://proxy:port python3 test_buildlic_api.py
"""

import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# ── 端點設定 ──────────────────────────────────────────────────────────────────
BASE_URL = "https://mcgbm.taichung.gov.tw/opendata/OpenDataSearchUrl.do"
FIXED_PARAMS = "d=OPENDATA&c=BUILDLIC"
REQUEST_TIMEOUT = 30   # 秒
INTER_REQUEST_DELAY = 1.5   # 秒，避免對伺服器造成過大壓力

# 代理伺服器（若需要，可設定環境變數 HTTPS_PROXY）
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

# ── 測試案例定義 ──────────────────────────────────────────────────────────────
# 格式：(案例名稱, 附加查詢字串, 說明)
TEST_CASES = [
    (
        "無條件查詢（第1-100筆）",
        "Start=1",
        "不帶任何過濾條件，確認 API 是否可正常回傳資料",
    ),
    (
        "無條件查詢（第101-200筆）",
        "Start=101",
        "分頁測試，確認第二批資料能正常分頁",
    ),
    (
        "按執照類別：建造執照",
        "Start=1&執照類別=建造執照",
        "過濾執照類別為建造執照",
    ),
    (
        "按執照類別：使用執照",
        "Start=1&執照類別=使用執照",
        "過濾執照類別為使用執照",
    ),
    (
        "按發照年份：113年（西元2024）",
        "Start=1&發照日期=113年",
        "查詢民國113年（2024年）核發的執照，驗證資料時效性",
    ),
    (
        "按發照年份：112年（西元2023）",
        "Start=1&發照日期=112年",
        "查詢民國112年（2023年）核發的執照",
    ),
    (
        "按發照年份：90年（舊台中縣資料）",
        "Start=1&發照日期=90年",
        "查詢民國90年（2001年）資料，測試合併前台中縣歷史資料回溯完整性",
    ),
    (
        "按行政區：西屯區（地號查詢）",
        "Start=1&地號.行政區=西屯區",
        "以地號行政區欄位查詢西屯區（原台中市區）",
    ),
    (
        "按行政區：豐原區（地號查詢）",
        "Start=1&地號.行政區=豐原區",
        "以地號行政區欄位查詢豐原區（原台中縣區）",
    ),
    (
        "按行政區：太平區（地號查詢）",
        "Start=1&地號.行政區=太平區",
        "以地號行政區欄位查詢太平區（原台中縣區）",
    ),
    (
        "複合條件：西屯區 + 建造執照",
        "Start=1&地號.行政區=西屯區&執照類別=建造執照",
        "多條件組合查詢，同時篩選地區和執照類型",
    ),
    (
        "複合條件：113年 + 使用執照",
        "Start=1&發照日期=113年&執照類別=使用執照",
        "年份 + 執照類別複合查詢，驗證最新使用執照資料",
    ),
    (
        "模糊查詢：起造人姓名",
        "Start=1&起造人代表人=陳.*明",
        "使用正規表示式模糊比對起造人姓名（.*為萬用符號）",
    ),
]

# ── 輔助函式 ──────────────────────────────────────────────────────────────────

def build_url(extra_params: str) -> str:
    """
    建構完整 URL，並將中文查詢值做 percent-encoding。
    保留 URL 結構字元（: / ? & = . % * + - _ ~ @ ! $ ' ( ) , ;）。
    """
    raw_url = f"{BASE_URL}?{FIXED_PARAMS}&{extra_params}"
    encoded_url = urllib.parse.quote(raw_url, safe=":/?&=.%*+-_~@!$'(),;")
    return encoded_url


def build_opener() -> urllib.request.OpenerDirector:
    """建構 urllib opener，支援代理及寬鬆 SSL（政府站可能使用舊版 TLS）。"""
    handlers = []

    if PROXY:
        handlers.append(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))

    # 部分政府伺服器使用舊版 TLS 或非標準憑證設定
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    handlers.append(https_handler)

    return urllib.request.build_opener(*handlers)


_OPENER = None


def fetch(url: str) -> dict:
    """發送 GET 請求，回傳解析後的 JSON 或包含 error 鍵的字典。"""
    global _OPENER
    if _OPENER is None:
        _OPENER = build_opener()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://mcgbm.taichung.gov.tw/opendata/Welcome.do",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
        },
    )
    try:
        with _OPENER.open(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            return {
                "status": status,
                "content_type": content_type,
                "raw": raw,
            }
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        return {
            "error": f"HTTP {exc.code}: {exc.reason}",
            "status": exc.code,
            "raw": body,
        }
    except urllib.error.URLError as exc:
        return {"error": f"URLError: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def parse_response(resp: dict) -> dict:
    """嘗試將回傳內容解析為 JSON；若失敗則保留原始文字。"""
    if "error" in resp and not resp.get("raw"):
        return resp

    raw = resp.get("raw", b"")
    if not raw:
        return resp

    # 嘗試自動偵測編碼（政府系統常用 Big5）
    for encoding in ("utf-8", "big5", "utf-8-sig"):
        try:
            text = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")

    try:
        data = json.loads(text)
        return {**resp, "json": data, "raw_preview": None}
    except Exception:
        return {**resp, "json": None, "raw_preview": text[:600]}


def summarise(parsed: dict) -> dict:
    """從解析結果中抽取摘要資訊。"""
    if "error" in parsed and not parsed.get("json"):
        preview = ""
        if parsed.get("raw"):
            preview = parsed["raw"][:300].decode("utf-8", errors="replace")
        return {"ok": False, "error": parsed["error"], "preview": preview}

    j = parsed.get("json")
    if j is None:
        return {
            "ok": False,
            "error": "非 JSON 回應",
            "preview": parsed.get("raw_preview", ""),
        }

    # 全國建管系統通常回傳 list 或 {"data": [...], ...}
    if isinstance(j, list):
        records = j
    elif isinstance(j, dict):
        records = (
            j.get("data")
            or j.get("records")
            or j.get("result")
            or j.get("建築執照存根基本資料")
            or []
        )
        if not isinstance(records, list):
            records = []
    else:
        records = []

    count = len(records)
    sample = records[0] if records else {}

    dates = []
    for r in records:
        d = r.get("發照日期") or ""
        if d:
            dates.append(str(d))
    latest_date = max(dates) if dates else "（無發照日期欄位）"

    return {
        "ok": True,
        "count": count,
        "latest_date_in_batch": latest_date,
        "fields": list(sample.keys()) if sample else [],
        "sample_record": sample,
        "raw_keys": list(j.keys()) if isinstance(j, dict) else "（頂層為 list）",
    }


# ── 連線預檢 ──────────────────────────────────────────────────────────────────

def connectivity_check() -> bool:
    """
    發送一次輕量請求確認伺服器可達。
    若伺服器在 TLS 握手時重置連線（常見於 IP 封鎖），提示使用者。
    回傳 True 表示可繼續；False 表示應終止（除非 --force）。
    """
    print("  [預檢] 測試伺服器連線 …", end=" ", flush=True)
    t0 = time.time()
    url = build_url("Start=1")
    resp = fetch(url)
    elapsed = time.time() - t0

    if "error" in resp:
        err = resp["error"]
        print(f"失敗（{elapsed:.1f}s）")
        print(f"  [預檢] 錯誤：{err}")
        if "Connection reset" in err or "104" in err:
            print()
            print("  ╔══════════════════════════════════════════════════════════╗")
            print("  ║  網路封鎖診斷                                            ║")
            print("  ║  mcgbm.taichung.gov.tw 在 TLS 握手階段重置了連線。      ║")
            print("  ║  這是台灣政府伺服器常見的 IP 白名單機制，海外 IP         ║")
            print("  ║  （包含 Cloud Agent）會被直接封鎖。                      ║")
            print("  ║                                                          ║")
            print("  ║  解決方法：                                              ║")
            print("  ║  1. 在台灣境內的機器上執行此腳本                        ║")
            print("  ║  2. 設定台灣出口的 VPN/代理：                           ║")
            print("  ║     HTTPS_PROXY=http://your-tw-proxy:port \\             ║")
            print("  ║       python3 test_buildlic_api.py                       ║")
            print("  ║  3. 加 --force 旗標可跳過預檢繼續執行（結果仍會失敗）   ║")
            print("  ╚══════════════════════════════════════════════════════════╝")
        return False

    print(f"成功（HTTP {resp.get('status')}，{elapsed:.1f}s）")
    return True


def print_separator(char="─", width=72):
    print(char * width)


# ── 主程式 ────────────────────────────────────────────────────────────────────

def run_tests(force: bool = False):
    print()
    print_separator("═")
    print("  臺中市建築執照存根 OpenData API — 功能與資料時效性測試")
    print(f"  執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  端點：{BASE_URL}")
    if PROXY:
        print(f"  代理：{PROXY}")
    print_separator("═")

    # 連線預檢
    print()
    if not connectivity_check() and not force:
        print()
        print("  跳過測試。請確認網路環境後重新執行，或加 --force 強制執行。")
        return 2

    print()
    results = []

    for idx, (name, params, desc) in enumerate(TEST_CASES, 1):
        url = build_url(params)
        print(f"\n【案例 {idx:02d}】{name}")
        print(f"  說明：{desc}")
        print(f"  URL ：{url}")

        t0 = time.time()
        resp = fetch(url)
        elapsed = time.time() - t0

        parsed = parse_response(resp)
        summary = summarise(parsed)

        if summary["ok"]:
            print(f"  狀態：✓ 成功（HTTP {parsed['status']}，耗時 {elapsed:.2f}s）")
            print(f"  筆數：{summary['count']} 筆（本批）")
            print(f"  最新發照日期（本批）：{summary['latest_date_in_batch']}")
            if summary["fields"]:
                shown = summary["fields"][:10]
                suffix = "…" if len(summary["fields"]) > 10 else ""
                print(f"  回傳欄位：{', '.join(shown)}{suffix}")
            if isinstance(summary.get("raw_keys"), list):
                print(f"  頂層 JSON 鍵：{summary['raw_keys']}")
            if summary["sample_record"]:
                sample_str = json.dumps(
                    summary["sample_record"], ensure_ascii=False, indent=2
                )
                indented = "\n".join(f"    {line}" for line in sample_str.splitlines())
                print(f"  第一筆範例：\n{indented}")
        else:
            print(f"  狀態：✗ 失敗（耗時 {elapsed:.2f}s）")
            print(f"  錯誤：{summary.get('error', '未知')}")
            if summary.get("preview"):
                print(f"  回應預覽：{summary['preview'][:300]}")

        results.append({
            "case": name,
            "params": params,
            "url": url,
            "elapsed": round(elapsed, 3),
            **{k: v for k, v in summary.items() if k != "sample_record"},
            "sample_record": (
                summary.get("sample_record") if summary.get("ok") else None
            ),
        })

        if idx < len(TEST_CASES):
            time.sleep(INTER_REQUEST_DELAY)

    # ── 整體摘要 ─────────────────────────────────────────────────────────────
    print()
    print_separator("═")
    print("  整體測試摘要")
    print_separator("═")

    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    total_records = sum(r.get("count", 0) for r in results if r.get("ok"))

    print(f"  成功案例：{ok_count} / {len(results)}")
    print(f"  失敗案例：{fail_count}")
    print(f"  總回傳筆數（所有成功案例加總）：{total_records}")
    print()

    all_dates = [
        r["latest_date_in_batch"]
        for r in results
        if r.get("ok") and "無" not in r.get("latest_date_in_batch", "無")
    ]
    if all_dates:
        print(f"  全部案例中最新發照日期（文字排序）：{max(all_dates)}")
        print()

    print("  各案例結果一覽：")
    print_separator()
    for r in results:
        status_icon = "✓" if r.get("ok") else "✗"
        count_str = f"{r.get('count', 0):4d} 筆" if r.get("ok") else "    -   "
        print(f"  {status_icon} [{count_str}]  {r['case']}")
        if not r.get("ok"):
            print(f"         └─ {r.get('error', '')}")
    print_separator()

    # 儲存完整結果至 JSON
    output_path = "buildlic_api_test_results.json"
    safe_results = []
    for r in results:
        try:
            json.dumps(r, ensure_ascii=False)
            safe_results.append(r)
        except TypeError:
            r2 = {k: v for k, v in r.items() if k != "sample_record"}
            r2["sample_record"] = "(無法序列化)"
            safe_results.append(r2)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_at": datetime.now().isoformat(),
                "endpoint": BASE_URL,
                "proxy": PROXY,
                "results": safe_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n  詳細結果已寫入：{output_path}")

    return 0 if fail_count == 0 else 1


def dry_run():
    """不實際發送請求，僅列出所有將被呼叫的 URL。"""
    print()
    print_separator("═")
    print("  臺中市建築執照存根 API — Dry-run 模式（僅列出 URL）")
    print_separator("═")
    for idx, (name, params, desc) in enumerate(TEST_CASES, 1):
        url = build_url(params)
        print(f"\n【{idx:02d}】{name}")
        print(f"  說明：{desc}")
        print(f"  URL ：{url}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--dry-run" in args:
        dry_run()
        sys.exit(0)

    force = "--force" in args
    sys.exit(run_tests(force=force))
