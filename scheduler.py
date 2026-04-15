#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler.py — 定期自動爬取排程器
"""

import threading
import time
from datetime import datetime

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _APScheduler_available = True
except ImportError:
    _APScheduler_available = False

import presale_crawler_full as crawler
import db as _db

ALL_CITIES = ["A","F","C","B","D","E","H","I","J","K","M","N","O","P","Q","T","U","V","W","X","Z"]

TOWN_MAP = {
    "A": ["A01","A02","A03","A04","A05","A06","A07","A08","A09","A10","A11","A12"],
    "F": ["F01","F02","F03","F04","F05","F06","F07","F08","F09","F10","F11","F12",
          "F13","F14","F15","F16","F17","F18","F19","F20","F21","F22","F23","F24",
          "F25","F26","F27","F28","F29"],
    "C": ["C01","C02","C03","C04","C05","C06","C07"],
    "B": ["B01","B02","B03","B04","B05","B06","B07","B08","B09","B10","B11","B12",
          "B13","B14","B15","B16","B17","B18","B19","B20","B21","B22","B23","B24",
          "B25","B26","B27","B28","B29"],
    "D": ["D01","D02","D03","D04","D05","D06","D07","D08","D09","D10","D11","D12",
          "D13","D14","D15","D16","D17","D18","D19","D20","D21","D22","D23","D24",
          "D25","D26","D27","D28","D29","D30","D31","D32","D33","D34","D35","D36","D37"],
    "E": ["E01","E02","E03","E04","E05","E06","E07","E08","E09","E10","E11","E12",
          "E13","E14","E15","E16","E17","E18","E19","E20","E21","E22","E23","E24",
          "E25","E26","E27","E28","E29","E30","E31","E32","E33","E34","E35","E36","E37","E38"],
    "H": ["H01","H02","H03","H04","H05","H06","H07","H08","H09","H10","H11","H12","H13"],
    "I": ["I01","I02"],
    "J": ["J01","J02","J03","J04","J05","J06","J07","J08","J09","J10","J11","J12","J13"],
    "K": ["K01","K02","K03","K04","K05","K06","K07","K08","K09","K10","K11","K12",
          "K13","K14","K15","K16","K17","K18"],
    "M": ["M01","M02","M03","M04","M05","M06","M07","M08","M09","M10","M11","M12","M13"],
    "N": ["N01","N02","N03","N04","N05","N06","N07","N08","N09","N10","N11","N12",
          "N13","N14","N15","N16","N17","N18","N19","N20","N21","N22","N23","N24","N25","N26"],
    "O": ["O01","O02","O03"],
    "P": ["P01","P02","P03","P04","P05","P06","P07","P08","P09","P10","P11","P12",
          "P13","P14","P15","P16","P17","P18"],
    "Q": ["Q01","Q02","Q03","Q04","Q05","Q06","Q07","Q08","Q09","Q10","Q11","Q12",
          "Q13","Q14","Q15","Q16","Q17","Q18","Q19","Q20"],
    "T": ["T01","T02","T03","T04","T05","T06","T07","T08","T09","T10","T11","T12",
          "T13","T14","T15","T16","T17","T18","T19","T20","T21","T22","T23","T24",
          "T25","T26","T27","T28","T29","T30","T31","T32","T33"],
    "U": ["U01","U02","U03","U04","U05","U06","U07","U08","U09","U10","U11","U12","U13"],
    "V": ["V01","V02","V03","V04","V05","V06","V07","V08","V09","V10","V11","V12",
          "V13","V14","V15","V16"],
    "W": ["W01","W02","W03"],
    "X": ["X01","X02","X03","X04","X05","X06"],
    "Z": ["Z01","Z02","Z03","Z04","Z05","Z06"],
}

_scheduler   = None
_enabled     = False
_running_job = False
_last_run    = None
_next_run    = None
_stop_event  = threading.Event()
_log_lines   = []
_log_lock    = threading.Lock()


def _log(msg: str):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with _log_lock:
        _log_lines.append(line)
        if len(_log_lines) > 200:
            _log_lines.pop(0)


def _get_current_roc_year() -> str:
    return str(datetime.now().year - 1911)


def _incremental_taiwan_crawl():
    global _running_job, _last_run, _stop_event

    if _running_job:
        _log("[Scheduler] 上一次任務仍在執行中，跳過此次排程")
        return

    _running_job = True
    _stop_event  = threading.Event()
    _last_run    = datetime.now().isoformat()
    endy         = _get_current_roc_year()
    starty       = str(int(endy) - 1)

    _log(f"[Scheduler] 開始全台增量爬取，範圍 {starty}~{endy} 年")

    city_name_map = {v: k for k, v in crawler.CITY_CODE.items()}
    total_presale_new = 0
    total_resale_new  = 0

    try:
        for city in ALL_CITIES:
            if _stop_event.is_set():
                _log("[Scheduler] 使用者要求停止"); break

            towns     = TOWN_MAP.get(city, [""])
            city_name = city_name_map.get(city, city)

            for town in towns:
                if _stop_event.is_set(): break

                _log(f"[Scheduler] {city_name}/{town} 預售爬取…")
                hist_id = None
                try:
                    hist_id = _db.history_start("presale", city, town, starty, endy)
                    bldg_rows, tx_rows = crawler.crawl(
                        city=city, town=town,
                        starty=starty, endy=endy, delay=0.5,
                        layer2=True, layer3=True, stop_event=_stop_event,
                    )
                    _db.history_done(hist_id, len(bldg_rows), len(tx_rows))
                    total_presale_new += len(tx_rows)
                    _log(f"  → 預售：{len(bldg_rows)} 棟，{len(tx_rows)} 筆")
                except Exception as e:
                    _log(f"  ✗ 預售失敗：{e}")
                    if hist_id:
                        try: _db.history_error(hist_id, str(e))
                        except Exception: pass

                if _stop_event.is_set(): break

                _log(f"[Scheduler] {city_name}/{town} 買賣爬取…")
                hist_id = None
                try:
                    hist_id = _db.history_start("resale", city, town, starty, endy)
                    tx_total, tx_new = crawler.crawl_resale(
                        city=city, town=town,
                        starty=starty, endy=endy,
                        ptype="1,2,3,4", delay=0.5, stop_event=_stop_event,
                    )
                    _db.history_done(hist_id, 0, tx_new)
                    total_resale_new += tx_new
                    _log(f"  → 買賣：{tx_total} 筆，新增 {tx_new} 筆")
                except Exception as e:
                    _log(f"  ✗ 買賣失敗：{e}")
                    if hist_id:
                        try: _db.history_error(hist_id, str(e))
                        except Exception: pass

                time.sleep(1.0)

    finally:
        _running_job = False
        stats = _db.get_stats()
        _log(f"[Scheduler] 全台爬取結束，預售新增 {total_presale_new} 筆，"
             f"買賣新增 {total_resale_new} 筆，資料庫：{stats}")


def start_scheduler():
    global _scheduler, _enabled, _next_run

    if not _APScheduler_available:
        _log("[Scheduler] APScheduler 未安裝，無法啟動排程")
        return False

    if _scheduler and _scheduler.running:
        return True

    _scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    _scheduler.add_job(
        _incremental_taiwan_crawl,
        trigger=CronTrigger(day="2,12,22", hour=3, minute=0, timezone="Asia/Taipei"),
        id="taiwan_crawl",
        name="全台增量爬取",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    _enabled = True

    job = _scheduler.get_job("taiwan_crawl")
    if job and job.next_run_time:
        _next_run = job.next_run_time.isoformat()

    _log(f"[Scheduler] 排程已啟動，下次執行：{_next_run}")
    return True


def stop_scheduler():
    global _scheduler, _enabled

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
    _enabled   = False
    _log("[Scheduler] 排程已停止")


def stop_running_job():
    global _stop_event
    _stop_event.set()
    _log("[Scheduler] 已發送停止信號")


def get_scheduler_status() -> dict:
    next_run = None
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("taiwan_crawl")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    with _log_lock:
        recent_logs = list(_log_lines[-50:])

    return {
        "enabled":     _enabled,
        "running_job": _running_job,
        "last_run":    _last_run,
        "next_run":    next_run,
        "recent_logs": recent_logs,
    }


def trigger_now():
    if _running_job:
        return False, "任務已在執行中"
    t = threading.Thread(target=_incremental_taiwan_crawl, daemon=True)
    t.start()
    return True, "已觸發全台增量爬取"


if _APScheduler_available:
    start_scheduler()
