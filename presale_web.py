#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, json, time, uuid, threading, queue, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from flask import Flask, render_template_string, request, Response, send_file, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from presale_crawler_full import (
    crawl, crawl_resale, L1_FIELDS, TX_FIELDS, CITY_CODE,
    load_checkpoint, list_checkpoints, delete_checkpoint, CKPT_DIR,
)
import db as _db
import scheduler as _sched

app  = Flask(__name__)
JOBS = {}
OUT  = os.path.dirname(os.path.abspath(__file__))
MAX_CONCURRENT_JOBS = 3

def _running_job_count():
    return sum(1 for j in JOBS.values() if j.get("status") == "running")

def _duplicate_running_job(city, town, starty, endy, data_type):
    for jid, j in JOBS.items():
        if (j.get("status") == "running"
                and j.get("city") == city
                and j.get("town", "") == (town or "")
                and str(j.get("starty", "")) == str(starty)
                and str(j.get("endy",   "")) == str(endy)
                and j.get("data_type") == data_type):
            return jid
    return None

CITIES = [
    ("A","台北市"),("F","新北市"),("C","基隆市"),("O","新竹市"),("I","嘉義市"),
    ("B","台中市"),("D","台南市"),("E","高雄市"),("H","桃園市"),("G","宜蘭縣"),
    ("J","新竹縣"),("K","苗栗縣"),("N","彰化縣"),("M","南投縣"),("Q","雲林縣"),
    ("P","嘉義縣"),("T","屏東縣"),("U","花蓮縣"),("V","台東縣"),
    ("W","金門縣"),("X","澎湖縣"),("Z","連江縣"),
]

TOWNS = {
    "A":[("","全市"),("A01","中正區"),("A02","大同區"),("A03","中山區"),("A04","松山區"),("A05","大安區"),("A06","萬華區"),("A07","信義區"),("A08","士林區"),("A09","北投區"),("A10","內湖區"),("A11","南港區"),("A12","文山區")],
    "B":[("","全市"),("B01","中區"),("B02","東區"),("B03","南區"),("B04","西區"),("B05","北區"),("B06","西屯區"),("B07","南屯區"),("B08","北屯區"),("B09","豐原區"),("B10","東勢區"),("B11","大甲區"),("B12","清水區"),("B13","沙鹿區"),("B14","梧棲區"),("B15","后里區"),("B16","神岡區"),("B17","潭子區"),("B18","大雅區"),("B19","新社區"),("B20","石岡區"),("B21","外埔區"),("B22","大安區"),("B23","烏日區"),("B24","大肚區"),("B25","龍井區"),("B26","霧峰區"),("B27","太平區"),("B28","大里區"),("B29","和平區")],
    "C":[("","全市"),("C01","仁愛區"),("C02","信義區"),("C03","中正區"),("C04","中山區"),("C05","安樂區"),("C06","暖暖區"),("C07","七堵區")],
    "D":[("","全市"),("D01","中西區"),("D02","東區"),("D03","南區"),("D04","北區"),("D05","安平區"),("D06","安南區"),("D07","永康區"),("D08","歸仁區"),("D09","新化區"),("D10","左鎮區"),("D11","玉井區"),("D12","楠西區"),("D13","南化區"),("D14","仁德區"),("D15","關廟區"),("D16","龍崎區"),("D17","官田區"),("D18","麻豆區"),("D19","佳里區"),("D20","西港區"),("D21","七股區"),("D22","將軍區"),("D23","學甲區"),("D24","北門區"),("D25","新營區"),("D26","後壁區"),("D27","白河區"),("D28","東山區"),("D29","六甲區"),("D30","下營區"),("D31","柳營區"),("D32","鹽水區"),("D33","善化區"),("D34","大內區"),("D35","山上區"),("D36","新市區"),("D37","安定區")],
    "E":[("","全市"),("E01","新興區"),("E02","前金區"),("E03","苓雅區"),("E04","鹽埕區"),("E05","鼓山區"),("E06","旗津區"),("E07","前鎮區"),("E08","三民區"),("E09","楠梓區"),("E10","小港區"),("E11","左營區"),("E12","仁武區"),("E13","大社區"),("E16","岡山區"),("E17","路竹區"),("E18","阿蓮區"),("E19","田寮區"),("E20","燕巢區"),("E21","橋頭區"),("E22","梓官區"),("E23","彌陀區"),("E24","永安區"),("E25","湖內區"),("E26","鳳山區"),("E27","大寮區"),("E28","林園區"),("E29","鳥松區"),("E30","大樹區"),("E31","旗山區"),("E32","美濃區"),("E33","六龜區"),("E34","內門區"),("E35","杉林區"),("E36","甲仙區"),("E40","茄萣區")],
    "F":[("","全市"),("F01","板橋區"),("F02","三重區"),("F03","中和區"),("F04","永和區"),("F05","新莊區"),("F06","新店區"),("F07","樹林區"),("F08","鶯歌區"),("F09","三峽區"),("F10","淡水區"),("F11","汐止區"),("F12","瑞芳區"),("F13","土城區"),("F14","蘆洲區"),("F15","五股區"),("F16","泰山區"),("F17","林口區"),("F18","深坑區"),("F19","石碇區"),("F20","坪林區"),("F21","三芝區"),("F22","石門區"),("F23","八里區"),("F24","平溪區"),("F25","雙溪區"),("F26","貢寮區"),("F27","金山區"),("F28","萬里區"),("F29","烏來區")],
    "G":[("","全縣"),("G01","宜蘭市"),("G02","羅東鎮"),("G03","蘇澳鎮"),("G04","頭城鎮"),("G05","礁溪鄉"),("G06","壯圍鄉"),("G07","員山鄉"),("G08","冬山鄉"),("G09","五結鄉"),("G10","三星鄉"),("G11","大同鄉"),("G12","南澳鄉")],
    "H":[("","全市"),("H01","中壢區"),("H02","平鎮區"),("H03","龍潭區"),("H04","楊梅區"),("H05","新屋區"),("H06","觀音區"),("H07","桃園區"),("H08","龜山區"),("H09","八德區"),("H10","大溪區"),("H11","復興區"),("H12","大園區"),("H13","蘆竹區")],
    "I":[("","全市"),("I01","東區"),("I02","西區")],
    "J":[("","全縣"),("J01","竹北市"),("J02","湖口鄉"),("J03","新豐鄉"),("J04","新埔鎮"),("J05","關西鎮"),("J06","芎林鄉"),("J07","寶山鄉"),("J08","竹東鎮"),("J09","五峰鄉"),("J10","橫山鄉"),("J11","尖石鄉"),("J12","北埔鄉"),("J13","峨眉鄉")],
    "K":[("","全縣"),("K01","苗栗市"),("K02","苑裡鎮"),("K03","通霄鎮"),("K04","竹南鎮"),("K05","頭份市"),("K06","造橋鄉"),("K07","頭屋鄉"),("K08","公館鄉"),("K09","大湖鄉"),("K10","泰安鄉"),("K11","銅鑼鄉"),("K12","三義鄉"),("K13","西湖鄉"),("K14","卓蘭鎮"),("K16","後龍鎮"),("K17","獅潭鄉"),("K18","南庄鄉")],
    "M":[("","全縣"),("M01","南投市"),("M02","中寮鄉"),("M03","草屯鎮"),("M04","國姓鄉"),("M05","埔里鎮"),("M06","仁愛鄉"),("M07","名間鄉"),("M08","集集鎮"),("M09","水里鄉"),("M10","魚池鄉"),("M11","信義鄉"),("M12","竹山鎮"),("M13","鹿谷鄉")],
    "N":[("","全縣"),("N01","彰化市"),("N02","芬園鄉"),("N03","花壇鄉"),("N04","秀水鄉"),("N05","鹿港鎮"),("N06","福興鄉"),("N07","線西鄉"),("N08","和美鎮"),("N09","伸港鄉"),("N10","員林市"),("N11","社頭鄉"),("N12","永靖鄉"),("N13","埔心鄉"),("N14","溪湖鎮"),("N15","大村鄉"),("N16","埔鹽鄉"),("N17","田中鎮"),("N18","北斗鎮"),("N19","田尾鄉"),("N20","埤頭鄉"),("N21","溪州鄉"),("N22","竹塘鄉"),("N23","二林鎮"),("N24","大城鄉"),("N25","芳苑鄉"),("N26","二水鄉")],
    "O":[("","全市"),("O01","東區"),("O02","北區"),("O03","香山區")],
    "P":[("","全縣"),("P01","太保市"),("P02","朴子市"),("P03","布袋鎮"),("P04","大林鎮"),("P05","民雄鄉"),("P06","溪口鄉"),("P07","新港鄉"),("P08","六腳鄉"),("P09","東石鄉"),("P10","義竹鄉"),("P11","鹿草鄉"),("P12","水上鄉"),("P13","中埔鄉"),("P14","竹崎鄉"),("P15","梅山鄉"),("P16","番路鄉"),("P17","大埔鄉"),("P18","阿里山鄉")],
    "Q":[("","全縣"),("Q01","斗南鎮"),("Q02","大埤鄉"),("Q03","虎尾鎮"),("Q04","土庫鎮"),("Q05","褒忠鄉"),("Q06","東勢鄉"),("Q07","台西鄉"),("Q08","崙背鄉"),("Q09","麥寮鄉"),("Q10","斗六市"),("Q11","林內鄉"),("Q12","古坑鄉"),("Q13","莿桐鄉"),("Q14","西螺鎮"),("Q15","二崙鄉"),("Q16","北港鎮"),("Q17","水林鄉"),("Q18","口湖鄉"),("Q19","四湖鄉"),("Q20","元長鄉")],
    "T":[("","全縣"),("T01","屏東市"),("T02","三地門鄉"),("T03","霧台鄉"),("T04","瑪家鄉"),("T05","九如鄉"),("T06","里港鄉"),("T07","高樹鄉"),("T08","鹽埔鄉"),("T09","長治鄉"),("T10","麟洛鄉"),("T11","竹田鄉"),("T12","內埔鄉"),("T13","萬丹鄉"),("T14","潮州鎮"),("T15","泰武鄉"),("T16","來義鄉"),("T17","萬巒鄉"),("T18","崁頂鄉"),("T19","新埤鄉"),("T20","南州鄉"),("T21","林邊鄉"),("T22","東港鎮"),("T23","琉球鄉"),("T24","佳冬鄉"),("T25","新園鄉"),("T26","枋寮鄉"),("T27","枋山鄉"),("T28","春日鄉"),("T29","獅子鄉"),("T30","車城鄉"),("T31","牡丹鄉"),("T32","恆春鎮"),("T33","滿州鄉")],
    "U":[("","全縣"),("U01","花蓮市"),("U02","新城鄉"),("U03","秀林鄉"),("U04","吉安鄉"),("U05","壽豐鄉"),("U06","鳳林鎮"),("U07","光復鄉"),("U08","豐濱鄉"),("U09","瑞穗鄉"),("U10","萬榮鄉"),("U11","玉里鎮"),("U12","卓溪鄉"),("U13","富里鄉")],
    "V":[("","全縣"),("V01","台東市"),("V02","綠島鄉"),("V03","蘭嶼鄉"),("V04","延平鄉"),("V05","卑南鄉"),("V06","鹿野鄉"),("V07","關山鎮"),("V08","海端鄉"),("V09","池上鄉"),("V10","東河鄉"),("V11","成功鎮"),("V12","長濱鄉"),("V13","太麻里鄉"),("V14","金峰鄉"),("V15","大武鄉"),("V16","達仁鄉")],
    "W":[("","全縣"),("W01","金城鎮"),("W02","金湖鎮"),("W03","金沙鎮"),("W04","金寧鄉"),("W05","烈嶼鄉"),("W06","烏坵鄉")],
    "X":[("","全縣"),("X01","馬公市"),("X02","西嶼鄉"),("X03","望安鄉"),("X04","七美鄉"),("X05","白沙鄉"),("X06","湖西鄉")],
    "Z":[("","全縣"),("Z01","南竿鄉"),("Z02","北竿鄉"),("Z03","莒光鄉"),("Z04","東引鄉")],
}


class QueueWriter:
    def __init__(self, q):
        self._q, self._buf = q, ""
    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:
                self._q.put(("log", line))
    def flush(self): pass


def _make_job(data_type="presale", city="", town="", starty="", endy=""):
    return {"status": "running", "queue": queue.Queue(),
            "stop_event": threading.Event(), "files": [],
            "data_type": data_type, "city": city, "town": town,
            "starty": starty, "endy": endy, "hist_id": None,
            "live_bldg": 0, "live_tx": 0}


def run_presale_job(job_id, city, town, starty, startm="1", endy="115", endm="12",
                   delay=0.3, do_l2=True, do_l3=True, limit=None, resume_ckpt=None):
    job = JOBS[job_id]; q = job["queue"]; stop_event = job["stop_event"]
    old_stdout = sys.stdout; sys.stdout = QueueWriter(q)
    hist_id = None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"{city}_{town or 'all'}_{ts}"
        bldg_file = (resume_ckpt or {}).get("bldg_file") or os.path.join(OUT, f"buildings_{tag}.csv")
        tx_file = ((resume_ckpt or {}).get("tx_file") or (os.path.join(OUT, f"transactions_{tag}.csv") if do_l2 else None))
        job["bldg_file"] = bldg_file; job["tx_file"] = tx_file
        hist_id = _db.history_start("presale", city, town, starty, endy)
        job["hist_id"] = hist_id
        def _progress(bldg_done, tx_done):
            job["live_bldg"] = bldg_done; job["live_tx"] = tx_done
        bldg_rows, tx_rows = crawl(city=city, town=town,
            starty=starty, startm=startm, endy=endy, endm=endm,
            delay=float(delay), layer2=do_l2, layer3=do_l3,
            limit=limit or None, stop_event=stop_event,
            resume_from_ckpt=resume_ckpt, bldg_file=bldg_file,
            tx_file=tx_file, progress_cb=_progress)
        stats = _db.get_stats_by(city, town)
        bldg_cnt = stats.get("buildings", len(bldg_rows))
        tx_cnt   = stats.get("presale_tx", len(tx_rows))
        if stop_event.is_set():
            job["status"] = "stopped"; _db.history_stopped(hist_id, bldg_cnt, tx_cnt)
        else:
            job["status"] = "done"; _db.history_done(hist_id, bldg_cnt, tx_cnt)
        files = _collect_files(bldg_file, tx_file); job["files"] = files
        q.put(("stopped" if stop_event.is_set() else "done", json.dumps(files)))
    except Exception as e:
        job["status"] = "error"; q.put(("log", f"[ERROR] {e}")); q.put(("log", traceback.format_exc())); q.put(("error", str(e)))
        if hist_id: _db.history_error(hist_id, str(e))
    finally:
        sys.stdout = old_stdout; q.put(None)


def run_resale_job(job_id, city, town, starty, startm="1", endy="115", endm="12",
                   delay=0.3, ptype="1,2,3,4", resume_ckpt=None):
    job = JOBS[job_id]; q = job["queue"]; stop_event = job["stop_event"]
    old_stdout = sys.stdout; sys.stdout = QueueWriter(q)
    hist_id = None
    try:
        hist_id = _db.history_start("resale", city, town, starty, endy)
        job["hist_id"] = hist_id
        def _progress(bldg_done, tx_done):
            job["live_bldg"] = bldg_done; job["live_tx"] = tx_done
        tx_total, tx_new = crawl_resale(city=city, town=town,
            starty=starty, startm=startm, endy=endy, endm=endm,
            ptype=ptype, delay=float(delay), stop_event=stop_event,
            resume_from_ckpt=resume_ckpt, progress_cb=_progress)
        stats = _db.get_stats_by(city, town)
        if stop_event.is_set():
            job["status"] = "stopped"; _db.history_stopped(hist_id, 0, stats.get("resale_tx", tx_new))
        else:
            job["status"] = "done"; _db.history_done(hist_id, 0, stats.get("resale_tx", tx_new))
        q.put(("done" if not stop_event.is_set() else "stopped",
               json.dumps({"tx_total": tx_total, "tx_new": tx_new})))
    except Exception as e:
        job["status"] = "error"; q.put(("log", f"[ERROR] {e}")); q.put(("log", traceback.format_exc())); q.put(("error", str(e)))
        if hist_id: _db.history_error(hist_id, str(e))
    finally:
        sys.stdout = old_stdout; q.put(None)


def _collect_files(bldg_file, tx_file):
    files = []
    if bldg_file and os.path.exists(bldg_file): files.append(("buildings", os.path.basename(bldg_file)))
    if tx_file and os.path.exists(tx_file): files.append(("transactions", os.path.basename(tx_file)))
    return files


@app.get("/api/towns/<city>")
def api_towns(city): return jsonify(TOWNS.get(city, []))

@app.get("/api/map-towns")
def api_map_towns():
    city = request.args.get("city", "") or None
    data_type = request.args.get("type", "all")
    raw = _db.get_towns_with_data(city=city, data_type=data_type)
    result = []
    for item in raw:
        c, t = item["city"], item["town"]
        name = next((n for code, n in TOWNS.get(c, []) if code == t), t)
        result.append({"city": c, "town": t, "name": name})
    return jsonify(result)

@app.get("/api/stats")
def api_stats(): return jsonify(_db.get_stats())

@app.get("/api/jobs/running")
def api_jobs_running():
    running = [{"job_id": jid, "data_type": j["data_type"], "city": j["city"],
                "town": j["town"], "starty": j["starty"], "endy": j["endy"], "status": j["status"]}
               for jid, j in JOBS.items() if j.get("status") == "running"]
    return jsonify({"count": len(running), "max": MAX_CONCURRENT_JOBS, "jobs": running})

@app.get("/api/history")
def api_history():
    limit = int(request.args.get("limit", 100))
    rows  = _db.get_history(limit)
    running = {job["hist_id"]: (jid, job) for jid, job in JOBS.items()
               if job.get("status") == "running" and job.get("hist_id")}
    for r in rows:
        match = running.get(r["id"])
        if match:
            jid, job = match; r["job_id"] = jid
            r["bldg_count"] = job.get("live_bldg", 0); r["tx_count"] = job.get("live_tx", 0)
        else:
            r["job_id"] = None
    return jsonify(rows)

@app.delete("/api/history/<int:hist_id>")
def api_delete_history(hist_id):
    _db.delete_history(hist_id); return jsonify({"ok": True})

@app.post("/api/coverage")
def api_coverage():
    f = request.json or {}
    result = _db.get_coverage(data_type=f.get("data_type","presale"), city=f.get("city",""),
        town=f.get("town",""), starty=int(f.get("starty",101)), endy=int(f.get("endy",115)))
    return jsonify(result)

@app.get("/api/map-data")
def api_map_data():
    rows = _db.get_map_data(request.args.get("city") or None, request.args.get("town") or None,
        request.args.get("type","all"), request.args.get("starty") or None, request.args.get("endy") or None)
    return jsonify(rows)

@app.get("/api/scheduler/status")
def api_sched_status(): return jsonify(_sched.get_scheduler_status())

@app.post("/api/scheduler/toggle")
def api_sched_toggle():
    f = request.json or {}
    if f.get("enable"):
        ok = _sched.start_scheduler(); return jsonify({"ok": ok, "status": _sched.get_scheduler_status()})
    else:
        _sched.stop_scheduler(); return jsonify({"ok": True, "status": _sched.get_scheduler_status()})

@app.post("/api/scheduler/trigger")
def api_sched_trigger():
    ok, msg = _sched.trigger_now(); return jsonify({"ok": ok, "msg": msg})

@app.post("/api/scheduler/stop-job")
def api_sched_stop_job():
    _sched.stop_running_job(); return jsonify({"ok": True})

@app.post("/api/start")
def api_start():
    if _running_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"目前已有 {MAX_CONCURRENT_JOBS} 個爬蟲在執行，請等待完成後再啟動"}), 429
    f = request.json or {}
    city = f.get("city","B"); town = f.get("town","")
    starty = str(f.get("starty","101")); startm = str(f.get("startm","1"))
    endy = str(f.get("endy","115")); endm = str(f.get("endm","12"))
    if _duplicate_running_job(city, town, starty, endy, "presale"):
        return jsonify({"error": f"相同範圍已在執行中"}), 429
    job_id = uuid.uuid4().hex; JOBS[job_id] = _make_job("presale", city, town, starty, endy)
    threading.Thread(target=run_presale_job, daemon=True, kwargs=dict(
        job_id=job_id, city=city, town=town, starty=starty, startm=startm, endy=endy, endm=endm,
        delay=float(f.get("delay",0.3)), do_l2=f.get("layer2",True), do_l3=f.get("layer3",True),
        limit=int(f["limit"]) if f.get("limit") else None)).start()
    return jsonify({"job_id": job_id})

# ── 全台模式 checkpoint 路徑 ─────────────────────────────────────────────────
TAIWAN_CKPT_DIR = os.path.expanduser("~/.presale_crawler")
def _taiwan_ckpt_path(dtype, starty, endy):
    return os.path.join(TAIWAN_CKPT_DIR, f"ckpt_taiwan_{dtype}_{starty}_{endy}.json")

def _save_taiwan_ckpt(dtype, starty, endy, done_pairs):
    path = _taiwan_ckpt_path(dtype, starty, endy)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"dtype": dtype, "starty": starty, "endy": endy,
                   "done_pairs": done_pairs,
                   "saved_at": datetime.now().isoformat()}, f, ensure_ascii=False)

def _load_taiwan_ckpt(dtype, starty, endy):
    path = _taiwan_ckpt_path(dtype, starty, endy)
    if not os.path.exists(path): return None
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return None

def _delete_taiwan_ckpt(dtype, starty, endy):
    path = _taiwan_ckpt_path(dtype, starty, endy)
    if os.path.exists(path): os.remove(path)

def _list_taiwan_ckpts():
    result = []
    for fname in os.listdir(TAIWAN_CKPT_DIR):
        if not fname.startswith("ckpt_taiwan_"): continue
        try:
            with open(os.path.join(TAIWAN_CKPT_DIR, fname), "r") as f:
                result.append(json.load(f))
        except: pass
    return result


TAIWAN_TOWN_MAP = {
    "A":["A01","A02","A03","A04","A05","A06","A07","A08","A09","A10","A11","A12"],
    "F":["F01","F02","F03","F04","F05","F06","F07","F08","F09","F10","F11","F12","F13","F14","F15","F16","F17","F18","F19","F20","F21","F22","F23","F24","F25","F26","F27","F28","F29"],
    "C":["C01","C02","C03","C04","C05","C06","C07"],
    "B":["B01","B02","B03","B04","B05","B06","B07","B08","B09","B10","B11","B12","B13","B14","B15","B16","B17","B18","B19","B20","B21","B22","B23","B24","B25","B26","B27","B28","B29"],
    "D":["D01","D02","D03","D04","D05","D06","D07","D08","D09","D10","D11","D12","D13","D14","D15","D16","D17","D18","D19","D20","D21","D22","D23","D24","D25","D26","D27","D28","D29","D30","D31","D32","D33","D34","D35","D36","D37"],
    "E":["E01","E02","E03","E04","E05","E06","E07","E08","E09","E10","E11","E12","E13","E16","E17","E18","E19","E20","E21","E22","E23","E24","E25","E26","E27","E28","E29","E30","E31","E32","E33","E34","E35","E36","E40"],
    "H":["H01","H02","H03","H04","H05","H06","H07","H08","H09","H10","H11","H12","H13"],
    "I":["I01","I02"],
    "J":["J01","J02","J03","J04","J05","J06","J07","J08","J09","J10","J11","J12","J13"],
    "K":["K01","K02","K03","K04","K05","K06","K07","K08","K09","K10","K11","K12","K13","K14","K16","K17","K18"],
    "M":["M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12","M13"],
    "N":["N01","N02","N03","N04","N05","N06","N07","N08","N09","N10","N11","N12","N13","N14","N15","N16","N17","N18","N19","N20","N21","N22","N23","N24","N25","N26"],
    "O":["O01","O02","O03"],
    "P":["P01","P02","P03","P04","P05","P06","P07","P08","P09","P10","P11","P12","P13","P14","P15","P16","P17","P18"],
    "Q":["Q01","Q02","Q03","Q04","Q05","Q06","Q07","Q08","Q09","Q10","Q11","Q12","Q13","Q14","Q15","Q16","Q17","Q18","Q19","Q20"],
    "T":["T01","T02","T03","T04","T05","T06","T07","T08","T09","T10","T11","T12","T13","T14","T15","T16","T17","T18","T19","T20","T21","T22","T23","T24","T25","T26","T27","T28","T29","T30","T31","T32","T33"],
    "U":["U01","U02","U03","U04","U05","U06","U07","U08","U09","U10","U11","U12","U13"],
    "V":["V01","V02","V03","V04","V05","V06","V07","V08","V09","V10","V11","V12","V13","V14","V15","V16"],
    "W":["W01","W02","W03"],
    "X":["X01","X02","X03","X04","X05","X06"],
    "G":["G01","G02","G03","G04","G05","G06","G07","G08","G09","G10","G11","G12"],
    "Z":["Z01","Z02","Z03","Z04"],
}
TAIWAN_CITY_ORDER = ["A","F","C","O","I","B","D","E","H","G","J","K","N","M","Q","P","T","U","V","W","X","Z"]


@app.get("/api/taiwan-ckpts")
def api_taiwan_ckpts():
    ckpts = _list_taiwan_ckpts()
    city_name_map = {v:k for k,v in CITY_CODE.items()}
    result = []
    for c in ckpts:
        done  = len(c.get("done_pairs", []))
        total = sum(len(TAIWAN_TOWN_MAP.get(city, [""])) for city in TAIWAN_CITY_ORDER)
        cur_city = ""
        # 找出下一個未完成的縣市
        done_set = set(tuple(x) for x in c.get("done_pairs", []))
        for city in TAIWAN_CITY_ORDER:
            for town in TAIWAN_TOWN_MAP.get(city, [""]):
                if (city, town) not in done_set:
                    cur_city = city_name_map.get(city, city)
                    break
            if cur_city: break
        result.append({
            "dtype": c["dtype"], "starty": c["starty"], "endy": c["endy"],
            "done": done, "total": total, "saved_at": c.get("saved_at",""),
            "cur_city": cur_city,
        })
    return jsonify(result)

@app.delete("/api/taiwan-ckpts/<dtype>/<starty>/<endy>")
def api_del_taiwan_ckpt(dtype, starty, endy):
    _delete_taiwan_ckpt(dtype, starty, endy)
    return jsonify({"ok": True})

@app.post("/api/resume-taiwan")
def api_resume_taiwan():
    f      = request.json or {}
    dtype  = f.get("dtype", "presale")
    starty = f.get("starty", "101")
    endy   = f.get("endy",   "115")
    delay  = float(f.get("delay", 0.5))
    ckpt   = _load_taiwan_ckpt(dtype, starty, endy)
    if not ckpt: return jsonify({"error": "找不到全台 checkpoint"}), 404
    job_id = uuid.uuid4().hex
    JOBS[job_id] = _make_job(dtype, "ALL", "", starty, endy)
    done_pairs = [tuple(x) for x in ckpt.get("done_pairs", [])]
    threading.Thread(target=_run_taiwan_job, daemon=True,
        kwargs=dict(job_id=job_id, dtype=dtype, starty=starty, endy=endy,
                    delay=delay, done_pairs=done_pairs)).start()
    return jsonify({"job_id": job_id})


def _run_taiwan_job(job_id, dtype, starty, endy, delay=0.5, done_pairs=None):
    """3 執行緒並行，逐縣市逐行政區爬取，每完成一個行政區存 checkpoint"""
    job        = JOBS[job_id]
    q          = job["queue"]
    stop_event = job["stop_event"]
    city_name_map = {v:k for k,v in CITY_CODE.items()}

    done_set  = set(done_pairs or [])
    lock      = threading.Lock()
    log_lock  = threading.Lock()

    # 展開所有 (city, town) 任務，略過已完成
    all_pairs = [(city, town)
                 for city in TAIWAN_CITY_ORDER
                 for town in TAIWAN_TOWN_MAP.get(city, [""])]
    todo = [p for p in all_pairs if p not in done_set]
    total = len(all_pairs)

    def log(msg):
        with log_lock:
            q.put(("log", msg))

    def do_one(city, town):
        if stop_event.is_set(): return
        city_name = city_name_map.get(city, city)
        hist_id = None
        try:
            if dtype == "presale":
                hist_id = _db.history_start("presale", city, town, starty, endy)
                bldg_rows, tx_rows = crawl(
                    city=city, town=town, starty=starty, endy=endy,
                    delay=delay, layer2=True, layer3=True, stop_event=stop_event)
                _db.history_done(hist_id, len(bldg_rows), len(tx_rows))
                with lock:
                    job["live_bldg"] += len(bldg_rows)
                    job["live_tx"]   += len(tx_rows)
            else:
                hist_id = _db.history_start("resale", city, town, starty, endy)
                tx_total, tx_new = crawl_resale(
                    city=city, town=town, starty=starty, endy=endy,
                    delay=delay, stop_event=stop_event)
                _db.history_done(hist_id, 0, tx_new)
                with lock:
                    job["live_tx"] += tx_new
            with lock:
                done_set.add((city, town))
                _save_taiwan_ckpt(dtype, starty, endy, list(done_set))
            done_count = len(done_set)
            log(f"[全台 {done_count}/{total}] ✓ {city_name}/{town}")
        except Exception as e:
            log(f"[全台] ✗ {city_name}/{town} 失敗：{e}")
            if hist_id:
                try: _db.history_error(hist_id, str(e))
                except: pass

    log(f"▶ 全台模式啟動（{dtype}），共 {len(todo)} 個行政區待爬，3 執行緒並行")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(do_one, city, town): (city, town) for city, town in todo}
        for fut in as_completed(futures):
            if stop_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try: fut.result()
            except: pass

    if stop_event.is_set():
        job["status"] = "stopped"
        log("⏹ 全台爬取已停止，進度已儲存，可從「未完成任務」繼續")
        q.put(("stopped", json.dumps([])))
    else:
        _delete_taiwan_ckpt(dtype, starty, endy)
        job["status"] = "done"
        stats = _db.get_stats()
        log(f"✅ 全台爬取完成！建案:{stats['buildings']} 預售:{stats['presale_tx']} 買賣:{stats['resale_tx']}")
        q.put(("done", json.dumps([])))
    q.put(None)


@app.post("/api/start-taiwan")
def api_start_taiwan():
    if _running_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"目前已有 {MAX_CONCURRENT_JOBS} 個爬蟲在執行，請等待完成後再啟動"}), 429
    f      = request.json or {}
    starty = str(f.get("starty", "101"))
    endy   = str(f.get("endy",   "115"))
    dtype  = f.get("data_type", "presale")
    delay  = float(f.get("delay", 0.5))
    job_id = uuid.uuid4().hex
    JOBS[job_id] = _make_job(dtype, "ALL", "", starty, endy)
    threading.Thread(target=_run_taiwan_job, daemon=True,
        kwargs=dict(job_id=job_id, dtype=dtype, starty=starty, endy=endy, delay=delay)).start()
    return jsonify({"job_id": job_id})


@app.post("/api/start-resale")
def api_start_resale():
    if _running_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"目前已有 {MAX_CONCURRENT_JOBS} 個爬蟲在執行，請等待完成後再啟動"}), 429
    f = request.json or {}
    city = f.get("city","B"); town = f.get("town","")
    starty = str(f.get("starty","110")); startm = str(f.get("startm","1"))
    endy = str(f.get("endy","115")); endm = str(f.get("endm","12"))
    if _duplicate_running_job(city, town, starty, endy, "resale"):
        return jsonify({"error": f"相同範圍已在執行中"}), 429
    job_id = uuid.uuid4().hex; JOBS[job_id] = _make_job("resale", city, town, starty, endy)
    threading.Thread(target=run_resale_job, daemon=True, kwargs=dict(
        job_id=job_id, city=city, town=town, starty=starty, startm=startm, endy=endy, endm=endm,
        delay=float(f.get("delay",0.3)), ptype=f.get("ptype","1,2,3,4"))).start()
    return jsonify({"job_id": job_id})

@app.post("/api/stop/<job_id>")
def api_stop(job_id):
    job = JOBS.get(job_id)
    if not job: return jsonify({"error": "not found"}), 404
    job["stop_event"].set(); job["status"] = "stopping"; return jsonify({"ok": True})

@app.post("/api/resume")
def api_resume():
    if _running_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"目前已有 {MAX_CONCURRENT_JOBS} 個爬蟲在執行"}), 429
    f = request.json or {}
    city = f.get("city"); town = f.get("town","")
    starty = str(f.get("starty","101")); endy = str(f.get("endy","115"))
    dtype = f.get("data_type","presale")
    if _duplicate_running_job(city, town, starty, endy, dtype):
        return jsonify({"error": "相同範圍已在執行中"}), 429
    ckpt = load_checkpoint(city, town, starty, endy, ckpt_type=dtype)
    if not ckpt: return jsonify({"error": "找不到 checkpoint"}), 404
    job_id = uuid.uuid4().hex; JOBS[job_id] = _make_job()
    if dtype == "resale":
        threading.Thread(target=run_resale_job, daemon=True, kwargs=dict(
            job_id=job_id, city=city, town=town, starty=starty, endy=endy,
            delay=float(f.get("delay",0.3)), ptype=f.get("ptype","1,2,3,4"), resume_ckpt=ckpt)).start()
    else:
        threading.Thread(target=run_presale_job, daemon=True, kwargs=dict(
            job_id=job_id, city=city, town=town, starty=starty, endy=endy,
            delay=float(f.get("delay",0.3)), do_l2=f.get("layer2",True),
            do_l3=f.get("layer3",True), limit=None, resume_ckpt=ckpt)).start()
    return jsonify({"job_id": job_id})

@app.get("/api/checkpoints")
def api_checkpoints():
    ckpts = list_checkpoints(); result = []
    for c in ckpts:
        dtype = c.get("ckpt_type","presale")
        done  = len(c.get("done_months",[])) if dtype=="resale" else len(c.get("done_ids",[]))
        total = (int(c.get("endy",115))-int(c.get("starty",101))+1)*12 if dtype=="resale" else len(c.get("all_buildings",[]))
        result.append({"ckpt_type":dtype,"city":c["city"],"town":c.get("town",""),
            "starty":c.get("starty","101"),"endy":c.get("endy","115"),
            "done":done,"total":total,"saved_at":c.get("saved_at",""),
            "bldg_file":os.path.basename(c.get("bldg_file","")),
            "tx_file":os.path.basename(c.get("tx_file",""))})
    return jsonify(result)

@app.delete("/api/checkpoints/<ckpt_type>/<city>/<town>/<starty>/<endy>")
def api_del_checkpoint(ckpt_type, city, town, starty, endy):
    delete_checkpoint(city, town, starty, endy, ckpt_type=ckpt_type); return jsonify({"ok": True})

@app.post("/api/del-checkpoint")
def api_del_checkpoint_post():
    f = request.json or {}
    delete_checkpoint(f.get("city",""), f.get("town",""), f.get("starty",""),
                      f.get("endy",""), ckpt_type=f.get("dtype","presale"))
    return jsonify({"ok": True})

@app.get("/api/progress/<job_id>")
def api_progress(job_id):
    job = JOBS.get(job_id)
    if not job: return Response('data: {"error":"not found"}\n\n', mimetype="text/event-stream")
    def generate():
        q = job["queue"]
        while True:
            item = q.get()
            if item is None: break
            event, data = item
            yield f"event: {event}\ndata: {data}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering":"no","Cache-Control":"no-cache"})

@app.get("/api/download/<filename>")
def api_download(filename):
    path = os.path.join(OUT, filename)
    if not os.path.exists(path): return "Not found", 404
    return send_file(path, as_attachment=True, download_name=filename, mimetype="text/csv")

@app.get("/api/download-db")
def api_download_db():
    from db import DB_PATH
    if not os.path.exists(DB_PATH): return "Not found", 404
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(DB_PATH, as_attachment=True,
                     download_name=f"presale_data_{ts}.db",
                     mimetype="application/octet-stream")


HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>不動產實價爬蟲</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<style>
body{background:#f0f2f5;font-family:"Noto Sans TC",sans-serif;}
.main-card{border:none;border-radius:16px;box-shadow:0 2px 20px rgba(0,0,0,.09);}
.nav-tabs .nav-link{font-weight:600;color:#555;border-radius:10px 10px 0 0;}
.nav-tabs .nav-link.active{color:#1a73e8;border-bottom-color:#fff;}
.type-toggle .btn{border-radius:20px;font-weight:600;font-size:.88rem;transition:.2s;}
#log-box{background:#0d1117;color:#c9d1d9;font-family:"SFMono-Regular",monospace;font-size:.82rem;height:320px;overflow-y:auto;border-radius:12px;padding:14px 16px;}
#log-box .ts{color:#58a6ff;margin-right:6px;}
#log-box .err{color:#ff7b72;}
#log-box .ok{color:#3fb950;}
#log-box .warn{color:#e3b341;}
.form-label{font-weight:600;font-size:.9rem;}
.ckpt-row{background:#fff8e1;border-radius:10px;padding:10px 14px;margin-bottom:8px;font-size:.88rem;}
#btn-stop{display:none;}
#map{height:480px;border-radius:12px;}
.stat-box{border-radius:12px;padding:18px;text-align:center;}
.stat-num{font-size:2rem;font-weight:800;color:#1a73e8;}
.stat-lbl{font-size:.8rem;color:#888;}
.hist-badge-done{background:#198754;}
.hist-badge-stopped{background:#f59e0b;}
.hist-badge-error{background:#dc3545;}
.hist-badge-running{background:#0d6efd;}
#sched-log{background:#0d1117;color:#c9d1d9;font-family:monospace;font-size:.8rem;height:200px;overflow-y:auto;border-radius:8px;padding:10px;}
</style>
</head>
<body>
<div class="container py-4" style="max-width:1100px">
  <div class="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
    <div class="d-flex align-items-center">
      <i class="bi bi-building-fill fs-2 text-primary me-3"></i>
      <div><h4 class="mb-0 fw-bold">不動產實價爬蟲</h4><small class="text-muted">台灣內政部不動產交易實價查詢</small></div>
    </div>
    <div class="d-flex gap-2 align-items-center flex-wrap" id="db-stats">
      <div class="stat-box bg-white shadow-sm"><div class="stat-num" id="st-bldg">—</div><div class="stat-lbl">預售建案</div></div>
      <div class="stat-box bg-white shadow-sm"><div class="stat-num" id="st-presale">—</div><div class="stat-lbl">預售成交</div></div>
      <div class="stat-box bg-white shadow-sm"><div class="stat-num" id="st-resale">—</div><div class="stat-lbl">買賣成交</div></div>
      <a href="/api/download-db" class="btn btn-success fw-bold px-3" style="border-radius:12px;white-space:nowrap">
        <i class="bi bi-database-down me-1"></i>下載資料庫<br><small style="font-size:.7rem;font-weight:400">存到 iPad</small>
      </a>
    </div>
  </div>
  <div id="running-badge" style="display:none;background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:6px 14px;font-size:13px;font-weight:500;color:#856404;align-items:center;gap:6px;margin-bottom:10px"></div>
  <div id="ckpt-panel" class="mb-3" style="display:none">
    <div class="card border-warning">
      <div class="card-header py-2 fw-bold text-dark" style="background:#fef3c7"><i class="bi bi-clock-history me-2 text-warning"></i>未完成任務（可繼續）</div>
      <div class="card-body py-2" id="ckpt-list"></div>
    </div>
  </div>
  <div class="main-card bg-white p-3">
    <ul class="nav nav-tabs mb-3">
      <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-crawler"><i class="bi bi-robot me-1"></i>爬蟲設定</button></li>
      <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-history"><i class="bi bi-journal-text me-1"></i>歷史紀錄</button></li>
      <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-map" onclick="initMap();if(_mapInited)loadMapData();"><i class="bi bi-map me-1"></i>地圖</button></li>
      <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-sched"><i class="bi bi-calendar-check me-1"></i>排程器</button></li>
    </ul>
    <div class="tab-content">
      <!-- 爬蟲設定 -->
      <div class="tab-pane fade show active" id="tab-crawler">
        <div class="type-toggle d-flex gap-2 mb-3">
          <button type="button" class="btn btn-primary fw-bold px-4" id="btn-presale" onclick="setType('presale')"><i class="bi bi-house-fill me-1"></i>預售屋</button>
          <button type="button" class="btn btn-outline-success fw-bold px-4" id="btn-resale" onclick="setType('resale')"><i class="bi bi-cash-coin me-1"></i>買賣成屋</button>
        </div>
        <div class="row g-3">
          <div class="col-lg-4">
            <div class="form-check form-switch mb-3">
              <input class="form-check-input" type="checkbox" id="chk-taiwan" onchange="toggleTaiwan()">
              <label class="form-check-label fw-bold" for="chk-taiwan">全台模式（自動爬取所有縣市）</label>
            </div>
            <div id="single-mode">
              <div class="mb-2"><label class="form-label">縣市</label><select class="form-select" id="sel-city" onchange="loadTowns()"></select></div>
              <div class="mb-2"><label class="form-label">行政區</label><select class="form-select" id="sel-town"></select></div>
            </div>
            <div class="mb-2">
              <label class="form-label">起始年月（民國）</label>
              <div class="d-flex gap-1">
                <input type="number" class="form-control" id="inp-starty" value="101" min="90" max="120" style="width:80px"><span class="align-self-center">年</span>
                <select class="form-select" id="inp-startm" style="width:80px"><option value="1">1月</option><option value="2">2月</option><option value="3">3月</option><option value="4">4月</option><option value="5">5月</option><option value="6">6月</option><option value="7">7月</option><option value="8">8月</option><option value="9">9月</option><option value="10">10月</option><option value="11">11月</option><option value="12">12月</option></select>
              </div>
            </div>
            <div class="mb-2">
              <label class="form-label">結束年月（民國）</label>
              <div class="d-flex gap-1">
                <input type="number" class="form-control" id="inp-endy" value="115" min="90" max="120" style="width:80px"><span class="align-self-center">年</span>
                <select class="form-select" id="inp-endm" style="width:80px"><option value="1">1月</option><option value="2">2月</option><option value="3">3月</option><option value="4">4月</option><option value="5">5月</option><option value="6">6月</option><option value="7">7月</option><option value="8">8月</option><option value="9">9月</option><option value="10">10月</option><option value="11">11月</option><option value="12" selected>12月</option></select>
              </div>
            </div>
            <div class="mb-2"><label class="form-label">請求間隔（秒）</label><input type="number" class="form-control" id="inp-delay" value="0.3" min="0.1" max="5" step="0.1"></div>
            <div id="presale-opts">
              <div class="mb-2"><label class="form-label">限制筆數（測試用）</label><input type="number" class="form-control" id="inp-limit" placeholder="空白=全部" min="1"></div>
              <div class="d-flex gap-3 mb-3">
                <div class="form-check"><input class="form-check-input" type="checkbox" id="chk-l2" checked><label class="form-check-label" for="chk-l2">成交列表</label></div>
                <div class="form-check"><input class="form-check-input" type="checkbox" id="chk-l3" checked><label class="form-check-label" for="chk-l3">交易明細</label></div>
              </div>
            </div>
            <div class="d-flex gap-2">
              <button class="btn btn-primary flex-fill fw-bold" id="btn-start" onclick="startCrawl()"><i class="bi bi-play-fill me-1"></i>開始爬取</button>
              <button class="btn btn-danger" id="btn-stop" onclick="stopCrawl()"><i class="bi bi-stop-fill"></i></button>
            </div>
          </div>
          <div class="col-lg-8">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <span class="text-muted small fw-bold">執行紀錄</span>
              <button class="btn btn-sm btn-outline-secondary" onclick="document.getElementById('log-box').innerHTML=''"><i class="bi bi-trash3"></i> 清除</button>
            </div>
            <div id="log-box"></div>
            <div id="dl-area" class="mt-2 d-flex gap-2 flex-wrap"></div>
          </div>
        </div>
      </div>
      <!-- 歷史紀錄 -->
      <div class="tab-pane fade" id="tab-history">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <span class="fw-bold">爬取歷史紀錄</span>
          <button class="btn btn-sm btn-outline-primary" onclick="loadHistory()"><i class="bi bi-arrow-clockwise"></i> 重新整理</button>
        </div>
        <div class="table-responsive">
          <table class="table table-hover table-sm">
            <thead class="table-light"><tr><th>類型</th><th>縣市</th><th>行政區</th><th>年份</th><th>狀態</th><th>建案/月份</th><th>成交數</th><th>開始時間</th><th>完成時間</th><th>操作</th></tr></thead>
            <tbody id="hist-body"></tbody>
          </table>
        </div>
      </div>
      <!-- 地圖 -->
      <div class="tab-pane fade" id="tab-map">
        <div class="row g-2 mb-2 align-items-end">
          <div class="col-auto"><label class="form-label mb-1">資料類型</label><select class="form-select form-select-sm" id="map-type" onchange="onMapTypeChange()"><option value="all">全部</option><option value="presale">預售屋</option><option value="resale">買賣成屋</option></select></div>
          <div class="col-auto"><label class="form-label mb-1">縣市</label><select class="form-select form-select-sm" id="map-city" onchange="onMapCityChange()"><option value="">全台</option></select></div>
          <div class="col-auto"><label class="form-label mb-1">行政區</label><select class="form-select form-select-sm" id="map-town" onchange="loadMapData()" style="min-width:90px"><option value="">全部</option></select></div>
          <div class="col-auto">
            <label class="form-label mb-1">年份（西元）</label>
            <div class="d-flex gap-1 align-items-center">
              <input type="number" class="form-control form-control-sm" id="map-starty" value="2015" style="width:72px" onchange="loadMapData()">
              <span class="text-muted">~</span>
              <input type="number" class="form-control form-control-sm" id="map-endy" value="2030" style="width:72px" onchange="loadMapData()">
            </div>
          </div>
          <div class="col-auto"><button class="btn btn-sm btn-outline-secondary" onclick="resetMapFilter()"><i class="bi bi-x-circle"></i> 清除</button></div>
          <div class="col-auto"><button class="btn btn-sm btn-outline-primary" onclick="loadMapData()"><i class="bi bi-search"></i> 套用</button></div>
          <div class="col-auto ms-auto"><small class="text-muted" id="map-count"></small></div>
        </div>
        <div id="map"></div>
      </div>
      <!-- 排程器 -->
      <div class="tab-pane fade" id="tab-sched">
        <div class="row g-3">
          <div class="col-md-5">
            <div class="card border-0 shadow-sm"><div class="card-body">
              <h6 class="fw-bold mb-3"><i class="bi bi-calendar3 me-2"></i>自動排程設定</h6>
              <div class="form-check form-switch mb-3"><input class="form-check-input" type="checkbox" id="chk-sched" onchange="toggleScheduler()"><label class="form-check-label fw-bold" for="chk-sched">啟用自動排程</label></div>
              <table class="table table-sm table-borderless">
                <tr><td class="text-muted">排程週期</td><td class="fw-bold">每月 2/12/22 日 03:00</td></tr>
                <tr><td class="text-muted">下次執行</td><td id="sched-next">—</td></tr>
                <tr><td class="text-muted">上次執行</td><td id="sched-last">—</td></tr>
                <tr><td class="text-muted">目前狀態</td><td id="sched-running">—</td></tr>
              </table>
              <div class="d-flex gap-2 mt-2">
                <button class="btn btn-sm btn-outline-primary" onclick="triggerSched()"><i class="bi bi-play-fill"></i> 立即執行</button>
                <button class="btn btn-sm btn-outline-danger" onclick="stopSchedJob()"><i class="bi bi-stop-fill"></i> 停止任務</button>
                <button class="btn btn-sm btn-outline-secondary" onclick="loadSchedStatus()"><i class="bi bi-arrow-clockwise"></i></button>
              </div>
            </div></div>
          </div>
          <div class="col-md-7"><h6 class="fw-bold">排程執行紀錄</h6><div id="sched-log"></div></div>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="modal fade" id="dup-modal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered"><div class="modal-content">
    <div class="modal-header bg-warning-subtle"><h5 class="modal-title"><i class="bi bi-exclamation-triangle me-2 text-warning"></i>偵測到重複資料</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body" id="dup-msg"></div>
    <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">取消</button><button class="btn btn-warning" id="dup-confirm">仍要爬取</button></div>
  </div></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
const CITIES={{ cities_json | safe }};
const TOWNS={{ towns_json | safe }};
let currentType='presale';
const jobs={presale:{jobId:null,evt:null},resale:{jobId:null,evt:null}};
let _mapInited=false,_leafMap=null,_markers=[],_clusterGroup=null,_legendEl=null;
const PALETTE=['#e74c3c','#3498db','#27ae60','#f39c12','#9b59b6','#1abc9c','#e67e22','#c0392b','#2980b9','#16a085','#8e44ad','#d35400','#1a5276','#196f3d','#6c3483','#922b21','#1f618d','#1e8449','#784212','#515a5a'];
const _tc={};
function districtColor(t){if(!t)return'#6c757d';if(_tc[t])return _tc[t];const n=parseInt((t.match(/\d+$/)||['0'])[0]);const c=PALETTE[n%PALETTE.length];_tc[t]=c;return c;}
window.onload=()=>{
  const cityEl=document.getElementById('sel-city');
  CITIES.forEach(([code,name])=>{const o=document.createElement('option');o.value=code;o.textContent=name;cityEl.appendChild(o);});
  cityEl.value='B';
  loadTowns();loadCkpts();loadStats();loadMapCities();loadSchedStatus();loadRunningBadge();
  setInterval(loadStats,15000);setInterval(loadCkpts,10000);setInterval(loadRunningBadge,5000);
  setInterval(()=>{if(_hasRunningJob())loadHistory();},10000);setInterval(loadSchedStatus,15000);
  document.querySelector('[data-bs-target="#tab-history"]').addEventListener('shown.bs.tab',loadHistory);
};
function setType(t){
  currentType=t;
  document.getElementById('btn-presale').className=t==='presale'?'btn btn-primary fw-bold px-4':'btn btn-outline-primary fw-bold px-4';
  document.getElementById('btn-resale').className=t==='resale'?'btn btn-success fw-bold px-4':'btn btn-outline-success fw-bold px-4';
  document.getElementById('presale-opts').style.display=t==='presale'?'':'none';
  const hasJob=!!jobs[t].jobId;
  document.getElementById('btn-start').disabled=hasJob;
  document.getElementById('btn-stop').style.display=hasJob?'inline-block':'none';
}
function toggleTaiwan(){document.getElementById('single-mode').style.display=document.getElementById('chk-taiwan').checked?'none':'';}
function loadTowns(){
  const city=document.getElementById('sel-city').value;const sel=document.getElementById('sel-town');sel.innerHTML='';
  (TOWNS[city]||[]).forEach(([code,name])=>{const o=document.createElement('option');o.value=code;o.textContent=name;sel.appendChild(o);});
}
function loadStats(){fetch('/api/stats').then(r=>r.json()).then(d=>{document.getElementById('st-bldg').textContent=d.buildings?.toLocaleString()||'0';document.getElementById('st-presale').textContent=d.presale_tx?.toLocaleString()||'0';document.getElementById('st-resale').textContent=d.resale_tx?.toLocaleString()||'0';});}
function loadCkpts(){
  Promise.all([
    fetch('/api/checkpoints').then(r=>r.json()),
    fetch('/api/taiwan-ckpts').then(r=>r.json()),
  ]).then(([list, taiwanList])=>{
    const panel=document.getElementById('ckpt-panel');const cont=document.getElementById('ckpt-list');
    const all = [];

    // 一般 checkpoint（單縣市）
    list.forEach(c=>{
      const pct=c.total?Math.round(c.done/c.total*100):0;
      const label=c.ckpt_type==='resale'?'買賣':'預售';
      const cityNm=CITIES.find(x=>x[0]===c.city)?.[1]||c.city;
      const townNm=(TOWNS[c.city]||[]).find(x=>x[0]===c.town)?.[1]||c.town||'全市';
      all.push(`<div class="ckpt-row"><div class="d-flex justify-content-between align-items-start">
        <div><span class="badge bg-${c.ckpt_type==='resale'?'success':'primary'} me-1">${label}</span>
        <strong>${cityNm} ${townNm}</strong>
        <span class="text-muted ms-2">${c.starty}~${c.endy}年</span>
        <span class="ms-2 text-secondary small">${c.done}/${c.total} (${pct}%)</span>
        <div class="text-muted small mt-1">儲存於 ${c.saved_at?.slice(0,19)||''}</div></div>
        <div class="d-flex gap-1">
          <button class="btn btn-sm btn-outline-primary" onclick="resumeCkpt('${c.ckpt_type}','${c.city}','${c.town}','${c.starty}','${c.endy}')"><i class="bi bi-play-fill"></i> 繼續</button>
          <button class="btn btn-sm btn-outline-danger" onclick="delCkpt('${c.ckpt_type}','${c.city}','${c.town}','${c.starty}','${c.endy}')"><i class="bi bi-x"></i></button>
        </div></div></div>`);
    });

    // 全台 checkpoint
    taiwanList.forEach(c=>{
      const pct=c.total?Math.round(c.done/c.total*100):0;
      const label=c.dtype==='resale'?'買賣':'預售';
      const curTxt=c.cur_city?`<span class="badge bg-warning text-dark ms-2">目前：${c.cur_city}</span>`:'';
      all.push(`<div class="ckpt-row" style="background:#e8f5e9"><div class="d-flex justify-content-between align-items-start">
        <div><span class="badge bg-${c.dtype==='resale'?'success':'primary'} me-1">${label}</span>
        <strong>🌏 全台模式</strong>${curTxt}
        <span class="text-muted ms-2">${c.starty}~${c.endy}年</span>
        <span class="ms-2 text-secondary small">${c.done}/${c.total} (${pct}%)</span>
        <div class="text-muted small mt-1">儲存於 ${c.saved_at?.slice(0,19)||''}</div></div>
        <div class="d-flex gap-1">
          <button class="btn btn-sm btn-outline-primary" onclick="resumeTaiwanCkpt('${c.dtype}','${c.starty}','${c.endy}')"><i class="bi bi-play-fill"></i> 繼續</button>
          <button class="btn btn-sm btn-outline-danger" onclick="delTaiwanCkpt('${c.dtype}','${c.starty}','${c.endy}')"><i class="bi bi-x"></i></button>
        </div></div></div>`);
    });

    if(!all.length){panel.style.display='none';return;}
    panel.style.display='';
    cont.innerHTML=all.join('');
  });
}
function resumeTaiwanCkpt(dtype,starty,endy){
  fetch('/api/resume-taiwan',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({dtype,starty,endy,delay:parseFloat(document.getElementById('inp-delay').value||0.5)})})
    .then(r=>r.json()).then(d=>{
      if(d.error){alert(d.error);return;}
      setType(dtype);startSSE(d.job_id,dtype);
      document.getElementById('btn-stop').style.display='inline-block';
      document.getElementById('btn-start').disabled=true;
      loadStats();loadCkpts();loadHistory();loadRunningBadge();
    });
}
function delTaiwanCkpt(dtype,starty,endy){
  fetch(`/api/taiwan-ckpts/${dtype}/${starty}/${endy}`,{method:'DELETE'}).then(()=>loadCkpts());
}
function resumeCkpt(dtype,city,town,starty,endy){fetch('/api/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_type:dtype,city,town,starty,endy})}).then(r=>r.json()).then(d=>{if(d.error){alert(d.error);return;}setType(dtype);startSSE(d.job_id,dtype);document.getElementById('btn-stop').style.display='inline-block';document.getElementById('btn-start').disabled=true;loadStats();loadCkpts();loadHistory();loadRunningBadge();});}
function delCkpt(dtype,city,town,starty,endy){
  fetch('/api/del-checkpoint',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({dtype,city,town,starty,endy})}).then(()=>loadCkpts());
}
async function startCrawl(){
  const runInfo=await fetch('/api/jobs/running').then(r=>r.json());
  if(runInfo.count>=runInfo.max){addLog(`⚠️ 已達最大並行數（${runInfo.max} 個）`,'warn');return;}
  const city=document.getElementById('sel-city').value;const town=document.getElementById('sel-town').value;
  const starty=parseInt(document.getElementById('inp-starty').value);const startm=parseInt(document.getElementById('inp-startm').value);
  const endy=parseInt(document.getElementById('inp-endy').value);const endm=parseInt(document.getElementById('inp-endm').value);
  const taiwan=document.getElementById('chk-taiwan').checked;
  if(taiwan){doStartTaiwan(starty,startm,endy,endm);return;}
  const cov=await fetch('/api/coverage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_type:currentType,city,town,starty,endy})}).then(r=>r.json());
  const ranges=cov.uncovered_ranges||[];const covYrs=cov.covered_years||[];
  if(ranges.length===0){
    const histDesc=(cov.history||[]).map(h=>`${h.starty}~${h.endy}年（${h.finished_at?.slice(0,10)||'—'}）`).join('、');
    document.getElementById('dup-msg').innerHTML=`<p class="fw-bold text-success mb-1">✅ 所選範圍已全部爬取完成</p><p class="mb-1 small text-muted">已有紀錄：${histDesc||'無'}</p><p class="text-warning mb-0">若需重新爬取請點「仍要爬取」。</p>`;
    const modal=new bootstrap.Modal(document.getElementById('dup-modal'));modal.show();
    document.getElementById('dup-confirm').onclick=()=>{modal.hide();doStart(city,town,starty,startm,endy,endm);};return;
  }
  if(covYrs.length>0){
    const rangeDesc=ranges.map(([s,e])=>s===e?`${s}年`:`${s}~${e}年`).join('、');
    addLog(`⏭ 自動跳過已完成年份`,'warn');addLog(`▶ 僅爬取未完成區間：${rangeDesc}`,'ok');
    _startRanges(city,town,ranges,0,startm,endm);return;
  }
  doStart(city,town,starty,startm,endy,endm);
}
function _startRanges(city,town,ranges,idx,startm,endm){
  if(idx>=ranges.length)return;const[s,e]=ranges[idx];
  doStart(city,town,s,idx===0?startm:1,e,idx===ranges.length-1?endm:12,()=>_startRanges(city,town,ranges,idx+1,startm,endm));
}
function doStartTaiwan(starty,startm,endy,endm){
  const delay=document.getElementById('inp-delay').value;
  fetch('/api/start-taiwan',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({data_type:currentType,starty:String(starty),endy:String(endy),delay:parseFloat(delay)})})
    .then(r=>{if(r.status===429)return r.json().then(d=>{addLog(`⚠️ ${d.error}`,'warn');throw new Error('busy');});return r.json();})
    .then(d=>{
      if(!d||!d.job_id)return;
      startSSE(d.job_id,currentType);
      document.getElementById('btn-stop').style.display='inline-block';
      document.getElementById('btn-start').disabled=true;
      addLog(`▶ 全台模式開始爬取（${currentType==='presale'?'預售屋':'買賣成屋'}）${starty}~${endy}年`,'ok');
    }).catch(e=>{if(e.message!=='busy')addLog(`❌ 啟動失敗：${e}`,'err');});
}
function doStart(city,town,starty,startm,endy,endm,onDone){
  const delay=document.getElementById('inp-delay').value;
  const endpoint=currentType==='presale'?'/api/start':'/api/start-resale';
  const body=currentType==='presale'?{city,town,starty:String(starty),startm:String(startm),endy:String(endy),endm:String(endm),delay:parseFloat(delay),layer2:document.getElementById('chk-l2').checked,layer3:document.getElementById('chk-l3').checked,limit:parseInt(document.getElementById('inp-limit').value)||null}:{city,town,starty:String(starty),startm:String(startm),endy:String(endy),endm:String(endm),delay:parseFloat(delay),ptype:'1,2,3,4'};
  const _type=currentType;
  fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(r=>{if(r.status===429)return r.json().then(d=>{addLog(`⚠️ ${d.error}`,'warn');throw new Error('busy');});return r.json();})
    .then(d=>{if(!d||!d.job_id)return;startSSE(d.job_id,_type,onDone);document.getElementById('btn-stop').style.display='inline-block';document.getElementById('btn-start').disabled=true;addLog(`▶ 開始爬取 ${city}/${town||'全市'} ${starty}年${startm}月~${endy}年${endm}月`,'ok');})
    .catch(e=>{if(e.message!=='busy')addLog(`❌ 啟動失敗：${e}`,'err');});
}
function stopCrawl(){const j=jobs[currentType];if(!j.jobId)return;fetch(`/api/stop/${j.jobId}`,{method:'POST'}).then(()=>addLog('⏹ 已發送停止信號…','warn'));}
function _hasRunningJob(){return Object.values(jobs).some(j=>j.jobId!==null);}
function loadRunningBadge(){fetch('/api/jobs/running').then(r=>r.json()).then(d=>{const badge=document.getElementById('running-badge');if(!badge)return;if(d.count===0){badge.style.display='none';return;}badge.style.display='inline-flex';const names=d.jobs.map(j=>`${j.data_type==='presale'?'預售':'買賣'} ${CITIES.find(x=>x[0]===j.city)?.[1]||j.city}`);badge.textContent=`⚙️ 執行中 ${d.count}/${d.max}：${names.join('、')}`;});}
let _statsThrottle=0,_ckptThrottle=0,_histThrottle=0,_mapThrottle=0;
function startSSE(jobId,type,onDone){
  type=type||currentType;const j=jobs[type];if(j.evt)j.evt.close();j.jobId=jobId;j.evt=new EventSource(`/api/progress/${jobId}`);
  j.evt.addEventListener('log',e=>{addLog(e.data);const now=Date.now();if(now-_statsThrottle>8000){_statsThrottle=now;loadStats();}if(now-_ckptThrottle>10000){_ckptThrottle=now;loadCkpts();}if(now-_histThrottle>10000){_histThrottle=now;loadHistory();}if(now-_mapThrottle>20000&&_mapInited){_mapThrottle=now;loadMapData();}loadRunningBadge();});
  j.evt.addEventListener('done',e=>{let files=[];try{files=JSON.parse(e.data);}catch{}addLog('✅ 爬取完成！','ok');showDownloads(files);finishJob(type);loadStats();loadCkpts();loadHistory();loadRunningBadge();if(_mapInited)loadMapData();if(onDone)onDone();});
  j.evt.addEventListener('stopped',()=>{addLog('⏹ 已停止，進度已儲存','warn');finishJob(type);loadStats();loadCkpts();loadHistory();loadRunningBadge();});
  j.evt.addEventListener('error',e=>{addLog(`❌ ${e.data}`,'err');finishJob(type);loadStats();loadHistory();loadRunningBadge();});
  j.evt.onerror=()=>{addLog('[連線中斷]','warn');finishJob(type);loadRunningBadge();};
}
function finishJob(type){type=type||currentType;const j=jobs[type];if(j.evt){j.evt.close();j.evt=null;}j.jobId=null;if(type===currentType){document.getElementById('btn-stop').style.display='none';document.getElementById('btn-start').disabled=false;}}
function addLog(msg,cls=''){const box=document.getElementById('log-box');const t=new Date().toTimeString().slice(0,8);const div=document.createElement('div');let klass=cls;if(!klass){if(/error|錯誤|失敗|✗/.test(msg))klass='err';else if(/完成|✅|\[\+\]/.test(msg))klass='ok';else if(/重試|Retry|中斷|warn|停止/.test(msg))klass='warn';}div.innerHTML=`<span class="ts">${t}</span>`+(klass?`<span class="${klass}">${esc(msg)}</span>`:esc(msg));box.appendChild(div);box.scrollTop=box.scrollHeight;}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function showDownloads(files){const area=document.getElementById('dl-area');area.innerHTML='';(files||[]).forEach(([type,fn])=>{const a=document.createElement('a');a.href=`/api/download/${fn}`;a.className='btn btn-outline-success btn-sm fw-bold';a.innerHTML=`<i class="bi bi-download me-1"></i>${type==='buildings'?'建案清單':'成交紀錄'} CSV`;a.download=fn;area.appendChild(a);});}
function loadHistory(){fetch('/api/history?limit=100').then(r=>r.json()).then(rows=>{const tbody=document.getElementById('hist-body');if(!rows.length){tbody.innerHTML='<tr><td colspan="10" class="text-center text-muted py-3">尚無紀錄</td></tr>';return;}const statusMap={done:'成功',stopped:'已停止',error:'失敗',running:'進行中'};const badgeCls={done:'hist-badge-done',stopped:'hist-badge-stopped',error:'hist-badge-error',running:'hist-badge-running'};tbody.innerHTML=rows.map(r=>{const cityNm=CITIES.find(x=>x[0]===r.city)?.[1]||r.city||'';const townNm=(TOWNS[r.city]||[]).find(x=>x[0]===r.town)?.[1]||r.town||'全部';const stopBtn=(r.status==='running'&&r.job_id)?`<button class="btn btn-danger btn-sm py-0 px-1" onclick="stopHistJob('${r.job_id}')"><i class="bi bi-stop-fill"></i></button> `:'';const delBtn=`<button class="btn btn-outline-secondary btn-sm py-0 px-1" onclick="delHistory(${r.id})"><i class="bi bi-trash3"></i></button>`;return `<tr><td><span class="badge bg-${r.data_type==='presale'?'primary':'success'}">${r.data_type==='presale'?'預售':'買賣'}</span></td><td>${cityNm}</td><td>${townNm}</td><td>${r.starty}~${r.endy}</td><td><span class="badge ${badgeCls[r.status]||'bg-secondary'}">${statusMap[r.status]||r.status}</span></td><td>${r.data_type==='resale'?(r.bldg_count?r.bldg_count+'月':'—'):(r.bldg_count??'—')}</td><td>${r.tx_count??'—'}</td><td class="text-nowrap small">${r.started_at?.slice(0,19)||'—'}</td><td class="text-nowrap small">${r.finished_at?.slice(0,19)||'—'}</td><td class="text-nowrap">${stopBtn}${delBtn}</td></tr>`;}).join('');});}
function stopHistJob(jobId){fetch(`/api/stop/${jobId}`,{method:'POST'}).then(()=>{addLog('⏹ 已發送停止信號','warn');setTimeout(loadHistory,1500);});}
function delHistory(histId){if(!confirm('確定要刪除此歷史紀錄？'))return;fetch(`/api/history/${histId}`,{method:'DELETE'}).then(loadHistory);}
function initMap(){if(_mapInited)return;if(window.L&&window.L.MarkerClusterGroup){_initMapCore();return;}const addCss=href=>{const l=document.createElement('link');l.rel='stylesheet';l.href=href;document.head.appendChild(l);};const addJs=(src,cb)=>{const s=document.createElement('script');s.src=src;s.onload=cb;document.head.appendChild(s);};addCss('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css');addCss('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css');addCss('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css');addJs('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',()=>addJs('https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js',_initMapCore));}
function _initMapCore(){if(_mapInited)return;_mapInited=true;_leafMap=L.map('map').setView([23.7,121.0],7);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(_leafMap);onMapCityChange();}
function loadMapCities(){const sel=document.getElementById('map-city');CITIES.forEach(([code,name])=>{const o=document.createElement('option');o.value=code;o.textContent=name;sel.appendChild(o);});}
function onMapCityChange(){const city=document.getElementById('map-city').value;const type=document.getElementById('map-type').value;const sel=document.getElementById('map-town');sel.innerHTML='<option value="">全部</option>';const params=new URLSearchParams({type});if(city)params.set('city',city);fetch(`/api/map-towns?${params}`).then(r=>r.json()).then(towns=>{towns.forEach(t=>{const o=document.createElement('option');o.value=t.town;o.textContent=t.name;sel.appendChild(o);});});loadMapData();}
function resetMapFilter(){document.getElementById('map-type').value='all';document.getElementById('map-city').value='';document.getElementById('map-starty').value='2015';document.getElementById('map-endy').value='2030';onMapCityChange();}
function onMapTypeChange(){onMapCityChange();}
function loadMapData(){if(!_mapInited)return;const type=document.getElementById('map-type').value;const city=document.getElementById('map-city').value;const town=document.getElementById('map-town').value;const starty=document.getElementById('map-starty').value;const endy=document.getElementById('map-endy').value;document.getElementById('map-count').textContent='載入中…';fetch(`/api/map-data?type=${type}&city=${city}&town=${town}&starty=${starty}&endy=${endy}`).then(r=>r.json()).then(rows=>{if(_clusterGroup)_leafMap.removeLayer(_clusterGroup);_clusterGroup=L.markerClusterGroup({chunkedLoading:true,maxClusterRadius:60});_markers=[];const townSeen={};rows.forEach(r=>{if(!r.lat||!r.lon)return;const color=districtColor(r.town);const isPresale=r.source==='presale';const icon=L.divIcon({className:'',html:`<div style="width:10px;height:10px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>`,iconSize:[10,10],iconAnchor:[5,5]});const popup=isPresale?`<b>${r.name||'—'}</b><br>${r.addr||''}<br>銷售狀態：${r.sales_status||'—'}<br>戶數：${r.house_count||'—'}`:`<b>${r.addr||'—'}</b><br>成交日：${r.trade_date||'—'}<br>總價：${r.total_price?.toLocaleString()||'—'} 元`;const m=L.marker([r.lat,r.lon],{icon}).bindPopup(popup);_clusterGroup.addLayer(m);_markers.push(m);if(r.town){if(!townSeen[r.town]){const townNm=(TOWNS[r.city]||[]).find(x=>x[0]===r.town)?.[1]||r.town;townSeen[r.town]={name:townNm,color,presale:0,resale:0};}if(isPresale)townSeen[r.town].presale++;else townSeen[r.town].resale++;}});const presaleCnt=rows.filter(r=>r.source==='presale').length;const resaleCnt=rows.filter(r=>r.source==='resale').length;let countTxt=`共 ${_markers.length} 筆`;if(presaleCnt&&resaleCnt)countTxt+=`（預售 ${presaleCnt} / 買賣 ${resaleCnt}）`;else if(presaleCnt)countTxt+=`（預售 ${presaleCnt} 筆）`;else if(resaleCnt)countTxt+=`（買賣 ${resaleCnt} 筆）`;document.getElementById('map-count').textContent=countTxt;_leafMap.addLayer(_clusterGroup);if(_markers.length>0)_leafMap.fitBounds(_clusterGroup.getBounds().pad(0.1));_updateMapLegend(townSeen);});}
function _updateMapLegend(townSeen){if(_legendEl){_legendEl.remove();_legendEl=null;}const entries=Object.values(townSeen).sort((a,b)=>(b.presale+b.resale)-(a.presale+a.resale));if(!entries.length)return;const ctrl=L.control({position:'bottomright'});ctrl.onAdd=()=>{const div=L.DomUtil.create('div');div.style.cssText='background:rgba(255,255,255,.92);padding:8px 12px;border-radius:8px;font-size:12px;max-height:220px;overflow-y:auto;box-shadow:0 1px 6px rgba(0,0,0,.2)';div.innerHTML='<b style="display:block;margin-bottom:4px">行政區</b>'+entries.map(e=>{const countStr=(e.presale>0&&e.resale>0)?`預售 ${e.presale} / 買賣 ${e.resale}`:e.presale>0?`${e.presale} 筆`:`買賣 ${e.resale} 筆`;return `<div style="display:flex;align-items:center;gap:6px;margin:2px 0"><div style="width:10px;height:10px;border-radius:50%;background:${e.color};flex-shrink:0"></div><span>${e.name}（${countStr}）</span></div>`;}).join('');return div;};ctrl.addTo(_leafMap);_legendEl=ctrl;}
function loadSchedStatus(){fetch('/api/scheduler/status').then(r=>r.json()).then(d=>{document.getElementById('chk-sched').checked=d.enabled;document.getElementById('sched-next').textContent=d.next_run?d.next_run.slice(0,19).replace('T',' '):'—';document.getElementById('sched-last').textContent=d.last_run?d.last_run.slice(0,19).replace('T',' '):'—';document.getElementById('sched-running').innerHTML=d.running_job?'<span class="badge bg-primary">執行中</span>':'<span class="badge bg-secondary">閒置</span>';const logBox=document.getElementById('sched-log');logBox.textContent=(d.recent_logs||[]).join('\n');logBox.scrollTop=logBox.scrollHeight;});}
function toggleScheduler(){const enable=document.getElementById('chk-sched').checked;fetch('/api/scheduler/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enable})}).then(()=>loadSchedStatus());}
function triggerSched(){if(!confirm('確定要立即執行全台增量爬取嗎？'))return;fetch('/api/scheduler/trigger',{method:'POST'}).then(r=>r.json()).then(d=>{alert(d.msg);loadSchedStatus();});}
function stopSchedJob(){fetch('/api/scheduler/stop-job',{method:'POST'}).then(()=>{alert('已發送停止信號');loadSchedStatus();});}
</script>
</body>
</html>"""

@app.get("/")
def index():
    return render_template_string(HTML,
        cities_json=json.dumps(CITIES, ensure_ascii=False),
        towns_json=json.dumps({k:v for k,v in TOWNS.items()}, ensure_ascii=False))

if __name__ == "__main__":
    print("[Web] 啟動於 http://localhost:5678")
    app.run(host="0.0.0.0", port=5678, debug=False, threaded=True)
