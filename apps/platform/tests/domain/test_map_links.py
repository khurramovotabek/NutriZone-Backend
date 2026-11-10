"""Map-card links pasted in the Dashboard must belong to the right service; the public settings expose them."""
from __future__ import annotations

import pytest

from apps.platform.domain.map_links import map_link_error


@pytest.mark.parametrize("field,url", [
    ("google_maps_url", ""),
    ("google_maps_url", "https://maps.app.goo.gl/AbC123"),
    ("google_maps_url", "https://www.google.com/maps/place/NUTRIZONE/@41.24,69.32,17z"),
    ("google_maps_url", "https://maps.google.com/?cid=2203917330504296357"),
    ("yandex_maps_url", "https://yandex.uz/maps/org/nutrizone/123456789/"),
    ("two_gis_url", "https://2gis.uz/tashkent/firm/70000001012345678"),
])
def test_links_of_the_right_service_pass(field, url):
    assert map_link_error(field, url) is None


@pytest.mark.parametrize("field,url", [
    ("google_maps_url", "https://www.google.com/search?q=nutrizone"),
    ("google_maps_url", "https://yandex.uz/maps/org/x/1/"),
    ("yandex_maps_url", "https://notyandex.uz/maps/"),
    ("two_gis_url", "javascript:alert(1)//2gis.uz"),
])
def test_other_links_are_rejected(field, url):
    assert map_link_error(field, url)


@pytest.mark.django_db
def test_public_settings_expose_the_brand_map_cards():
    from rest_framework.test import APIClient

    from apps.platform.infrastructure.models import SiteSettings

    SiteSettings.objects.update_or_create(pk=1, defaults={"google_maps_url": "https://maps.app.goo.gl/AbC123"})
    data = APIClient().get("/api/v1/settings/public").json()["data"]
    assert data["map_listings"] == {"google": "https://maps.app.goo.gl/AbC123", "yandex": "", "two_gis": ""}
