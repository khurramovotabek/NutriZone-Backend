"""
Location detection for the address form and the dashboard -- every way a customer can say "here":

* `locate(lat, lng)`      -- a point (GPS, a pin on the map, a pasted link) → our own City / Region / Country / District
                             (nearest city centre in the reference data) + the street and house from OpenStreetMap.
* `geocode(query)`        -- "Chorsu", "Amir Temur 15", "Tashkent City" → points to choose from (Uzbekistan first).
* `parse_map_link(text)`  -- a link shared from Yandex / Google / Apple Maps / 2GIS / Telegram, or "41.31, 69.27"
                             → the coordinates. Short links (yandex.uz/maps/-/…, maps.app.goo.gl/…) are followed
                             server-side, only through the map providers' own hosts.

Street-level data comes from Nominatim (OpenStreetMap), called from the backend with an identifying User-Agent,
answers cached (a day for reverse, an hour for search) and at most ~1 request per second across the whole site, as
its usage policy asks. When Nominatim is slow or down everything still works -- the city / region come from our
own data and the customer types the street.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from difflib import SequenceMatcher
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("nutrizone.app")

LANGS = ("uz", "ru", "en")
SERVICE_RADIUS_KM = 60  # farther than this from every city we serve → "outside our delivery area"
UZ_BOUNDS = (37.1, 45.7, 55.9, 73.2)  # lat_min, lat_max, lng_min, lng_max


def _enabled() -> bool:
    return bool(getattr(settings, "GEOCODER_ENABLED", True))


def _base() -> str:
    return (getattr(settings, "GEOCODER_URL", "") or "https://nominatim.openstreetmap.org").rstrip("/")


def _headers() -> dict:
    return {"User-Agent": getattr(settings, "GEOCODER_USER_AGENT", "") or "NutriZone/1.0 (+https://nutrizone.uz; support@nutrizone.uz)"}


def _slot(wait: float = 1.2) -> bool:
    """A site-wide ~1 req/s gate for the free Nominatim service (shared through the cache, so all workers respect it)."""
    deadline = time.monotonic() + wait
    while True:
        if cache.add("geo:nominatim:slot", 1, timeout=1):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.15)


def _get(path: str, params: dict):
    import requests

    if not _enabled() or not _slot():
        return None
    try:
        r = requests.get(f"{_base()}{path}", params={**params, "format": "jsonv2"}, headers=_headers(), timeout=4)
        return r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001 - street data is a bonus, never a failure
        logger.warning("geocoder: %s failed", path, exc_info=True)
        return None


def in_uzbekistan(lat: float, lng: float) -> bool:
    return UZ_BOUNDS[0] <= lat <= UZ_BOUNDS[1] and UZ_BOUNDS[2] <= lng <= UZ_BOUNDS[3]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- reverse / search (OpenStreetMap)


def reverse(lat: float, lng: float, lang: str = "uz") -> dict | None:
    lang = lang if lang in LANGS else "uz"
    key = f"geo:rev:{lang}:{lat:.5f}:{lng:.5f}"
    hit = cache.get(key)
    if hit is not None:
        return hit or None
    data = _get("/reverse", {"lat": f"{lat:.6f}", "lon": f"{lng:.6f}", "zoom": 18, "addressdetails": 1, "accept-language": lang})
    out = None
    if data and not data.get("error"):
        a = data.get("address") or {}
        road = a.get("road") or a.get("pedestrian") or a.get("residential") or a.get("footway") or ""
        house = a.get("house_number") or ""
        street = f"{road} {house}".strip() if road else ""
        out = {
            "street": street, "road": road, "house": house, "place": a.get("amenity") or a.get("shop") or a.get("building") or "",
            "neighbourhood": a.get("neighbourhood") or a.get("quarter") or a.get("suburb") or "",
            "district": a.get("city_district") or a.get("district") or a.get("county") or "", "city": a.get("city") or a.get("town") or a.get("village") or "",
            "region": a.get("state") or "", "postcode": a.get("postcode") or "", "country_code": (a.get("country_code") or "").upper(), "label": data.get("display_name") or "",
        }
    cache.set(key, out or {}, 60 * 60 * 24 if out else 60 * 5)
    return out


def geocode(query: str, lang: str = "uz", near: tuple[float, float] | None = None, limit: int = 6) -> list[dict]:
    """Places matching a free-text query, Uzbekistan only, closest to `near` first when given."""
    query = (query or "").strip()
    if len(query) < 3:
        return []
    lang = lang if lang in LANGS else "uz"
    key = f"geo:search:{lang}:{hashlib.sha1(query.lower().encode()).hexdigest()}"
    rows = cache.get(key)
    if rows is None:
        data = _get("/search", {"q": query, "countrycodes": "uz", "limit": 10, "addressdetails": 1, "accept-language": lang})
        rows = []
        for d in data or []:
            try:
                lat, lng = float(d["lat"]), float(d["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            name = d.get("name") or (d.get("display_name") or "").split(",")[0]
            rest = ", ".join(p.strip() for p in (d.get("display_name") or "").split(",")[1:4])
            rows.append({"title": name, "subtitle": rest, "lat": lat, "lng": lng, "kind": d.get("type") or d.get("category") or ""})
        cache.set(key, rows, 60 * 60 if rows else 60 * 5)
    if near:
        rows = sorted(rows, key=lambda r: haversine_km(near[0], near[1], r["lat"], r["lng"]))
    return rows[:limit]


# ---------------------------------------------------------------- our own reference data


def _name(translations, lang: str, fallback: str) -> str:
    names = {t.locale_code: t.name for t in translations}
    return names.get(lang) or names.get("uz") or names.get("en") or fallback


_CYR = dict(zip("абвгғдеёжзийкқлмнопрстуўфхҳцчшъьэюя", ["a", "b", "v", "g", "g'", "d", "e", "yo", "j", "z", "i", "y", "k", "q", "l", "m", "n", "o", "p", "r", "s", "t", "u", "o'", "f", "x", "h", "ts", "ch", "sh", "'", "", "e", "yu", "ya"]))


def _latinize(text: str) -> str:
    """Uzbek Cyrillic → Latin, so "Навоий Тумани" meets "Navoiy tumani" (OSM mixes both scripts)."""
    return "".join(_CYR.get(ch, ch) for ch in text.lower()).replace("ŭ", "o'").replace("ğ", "g'")


def _norm(text: str) -> str:
    """'Yunusobod Tumani' / 'Юнусабадский район' / "Mirzo Ulug'bek tumani" → a comparable stem."""
    text = _latinize(text or "").replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'").replace("`", "'")
    for word in (" tumani", " district", " район", "ский", " shahri", " city", "город "):
        text = text.replace(word, "")
    text = re.sub(r"[^a-zа-яё0-9]+", "", text)
    # Uzbek Latin is spelled several ways on maps: Shayxontohur / Shayhontohur, Ulug'bek / Ulugbek, Yakkasaroy / Yakkasaray
    return text.replace("x", "h").replace("ay", "oy") if re.match(r"[a-z]", text) else text


def nearest_city(lat: float, lng: float, lang: str = "uz", region_id=None):
    from apps.geo.infrastructure import models as orm

    cities = orm.City.objects.filter(status="active", center_latitude__isnull=False).select_related("region__country").prefetch_related(
        "translations", "region__translations", "region__country__translations")
    if region_id is not None:
        cities = cities.filter(region_id=region_id)
    best = min(((haversine_km(lat, lng, c.center_latitude, c.center_longitude), c) for c in cities), default=None, key=lambda x: x[0])
    return best


def _match_district(region_id, osm_names: list[str]):
    from apps.geo.infrastructure import models as orm

    # a city's own name ("Nukus shahri", "город Навои") is not a district -- never match it to the like-named tuman
    wanted = {_norm(n) for n in osm_names if n and not re.search(r"shahri|shahar|город|city|hokimiyat|ҳокимият|хокимият", n, re.I)}
    wanted.discard("")
    if not wanted:
        return None
    for d in orm.District.objects.filter(region_id=region_id, status="active").prefetch_related("translations"):
        for t in d.translations.all():
            stem = _norm(t.name)
            if stem and any(w.startswith(stem) or stem.startswith(w) or SequenceMatcher(None, w, stem).ratio() >= 0.85 for w in wanted):
                return d
    return None


def _match_region(state: str):
    """OSM's state ("Andijon viloyati", "Андижанская область", "Tashkent") → our Region (any of its translations)."""
    from apps.geo.infrastructure import models as orm

    def stem(text: str) -> str:
        text = re.sub(r"(?i)\b(viloyati|viloyat|region|province|oblast|respublikasi|republic|shahri|city|область|республика|город)\b", "", text or "")
        return _norm(text).replace("skaya", "").replace("skiy", "")

    city_rx = re.compile(r"(?i)\b(shahri|city|город)\b")
    wanted, wanted_city = stem(state), bool(city_rx.search(state or ""))
    if not wanted:
        return None
    regions = list(orm.Region.objects.filter(status="active").prefetch_related("translations"))
    for region in regions:  # the exact name first ("Toshkent viloyati" must not land on "Toshkent shahri")
        if any(_norm(t.name) == _norm(state) for t in region.translations.all()):
            return region
    for region in regions:
        for t in region.translations.all():
            have = stem(t.name)
            if have and bool(city_rx.search(t.name)) == wanted_city and (have == wanted or SequenceMatcher(None, have, wanted).ratio() >= 0.82):
                return region
    return None


def locate(lat: float, lng: float, lang: str = "uz", with_street: bool = True) -> dict:
    """A point → what the address form fills in: city / region / country (ids from our data), district, street, house.
    The region comes from the map provider's own boundaries (OSM state) when it names one of ours -- the nearest city
    centre alone put Andijan points into Tashkent while a region had no city in our data."""
    lang = lang if lang in LANGS else "uz"
    street = reverse(lat, lng, lang) if with_street else None
    region_hit = _match_region(street.get("region", "")) if street else None
    if region_hit is not None and street and _norm(street.get("city", "")) in {_norm("Toshkent"), _norm("Tashkent"), _norm("Ташкент")}:
        from apps.geo.infrastructure import models as orm

        region_hit = orm.Region.objects.filter(code="TGCITYR").first() or region_hit  # OSM puts the capital's districts under "Tashkent"
    found = nearest_city(lat, lng, lang, region_hit.id if region_hit else None) or (None if region_hit else nearest_city(lat, lng, lang))
    out: dict = {"latitude": round(lat, 6), "longitude": round(lng, 6), "in_uzbekistan": in_uzbekistan(lat, lng), "city": None, "region": None, "country": None,
                 "district": None, "distance_km": None, "in_service_area": False, "street": "", "house": "", "label": "", "postcode": ""}
    if not found and region_hit is not None:  # a region we know but with no city on file: still fill region / country
        out.update({"region": {"id": str(region_hit.id), "name": _name(region_hit.translations.all(), lang, region_hit.code)},
                    "country": {"id": str(region_hit.country_id), "name": _name(region_hit.country.translations.all(), lang, region_hit.country.code), "code": region_hit.country.code}})
        district = _match_district(region_hit.id, [street.get("district") or street.get("neighbourhood")] if street else [])
        if district:
            out["district"] = {"id": str(district.id), "name": _name(district.translations.all(), lang, district.code)}
    if found:
        km, city = found
        region, country = city.region, city.region.country
        out.update({
            "city": {"id": str(city.id), "name": _name(city.translations.all(), lang, city.code)},
            "region": {"id": str(region.id), "name": _name(region.translations.all(), lang, region.code)},
            "country": {"id": str(country.id), "name": _name(country.translations.all(), lang, country.code), "code": country.code},
            "distance_km": round(km, 1), "in_service_area": km <= SERVICE_RADIUS_KM and out["in_uzbekistan"],
        })
        district = _match_district(region.id, [street.get("district") or street.get("neighbourhood")] if street else [])
        if district:
            out["district"] = {"id": str(district.id), "name": _name(district.translations.all(), lang, district.code)}
    if street:
        out.update({"street": street["street"], "house": street["house"], "label": street["label"], "postcode": street["postcode"], "place": street["place"]})
    return out


# ---------------------------------------------------------------- links shared from map apps

_COORD = r"(-?\d{1,2}(?:\.\d+)?)"
_LNG = r"(-?\d{1,3}(?:\.\d+)?)"
_PATTERNS = [  # (regex, lat group, lng group) -- most specific first
    (re.compile(r"!3d" + _COORD + r"!4d" + _LNG), 1, 2),  # Google place data
    (re.compile(r"@" + _COORD + r"," + _LNG + r","), 1, 2),  # Google viewport
    (re.compile(r"[?&](?:pt|whatshere%5Bpoint%5D|whatshere\[point\])=" + _LNG + r"(?:,|%2C)" + _COORD), 2, 1),  # Yandex pin: lng,lat (before its viewport `ll`)
    (re.compile(r"[?&](?:q|query|ll|daddr|sll|destination)=" + _COORD + r"(?:,|%2C)\s*" + _LNG), 1, 2),  # Google / Apple (Yandex ll is swapped below)
    (re.compile(r"/geo/" + _LNG + r"(?:,|%2C)" + _COORD), 2, 1),  # 2GIS: lng,lat
    (re.compile(r"geo:" + _COORD + r"," + _LNG), 1, 2),  # geo: URI
    (re.compile(r"^\s*" + _COORD + r"\s*[,; ]\s*" + _LNG + r"\s*$"), 1, 2),  # "41.31, 69.27"
]
SHORT_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co", "yandex.uz", "yandex.ru", "yandex.com", "ya.cc", "go.2gis.com", "2gis.uz", "2gis.ru", "maps.apple.com", "maps.apple")
MAP_HOSTS = SHORT_HOSTS + ("google.com", "www.google.com", "maps.google.com", "www.google.co.uz", "2gis.com", "yandex.kz", "www.openstreetmap.org", "openstreetmap.org")


def _from_text(text: str) -> tuple[float, float] | None:
    text = unquote(text or "")
    for rx, gi_lat, gi_lng in _PATTERNS:
        m = rx.search(text)
        if m:
            lat, lng = float(m.group(gi_lat)), float(m.group(gi_lng))
            if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0):
                # Yandex `ll` is lng,lat; when the numbers only make sense the other way round (Uzbekistan: lat 37–46, lng 55–73), swap
                if not in_uzbekistan(lat, lng) and in_uzbekistan(lng, lat):
                    lat, lng = lng, lat
                return lat, lng
    return None


def _host_ok(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in MAP_HOSTS)


def parse_map_link(text: str) -> dict | None:
    """Coordinates from a pasted link or "lat, lng". A short link is followed (≤ 4 hops, map hosts only)."""
    text = (text or "").strip()[:2000]
    point = _from_text(text)
    if point:
        return {"latitude": point[0], "longitude": point[1]}
    m = re.search(r"https?://\S+", text)
    if not m:
        return None
    url = m.group(0)
    import requests

    for _ in range(4):
        if not _host_ok(urlparse(url).hostname or ""):
            return None  # never fetch arbitrary hosts (SSRF)
        try:
            r = requests.get(url, headers=_headers(), timeout=4, allow_redirects=False)
        except Exception:  # noqa: BLE001
            return None
        nxt = r.headers.get("Location")
        if not nxt:
            point = _from_text(r.url) or _from_text(r.text[:200000] if r.status_code == 200 else "")
            return {"latitude": point[0], "longitude": point[1]} if point else None
        url = requests.compat.urljoin(url, nxt)
        point = _from_text(url)
        if point:
            return {"latitude": point[0], "longitude": point[1]}
    return None


def query_language(request) -> str:
    lang = (request.query_params.get("lang") or request.headers.get("Accept-Language", "uz")[:2]).lower()
    return lang if lang in LANGS else "uz"
