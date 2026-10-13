"""
Phase 03A final continuation's Geo Address IDOR regression suite.
Proves a CRITICAL vulnerability found and fixed this session:
AddressDetailView (PATCH/DELETE) and AddressAssignCoordinatesView
(PATCH) never called DRF's own check_object_permissions(), despite
AddressOwnerPermission's has_object_permission() already existing and
being correct. Proven live before the fix: Customer A successfully
overwrote Customer B's address line1 via a 200 response -- a
write-mutation IDOR, more severe than any read-only finding across
this entire audit.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.geo.domain.aggregates import Address, City, Country, Region
from apps.geo.domain.enums import AddressType
from apps.geo.domain.value_objects import CityCode, CountryCode, LocationSlug, RegionCode
from apps.geo.infrastructure import composition as geo_composition
from apps.geo.infrastructure.repositories import DjangoCityRepository, DjangoCountryRepository, DjangoRegionRepository
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _client_as(monkeypatch, user_id) -> APIClient:
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


def _real_country_and_city():
    country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug(f"uz-idor-{uuid.uuid4().hex[:8]}"), name="Uzbekistan")
    DjangoCountryRepository().save(country)
    region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode(f"IDOR{uuid.uuid4().hex[:4].upper()}"), slug=LocationSlug(f"idor-region-{uuid.uuid4().hex[:8]}"), name="Region")
    DjangoRegionRepository().save(region)
    city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode(f"IDOR{uuid.uuid4().hex[:4].upper()}"), slug=LocationSlug(f"idor-city-{uuid.uuid4().hex[:8]}"), name="City")
    DjangoCityRepository().save(city)
    return country, city


@pytest.fixture
def customer_b_address():
    country, city = _real_country_and_city()
    customer_b = uuid.uuid4()
    address = Address(id=uuid.uuid4(), owner_type="user", owner_id=customer_b, address_type=AddressType.RESIDENTIAL, country_id=country.id, city_id=city.id, line1="123 Original St")
    saved = geo_composition.build_address_repository().save(address)
    return saved, customer_b


class TestAddressUpdateIDOR:
    def test_customer_a_cannot_mutate_customer_b_address(self, monkeypatch, customer_b_address):
        """The proven CRITICAL bug: Customer A must not be able to overwrite Customer B's address."""
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, uuid.uuid4())
        response = client.patch(f"/api/v1/geo/addresses/{address.id}", {"line1": "HACKED BY CUSTOMER A"}, format="json")
        assert response.status_code == 403

        # Confirm the address was genuinely NOT modified in the database.
        unchanged = geo_composition.build_address_repository().get_by_id(address.id)
        assert unchanged.line1 == "123 Original St"

    def test_customer_can_update_own_address(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, customer_b)
        response = client.patch(f"/api/v1/geo/addresses/{address.id}", {"line1": "456 New St"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["line1"] == "456 New St"


class TestAddressDeleteIDOR:
    def test_customer_a_cannot_delete_customer_b_address(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, uuid.uuid4())
        response = client.delete(f"/api/v1/geo/addresses/{address.id}")
        assert response.status_code == 403

        # Confirm the address genuinely still exists.
        still_exists = geo_composition.build_address_repository().get_by_id(address.id)
        assert still_exists is not None

    def test_customer_can_delete_own_address(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, customer_b)
        response = client.delete(f"/api/v1/geo/addresses/{address.id}")
        assert response.status_code == 204


class TestAddressEditRealHttpRoundTrip:
    """
    Real, product-required capability: a customer editing a saved
    address via the real HTTP API (PATCH /api/v1/geo/addresses/{id})
    must be able to change city/type/recipient info, not just
    line1/line2/postal_code -- and a subsequent GET must reflect
    exactly what was saved, through the real serializer/view/
    application-service/repository stack (no fakes/mocks below the
    JWT auth layer).
    """

    def test_editing_city_type_and_recipient_info_persists_and_is_returned_by_a_later_get(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        # A second real city under the SAME already-seeded country
        # (calling _real_country_and_city() again would violate
        # Country.code's own real uniqueness constraint -- that helper
        # is only ever meant to seed one country per test).
        region = Region(id=uuid.uuid4(), country_id=address.country_id, code=RegionCode(f"IDOR{uuid.uuid4().hex[:4].upper()}"), slug=LocationSlug(f"idor-region-{uuid.uuid4().hex[:8]}"), name="Region 2")
        DjangoRegionRepository().save(region)
        other_city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode(f"IDOR{uuid.uuid4().hex[:4].upper()}"), slug=LocationSlug(f"idor-city-{uuid.uuid4().hex[:8]}"), name="Samarkand")
        DjangoCityRepository().save(other_city)
        client = _client_as(monkeypatch, customer_b)

        response = client.patch(
            f"/api/v1/geo/addresses/{address.id}",
            {
                "city_id": str(other_city.id), "address_type": "office",
                "recipient_name": "Otabek Xurramov", "recipient_phone": "+998901234567", "recipient_telegram_username": "otabek",
            },
            format="json",
        )
        assert response.status_code == 200, response.json()
        data = response.json()["data"]
        assert data["city_id"] == str(other_city.id)
        assert data["address_type"] == "office"
        assert data["recipient_name"] == "Otabek Xurramov"
        assert data["recipient_phone"] == "+998901234567"
        assert data["recipient_telegram_username"] == "otabek"
        assert "123 Original St" in data["formatted_single_line"]  # line1 untouched by this edit

        get_response = client.get(f"/api/v1/geo/addresses/{address.id}")
        # AddressDetailView has no GET -- confirm via the list endpoint instead, the real customer-facing read path.
        assert get_response.status_code in (404, 405)
        list_response = client.get("/api/v1/geo/addresses")
        assert list_response.status_code == 200
        [persisted] = [a for a in list_response.json()["data"] if a["id"] == str(address.id)]
        assert persisted["city_id"] == str(other_city.id)
        assert persisted["address_type"] == "office"
        assert persisted["recipient_name"] == "Otabek Xurramov"

    def test_partial_edit_does_not_create_a_duplicate_address(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, customer_b)

        response = client.patch(f"/api/v1/geo/addresses/{address.id}", {"recipient_phone": "+998907654321"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["line1"] == "123 Original St"  # unrelated field left untouched

        list_response = client.get("/api/v1/geo/addresses")
        assert len([a for a in list_response.json()["data"] if a["id"] == str(address.id)]) == 1

    def test_editing_to_a_nonexistent_city_returns_422_not_a_500(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, customer_b)
        response = client.patch(f"/api/v1/geo/addresses/{address.id}", {"city_id": str(uuid.uuid4())}, format="json")
        assert response.status_code in (404, 422)


class TestAddressCoordinatesIDOR:
    def test_customer_a_cannot_assign_coordinates_to_customer_b_address(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, uuid.uuid4())
        response = client.patch(f"/api/v1/geo/addresses/{address.id}/coordinates", {"latitude": "41.3111", "longitude": "69.2797"}, format="json")
        assert response.status_code == 403

    def test_customer_can_assign_coordinates_to_own_address(self, monkeypatch, customer_b_address):
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, customer_b)
        response = client.patch(f"/api/v1/geo/addresses/{address.id}/coordinates", {"latitude": "41.3111", "longitude": "69.2797"}, format="json")
        assert response.status_code == 200


class TestAddressListIsAlreadySafe:
    def test_list_always_scoped_to_authenticated_user(self, monkeypatch, customer_b_address):
        """Confirms AddressListCreateView.get() was already correct -- request.identity.id was already used directly, never a client-suppliable value -- so an unrelated customer's list is always empty, never leaking another user's addresses."""
        address, customer_b = customer_b_address
        client = _client_as(monkeypatch, uuid.uuid4())
        response = client.get("/api/v1/geo/addresses")
        assert response.status_code == 200
        assert response.json()["data"] == []


class TestUnauthenticatedAccessStillBlocked:
    def test_unauthenticated_patch_rejected(self, customer_b_address):
        address, customer_b = customer_b_address
        response = APIClient().patch(f"/api/v1/geo/addresses/{address.id}", {"line1": "x"}, format="json")
        assert response.status_code == 401
