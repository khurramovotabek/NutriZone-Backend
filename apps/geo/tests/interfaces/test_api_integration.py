"""
Full-stack API integration tests -- real URL routing, serializers,
views, application services, and repository layer together against a
real database. Matches
`apps.products.tests.interfaces.test_api_integration`'s pattern.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.geo.domain.aggregates import City, Country, Region
from apps.geo.domain.value_objects import CityCode, CountryCode, LocationSlug, RegionCode
from apps.geo.infrastructure.repositories import DjangoCityRepository, DjangoCountryRepository, DjangoRegionRepository
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


class TestPublicHierarchyEndpoints:
    def test_list_countries(self, api_client):
        repo = DjangoCountryRepository()
        repo.save(Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uzbekistan"), name="Uzbekistan"))

        response = api_client.get("/api/v1/geo/countries")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_list_regions_for_country(self, api_client):
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz-regions"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = DjangoRegionRepository()
        region_repo.save(Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TASH"), slug=LocationSlug("tashkent-region"), name="Tashkent"))

        response = api_client.get(f"/api/v1/geo/countries/{country.id}/regions")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_get_city_detail(self, api_client):
        region_repo = DjangoRegionRepository()
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz-city-detail"), name="Uzbekistan")
        country_repo.save(country)
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TCD"), slug=LocationSlug("tashkent-cd"), name="Tashkent")
        region_repo.save(region)
        city_repo = DjangoCityRepository()
        city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("TCD1"), slug=LocationSlug("tashkent-city-cd"), name="Tashkent City")
        city_repo.save(city)

        response = api_client.get(f"/api/v1/geo/cities/{city.id}")
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Tashkent City"

    def test_get_nonexistent_city_returns_404(self, api_client):
        response = api_client.get(f"/api/v1/geo/cities/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_location_search_endpoint(self, api_client):
        response = api_client.get("/api/v1/geo/locations/search?q=tash")
        assert response.status_code == 200

    def test_location_autocomplete_endpoint(self, api_client):
        response = api_client.get("/api/v1/geo/locations/autocomplete?q=tas")
        assert response.status_code == 200

    def test_reverse_geocode_missing_params_returns_422(self, api_client):
        response = api_client.get("/api/v1/geo/locations/reverse-geocode")
        assert response.status_code == 422

    def test_reverse_geocode_valid_params(self, api_client):
        response = api_client.get("/api/v1/geo/locations/reverse-geocode?latitude=41.3&longitude=69.2")
        assert response.status_code == 200

class TestAdminEndpointsUnauthenticated:
    def test_admin_country_list_requires_auth(self, api_client):
        response = api_client.get("/api/v1/geo/admin/countries")
        assert response.status_code == 401

    def test_admin_country_create_requires_auth(self, api_client):
        response = api_client.post("/api/v1/geo/admin/countries", {"code": "UZ", "name": "Uzbekistan"}, format="json")
        assert response.status_code == 401


class TestAdminEndpointsPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_admin_country_create_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/geo/admin/countries", {"code": "UZ", "name": "Uzbekistan"}, format="json")
        assert response.status_code == 403


class TestAdminEndpointsAuthorized:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_create_country(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/geo/admin/countries", {"code": "UZ", "name": "Uzbekistan"}, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["code"] == "UZ"

    def test_create_country_duplicate_code_returns_409(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        api_client.post("/api/v1/geo/admin/countries", {"code": "KZ", "name": "Kazakhstan"}, format="json")
        response = api_client.post("/api/v1/geo/admin/countries", {"code": "KZ", "name": "Kazakhstan Again"}, format="json")
        assert response.status_code == 409

    def test_full_hierarchy_creation_flow(self, api_client):
        """Verifies the merged list+create views resolve correctly for every hierarchy level -- the exact class of routing bug fixed in the Products module, here verified never to have occurred."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        country_response = api_client.post("/api/v1/geo/admin/countries", {"code": "TJ", "name": "Tajikistan"}, format="json")
        assert country_response.status_code == 201
        country_id = country_response.json()["data"]["id"]

        region_response = api_client.post(f"/api/v1/geo/admin/countries/{country_id}/regions", {"code": "DUSH", "name": "Dushanbe Region"}, format="json")
        assert region_response.status_code == 201
        region_id = region_response.json()["data"]["id"]

        city_response = api_client.post("/api/v1/geo/admin/cities", {"region_id": region_id, "code": "DUS", "name": "Dushanbe"}, format="json")
        assert city_response.status_code == 201

        # List endpoints on the SAME paths must also still work (proves GET wasn't shadowed by POST or vice versa).
        list_response = api_client.get("/api/v1/geo/admin/countries")
        assert list_response.status_code == 200
        list_regions_response = api_client.get(f"/api/v1/geo/admin/countries/{country_id}/regions")
        assert list_regions_response.status_code == 200

    def test_update_and_delete_country(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/geo/admin/countries", {"code": "KG", "name": "Kyrgyzstan"}, format="json")
        country_id = create_response.json()["data"]["id"]

        update_response = api_client.patch(f"/api/v1/geo/admin/countries/{country_id}", {"name": "Kyrgyz Republic"}, format="json")
        assert update_response.status_code == 200
        assert update_response.json()["data"]["name"] == "Kyrgyz Republic"

        delete_response = api_client.delete(f"/api/v1/geo/admin/countries/{country_id}")
        assert delete_response.status_code == 204

    def test_response_envelope_has_request_id(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/geo/admin/countries", {"code": "TM", "name": "Turkmenistan"}, format="json")
        assert "request_id" in response.json()["meta"]


class TestAddressSelfService:
    @pytest.fixture(autouse=True)
    def _authenticated_user(self, monkeypatch):
        self.user_id = uuid.uuid4()
        fake_user = SimpleNamespace(id=self.user_id, is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )

    def test_create_and_list_own_addresses(self, api_client):
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz-addr-test"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = DjangoRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("ADDR"), slug=LocationSlug("addr-region"), name="Region")
        region_repo.save(region)
        city_repo = DjangoCityRepository()
        city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("ADDR1"), slug=LocationSlug("addr-city"), name="City")
        city_repo.save(city)

        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post(
            "/api/v1/geo/addresses",
            {"address_type": "residential", "country_id": str(country.id), "city_id": str(city.id), "line1": "123 Main St", "recipient_name": "Test Recipient", "recipient_phone": "+998901234567"},
            format="json",
        )
        assert create_response.status_code == 201

        list_response = api_client.get("/api/v1/geo/addresses")
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1

    def test_validate_address_endpoint(self, api_client):
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz-validate"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = DjangoRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("VAL"), slug=LocationSlug("val-region"), name="Region")
        region_repo.save(region)
        city_repo = DjangoCityRepository()
        city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("VAL1"), slug=LocationSlug("val-city"), name="City")
        city_repo.save(city)

        response = api_client.post("/api/v1/geo/addresses/validate", {"country_id": str(country.id), "city_id": str(city.id), "line1": "123 Main St"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is True
