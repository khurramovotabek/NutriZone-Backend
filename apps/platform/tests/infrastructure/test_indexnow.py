"""IndexNow: the sitemap's changed pages go to the protocol endpoint with our key, other hosts never do."""
from __future__ import annotations

from datetime import datetime, timezone

from apps.platform.infrastructure import indexnow

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://nutrizone.uz/</loc><lastmod>2026-11-10T01:00:00.000Z</lastmod></url>
<url><loc>https://nutrizone.uz/products/old</loc><lastmod>2026-10-01T00:00:00Z</lastmod></url>
<url><loc>https://nutrizone.uz/guides</loc></url>
<url><loc>https://nutrizone.uz/</loc><lastmod>2026-11-10T01:00:00Z</lastmod></url>
</urlset>"""


def test_only_recently_changed_pages_are_picked_and_duplicates_dropped():
    since = datetime(2026, 11, 8, tzinfo=timezone.utc)
    assert indexnow.sitemap_urls(SITEMAP, since) == ["https://nutrizone.uz/", "https://nutrizone.uz/guides"]
    assert len(indexnow.sitemap_urls(SITEMAP)) == 3


def test_submit_sends_key_and_our_host_only(monkeypatch, settings):
    settings.FRONTEND_URL = "https://nutrizone.uz"
    sent = []
    monkeypatch.setattr(indexnow, "_post", lambda payload: sent.append(payload) or 200)
    result = indexnow.submit(["https://nutrizone.uz/a", "https://evil.example.com/b"])
    assert result == {"submitted": 1, "statuses": [200]}
    assert sent[0]["host"] == "nutrizone.uz" and sent[0]["urlList"] == ["https://nutrizone.uz/a"]
    assert sent[0]["keyLocation"] == f"https://nutrizone.uz/{indexnow.DEFAULT_KEY}.txt"
