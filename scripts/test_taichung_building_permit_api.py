#!/usr/bin/env python3
"""
台中市建築執照存根 OpenData API 測試腳本

測試兩種端點：
1. 建管系統直接端點 (mcgbm.taichung.gov.tw/opendata/OpenDataSearchUrl.do)
   - 全國建管系統標準 API，支援中文欄位查詢
   - 固定參數：d=OPENDATA, c=BUILDLIC
   - 每次最多回傳 100 筆

2. 台中市資料中心 Swagger 端點 (datacenter.taichung.gov.tw/swagger/OpenData/{UUID})
   - JSON UUID: 1799965e-f7b0-4ba2-a70b-2a419cba8540
   - CSV UUID:  c4ecc0cd-02b5-49b2-8dee-5bfe5a557092
   - XML UUID:  78b90f9e-a2b2-44b6-9a5a-d47f633861e7
   - 標準參數：offset, limit, fields, sort, filters, q

已知限制：
- mcgbm.taichung.gov.tw 對海外 IP（非台灣）會在 TLS 層面 reset 連線
- datacenter 的 SERVICES 類型資料集可能無法透過標準參數查詢
"""

import json
import sys
import time
import ssl
import socket
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

MCGBM_BASE = "https://mcgbm.taichung.gov.tw/opendata/OpenDataSearchUrl.do"
DATACENTER_BASE = "https://datacenter.taichung.gov.tw/swagger/OpenData"

DATACENTER_UUIDS = {
    "JSON": "1799965e-f7b0-4ba2-a70b-2a419cba8540",
    "CSV": "c4ecc0cd-02b5-49b2-8dee-5bfe5a557092",
    "XML": "78b90f9e-a2b2-44b6-9a5a-d47f633861e7",
}

TIMEOUT = 30
RESULTS = []


def log(msg: str):
    print(msg)


def fetch(url: str, label: str, timeout: int = TIMEOUT) -> dict | list | str | None:
    log(f"\n{'='*70}")
    log(f"測試: {label}")
    log(f"URL : {url}")
    log(f"{'='*70}")

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.time() - t0
            status = resp.status
            ct = resp.headers.get("Content-Type", "unknown")
            raw = resp.read()
            log(f"  HTTP {status} | Content-Type: {ct} | {len(raw)} bytes | {elapsed:.2f}s")

            text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                log("  ⚠ 回傳空內容")
                return None

            if text.strip() == "查無此資料！":
                log("  ⚠ API 回傳：查無此資料！")
                return "NO_DATA"

            try:
                data = json.loads(text)
                return data
            except json.JSONDecodeError:
                log(f"  回傳非 JSON，前 1000 字元：")
                log(f"  {text[:1000]}")
                return text

    except urllib.error.HTTPError as e:
        log(f"  HTTP 錯誤: {e.code} {e.reason}")
        return None
    except urllib.error.URLError as e:
        log(f"  連線錯誤: {e.reason}")
        return None
    except socket.timeout:
        log("  連線逾時")
        return None
    except Exception as e:
        log(f"  未預期錯誤: {type(e).__name__}: {e}")
        return None


def analyse(data, label: str) -> int:
    if data is None:
        log("  → 無法分析（連線失敗）")
        return 0
    if data == "NO_DATA":
        log("  → SERVICES 類型端點返回「查無此資料」，可能需要特定查詢參數或僅限台灣 IP")
        return 0

    if isinstance(data, list):
        count = len(data)
        log(f"  → 回傳 {count} 筆資料")
        if count > 0:
            fields = list(data[0].keys())
            log(f"  → 欄位 ({len(fields)}): {fields}")
            log(f"  → 第 1 筆:")
            for k, v in list(data[0].items()):
                log(f"       {k}: {v}")
            if count > 1:
                log(f"  → 第 {count} 筆 (最後):")
                for k, v in list(data[-1].items())[:8]:
                    log(f"       {k}: {v}")

            dates = [r.get("發照日期", "") for r in data if r.get("發照日期")]
            if dates:
                dates.sort()
                log(f"  → 發照日期範圍: {dates[0]} ~ {dates[-1]}")
        return count

    elif isinstance(data, dict):
        log(f"  → 回傳 dict，keys: {list(data.keys())}")
        snippet = json.dumps(data, ensure_ascii=False, indent=2)[:2000]
        log(f"  → 內容:\n{snippet}")
        if "data" in data and isinstance(data["data"], list):
            return len(data["data"])
        return 1

    elif isinstance(data, str):
        log(f"  → 回傳字串 ({len(data)} chars): {data[:500]}")
        return 0

    return 0


def record(label: str, endpoint: str, params: dict, data, count: int):
    RESULTS.append({
        "test": label,
        "endpoint": endpoint,
        "params": params,
        "success": data is not None and data != "NO_DATA",
        "no_data": data == "NO_DATA",
        "record_count": count,
    })


# ── Phase 1: Network diagnostics ────────────────────────────────────────

def phase_network():
    log("\n" + "█" * 70)
    log(" Phase 1: 網路連線診斷")
    log("█" * 70)

    targets = [
        ("mcgbm.taichung.gov.tw", 443),
        ("datacenter.taichung.gov.tw", 443),
        ("opendata.taichung.gov.tw", 443),
    ]
    for host, port in targets:
        log(f"\n  → {host}:{port}")
        try:
            ip = socket.getaddrinfo(host, port)[0][4][0]
            log(f"    DNS 解析: {ip}")
        except Exception as e:
            log(f"    DNS 失敗: {e}")
            continue

        try:
            sock = socket.create_connection((host, port), timeout=10)
            log(f"    TCP 連線: OK")
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                log(f"    TLS 握手: OK ({ssock.version()})")
                cert = ssock.getpeercert()
                cn = dict(x[0] for x in cert.get("subject", ()))
                log(f"    憑證 CN : {cn.get('commonName', 'N/A')}")
        except ssl.SSLError as e:
            log(f"    TLS 錯誤: {e}")
        except ConnectionResetError:
            log(f"    ⚠ TLS 握手被 reset — 伺服器可能封鎖海外 IP")
        except socket.timeout:
            log(f"    連線逾時")
        except Exception as e:
            log(f"    錯誤: {type(e).__name__}: {e}")


# ── Phase 2: mcgbm.taichung.gov.tw (建管系統) ───────────────────────────

def phase_mcgbm():
    log("\n" + "█" * 70)
    log(" Phase 2: 建管系統端點 (mcgbm.taichung.gov.tw)")
    log("█" * 70)

    tests = [
        ("發照日期查詢 114年", {"發照日期": "114年", "Start": "1"}),
        ("發照日期查詢 115年 (今年)", {"發照日期": "115年", "Start": "1"}),
        ("特定月份 114年03月", {"執照類別": "建造執照", "發照日期": "114年03月", "Start": "1"}),
        ("模糊查詢起造人姓王", {"起造人代表人": "王.*", "發照日期": "113年", "Start": "1"}),
        ("分頁 Start=101", {"發照日期": "113年", "Start": "101"}),
        ("歷史 100年 (2011)", {"發照日期": "100年", "Start": "1"}),
        ("歷史 95年 (2006)", {"發照日期": "95年", "Start": "1"}),
        ("無條件查詢", {"Start": "1"}),
    ]

    for label, params in tests:
        base_params = {"d": "OPENDATA", "c": "BUILDLIC"}
        base_params.update(params)
        qs = urllib.parse.urlencode(base_params, quote_via=urllib.parse.quote)
        url = f"{MCGBM_BASE}?{qs}"
        data = fetch(url, f"[mcgbm] {label}")
        count = analyse(data, label)
        record(label, "mcgbm", params, data, count)
        time.sleep(0.5)


# ── Phase 3: datacenter.taichung.gov.tw (資料中心 Swagger) ──────────────

def phase_datacenter():
    log("\n" + "█" * 70)
    log(" Phase 3: 資料中心 Swagger 端點 (datacenter.taichung.gov.tw)")
    log("█" * 70)

    uuid_json = DATACENTER_UUIDS["JSON"]
    base = f"{DATACENTER_BASE}/{uuid_json}"

    tests = [
        ("預設查詢 (limit=5)", {"limit": "5"}),
        ("全文檢索 q=臺中", {"q": "臺中", "limit": "5"}),
        ("全文檢索 q=114年", {"q": "114年", "limit": "5"}),
        ("filters 發照日期", {"filters": '{"發照日期":"114年"}', "limit": "5"}),
        ("指定欄位", {"fields": "核發執照字號,發照日期,起造人代表人", "limit": "5"}),
        ("offset + limit", {"offset": "0", "limit": "3"}),
    ]

    for label, params in tests:
        qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        url = f"{base}?{qs}"
        data = fetch(url, f"[datacenter-JSON] {label}")
        count = analyse(data, label)
        record(label, "datacenter-JSON", params, data, count)
        time.sleep(0.5)

    log("\n── 靜態資料集對照測試 ──")
    static_uuid = "cbd2f79a-e4a2-49e4-a9b9-195c04bc60b4"
    url = f"{DATACENTER_BASE}/{static_uuid}?limit=2"
    data = fetch(url, "[datacenter] 靜態資料集對照 (昇降設備)")
    count = analyse(data, "靜態對照")
    record("靜態資料集對照", "datacenter-static", {"limit": "2"}, data, count)


# ── Phase 4: 其他縣市建管系統對照 ────────────────────────────────────────

def phase_other_counties():
    log("\n" + "█" * 70)
    log(" Phase 4: 其他縣市建管系統對照（驗證 API 格式）")
    log("█" * 70)

    other_hosts = [
        ("彰化縣", "https://cpami.chcg.gov.tw/opendata/OpenDataSearchUrl.do"),
        ("苗栗縣", "https://bm.miaoli.gov.tw/opendata/OpenDataSearchUrl.do"),
        ("新北市", "https://building-apply.publicwork.ntpc.gov.tw/opendata/OpenDataSearchUrl.do"),
        ("基隆市", "https://master.klcg.gov.tw/opendata/OpenDataSearchUrl.do"),
    ]

    for county, base_url in other_hosts:
        params = {"d": "OPENDATA", "c": "BUILDLIC", "Start": "1", "發照日期": "114年01月"}
        qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        url = f"{base_url}?{qs}"
        data = fetch(url, f"[{county}] 建照查詢 114年01月", timeout=15)
        count = analyse(data, f"{county} 對照")
        record(f"{county} 對照", county, params, data, count)
        time.sleep(0.5)


# ── Summary ─────────────────────────────────────────────────────────────

def print_summary():
    log("\n\n" + "█" * 70)
    log(" 測試結果總覽")
    log("█" * 70)

    for r in RESULTS:
        if r["success"]:
            icon = "✅"
        elif r["no_data"]:
            icon = "🔸"
        else:
            icon = "❌"
        log(f"  {icon} [{r['endpoint']}] {r['test']}")
        log(f"      筆數: {r['record_count']}, 參數: {r['params']}")

    log(f"\n{'─'*70}")
    log(" 分析結論")
    log(f"{'─'*70}")

    mcgbm_ok = any(r["success"] for r in RESULTS if r["endpoint"] == "mcgbm")
    dc_ok = any(r["success"] for r in RESULTS if r["endpoint"].startswith("datacenter-JSON"))
    dc_static_ok = any(r["success"] for r in RESULTS if r["endpoint"] == "datacenter-static")
    other_ok = [r for r in RESULTS if r["endpoint"] not in ("mcgbm", "datacenter-JSON", "datacenter-static") and r["success"]]

    if mcgbm_ok:
        log("  ✅ mcgbm.taichung.gov.tw 可正常連線，建管系統 API 可用")
    else:
        log("  ❌ mcgbm.taichung.gov.tw 無法連線（可能封鎖海外 IP，僅限台灣境內存取）")

    if dc_ok:
        log("  ✅ datacenter.taichung.gov.tw 建照 JSON 端點可查詢到資料")
    else:
        if dc_static_ok:
            log("  🔸 datacenter.taichung.gov.tw 靜態資料集可用，但建照 SERVICES 端點回傳「查無此資料」")
            log("     → 建照存根為動態查詢型（SERVICES），datacenter 可能僅作為元資料入口")
            log("     → 實際查詢仍需透過 mcgbm.taichung.gov.tw 端點")
        else:
            log("  ❌ datacenter.taichung.gov.tw 端點均無法取得建照資料")

    if other_ok:
        counties = [r["endpoint"] for r in other_ok]
        log(f"  ✅ 其他縣市建管系統可連線：{', '.join(counties)}")
        log("     → 確認 OpenDataSearchUrl.do API 格式可行，台中端點僅是存取限制問題")
    else:
        log("  ⚠ 其他縣市建管系統也無法連線（可能全面限制海外 IP）")

    log(f"\n{'─'*70}")
    log(" 建議")
    log(f"{'─'*70}")
    log("  1. 若需從海外存取，考慮透過台灣 VPN/Proxy 連線至 mcgbm.taichung.gov.tw")
    log("  2. API 查詢格式確認正確：")
    log("     OpenDataSearchUrl.do?d=OPENDATA&c=BUILDLIC&Start=1&發照日期=114年03月")
    log("  3. 發照日期格式為民國年: '114年' 或 '114年03月'")
    log("  4. 支援模糊查詢: 起造人代表人=王.*明")
    log("  5. 每次回傳最多 100 筆，需用 Start 參數分頁")
    log("  6. 雙層欄位用點號：地號.行政區=西屯, 門牌.路街段巷弄=中正路")


def main():
    log("=" * 70)
    log(f" 台中市建築執照存根 OpenData API 測試報告")
    log(f" 執行時間: {datetime.now().isoformat()}")
    log(f" Python:   {sys.version}")
    log("=" * 70)

    phase_network()
    phase_mcgbm()
    phase_datacenter()
    phase_other_counties()
    print_summary()


if __name__ == "__main__":
    main()
