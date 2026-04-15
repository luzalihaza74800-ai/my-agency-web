#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3, os, json
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presale_data.db")

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS buildings (
    id TEXT PRIMARY KEY, city TEXT NOT NULL, town TEXT, name TEXT, addr TEXT,
    apply TEXT, mark TEXT, AA11 TEXT, base TEXT, license TEXT, material TEXT,
    purpose TEXT, reg_date TEXT, apply_date TEXT, self_sale TEXT, agent_sale TEXT,
    house_count INTEGER, sales_status TEXT, lat REAL, lon REAL, crawled_at TEXT
);
CREATE TABLE IF NOT EXISTS presale_transactions (
    tx_id TEXT PRIMARY KEY, building_id TEXT, building_name TEXT, addr TEXT,
    trade_date TEXT, total_price INTEGER, unit_price INTEGER, area REAL,
    floor TEXT, build_type TEXT, layout TEXT, trade_target TEXT, park_price INTEGER,
    material TEXT, purpose TEXT, cancel_info TEXT, main_area REAL, balcony_area REAL,
    public_area REAL, park_area REAL, rain_area REAL, land_no TEXT, land_zone TEXT,
    land_share TEXT, park_no TEXT, park_type TEXT, park_floor TEXT, note TEXT,
    special_flag TEXT, crawled_at TEXT,
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);
CREATE TABLE IF NOT EXISTS resale_transactions (
    tx_id TEXT PRIMARY KEY, city TEXT, town TEXT, addr TEXT, community TEXT,
    trade_date TEXT, total_price INTEGER, unit_price INTEGER, area REAL,
    floor TEXT, build_type TEXT, layout TEXT, trade_target TEXT, park_price INTEGER,
    purpose TEXT, age INTEGER, elevator TEXT, management TEXT, urban_zone TEXT,
    non_urban_zone TEXT, lat REAL, lon REAL, main_area REAL, balcony_area REAL,
    public_area REAL, park_area REAL, rain_area REAL, land_no TEXT, land_zone TEXT,
    land_share TEXT, park_no TEXT, park_type TEXT, park_floor TEXT,
    build_structure TEXT, complete_year TEXT, note TEXT, special_flag TEXT,
    ptype TEXT, crawled_at TEXT
);
CREATE TABLE IF NOT EXISTS crawl_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, data_type TEXT NOT NULL,
    city TEXT, town TEXT, starty TEXT, endy TEXT, status TEXT,
    bldg_count INTEGER DEFAULT 0, tx_count INTEGER DEFAULT 0,
    started_at TEXT, finished_at TEXT, error_msg TEXT
);
CREATE INDEX IF NOT EXISTS idx_buildings_city_town ON buildings(city, town);
CREATE INDEX IF NOT EXISTS idx_presale_building ON presale_transactions(building_id);
CREATE INDEX IF NOT EXISTS idx_presale_date ON presale_transactions(trade_date);
CREATE INDEX IF NOT EXISTS idx_resale_city_town ON resale_transactions(city, town);
CREATE INDEX IF NOT EXISTS idx_resale_date ON resale_transactions(trade_date);
CREATE INDEX IF NOT EXISTS idx_history_type ON crawl_history(data_type, city, town);
""")
    with get_conn() as conn:
        conn.execute("""
            UPDATE crawl_history SET status='error',
              error_msg='伺服器重啟中斷', finished_at=started_at
            WHERE status='running'
        """)
    print(f"[DB] 資料庫初始化完成：{DB_PATH}")

def upsert_building(row: dict):
    sql = """INSERT INTO buildings
        (id,city,town,name,addr,apply,mark,AA11,base,license,material,purpose,
         reg_date,apply_date,self_sale,agent_sale,house_count,sales_status,lat,lon,crawled_at)
        VALUES (:id,:city,:town,:name,:addr,:apply,:mark,:AA11,:base,:license,:material,
         :purpose,:reg_date,:apply_date,:self_sale,:agent_sale,:house_count,
         :sales_status,:lat,:lon,:crawled_at)
        ON CONFLICT(id) DO UPDATE SET
        sales_status=excluded.sales_status, self_sale=excluded.self_sale,
        agent_sale=excluded.agent_sale, crawled_at=excluded.crawled_at"""
    with get_conn() as conn:
        conn.execute(sql, row)

def upsert_buildings_batch(rows: list):
    if not rows: return
    sql = """INSERT INTO buildings
        (id,city,town,name,addr,apply,mark,AA11,base,license,material,purpose,
         reg_date,apply_date,self_sale,agent_sale,house_count,sales_status,lat,lon,crawled_at)
        VALUES (:id,:city,:town,:name,:addr,:apply,:mark,:AA11,:base,:license,:material,
         :purpose,:reg_date,:apply_date,:self_sale,:agent_sale,:house_count,
         :sales_status,:lat,:lon,:crawled_at)
        ON CONFLICT(id) DO UPDATE SET
        sales_status=excluded.sales_status, self_sale=excluded.self_sale,
        agent_sale=excluded.agent_sale, crawled_at=excluded.crawled_at"""
    with get_conn() as conn:
        conn.executemany(sql, rows)

def upsert_presale_tx(row: dict):
    sql = """INSERT OR IGNORE INTO presale_transactions
        (tx_id,building_id,building_name,addr,trade_date,total_price,unit_price,
         area,floor,build_type,layout,trade_target,park_price,material,purpose,
         cancel_info,main_area,balcony_area,public_area,park_area,rain_area,
         land_no,land_zone,land_share,park_no,park_type,park_floor,note,special_flag,crawled_at)
        VALUES (:tx_id,:building_id,:building_name,:addr,:trade_date,:total_price,
         :unit_price,:area,:floor,:build_type,:layout,:trade_target,:park_price,
         :material,:purpose,:cancel_info,:main_area,:balcony_area,:public_area,
         :park_area,:rain_area,:land_no,:land_zone,:land_share,:park_no,
         :park_type,:park_floor,:note,:special_flag,:crawled_at)"""
    with get_conn() as conn:
        conn.execute(sql, row)

def upsert_presale_tx_batch(rows: list):
    if not rows: return
    sql = """INSERT OR IGNORE INTO presale_transactions
        (tx_id,building_id,building_name,addr,trade_date,total_price,unit_price,
         area,floor,build_type,layout,trade_target,park_price,material,purpose,
         cancel_info,main_area,balcony_area,public_area,park_area,rain_area,
         land_no,land_zone,land_share,park_no,park_type,park_floor,note,special_flag,crawled_at)
        VALUES (:tx_id,:building_id,:building_name,:addr,:trade_date,:total_price,
         :unit_price,:area,:floor,:build_type,:layout,:trade_target,:park_price,
         :material,:purpose,:cancel_info,:main_area,:balcony_area,:public_area,
         :park_area,:rain_area,:land_no,:land_zone,:land_share,:park_no,
         :park_type,:park_floor,:note,:special_flag,:crawled_at)"""
    with get_conn() as conn:
        conn.executemany(sql, rows)

def upsert_resale_tx(row: dict):
    sql = """INSERT OR IGNORE INTO resale_transactions
        (tx_id,city,town,addr,community,trade_date,total_price,unit_price,
         area,floor,build_type,layout,trade_target,park_price,purpose,age,
         elevator,management,urban_zone,non_urban_zone,lat,lon,
         main_area,balcony_area,public_area,park_area,rain_area,
         land_no,land_zone,land_share,park_no,park_type,park_floor,
         build_structure,complete_year,note,special_flag,ptype,crawled_at)
        VALUES (:tx_id,:city,:town,:addr,:community,:trade_date,:total_price,:unit_price,
         :area,:floor,:build_type,:layout,:trade_target,:park_price,:purpose,:age,
         :elevator,:management,:urban_zone,:non_urban_zone,:lat,:lon,
         :main_area,:balcony_area,:public_area,:park_area,:rain_area,
         :land_no,:land_zone,:land_share,:park_no,:park_type,:park_floor,
         :build_structure,:complete_year,:note,:special_flag,:ptype,:crawled_at)"""
    with get_conn() as conn:
        conn.execute(sql, row)

def upsert_resale_tx_batch(rows: list):
    if not rows: return
    sql = """INSERT OR IGNORE INTO resale_transactions
        (tx_id,city,town,addr,community,trade_date,total_price,unit_price,
         area,floor,build_type,layout,trade_target,park_price,purpose,age,
         elevator,management,urban_zone,non_urban_zone,lat,lon,
         main_area,balcony_area,public_area,park_area,rain_area,
         land_no,land_zone,land_share,park_no,park_type,park_floor,
         build_structure,complete_year,note,special_flag,ptype,crawled_at)
        VALUES (:tx_id,:city,:town,:addr,:community,:trade_date,:total_price,:unit_price,
         :area,:floor,:build_type,:layout,:trade_target,:park_price,:purpose,:age,
         :elevator,:management,:urban_zone,:non_urban_zone,:lat,:lon,
         :main_area,:balcony_area,:public_area,:park_area,:rain_area,
         :land_no,:land_zone,:land_share,:park_no,:park_type,:park_floor,
         :build_structure,:complete_year,:note,:special_flag,:ptype,:crawled_at)"""
    with get_conn() as conn:
        conn.executemany(sql, rows)

def history_start(data_type, city, town, starty, endy) -> int:
    with get_conn() as conn:
        cur = conn.execute("""INSERT INTO crawl_history
            (data_type,city,town,starty,endy,status,started_at)
            VALUES (?,?,?,?,?,'running',?)""",
            (data_type, city, town, starty, endy, datetime.now().isoformat()))
        return cur.lastrowid

def history_done(history_id: int, bldg_count: int, tx_count: int):
    with get_conn() as conn:
        conn.execute("""UPDATE crawl_history
            SET status='done', bldg_count=?, tx_count=?, finished_at=? WHERE id=?""",
            (bldg_count, tx_count, datetime.now().isoformat(), history_id))

def history_stopped(history_id: int, bldg_count: int, tx_count: int):
    with get_conn() as conn:
        conn.execute("""UPDATE crawl_history
            SET status='stopped', bldg_count=?, tx_count=?, finished_at=? WHERE id=?""",
            (bldg_count, tx_count, datetime.now().isoformat(), history_id))

def history_error(history_id: int, error_msg: str):
    with get_conn() as conn:
        conn.execute("""UPDATE crawl_history
            SET status='error', error_msg=?, finished_at=? WHERE id=?""",
            (str(error_msg)[:500], datetime.now().isoformat(), history_id))

def get_history(limit=100) -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM crawl_history ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]

def check_duplicate(data_type, city, town, starty, endy) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("""SELECT * FROM crawl_history
            WHERE data_type=? AND city=? AND town=? AND starty=? AND endy=? AND status='done'
            ORDER BY id DESC LIMIT 1""",
            (data_type, city, town, starty, endy)).fetchone()
        return dict(row) if row else None

def get_coverage(data_type: str, city: str, town: str, starty: int, endy: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute("""SELECT starty, endy, finished_at FROM crawl_history
            WHERE data_type=? AND city=? AND (town=? OR (town='' AND ?='')) AND status='done'
            ORDER BY starty""",
            (data_type, city, town, town)).fetchall()
    covered = set()
    history = []
    for r in rows:
        s, e = int(r[0]), int(r[1])
        for y in range(s, e + 1): covered.add(y)
        history.append({"starty": s, "endy": e, "finished_at": r[2]})
    requested = set(range(starty, endy + 1))
    covered_in_range   = sorted(covered & requested)
    uncovered_in_range = sorted(requested - covered)
    uncovered_ranges = []
    if uncovered_in_range:
        s = uncovered_in_range[0]; e = uncovered_in_range[0]
        for y in uncovered_in_range[1:]:
            if y == e + 1: e = y
            else: uncovered_ranges.append((s, e)); s = e = y
        uncovered_ranges.append((s, e))
    return {"covered_years": covered_in_range, "uncovered_years": uncovered_in_range,
            "uncovered_ranges": uncovered_ranges, "history": history}

def get_known_building_ids(city: str, town: str) -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM buildings WHERE city=? AND town=?",
            (city, town)).fetchall()
        return {r["id"] for r in rows}

def get_known_resale_tx_ids(city: str, town: str) -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT tx_id FROM resale_transactions WHERE city=? AND town=?",
            (city, town)).fetchall()
        return {r["tx_id"] for r in rows}

def get_map_data(city: str = None, town: str = None,
                 data_type: str = "all", starty: str = None, endy: str = None) -> list:
    results = []
    with get_conn() as conn:
        if data_type in ("presale", "all"):
            q = ("SELECT id,city,town,name,addr,lat,lon,sales_status,house_count "
                 "FROM buildings WHERE lat IS NOT NULL")
            params = []
            if city:   q += " AND city=?";   params.append(city)
            if town:   q += " AND town=?";   params.append(town)
            if starty: q += " AND SUBSTR(apply_date,1,4) >= ?"; params.append(str(starty))
            if endy:   q += " AND SUBSTR(apply_date,1,4) <= ?"; params.append(str(endy))
            for r in conn.execute(q, params).fetchall():
                d = dict(r); d["source"] = "presale"; results.append(d)
        if data_type in ("resale", "all"):
            q = ("SELECT tx_id,city,town,addr,community,lat,lon,"
                 "total_price,unit_price,trade_date,purpose "
                 "FROM resale_transactions WHERE lat IS NOT NULL")
            params = []
            if city:   q += " AND city=?";   params.append(city)
            if town:   q += " AND town=?";   params.append(town)
            if starty: q += " AND SUBSTR(trade_date,1,4) >= ?"; params.append(str(starty))
            if endy:   q += " AND SUBSTR(trade_date,1,4) <= ?"; params.append(str(endy))
            for r in conn.execute(q, params).fetchall():
                d = dict(r); d["source"] = "resale"; results.append(d)
    return results

def delete_history(history_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM crawl_history WHERE id=?", (history_id,))

def get_stats() -> dict:
    with get_conn() as conn:
        b  = conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
        pt = conn.execute("SELECT COUNT(*) FROM presale_transactions").fetchone()[0]
        rt = conn.execute("SELECT COUNT(*) FROM resale_transactions").fetchone()[0]
        h  = conn.execute("SELECT COUNT(*) FROM crawl_history WHERE status='done'").fetchone()[0]
        return {"buildings": b, "presale_tx": pt, "resale_tx": rt, "crawls_done": h}

def get_stats_by(city: str, town: str) -> dict:
    with get_conn() as conn:
        if town:
            b  = conn.execute("SELECT COUNT(*) FROM buildings WHERE city=? AND town=?",
                (city, town)).fetchone()[0]
            pt = conn.execute("""SELECT COUNT(*) FROM presale_transactions pt
                JOIN buildings b ON pt.building_id=b.id WHERE b.city=? AND b.town=?""",
                (city, town)).fetchone()[0]
            rt = conn.execute("SELECT COUNT(*) FROM resale_transactions WHERE city=? AND town=?",
                (city, town)).fetchone()[0]
        else:
            b  = conn.execute("SELECT COUNT(*) FROM buildings WHERE city=?", (city,)).fetchone()[0]
            pt = conn.execute("""SELECT COUNT(*) FROM presale_transactions pt
                JOIN buildings b ON pt.building_id=b.id WHERE b.city=?""",
                (city,)).fetchone()[0]
            rt = conn.execute("SELECT COUNT(*) FROM resale_transactions WHERE city=?",
                (city,)).fetchone()[0]
        return {"buildings": b, "presale_tx": pt, "resale_tx": rt}

def get_towns_with_data(city: str = None, data_type: str = "all") -> list:
    with get_conn() as conn:
        towns = set()
        if data_type in ("all", "presale"):
            q = "SELECT DISTINCT city, town FROM buildings WHERE town != ''"; p = []
            if city: q += " AND city=?"; p.append(city)
            for row in conn.execute(q, p).fetchall(): towns.add((row[0], row[1]))
        if data_type in ("all", "resale"):
            q = "SELECT DISTINCT city, town FROM resale_transactions WHERE town != ''"; p = []
            if city: q += " AND city=?"; p.append(city)
            for row in conn.execute(q, p).fetchall(): towns.add((row[0], row[1]))
        return [{"city": c, "town": t} for c, t in sorted(towns)]

init_db()
