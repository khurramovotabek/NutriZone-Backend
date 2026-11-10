"""
IndexNow (indexnow.org): tells Bing, Yandex, Seznam, Naver and Yep the moment a storefront page is new or changed,
instead of waiting for the next crawl. Bing's index is what ChatGPT search and Copilot answer from, so a fresh
product or price there is a fresh product in their answers; Yandex shares the same feed.

The source of truth is the storefront's own sitemap (every public page, with hreflang twins and lastmod), so nothing
here has to know about products, brands or guides. The key is public by design: the storefront serves it as
/<key>.txt (nutrizone-frontend/public), which proves the submissions come from the site owner.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from django.conf import settings

log = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
DEFAULT_KEY = "bb58dec54c543cfe8e3b95711f6acfaf"
BATCH = 10_000  # the protocol's per-request limit
_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _site() -> str:
    return (getattr(settings, "FRONTEND_URL", None) or "https://nutrizone.uz").rstrip("/")


def _key() -> str:
    return getattr(settings, "INDEXNOW_KEY", None) or DEFAULT_KEY


def sitemap_urls(xml_text: str, since: datetime | None = None) -> list[str]:
    """Page URLs from a sitemap, only those modified at/after `since` when given (a page without lastmod always counts)."""
    out: list[str] = []
    for node in ET.fromstring(xml_text).findall("s:url", _NS):
        loc = (node.findtext("s:loc", default="", namespaces=_NS) or "").strip()
        if not loc:
            continue
        if since is not None:
            raw = (node.findtext("s:lastmod", default="", namespaces=_NS) or "").strip()
            try:
                modified = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
            except ValueError:
                modified = None
            if modified is not None:
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=timezone.utc)
                if modified < since:
                    continue
        out.append(loc)
    return list(dict.fromkeys(out))


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "NutriZone-IndexNow/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 -- our own storefront
        return resp.read().decode("utf-8")


def _post(payload: dict) -> int:
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "NutriZone-IndexNow/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 -- fixed endpoint
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def submit(urls: list[str]) -> dict:
    """POST the URLs (same host only) in protocol-sized batches; returns the HTTP status of every batch."""
    site = _site()
    host = urlsplit(site).hostname or ""
    urls = [u for u in urls if urlsplit(u).hostname == host]
    statuses: list[int] = []
    for i in range(0, len(urls), BATCH):
        statuses.append(_post({"host": host, "key": _key(), "keyLocation": f"{site}/{_key()}.txt", "urlList": urls[i:i + BATCH]}))
    result = {"submitted": len(urls), "statuses": statuses}
    log.info("indexnow: %s", result)
    return result


def submit_changed(days: float | None = 2) -> dict:
    """The sitemap's pages changed in the last `days` (all of them when None)."""
    since = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None
    return submit(sitemap_urls(_fetch(f"{_site()}/sitemap.xml"), since))
