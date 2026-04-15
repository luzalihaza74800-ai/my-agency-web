#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣預售建案備查爬蟲 v4 — 三層完整資料
"""

import requests, json, hashlib, base64, csv, time, argparse, sys, os
from Crypto.Cipher import AES
from Crypto import Random
from datetime import datetime, timedelta

try:
    import db as _db
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

TIMEOUT      = 60
MAX_RETRY    = 3
RETRY_WAIT   = [2, 6, 15]
CKPT_DIR     = os.path.expanduser("~/.presale_crawler")
os.makedirs(CKPT_DIR, exist_ok=True)

BASE_URL  = "https://lvr.land.moi.gov.tw"
CRYPT_KEY = "lvr.land.moi.gov.tw"

CITY_CODE = {
    "台北市":"A","台中市":"B","基隆市":"C","台南市":"D","高雄市":"E",
    "新北市":"F","宜蘭縣":"G","桃園市":"H","嘉義市":"I","新竹縣":"J",
    "苗栗縣":"K","南投縣":"M","彰化縣":"N","嘉義縣":"P","雲林縣":"Q",
    "屏東縣":"T","花蓮縣":"U","台東縣":"V","金門縣":"W","澎湖縣":"X",
    "連江縣":"Z","新竹市":"O",
}

L1_FIELDS = [
    ("name","建案名稱"),("addr","坐落街道"),("apply","起造人"),("mark","建商負責人"),
    ("AA11","使用分區"),("b","坐落基地"),("license","建築執照"),("ma","主要建材"),
    ("pu","主要用途"),("ldate","完成第一次登記日期"),("applydate","申報備查日期"),
    ("e","自行銷售期間"),("f","委託代銷期間"),("house","總戶數"),("s","銷售狀態"),
    ("lat","緯度"),("lon","經度"),
]

TX_FIELDS = [
    ("_name","建案名稱"),("_sq","建案代碼"),("bu","棟及號"),("a","建物門牌"),
    ("e","成交日期"),("tp","總價（元）"),("p","單價（元/坪）"),("s","總面積（坪）"),
    ("f","樓別/樓高"),("b","建物型態"),("v","建物格局"),("t","交易標的"),
    ("cp","車位總價（萬元）"),("ma","主要建材"),("pu","主要用途"),("cinfo","解約情形"),
    ("主建物面積","主建物面積（坪）"),("陽台面積","陽台面積（坪）"),
    ("公共面積","共同使用部分面積（坪）"),("停車位面積","停車位面積（坪）"),
    ("雨遮面積","雨遮面積（坪）"),("土地地號","土地地號"),("土地使用分區","土地使用分區"),
    ("土地持分","土地持分移轉"),("車位序號","車位序號"),("車位類別","車位類別"),
    ("車位所在樓層","車位所在樓層"),("備註","備註"),
]


def _evp(pw: str, salt: bytes):
    d, di = b'', b''
    while len(d) < 48:
        di = hashlib.md5(di + pw.encode() + salt).digest(); d += di
    return d[:32], d[32:48]

def aes_encrypt(text: str) -> str:
    salt = Random.new().read(8)
    key, iv = _evp(CRYPT_KEY, salt)
    pad = 16 - len(text.encode()) % 16
    enc = AES.new(key, AES.MODE_CBC, iv).encrypt(text.encode() + bytes([pad]*pad))
    inner = base64.b64encode(b'Salted__' + salt + enc).decode()
    return base64.b64encode(inner.encode()).decode()

def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def jdump(d: dict) -> str:
    return json.dumps(d, separators=(',', ':'), ensure_ascii=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"{BASE_URL}/jsp/list.jsp",
    })
    return s

def fresh_token(session: requests.Session) -> str:
    r = session.get(f"{BASE_URL}/jsp/setToken.jsp", timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def _get_with_retry(session, url, *, stop_event=None) -> requests.Response:
    last_err = None
    for attempt in range(MAX_RETRY + 1):
        if stop_event and stop_event.is_set():
            raise InterruptedError("使用者要求停止")
        try:
            r = session.get(url, timeout=TIMEOUT)
            return r
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt < MAX_RETRY:
                wait = RETRY_WAIT[attempt]
                print(f"[Retry {attempt+1}/{MAX_RETRY}] 連線逾時，{wait}s 後重試… ({e})")
                for _ in range(wait * 2):
                    if stop_event and stop_event.is_set():
                        raise InterruptedError("使用者要求停止")
                    time.sleep(0.5)
    raise last_err


def layer1_buildings(session, city, town, starty="101", startm="1",
                     endy="115", endm="4", stop_event=None) -> list:
    token = fresh_token(session)
    params = {
        "starty": starty, "startm": startm, "endy": endy, "endm": endm,
        "qryType": "saleRemark", "city": city, "town": town, "ptype": "1",
        "p_build":"", "p_builders":"", "p_road":"",
        "p_land":"", "p_lnsy":"", "p_lnsno":"", "token": token,
    }
    pj = jdump(params)
    url = f"{BASE_URL}/SERVICE/QueryPrice/SaleData/{md5(pj)}?q={aes_encrypt(pj)}"
    r = _get_with_retry(session, url, stop_event=stop_event)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("token") == "401":
        raise RuntimeError("Token 401")
    return data


def layer2_transactions(session, city, town, case_sq, stop_event=None) -> tuple:
    params = {
        "qryType": "Sale", "city": city, "town": town, "sq": case_sq,
        "unit": "2", "t_unit": "1", "p_unit": "1",
    }
    pj = jdump(params)
    l2_hash = md5(pj)
    url = f"{BASE_URL}/SERVICE/QueryPrice/SaleList/{l2_hash}?q={aes_encrypt(pj)}"
    r = _get_with_retry(session, url, stop_event=stop_event)
    if r.status_code == 500:
        return [], l2_hash
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("token") == "401":
        raise RuntimeError("Token 401")
    rows = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    return rows, l2_hash


def layer3_detail(session, l2_hash, row, stop_event=None) -> dict:
    params = {
        "sq": row["sq"], "qryType": "sale", "cp": row.get("cp", ""),
        "unit": "2", "t_unit": "1", "p_unit": "1",
        "t": row.get("t", ""), "f": row.get("f", ""),
    }
    pj = jdump(params)
    url = f"{BASE_URL}/SERVICE/QueryPrice/detail/{l2_hash}/{aes_encrypt(pj)}"
    r = _get_with_retry(session, url, stop_event=stop_event)
    if r.status_code != 200:
        return {}
    try:
        data = r.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_special_flag(note: str, cinfo: str = "") -> str:
    text = f"{note} {cinfo}"
    flags = []
    if "解約" in text: flags.append("解約注記")
    if "毛坯" in text or "毛胚" in text: flags.append("毛坯屋")
    if "地上權" in text: flags.append("地上權")
    if "親友" in text: flags.append("親友交易")
    return ",".join(flags)


def biz_query_main(session, city, town, starty="114", startm="1",
                   endy="114", endm="3", ptype="1,2,3,4", stop_event=None) -> tuple:
    token = fresh_token(session)
    params = {
        "ptype": ptype, "starty": starty, "startm": startm, "endy": endy, "endm": endm,
        "qryType": "biz", "city": city, "town": town, "p_build": "", "ftype": "",
        "price_s": "", "price_e": "", "unit_price_s": "", "unit_price_e": "",
        "area_s": "", "area_e": "", "build_s": "", "build_e": "",
        "buildyear_s": "", "buildyear_e": "", "doorno": "", "pattern": "",
        "community": "", "floor": "", "rent_type": "", "rent_order": "",
        "urban": "", "urbantext": "", "nurban": "", "aa12": "",
        "p_purpose": "", "p_unusualcode": "", "tmoney_unit": "1",
        "pmoney_unit": "1", "unit": "2", "token": token,
    }
    pj = jdump(params)
    l2_hash = md5(pj)
    url = f"{BASE_URL}/SERVICE/QueryPrice/{l2_hash}?q={aes_encrypt(pj)}"
    r = _get_with_retry(session, url, stop_event=stop_event)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("token") == "401":
        raise RuntimeError("Token 401")
    rows = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    return rows, l2_hash


def biz_query_detail(session, l2_hash, row, stop_event=None) -> dict:
    params = {
        "sq": row.get("sq", ""), "qryType": "biz", "cp": row.get("cp", ""),
        "unit": "2", "t_unit": "1", "p_unit": "1",
        "t": row.get("t", ""), "f": row.get("f", ""),
    }
    pj = jdump(params)
    url = f"{BASE_URL}/SERVICE/QueryPrice/detail/{l2_hash}/{aes_encrypt(pj)}"
    r = _get_with_retry(session, url, stop_event=stop_event)
    if r.status_code != 200:
        return {}
    try:
        data = r.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _ckpt_path(city, town, starty, endy, ckpt_type="presale"):
    key = f"{city}_{town or 'all'}_{starty}_{endy}"
    return os.path.join(CKPT_DIR, f"ckpt_{ckpt_type}_{key}.json")

def save_checkpoint(city, town, starty, endy, done_ids: list, bldg_file: str,
                    tx_file: str, all_buildings: list, ckpt_type="presale"):
    path = _ckpt_path(city, town, starty, endy, ckpt_type)
    data = {
        "ckpt_type": ckpt_type, "city": city, "town": town,
        "starty": starty, "endy": endy, "done_ids": done_ids,
        "bldg_file": bldg_file, "tx_file": tx_file,
        "all_buildings": all_buildings, "saved_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_resale_checkpoint(city, town, starty, endy, done_months: list):
    path = _ckpt_path(city, town, starty, endy, "resale")
    data = {
        "ckpt_type": "resale", "city": city, "town": town,
        "starty": starty, "endy": endy, "done_months": done_months,
        "saved_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_checkpoint(city, town, starty, endy, ckpt_type="presale"):
    path = _ckpt_path(city, town, starty, endy, ckpt_type)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def delete_checkpoint(city, town, starty, endy, ckpt_type="presale"):
    path = _ckpt_path(city, town, starty, endy, ckpt_type)
    if os.path.exists(path):
        os.remove(path)

def delete_city_checkpoints(city, town, ckpt_type="presale"):
    town_key = town or 'all'
    new_prefix = f"ckpt_{ckpt_type}_{city}_{town_key}_"
    old_prefix = f"ckpt_{city}_{town_key}_"
    for fname in os.listdir(CKPT_DIR):
        if not fname.endswith(".json"): continue
        if fname.startswith(new_prefix) or fname.startswith(old_prefix):
            os.remove(os.path.join(CKPT_DIR, fname))

def cleanup_old_checkpoints(max_days=20):
    cutoff = datetime.now() - timedelta(days=max_days)
    for fname in os.listdir(CKPT_DIR):
        if not (fname.startswith("ckpt_") and fname.endswith(".json")): continue
        path = os.path.join(CKPT_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved_at = datetime.fromisoformat(data.get("saved_at", ""))
            if saved_at < cutoff:
                os.remove(path)
                print(f"[Checkpoint] 已清除過期備份：{fname}")
        except Exception:
            pass

def list_checkpoints():
    raw = []
    for fname in os.listdir(CKPT_DIR):
        if not (fname.startswith("ckpt_") and fname.endswith(".json")): continue
        path = os.path.join(CKPT_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "ckpt_type" not in data: continue
            raw.append(data)
        except Exception:
            pass
    seen = {}
    for d in sorted(raw, key=lambda x: x.get("saved_at", ""), reverse=True):
        key = (d.get("ckpt_type"), d.get("city"), d.get("town"),
               d.get("starty"), d.get("endy"))
        if key not in seen:
            seen[key] = d
    return list(seen.values())


def roc_to_ad(s: str) -> str:
    s = str(s).strip()
    if len(s) == 7 and s.isdigit():
        return f"{int(s[:3])+1911}/{s[3:5]}/{s[5:7]}"
    if '/' in s:
        parts = s.split('/')
        if len(parts) == 3 and parts[0].isdigit() and int(parts[0]) < 200:
            return f"{int(parts[0])+1911}/{parts[1]}/{parts[2]}"
    return s

def flatten_building(b: dict) -> dict:
    row = {}
    for key, col in L1_FIELDS:
        val = b.get(key, "")
        if key in ("applydate", "ldate") and val:
            val = roc_to_ad(val)
        row[col] = val
    return row

def flatten_transaction(bldg: dict, sq: str, tx: dict, detail: dict) -> dict:
    row = {}
    for key, col in TX_FIELDS:
        if key == "_name": row[col] = bldg.get("name", "")
        elif key == "_sq": row[col] = sq
        elif key in ("主建物面積","陽台面積","公共面積","停車位面積","雨遮面積"):
            bl = detail.get("buildlist", {})
            mapping = {"主建物面積":"主建物","陽台面積":"陽台","公共面積":"共同使用部分",
                       "停車位面積":"停車位","雨遮面積":"雨遮"}
            row[col] = bl.get(mapping[key], "")
        elif key == "土地地號": row[col] = " / ".join(d.get("d1","") for d in detail.get("d", []))
        elif key == "土地使用分區": row[col] = " / ".join(d.get("d3","") for d in detail.get("d", []))
        elif key == "土地持分": row[col] = " / ".join(d.get("d5","") for d in detail.get("d", []))
        elif key == "車位序號": row[col] = " / ".join(r.get("r1","") for r in detail.get("r", []))
        elif key == "車位類別": row[col] = " / ".join(r.get("r2","") for r in detail.get("r", []))
        elif key == "車位所在樓層": row[col] = " / ".join(r.get("r6","") for r in detail.get("r", []))
        elif key == "備註": row[col] = detail.get("note", "")
        else: row[col] = tx.get(key, "")
    return row


def _to_int(v):
    try: return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError): return None

def _to_float(v):
    try: return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError): return None


def flatten_building_for_db(bldg: dict, city: str, town: str) -> dict:
    return {
        "id": bldg.get("id", ""), "city": city, "town": town,
        "name": bldg.get("name", ""), "addr": bldg.get("addr", ""),
        "apply": bldg.get("apply", ""), "mark": bldg.get("mark", ""),
        "AA11": bldg.get("AA11", ""), "base": bldg.get("b", ""),
        "license": bldg.get("license", ""), "material": bldg.get("ma", ""),
        "purpose": bldg.get("pu", ""), "reg_date": roc_to_ad(bldg.get("ldate", "")),
        "apply_date": roc_to_ad(bldg.get("applydate", "")),
        "self_sale": bldg.get("e", ""), "agent_sale": bldg.get("f", ""),
        "house_count": _to_int(bldg.get("house", "")) or 0,
        "sales_status": bldg.get("s", ""),
        "lat": _to_float(bldg.get("lat", "")), "lon": _to_float(bldg.get("lon", "")),
        "crawled_at": datetime.now().isoformat(),
    }


def flatten_presale_tx_for_db(bldg: dict, sq: str, tx: dict, detail: dict) -> dict:
    bl    = detail.get("buildlist", {}) if detail else {}
    lands = detail.get("d", []) if detail else []
    parks = detail.get("r", []) if detail else []
    note  = detail.get("note", "") if detail else ""
    cinfo = tx.get("cinfo", "")
    tx_id = f"{sq}_{tx.get('sq', tx.get('bu', ''))}"
    return {
        "tx_id": tx_id, "building_id": bldg.get("id", ""),
        "building_name": bldg.get("name", ""), "addr": tx.get("a", ""),
        "trade_date": roc_to_ad(tx.get("e", "")),
        "total_price": _to_int(tx.get("tp", "")), "unit_price": _to_int(tx.get("p", "")),
        "area": _to_float(tx.get("s", "")), "floor": tx.get("f", ""),
        "build_type": tx.get("b", ""), "layout": tx.get("v", ""),
        "trade_target": tx.get("t", ""), "park_price": _to_int(tx.get("cp", "")),
        "material": tx.get("ma", ""), "purpose": tx.get("pu", ""), "cancel_info": cinfo,
        "main_area": _to_float(bl.get("主建物", "")), "balcony_area": _to_float(bl.get("陽台", "")),
        "public_area": _to_float(bl.get("共同使用部分", "")), "park_area": _to_float(bl.get("停車位", "")),
        "rain_area": _to_float(bl.get("雨遮", "")),
        "land_no": " / ".join(d.get("d1", "") for d in lands),
        "land_zone": " / ".join(d.get("d3", "") for d in lands),
        "land_share": " / ".join(d.get("d5", "") for d in lands),
        "park_no": " / ".join(r.get("r1", "") for r in parks),
        "park_type": " / ".join(r.get("r2", "") for r in parks),
        "park_floor": " / ".join(r.get("r6", "") for r in parks),
        "note": note, "special_flag": parse_special_flag(note, cinfo),
        "crawled_at": datetime.now().isoformat(),
    }


def flatten_resale_tx_for_db(row: dict, detail: dict, city: str, town: str, ptype: str) -> dict:
    bl    = detail.get("buildlist", {}) if detail else {}
    lands = detail.get("d", []) if detail else []
    parks = detail.get("r", []) if detail else []
    note  = (detail.get("note", "") if detail else "") or row.get("note", "")
    cinfo = row.get("cinfo", "")
    return {
        "tx_id": row.get("sq", ""), "city": city, "town": town,
        "addr": row.get("a", ""),
        "community": row.get("community", row.get("cm", row.get("c", ""))),
        "trade_date": roc_to_ad(row.get("e", "")),
        "total_price": _to_int(row.get("tp", "")), "unit_price": _to_int(row.get("p", "")),
        "area": _to_float(row.get("s", "")), "floor": row.get("f", ""),
        "build_type": row.get("b", ""), "layout": row.get("v", ""),
        "trade_target": row.get("t", ""), "park_price": _to_int(row.get("cp", "")),
        "purpose": row.get("pu", ""), "age": _to_int(row.get("age", row.get("ag", ""))),
        "elevator": row.get("elevator", row.get("el", "")),
        "management": row.get("manage", row.get("mg", row.get("management", ""))),
        "urban_zone": row.get("AA11", ""), "non_urban_zone": row.get("AA21", ""),
        "lat": _to_float(row.get("lat", "")), "lon": _to_float(row.get("lon", "")),
        "main_area": _to_float(bl.get("主建物", "")), "balcony_area": _to_float(bl.get("陽台", "")),
        "public_area": _to_float(bl.get("共同使用部分", "")), "park_area": _to_float(bl.get("停車位", "")),
        "rain_area": _to_float(bl.get("雨遮", "")),
        "land_no": " / ".join(d.get("d1", "") for d in lands),
        "land_zone": " / ".join(d.get("d3", "") for d in lands),
        "land_share": " / ".join(d.get("d5", "") for d in lands),
        "park_no": " / ".join(r.get("r1", "") for r in parks),
        "park_type": " / ".join(r.get("r2", "") for r in parks),
        "park_floor": " / ".join(r.get("r6", "") for r in parks),
        "build_structure": row.get("ms", row.get("struct", row.get("bs", ""))),
        "complete_year": row.get("cy", row.get("complete_year", "")),
        "note": note, "special_flag": parse_special_flag(note, cinfo),
        "ptype": ptype, "crawled_at": datetime.now().isoformat(),
    }


def crawl(city, town, starty="101", startm="1", endy="115", endm="12", delay=0.3,
          layer2=True, layer3=True, limit=None,
          stop_event=None, resume_from_ckpt=None,
          bldg_file=None, tx_file=None, progress_cb=None):
    session = make_session()
    cleanup_old_checkpoints(max_days=20)

    if resume_from_ckpt:
        ckpt      = resume_from_ckpt
        done_ids  = set(ckpt["done_ids"])
        buildings = ckpt["all_buildings"]
        bldg_file = ckpt["bldg_file"] or bldg_file
        tx_file   = ckpt["tx_file"]   or tx_file
        remaining = sum(1 for b in buildings if b.get("id") not in done_ids)
        print(f"[Resume] 從斷點繼續，已完成 {len(done_ids)} 棟，剩餘 {remaining} 棟")
    else:
        done_ids = set()
        delete_city_checkpoints(city, town, "presale")
        print("[Layer 1] 查詢建案清單…")
        buildings = layer1_buildings(session, city, town, starty=starty, startm=startm,
                                     endy=endy, endm=endm, stop_event=stop_event)
        seen_ids = set(); deduped = []
        for b in buildings:
            bid = b.get("id", "")
            if bid and bid in seen_ids: continue
            seen_ids.add(bid); deduped.append(b)
        if len(deduped) < len(buildings):
            print(f"[Layer 1] 去除重複 {len(buildings)-len(deduped)} 筆，剩 {len(deduped)} 筆")
        buildings = deduped
        if limit:
            buildings = buildings[:limit]
            print(f"[Layer 1] 取得 {len(buildings)} 筆建案（限制前 {limit} 筆）")
        else:
            print(f"[Layer 1] 取得 {len(buildings)} 筆建案")
        if bldg_file:
            _write_csv_header([c for _, c in L1_FIELDS], bldg_file)
        if tx_file:
            _write_csv_header([c for _, c in TX_FIELDS], tx_file)

    if not layer2:
        bldg_rows = [flatten_building(b) for b in buildings]
        if bldg_file:
            _append_csv_rows(bldg_rows, [c for _, c in L1_FIELDS], bldg_file)
        return bldg_rows, []

    tx_rows = []; bldg_rows = []; total_bldg = len(buildings); stopped = False

    for i, bldg in enumerate(buildings, 1):
        if stop_event and stop_event.is_set():
            print("[停止] 使用者要求停止，儲存目前進度…")
            stopped = True; break

        bldg_id   = bldg.get("id", "")
        bldg_name = bldg.get("name", "")
        idlist    = bldg.get("idlist", [])

        if bldg_id in done_ids:
            print(f"[Skip]   ({i}/{total_bldg}) {bldg_name}（已完成）")
            continue

        flat_bldg = flatten_building(bldg)
        bldg_rows.append(flat_bldg)
        if bldg_file:
            _append_csv_rows([flat_bldg], [c for _, c in L1_FIELDS], bldg_file)
        if _DB_AVAILABLE:
            try:
                _db.upsert_building(flatten_building_for_db(bldg, city, town))
            except Exception as e:
                print(f"[DB] 建案寫入失敗：{e}")

        if not idlist:
            done_ids.add(bldg_id)
            _save_ckpt(city, town, starty, endy, done_ids, bldg_file, tx_file, buildings)
            continue

        print(f"[Layer 2] ({i}/{total_bldg}) {bldg_name}", end="", flush=True)

        all_txns = []; l2_hash = ""
        for entry in idlist:
            if stop_event and stop_event.is_set():
                stopped = True; break
            parts = entry.split(",")
            if len(parts) < 2: continue
            case_sq = f"{parts[0]}-{parts[1]}"
            time.sleep(delay)
            txns, h = layer2_transactions(session, city, town, case_sq, stop_event=stop_event)
            if txns:
                all_txns.extend([(case_sq, t) for t in txns]); l2_hash = h

        if stopped: break
        print(f" → {len(all_txns)} 筆成交")

        if not all_txns or not layer3:
            batch    = [flatten_transaction(bldg, sq, tx, {}) for sq, tx in all_txns]
            db_batch = [flatten_presale_tx_for_db(bldg, sq, tx, {}) for sq, tx in all_txns]
            tx_rows.extend(batch)
            if tx_file and batch:
                _append_csv_rows(batch, [c for _, c in TX_FIELDS], tx_file)
            if _DB_AVAILABLE and db_batch:
                try: _db.upsert_presale_tx_batch(db_batch)
                except Exception as e: print(f"[DB] 交易批次寫入失敗：{e}")
        else:
            batch = []; db_batch = []
            for sq, tx in all_txns:
                if stop_event and stop_event.is_set():
                    stopped = True; break
                time.sleep(delay)
                detail = layer3_detail(session, l2_hash, tx, stop_event=stop_event)
                row = flatten_transaction(bldg, sq, tx, detail)
                tx_rows.append(row); batch.append(row)
                db_batch.append(flatten_presale_tx_for_db(bldg, sq, tx, detail))
            if tx_file and batch:
                _append_csv_rows(batch, [c for _, c in TX_FIELDS], tx_file)
            if _DB_AVAILABLE and db_batch:
                try: _db.upsert_presale_tx_batch(db_batch)
                except Exception as e: print(f"[DB] 交易批次寫入失敗：{e}")
            if stopped: break

        done_ids.add(bldg_id)
        _save_ckpt(city, town, starty, endy, done_ids, bldg_file, tx_file, buildings)
        if progress_cb:
            progress_cb(len(done_ids), len(tx_rows))

    if not stopped:
        delete_checkpoint(city, town, starty, endy)
        print("[完成] 所有建案爬取完畢，checkpoint 已清除")
    else:
        remaining = sum(1 for b in buildings if b.get("id") not in done_ids)
        print(f"[中斷] 進度已儲存，剩餘 {remaining} 棟，可從網頁點「繼續」恢復")

    return bldg_rows, tx_rows


def _save_ckpt(city, town, starty, endy, done_ids, bldg_file, tx_file, buildings):
    save_checkpoint(city, town, starty, endy,
                    list(done_ids), bldg_file or "", tx_file or "", buildings,
                    ckpt_type="presale")


def crawl_resale(city, town, starty="101", startm="1", endy="115", endm="12",
                 ptype="1,2,3,4", delay=0.3,
                 stop_event=None, resume_from_ckpt=None, progress_cb=None):
    if not _DB_AVAILABLE:
        raise RuntimeError("db.py 未載入，無法執行買賣查詢")

    session = make_session()
    cleanup_old_checkpoints(max_days=20)

    all_months = []
    sy, sm = int(starty), int(startm)
    ey, em = int(endy),   int(endm)
    for y in range(sy, ey + 1):
        m_start = sm if y == sy else 1
        m_end   = em if y == ey else 12
        for m in range(m_start, m_end + 1):
            all_months.append((str(y), str(m)))

    if resume_from_ckpt:
        done_set  = set(tuple(x) for x in resume_from_ckpt.get("done_months", []))
        remaining = [p for p in all_months if p not in done_set]
        print(f"[Resume] 買賣斷點繼續，已完成 {len(done_set)} 個月，剩餘 {len(remaining)} 個月")
    else:
        done_set  = set()
        remaining = all_months
        delete_city_checkpoints(city, town, "resale")

    known_ids = _db.get_known_resale_tx_ids(city, town)
    print(f"[Resale] DB 已知 {len(known_ids)} 筆，開始增量爬取…")

    tx_total = 0; tx_new = 0; stopped = False; total = len(remaining)

    for mi, (y, m) in enumerate(remaining, 1):
        if stop_event and stop_event.is_set():
            print("[停止] 使用者要求停止"); stopped = True; break

        print(f"[Resale] ({mi}/{total}) {y}年{m}月", end="", flush=True)

        try:
            rows, l2_hash = biz_query_main(session, city, town,
                starty=y, startm=m, endy=y, endm=m,
                ptype=ptype, stop_event=stop_event)
        except InterruptedError:
            stopped = True; break
        except Exception as e:
            print(f" ✗ 主列表失敗：{e}")
            done_set.add((y, m)); time.sleep(delay); continue

        new_rows = [r for r in rows if r.get("sq", "") not in known_ids]
        print(f" → {len(rows)} 筆，新增 {len(new_rows)} 筆")
        tx_total += len(rows)

        db_batch = []
        for row in new_rows:
            if stop_event and stop_event.is_set():
                stopped = True; break
            time.sleep(delay)
            try:
                detail = biz_query_detail(session, l2_hash, row, stop_event=stop_event)
            except InterruptedError:
                stopped = True; break
            except Exception:
                detail = {}
            db_batch.append(flatten_resale_tx_for_db(row, detail, city, town, ptype))
            known_ids.add(row.get("sq", ""))

        if db_batch:
            try:
                _db.upsert_resale_tx_batch(db_batch); tx_new += len(db_batch)
            except Exception as e:
                print(f"[DB] 批次寫入失敗：{e}")

        if stopped: break

        done_set.add((y, m))
        save_resale_checkpoint(city, town, starty, endy, list(done_set))
        if progress_cb:
            progress_cb(len(done_set), tx_total)
        time.sleep(delay)

    if not stopped:
        delete_checkpoint(city, town, starty, endy, "resale")
        print(f"[Resale] 完成：共 {tx_total} 筆，新增 {tx_new} 筆")
    else:
        if done_set:
            save_resale_checkpoint(city, town, starty, endy, list(done_set))
        remaining_count = total - len(done_set)
        print(f"[Resale] 中斷：已處理 {len(done_set)} 個月，"
              f"剩餘約 {remaining_count} 個月，共 {tx_total} 筆，新增 {tx_new} 筆")

    return tx_total, tx_new


def _write_csv_header(fieldnames, filename):
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writeheader()

def _append_csv_rows(rows, fieldnames, filename):
    if not rows: return
    with open(filename, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writerows(rows)

def save_csv(rows, fieldnames, filename):
    if not rows:
        print(f"  (無資料，跳過 {filename})"); return
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"[+] 已儲存：{filename}  ({len(rows)} 列)")

def print_summary(bldg_rows, tx_rows, n=10):
    print(f"\n{'='*72}")
    print(f"建案清單：{len(bldg_rows)} 筆  |  成交記錄：{len(tx_rows)} 筆")
    print(f"{'='*72}")


def main():
    p = argparse.ArgumentParser(description="預售建案三層爬蟲")
    p.add_argument("--city",   default="B")
    p.add_argument("--town",   default="B06")
    p.add_argument("--starty", default="101")
    p.add_argument("--endy",   default="115")
    p.add_argument("--delay",  default=0.3, type=float)
    p.add_argument("--no-l2",  action="store_true")
    p.add_argument("--no-l3",  action="store_true")
    p.add_argument("--limit",  default=None, type=int)
    p.add_argument("--out-dir",default="~/Desktop")
    args = p.parse_args()

    out_dir = os.path.expanduser(args.out_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{args.city}_{args.town or 'all'}_{ts}"

    bldg_rows, tx_rows = crawl(
        city=args.city, town=args.town,
        starty=args.starty, endy=args.endy,
        delay=args.delay,
        layer2=not args.no_l2,
        layer3=not args.no_l3,
        limit=args.limit,
    )

    print_summary(bldg_rows, tx_rows)
    save_csv(bldg_rows, [col for _, col in L1_FIELDS],
             os.path.join(out_dir, f"buildings_{tag}.csv"))
    if tx_rows:
        save_csv(tx_rows, [col for _, col in TX_FIELDS],
                 os.path.join(out_dir, f"transactions_{tag}.csv"))


if __name__ == "__main__":
    main()
