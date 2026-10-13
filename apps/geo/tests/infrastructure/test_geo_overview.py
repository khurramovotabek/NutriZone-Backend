"""
NutriZone Admin "Geo Overview" tests -- closes a real, confirmed gap:
Country/Region/District/City/Neighborhood/Address form a real
geographic hierarchy but had zero visual overview, only separate,
bare, standard Django admin grids.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.geo.infrastructure import models as geo_orm
from apps.geo.infrastructure.geo_overview import GeoOverviewAggregator

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    AuthUser = get_user_model()
    user = AuthUser.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


def _make_country(code="UZ", name="Uzbekistan"):
    country = geo_orm.Country.objects.create(id=uuid.uuid4(), code=code, status="active")
    geo_orm.CountryTranslation.objects.create(id=uuid.uuid4(), country=country, locale_code="en", name=name, slug=name.lower())
    return country


class TestGeoOverviewAggregator:
    def test_country_reports_real_hierarchy_counts(self):
        country = _make_country()
        region = geo_orm.Region.objects.create(id=uuid.uuid4(), country=country, code="TSH-R", status="active")
        geo_orm.District.objects.create(id=uuid.uuid4(), region=region, code="TSH-D1", status="active")
        city = geo_orm.City.objects.create(id=uuid.uuid4(), region=region, code="TSH-C1", status="active", center_latitude=41.3, center_longitude=69.2)
        geo_orm.Neighborhood.objects.create(id=uuid.uuid4(), city=city, code="TSH-N1", status="active")
        geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type="residential", country=country, city=city, line1="Test", normalized_signature="sig-1")

        countries = GeoOverviewAggregator().countries_with_hierarchy_counts()
        matching = next(c for c in countries if c["code"] == "UZ")
        assert matching["region_count"] == 1
        assert matching["district_count"] == 1
        assert matching["city_count"] == 1
        assert matching["neighborhood_count"] == 1
        assert matching["address_count"] == 1

    def test_country_with_no_children_reports_zeros_not_an_error(self):
        _make_country(code="XZ", name="Empty Country")
        countries = GeoOverviewAggregator().countries_with_hierarchy_counts()
        matching = next(c for c in countries if c["code"] == "XZ")
        assert matching["region_count"] == 0
        assert matching["city_count"] == 0

    def test_city_missing_coordinates_is_flagged_and_city_with_coordinates_is_not(self):
        country = _make_country(code="KG", name="Kyrgyzstan")
        region = geo_orm.Region.objects.create(id=uuid.uuid4(), country=country, code="KG-R", status="active")
        with_coords = geo_orm.City.objects.create(id=uuid.uuid4(), region=region, code="KG-C1", status="active", center_latitude=42.8, center_longitude=74.6)
        geo_orm.CityTranslation.objects.create(id=uuid.uuid4(), city=with_coords, locale_code="en", name="Has Coords", slug="has-coords")
        without_coords = geo_orm.City.objects.create(id=uuid.uuid4(), region=region, code="KG-C2", status="active")
        geo_orm.CityTranslation.objects.create(id=uuid.uuid4(), city=without_coords, locale_code="en", name="No Coords", slug="no-coords")

        missing = GeoOverviewAggregator().cities_missing_coordinates()
        names = {c["name"] for c in missing}
        assert "No Coords" in names
        assert "Has Coords" not in names


class TestGeoOverviewPage:
    def test_page_renders_real_country_data(self, staff_client):
        _make_country(code="TJ", name="Tajikistan")

        response = staff_client.get("/django-admin/geo-overview/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Tajikistan" in content
        assert "TJ" in content

    def test_page_requires_staff_authentication(self):
        response = Client().get("/django-admin/geo-overview/")
        assert response.status_code in (302, 403)

    def test_page_is_linked_from_the_dashboard_home(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "geo-overview" in response.content.decode()
