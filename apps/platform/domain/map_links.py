"""Which map service a pasted "map card" link must belong to (Dashboard: site settings + each store's form)."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

MAP_HOSTS: dict[str, tuple[str, ...]] = {
    "google_maps_url": ("google.com", "google.co.uz", "goo.gl", "g.page", "g.co"),
    "yandex_maps_url": ("yandex.uz", "yandex.ru", "yandex.com", "yandex.kz", "ya.cc", "ya.ru"),
    "two_gis_url": ("2gis.uz", "2gis.ru", "2gis.com"),
}


def map_link_error(field: str, url: str) -> str | None:
    """None when `url` is empty or a page of the map service `field` is for; otherwise the message to show."""
    if not url:
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not any(host == h or host.endswith("." + h) for h in MAP_HOSTS[field]):
        return "Bu havola shu xarita xizmatiga tegishli emas — xaritadagi «Ulashish» tugmasidan olingan havolani qo'ying."
    if field == "google_maps_url" and host.endswith(("google.com", "google.co.uz")):
        on_maps = host.startswith("maps.") or parts.path.startswith("/maps")
        if not on_maps and "cid" not in parse_qs(parts.query):
            return "Google Maps'dagi kartaning havolasini qo'ying (…/maps/place/… yoki maps.app.goo.gl/…)."
    return None
