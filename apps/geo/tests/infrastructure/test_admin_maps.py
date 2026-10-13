"""
Real, closed gap: Address.coordinate_preview previously showed only a
bare lat/lng number pair, even though real coordinate_latitude+longitude
data existed. It now renders a real, interactive Leaflet map
(self-hosted, no API key -- vendored the same way this project already
vendors Chart.js) on the change form.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from apps.geo.infrastructure import models as geo_orm

pytestmark = pytest.mark.django_db


def _admin_client() -> Client:
    ContentType.objects.clear_cache()
    admin_user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


def _make_city():
    country = geo_orm.Country.objects.filter(code="UZ").first() or geo_orm.Country.objects.create(id=uuid.uuid4(), code="UZ")
    region = geo_orm.Region.objects.create(id=uuid.uuid4(), country=country, code=f"R{uuid.uuid4().hex[:4].upper()}")
    return geo_orm.City.objects.create(id=uuid.uuid4(), region=region, code=f"C{uuid.uuid4().hex[:4].upper()}")


class TestMapTileProvider:
    def test_tile_provider_is_not_a_host_that_requires_an_api_key_or_returns_403(self):
        """
        Real, closed production bug (dashboard cleanup phase): CARTO's
        free basemaps.cartocdn.com tiles now require a registered API
        key -- confirmed live, every tile rendered a literal
        "API KEY REQUIRED" watermark instead of a real map. That host
        had itself replaced tile.openstreetmap.org after ITS own
        confirmed "403 Access blocked" bug (OpenStreetMap's own Tile
        Usage Policy blocks exactly this traffic shape). Confirms the JS
        asset references neither now-broken host.
        """
        import pathlib

        js_path = pathlib.Path(__file__).resolve().parents[3] / "platform" / "static" / "admin" / "js" / "nutrizone-geo-maps.js"
        content = js_path.read_text()
        tile_url_line = next(line for line in content.splitlines() if line.strip().startswith("var NZ_MAP_TILE_URL"))
        assert "tile.openstreetmap.org" not in tile_url_line
        assert "cartocdn.com" not in tile_url_line
        assert "arcgisonline.com" in tile_url_line


class TestGeoAdminTiles:
    def test_dashboard_geo_maps_use_esri_tiles(self):
        import pathlib

        js = (pathlib.Path(__file__).resolve().parents[3] / "platform" / "static" / "admin" / "js" / "nutrizone-geo-admin.js").read_text()
        assert "arcgisonline.com" in js and "tile.openstreetmap.org" not in js and "cartocdn.com" not in js


class TestAddressMap:
    def test_change_page_includes_a_real_leaflet_marker_for_an_address_with_coordinates(self):
        city = _make_city()
        address = geo_orm.Address.objects.create(
            id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type="residential",
            country=city.region.country, city=city, line1="Test St",
            coordinate_latitude=41.311081, coordinate_longitude=69.240562,
        )
        client = _admin_client()
        response = client.get(f"/django-admin/geo/address/{address.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "data-nzgeo-view" in content
        assert 'data-lat="41.311081"' in content
        assert 'data-lng="69.240562"' in content

    def test_address_without_coordinates_shows_an_honest_empty_state(self):
        city = _make_city()
        address = geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type="residential", country=city.region.country, city=city, line1="Test St")
        client = _admin_client()
        response = client.get(f"/django-admin/geo/address/{address.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "data-nzgeo-view" not in content
        assert "Koordinata yo'q" in content
