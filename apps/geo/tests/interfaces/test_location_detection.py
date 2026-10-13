"""
Location detection and the premium Geo dashboard:

* `locations/locate` -- a point → our city / region / country / district + street (OpenStreetMap faked here),
* `locations/geocode` -- place search, `locations/parse-link` -- coordinates from Yandex / Google / Apple / 2GIS links
  (and never a request to a host that isn't a map provider),
* addresses keep the courier's details (podyezd, floor, flat, door code, landmark), their region, the GPS accuracy
  and how the point was found; a district must lie in the address's region; the order line carries the details,
* every Geo & Location dashboard page renders, and "Manzillar xaritasi" shows addresses and stores together.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import User as AuthUser
from django.test import Client
from rest_framework.test import APIClient

from apps.geo.infrastructure import models as orm
from apps.geo.infrastructure.gateways import geocoder

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

TASHKENT = (41.3111, 69.2797)


@pytest.fixture(autouse=True)
def _own_cache(monkeypatch):
    """The geocoder caches answers; tests get a private cache so nothing leaks between them (or from the dev site)."""
    from django.core.cache.backends.locmem import LocMemCache

    monkeypatch.setattr(geocoder, "cache", LocMemCache(f"geo-test-{uuid.uuid4().hex}", {}))


def _place():
    """UZ → Toshkent shahri → Toshkent (centre known) + Yunusobod tumani."""
    country = orm.Country.objects.filter(code="UZ").first() or orm.Country.objects.create(code="UZ", status="active")
    region = orm.Region.objects.create(country=country, code=f"T{uuid.uuid4().hex[:5].upper()}")
    orm.RegionTranslation.objects.create(region=region, locale_code="uz", name="Toshkent shahri", slug=f"tsh-{uuid.uuid4().hex[:6]}")
    city = orm.City.objects.create(region=region, code=f"C{uuid.uuid4().hex[:5].upper()}", center_latitude=41.2995, center_longitude=69.2401)
    orm.CityTranslation.objects.create(city=city, locale_code="uz", name="Toshkent", slug=f"toshkent-{uuid.uuid4().hex[:6]}")
    district = orm.District.objects.create(region=region, code=f"D{uuid.uuid4().hex[:5].upper()}")
    orm.DistrictTranslation.objects.create(district=district, locale_code="uz", name="Yunusobod tumani", slug=f"yunusobod-{uuid.uuid4().hex[:6]}")
    return country, region, city, district


def _osm_reverse(*_args, **_kwargs):
    return {"display_name": "Amir Temur ko'chasi 15, Yunusobod Tumani, Toshkent", "address": {"road": "Amir Temur ko'chasi", "house_number": "15",
            "city_district": "Yunusobod Tumani", "city": "Toshkent", "postcode": "100000", "country_code": "uz"}}


def _client_as(monkeypatch, user_id) -> APIClient:
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


def _admin() -> Client:
    user = AuthUser.objects.create_superuser(username=f"geo_{uuid.uuid4().hex[:6]}", password="x-pass-12345")
    c = Client()
    c.force_login(user)
    return c


class TestLocate:
    def test_point_resolves_to_our_city_region_district_and_street(self):
        _country, region, city, district = _place()
        with mock.patch.object(geocoder, "_get", side_effect=_osm_reverse):
            data = APIClient().get("/api/v1/geo/locations/locate", {"lat": TASHKENT[0], "lng": TASHKENT[1], "lang": "uz"}).json()["data"]
        assert data["city"]["id"] == str(city.id) and data["region"]["id"] == str(region.id) and data["district"]["id"] == str(district.id)
        assert data["street"] == "Amir Temur ko'chasi 15" and data["in_service_area"] is True and data["postcode"] == "100000"

    def test_without_street_service_the_city_still_resolves(self):
        _place()
        with mock.patch.object(geocoder, "_get", return_value=None):
            data = APIClient().get("/api/v1/geo/locations/locate", {"lat": TASHKENT[0], "lng": TASHKENT[1]}).json()["data"]
        assert data["city"] is not None and data["street"] == ""

    def test_far_away_point_is_outside_the_service_area(self):
        _place()
        with mock.patch.object(geocoder, "_get", return_value=None):
            data = APIClient().get("/api/v1/geo/locations/locate", {"lat": 48.85, "lng": 2.35}).json()["data"]
        assert data["in_service_area"] is False and data["in_uzbekistan"] is False

    def test_bad_coordinates_are_rejected(self):
        assert APIClient().get("/api/v1/geo/locations/locate", {"lat": "abc", "lng": 1}).status_code == 422
        assert APIClient().get("/api/v1/geo/locations/locate", {"lat": 120, "lng": 1}).status_code == 422


class TestGeocodeAndLinks:
    def test_search_returns_places_closest_first(self):
        rows = [{"lat": "41.40", "lon": "69.30", "name": "Uzoq", "display_name": "Uzoq, Toshkent"}, {"lat": "41.311", "lon": "69.28", "name": "Yaqin", "display_name": "Yaqin, Toshkent"}]
        with mock.patch.object(geocoder, "_get", return_value=rows):
            data = APIClient().get("/api/v1/geo/locations/geocode", {"q": f"Chorsu {uuid.uuid4().hex[:4]}", "lat": TASHKENT[0], "lng": TASHKENT[1]}).json()["data"]
        assert [r["title"] for r in data] == ["Yaqin", "Uzoq"]

    @pytest.mark.parametrize("text", [
        "https://yandex.uz/maps/?ll=69.240562%2C41.299496&z=12&pt=69.2797,41.3111",
        "https://www.google.com/maps/place/X/@41.30,69.20,17z/data=!3m1!4b1!8m2!3d41.3111!4d69.2797",
        "https://maps.apple.com/?ll=41.3111,69.2797&q=Pin",
        "https://2gis.uz/tashkent/geo/69.2797,41.3111",
        "41.3111, 69.2797",
    ])
    def test_links_from_every_map_app(self, text):
        r = APIClient().post("/api/v1/geo/locations/parse-link", {"text": text}, format="json")
        assert r.status_code == 200 and r.json()["data"] == {"latitude": 41.3111, "longitude": 69.2797}

    def test_never_fetches_a_host_that_is_not_a_map_provider(self):
        with mock.patch("requests.get") as get:
            r = APIClient().post("/api/v1/geo/locations/parse-link", {"text": "https://169.254.169.254/latest/meta-data"}, format="json")
        assert r.status_code == 422 and not get.called

    def test_short_link_is_followed_through_map_hosts(self):
        hop = mock.Mock(status_code=302, headers={"Location": "https://yandex.uz/maps/?pt=69.2797,41.3111&z=17"}, url="https://yandex.uz/maps/-/CDabc", text="")
        with mock.patch("requests.get", return_value=hop):
            point = geocoder.parse_map_link("Mana joy: https://yandex.uz/maps/-/CDabc")
        assert point == {"latitude": 41.3111, "longitude": 69.2797}


class TestAddressDetails:
    def test_create_keeps_courier_details_region_and_accuracy(self, monkeypatch):
        country, region, city, district = _place()
        owner = uuid.uuid4()
        c = _client_as(monkeypatch, owner)
        with mock.patch("common.permissions.HasPermissionCode.has_permission", return_value=True):
            r = c.post("/api/v1/geo/addresses", {"address_type": "residential", "country_id": str(country.id), "city_id": str(city.id), "district_id": str(district.id),
                                                 "line1": "Amir Temur 15", "recipient_name": "Aziz", "recipient_phone": "+998901112233",
                                                 "metadata": {"entrance": "2", "floor": "5", "unit": "34", "entrance_code": "34K", "delivery_instructions": "Makro ro'parasi"}}, format="json")
            assert r.status_code == 201, r.content
            data = r.json()["data"]
            assert data["region_id"] == str(region.id) and data["district_id"] == str(district.id)
            assert data["metadata"]["entrance"] == "2" and data["metadata"]["delivery_instructions"] == "Makro ro'parasi"
            r = c.patch(f"/api/v1/geo/addresses/{data['id']}/coordinates", {"latitude": TASHKENT[0], "longitude": TASHKENT[1], "source": "gps", "accuracy_meters": 12.4}, format="json")
        assert r.status_code == 200 and r.json()["data"]["coordinate_source"] == "gps" and r.json()["data"]["coordinate_accuracy_meters"] == 12.4

    def test_district_of_another_region_is_refused(self, monkeypatch):
        country, _region, city, _district = _place()
        _c2, _r2, _city2, foreign = _place()
        with mock.patch("common.permissions.HasPermissionCode.has_permission", return_value=True):
            r = _client_as(monkeypatch, uuid.uuid4()).post("/api/v1/geo/addresses", {"address_type": "residential", "country_id": str(country.id), "city_id": str(city.id),
                                                                                    "district_id": str(foreign.id), "line1": "X 1", "recipient_name": "A", "recipient_phone": "+998901112233"}, format="json")
        assert r.status_code == 422

    def test_courier_line(self):
        from apps.geo.application.services.address import delivery_details_line, metadata_from

        line = delivery_details_line(metadata_from({"entrance": "2", "floor": "5", "unit": "34", "entrance_code": "34K", "delivery_instructions": "Makro ro'parasi"}))
        assert line == "2-podyezd · 5-qavat · 34-xonadon · domofon 34K · Mo'ljal: Makro ro'parasi"
        assert delivery_details_line(metadata_from({})) == ""


class TestDashboard:
    def test_every_geo_page_renders(self):
        country, region, city, district = _place()
        address = orm.Address.objects.create(owner_type="user", owner_id=uuid.uuid4(), address_type="residential", country=country, region=region, city=city,
                                             line1="Amir Temur 15", coordinate_latitude=41.311081, coordinate_longitude=69.240562, coordinate_source="gps",
                                             coordinate_accuracy_meters=14, normalized_signature="x")
        orm.AddressMetadata.objects.create(address=address, entrance="3", delivery_instructions="Ko'k darvoza")
        c = _admin()
        for url in ("/django-admin/geo/country/", "/django-admin/geo/region/", "/django-admin/geo/district/", "/django-admin/geo/city/", "/django-admin/geo/address/",
                    f"/django-admin/geo/region/{region.pk}/change/", f"/django-admin/geo/district/{district.pk}/change/", f"/django-admin/geo/city/{city.pk}/change/",
                    "/django-admin/geo/city/add/", "/django-admin/geo/address/add/", f"/django-admin/geo/country/{country.pk}/change/"):
            assert c.get(url).status_code == 200, url
        html = c.get(f"/django-admin/geo/address/{address.pk}/change/").content.decode()
        assert 'data-nzgeo-view data-lat="41.311081"' in html and "data-nzgeo-picker" in html and "Ko&#x27;k darvoza" in html and "maps.apple.com" in html

    def test_address_without_point_says_so(self):
        country, region, city, _ = _place()
        address = orm.Address.objects.create(owner_type="user", owner_id=uuid.uuid4(), address_type="residential", country=country, city=city, line1="X 1", normalized_signature="y")
        html = _admin().get(f"/django-admin/geo/address/{address.pk}/change/").content.decode()
        assert "Koordinata yo'q" in html and "data-nzgeo-view" not in html

    def test_map_shows_addresses_and_stores_with_nearest_store(self):
        from apps.geo.infrastructure.admin_map import map_points
        from apps.stores.infrastructure.models import Store

        country, region, city, _ = _place()
        orm.Address.objects.create(owner_type="user", owner_id=uuid.uuid4(), address_type="residential", country=country, region=region, city=city, line1="Uy 1",
                                   coordinate_latitude=41.3111, coordinate_longitude=69.2797, normalized_signature="z")
        Store.objects.create(name="Chilonzor filiali", slug=f"chil-{uuid.uuid4().hex[:6]}", latitude=41.2856, longitude=69.2034)
        points, stats = map_points(region.id)
        kinds = {p["kind"] for p in points}
        assert {"address", "store", "city"} <= kinds and stats["avg_km"] is not None
        assert "Chilonzor filiali" in next(p for p in points if p["kind"] == "address")["subtitle"]
        assert _admin().get("/django-admin/geo/map/").status_code == 200


class TestNamesInTheShoppersLanguage:
    def test_districts_come_back_in_the_requested_language(self):
        _country, region, _city, district = _place()
        orm.DistrictTranslation.objects.create(district=district, locale_code="ru", name="Юнусабадский район", slug=f"yunusabad-{uuid.uuid4().hex[:6]}")
        ru = APIClient().get(f"/api/v1/geo/regions/{region.id}/districts", HTTP_ACCEPT_LANGUAGE="ru").json()["data"]
        uz = APIClient().get(f"/api/v1/geo/regions/{region.id}/districts", HTTP_ACCEPT_LANGUAGE="uz").json()["data"]
        en = APIClient().get(f"/api/v1/geo/regions/{region.id}/districts", HTTP_ACCEPT_LANGUAGE="en").json()["data"]
        assert ru[0]["name"] == "Юнусабадский район" and uz[0]["name"] == "Yunusobod tumani"
        assert en[0]["name"] == "Yunusobod tumani"  # no English name yet → Uzbek, never a raw id


class TestHyphenatedCodes:
    """Reference data uses "UZ-SA" / "SA-SAMAR" / "TSH-CHI": loading them used to fail, so addresses only worked in Tashkent."""

    def test_address_in_a_city_with_a_hyphenated_code(self, monkeypatch):
        from apps.geo.domain.value_objects import CityCode, DistrictCode, RegionCode

        assert CityCode("SA-SAMAR").value == "SA-SAMAR" and RegionCode("UZ-SA").value == "UZ-SA" and DistrictCode("TSH-CHI").value == "TSH-CHI"
        for bad in ("-SA", "SA-", "S", "SA--X", "sa-samar", "ABCDEFGHIJK"):
            with pytest.raises(Exception):
                CityCode(bad)
        country = orm.Country.objects.filter(code="UZ").first() or orm.Country.objects.create(code="UZ", status="active")
        suffix = uuid.uuid4().hex[:3].upper()
        region = orm.Region.objects.create(country=country, code=f"UZ-{suffix}")
        city = orm.City.objects.create(region=region, code=f"SA-{suffix}")
        orm.CityTranslation.objects.create(city=city, locale_code="uz", name="Samarqand", slug=f"samarqand-{suffix.lower()}")
        with mock.patch("common.permissions.HasPermissionCode.has_permission", return_value=True):
            r = _client_as(monkeypatch, uuid.uuid4()).post("/api/v1/geo/addresses", {"address_type": "residential", "country_id": str(country.id), "city_id": str(city.id),
                                                                                    "line1": "Registon 1", "recipient_name": "A", "recipient_phone": "+998901112233"}, format="json")
        assert r.status_code == 201, r.content
