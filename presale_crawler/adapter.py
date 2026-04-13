"""
將 API 原始回應轉換為友善的中英文欄位名稱。

內政部 QueryPrice API 使用單字母 key（a, tp, p…），
這裡對應到可讀的欄位名稱，方便後續匯出 CSV。
"""

from __future__ import annotations

from typing import Mapping

# 預售屋建案備查（saleremark）— 以建案為單位的摘要資訊
SALEREMARK_FIELDS: Mapping[str, tuple[str, str]] = {
    "name": ("project_name", "建案名稱"),
    "addr": ("address", "基地位置"),
    "apply": ("applicant_company", "申報人/公司"),
    "applydate": ("apply_date", "申報日期"),
    "license": ("license_number", "建造執照號碼"),
    "ldate": ("license_date", "核發日期"),
    "house": ("house_count", "戶數"),
    "ma": ("construction_type", "主要建材"),
    "mark": ("performance_guarantee", "履約擔保機制"),
    "e": ("sales_period", "銷售期間"),
    "s": ("schedule", "工程進度"),
    "AA11": ("zone_type", "使用分區"),
    "city": ("city_code", "縣市代碼"),
    "town": ("town_code", "鄉鎮市區代碼"),
    "lat": ("latitude", "緯度"),
    "lon": ("longitude", "經度"),
}

# 預售屋買賣（presale）— 個別交易紀錄
PRESALE_FIELDS: Mapping[str, tuple[str, str]] = {
    "a": ("address", "建物區段門牌"),
    "b": ("building_type", "建物型態"),
    "bn": ("building_name", "建案名稱"),
    "bu": ("building_unit", "棟及號"),
    "e": ("transaction_date", "交易日期"),
    "f": ("floor", "樓別/樓高"),
    "j": ("bedrooms", "房"),
    "k": ("living_rooms", "廳"),
    "l": ("bathrooms", "衛"),
    "v": ("layout", "建物格局"),
    "p": ("unit_price", "單價(元/坪)"),
    "tp": ("total_price", "總價(元)"),
    "s": ("area", "總面積(坪)"),
    "t": ("transaction_object", "交易標的"),
    "ma": ("construction_type", "主要建材"),
    "cp": ("carpark_price", "車位總價(元)"),
    "pu": ("usage", "主要用途"),
    "lat": ("latitude", "緯度"),
    "lon": ("longitude", "經度"),
    "note": ("note", "備註"),
}

# 不動產買賣（biz）
BIZ_FIELDS: Mapping[str, tuple[str, str]] = {
    "a": ("address", "區段位置或門牌"),
    "b": ("building_type", "建物型態"),
    "bn": ("building_name", "社區簡稱"),
    "bs": ("main_building_ratio", "主建物佔比(%)"),
    "e": ("transaction_date", "交易日期"),
    "f": ("floor", "樓別/樓高"),
    "j": ("bedrooms", "房"),
    "k": ("living_rooms", "廳"),
    "l": ("bathrooms", "衛"),
    "v": ("layout", "建物格局"),
    "p": ("unit_price", "單價(元/坪)"),
    "tp": ("total_price", "總價(元)"),
    "s": ("area", "總面積(坪)"),
    "t": ("transaction_object", "交易標的"),
    "m": ("has_management", "管理組織"),
    "el": ("has_elevator", "有無電梯"),
    "lat": ("latitude", "緯度"),
    "lon": ("longitude", "經度"),
    "note": ("note", "備註"),
}

# 不動產租賃（rent）
RENT_FIELDS: Mapping[str, tuple[str, str]] = {
    "a": ("address", "區段位置或門牌"),
    "b": ("building_type", "建物型態"),
    "bn": ("building_name", "社區簡稱"),
    "e": ("transaction_date", "交易日期"),
    "f": ("floor", "樓別/樓高"),
    "v": ("layout", "建物格局"),
    "p": ("unit_price", "單價(元/坪)"),
    "tp": ("total_price", "租金總額(元)"),
    "s": ("area", "總面積(坪)"),
    "rperiod": ("rental_period", "租賃期間"),
    "rtype": ("rental_type", "租賃型態"),
    "fn": ("furniture", "附屬設備"),
    "lat": ("latitude", "緯度"),
    "lon": ("longitude", "經度"),
    "note": ("note", "備註"),
}

FIELD_MAPPINGS = {
    "saleremark": SALEREMARK_FIELDS,
    "presale": PRESALE_FIELDS,
    "biz": BIZ_FIELDS,
    "rent": RENT_FIELDS,
}


def normalize(records: list[dict], query_type: str) -> list[dict]:
    """
    將原始 API 紀錄轉換為友善 key 的 dict。

    回傳的 dict 使用中文欄位名稱作為 key，方便直接匯出 CSV。
    """
    if query_type not in FIELD_MAPPINGS:
        raise ValueError(
            f"未知 query_type {query_type!r}；"
            f"可用：{sorted(FIELD_MAPPINGS)}"
        )
    mapping = FIELD_MAPPINGS[query_type]
    return [_normalize_one(r, mapping) for r in records]


def normalize_en(records: list[dict], query_type: str) -> list[dict]:
    """同 normalize()，但使用英文欄位名稱。"""
    if query_type not in FIELD_MAPPINGS:
        raise ValueError(
            f"未知 query_type {query_type!r}；"
            f"可用：{sorted(FIELD_MAPPINGS)}"
        )
    mapping = FIELD_MAPPINGS[query_type]
    return [_normalize_one_en(r, mapping) for r in records]


def get_csv_headers(query_type: str, lang: str = "zh") -> list[str]:
    """取得指定查詢類型的 CSV 欄位標題。"""
    mapping = FIELD_MAPPINGS[query_type]
    if lang == "zh":
        return [zh for _, (_, zh) in mapping.items()]
    return [en for _, (en, _) in mapping.items()]


def _normalize_one(record: dict, mapping: Mapping[str, tuple[str, str]]) -> dict:
    return {zh: record.get(raw, "") for raw, (_, zh) in mapping.items()}


def _normalize_one_en(record: dict, mapping: Mapping[str, tuple[str, str]]) -> dict:
    return {en: record.get(raw, "") for raw, (en, _) in mapping.items()}
