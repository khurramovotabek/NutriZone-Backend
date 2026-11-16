"""Weekly/monthly analytics reports carry the Hududlar section; /hududlar sends it on its own."""
from __future__ import annotations

from datetime import datetime

from apps.platform.infrastructure import business_analytics as ba
from apps.telegram_bot.infrastructure import analytics_bot, analytics_report, analytics_rich

DATA = {
    "summary": {"revenue": 1_000_000.0, "regions_active": 2, "regions_total": 14, "tashkent_share": 80.0, "pipeline_orders": 1, "pipeline_value": 50_000.0},
    "regions": [
        {"code": "TGCITYR", "name": "Toshkent shahri", "revenue": 800_000.0, "previous_revenue": 400_000.0, "share": 80.0, "orders": 4,
         "online_revenue": 300_000.0, "pos_revenue": 500_000.0, "cities": [{"city": "Tashkent", "orders": 2, "revenue": 300_000.0}]},
        {"code": "UZ-SA", "name": "Samarqand viloyati", "revenue": 200_000.0, "previous_revenue": 0.0, "share": 20.0, "orders": 1,
         "online_revenue": 200_000.0, "pos_revenue": 0.0, "cities": [{"city": "Samarkand", "orders": 1, "revenue": 200_000.0}]},
        {"code": "UZ-BU", "name": "Buxoro viloyati", "revenue": 0.0, "previous_revenue": 0.0, "share": 0, "orders": 0,
         "online_revenue": 0.0, "pos_revenue": 0.0, "cities": []},
    ],
}


def _r(key="week", store_ids=None):
    return {"period": ba.period(key), "store_ids": store_ids, "regions": DATA, "generated_at": datetime(2026, 11, 16, 9, 0)}


def test_classic_section_lists_regions_with_sales_only():
    text = analytics_report.regions(_r())
    assert "HUDUDLAR" in text and "Toshkent shahri" in text and "Samarqand viloyati" in text
    assert "Buxoro" not in text
    assert "▲ 100%" in text  # 400k -> 800k
    assert "2 / 14" in text


def test_branch_scoped_report_skips_regions():
    assert analytics_report.regions(_r(store_ids=["x"])) is None
    doc = analytics_rich.build_regions_doc(_r(store_ids=["x"]))
    assert "Bu davrda savdo qayd etilmagan" in doc.html


def test_rich_regions_doc_and_command():
    doc = analytics_rich.build_regions_doc(_r("30d"), dashboard_url="https://api.example/django-admin/")
    assert "Hududlar" in doc.html and "Samarqand viloyati" in doc.html and "#nz-regions" in doc.html
    assert "regions" in doc.images
    assert analytics_bot.REPORTS["hududlar"] == ("30d", "regions")
    assert analytics_bot.ALIASES["regions"] == "hududlar"
    assert any(c == "hududlar" for c, _ in analytics_bot.COMMANDS)
