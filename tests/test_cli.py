from tw_presale_crawler.cli import (
    CrawlQuery,
    CrawlResult,
    RegionCode,
    build_city_summary,
    normalize_name,
    normalize_project_row,
)


def test_normalize_name_handles_tai_variant_and_spaces():
    assert normalize_name("台 中 市") == "臺中市"
    assert normalize_name("臺中市") == "臺中市"


def test_normalize_project_row_maps_fields():
    region = RegionCode(
        city_code="B",
        district_code="B06",
        city_title="臺中市",
        district_title="西屯區",
    )
    row = {
        "id": "abc123",
        "name": "正直上弦．壹",
        "addr": "西屯區順和段",
        "apply": "正直建設股份有限公司",
        "house": "7",
        "AA11": "第二種住宅區",
        "pu": "集合住宅",
        "ma": "鋼筋混凝土造",
        "license": "113中都建字第00001號",
        "chkdate": "1130101",
        "applydate": "1121231",
        "s": "1130101~1160101",
        "f": "1160101",
        "lat": 24.1,
        "lon": 120.6,
    }

    normalized = normalize_project_row(row, region, "https://example.test/sale")

    assert normalized["city"] == "臺中市"
    assert normalized["district"] == "西屯區"
    assert normalized["project_name"] == "正直上弦．壹"
    assert normalized["household_count"] == "7"
    assert normalized["source_url"] == "https://example.test/sale"


def test_build_city_summary_contains_counts_and_sample_projects():
    query = CrawlQuery(start_year=110, start_month=7, end_year=115, end_month=12)
    region = RegionCode(
        city_code="B",
        district_code="B06",
        city_title="臺中市",
        district_title="西屯區",
    )
    result = CrawlResult(
        region=region,
        raw_rows=[
            {"name": "續森"},
            {"name": "雅敦蔚山"},
            {"name": "正直上弦．壹"},
        ],
        normalized_rows=[],
        sale_data_url="https://example.test/saledata",
    )

    summary = build_city_summary([result], query)

    assert len(summary) == 1
    assert summary[0]["count"] == 3
    assert summary[0]["first_project"] == "續森"
    assert "雅敦蔚山" in summary[0]["sample_projects"]
