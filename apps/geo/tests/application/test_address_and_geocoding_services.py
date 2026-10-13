from __future__ import annotations

import uuid

import pytest

from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.application.services.address import (
    AssignCoordinates, CreateAddress, DeleteAddress, NormalizeAddress, UpdateAddress, ValidateAddress,
)
from apps.geo.application.services.geocoding import ReverseGeocode, SearchLocations
from apps.geo.application.services.queries import ListCities, ListCountries
from apps.geo.domain.aggregates import City, Country
from apps.geo.domain.enums import AddressType
from apps.geo.domain.exceptions import DuplicateAddressDetected, GeoEntityNotFound
from apps.geo.domain.value_objects import CityCode, CountryCode, GeoPoint, LocationSlug, Coordinate
from apps.geo.tests.application.fakes import (
    FakeAddressRepository, FakeCityRepository, FakeCountryRepository, collect_events,
)
from common.exceptions import ResourceNotFound


def _ctx():
    events: list = []
    return GeoServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


def _seeded_city_and_country():
    country_repo = FakeCountryRepository()
    country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Uzbekistan")
    country_repo.save(country)
    city_repo = FakeCityRepository()
    city = City(id=uuid.uuid4(), region_id=uuid.uuid4(), code=CityCode("TAS"), slug=LocationSlug("tashkent"), name="Tashkent")
    city_repo.save(city)
    return country_repo, country, city_repo, city


@pytest.mark.django_db
class TestCreateAddress:
    def test_creates_address(self):
        country_repo, country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        ctx, events = _ctx()

        address = CreateAddress(address_repo, city_repo, country_repo, ctx).execute(
            owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL.value,
            country_id=country.id, city_id=city.id, line1="123 Main St",
        )

        assert address.line1 == "123 Main St"
        assert any(e[0] == "AddressCreated" for e in events)

    def test_creates_address_with_recipient_details(self):
        """Real, product-required capability: who the delivery is for -- name and phone required, Telegram username optional."""
        country_repo, country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        ctx, _ = _ctx()

        address = CreateAddress(address_repo, city_repo, country_repo, ctx).execute(
            owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL.value,
            country_id=country.id, city_id=city.id, line1="123 Main St",
            recipient_name="Aziz Karimov", recipient_phone="+998901234567", recipient_telegram_username="azizkarimov",
        )

        assert address.recipient_name == "Aziz Karimov"
        assert address.recipient_phone == "+998901234567"
        assert address.recipient_telegram_username == "azizkarimov"

        reloaded = address_repo.get_by_id(address.id)
        assert reloaded.recipient_name == "Aziz Karimov"
        assert reloaded.recipient_phone == "+998901234567"

    def test_recipient_telegram_username_is_optional(self):
        country_repo, country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        ctx, _ = _ctx()

        address = CreateAddress(address_repo, city_repo, country_repo, ctx).execute(
            owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL.value,
            country_id=country.id, city_id=city.id, line1="123 Main St",
            recipient_name="Bekzod", recipient_phone="+998907654321",
        )
        assert address.recipient_telegram_username is None

    def test_duplicate_address_for_same_owner_raises(self):
        country_repo, country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        ctx, _ = _ctx()
        owner_id = uuid.uuid4()

        service = CreateAddress(address_repo, city_repo, country_repo, ctx)
        service.execute(owner_type="user", owner_id=owner_id, address_type=AddressType.RESIDENTIAL.value, country_id=country.id, city_id=city.id, line1="123 Main St")

        with pytest.raises(DuplicateAddressDetected):
            service.execute(owner_type="user", owner_id=owner_id, address_type=AddressType.RESIDENTIAL.value, country_id=country.id, city_id=city.id, line1="123 Main St")

    def test_unknown_city_raises(self):
        country_repo, country, _city_repo, _city = _seeded_city_and_country()
        ctx, _ = _ctx()
        with pytest.raises(GeoEntityNotFound):
            CreateAddress(FakeAddressRepository(), FakeCityRepository(), country_repo, ctx).execute(
                owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL.value,
                country_id=country.id, city_id=uuid.uuid4(), line1="123 Main St",
            )


@pytest.mark.django_db
class TestUpdateDeleteAddress:
    def test_update_address(self):
        _country_repo, _country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        from apps.geo.domain.aggregates import Address

        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=city.id, line1="Old Line")
        address_repo.save(address)
        ctx, events = _ctx()

        updated = UpdateAddress(address_repo, city_repo, ctx).execute(address_id=address.id, line1="New Line")

        assert updated.line1 == "New Line"
        assert any(e[0] == "AddressUpdated" for e in events)

    def test_update_address_can_change_city_type_and_recipient_info(self):
        """Real, product-required capability: a customer editing a saved address must be able to correct its city, type, and recipient info -- not just line1/line2/postal_code."""
        _country_repo, _country, city_repo, city = _seeded_city_and_country()
        second_city = City(id=uuid.uuid4(), region_id=uuid.uuid4(), code=CityCode("SAM"), slug=LocationSlug("samarkand"), name="Samarkand")
        city_repo.save(second_city)
        address_repo = FakeAddressRepository()
        from apps.geo.domain.aggregates import Address

        address = Address(
            id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=city.id,
            line1="Old Line", recipient_name="Old Name", recipient_phone="+998900000000", recipient_telegram_username="old_user",
        )
        address_repo.save(address)
        ctx, events = _ctx()

        updated = UpdateAddress(address_repo, city_repo, ctx).execute(
            address_id=address.id, city_id=second_city.id, address_type=AddressType.OFFICE.value,
            recipient_name="New Name", recipient_phone="+998911111111", recipient_telegram_username="new_user",
        )

        assert updated.city_id == second_city.id
        assert updated.address_type == AddressType.OFFICE
        assert updated.recipient_name == "New Name"
        assert updated.recipient_phone == "+998911111111"
        assert updated.recipient_telegram_username == "new_user"
        # The formatted display string must reflect the NEW city, never the stale one.
        assert "Samarkand" in updated.formatted.single_line
        assert "Tashkent" not in updated.formatted.single_line

    def test_update_address_partial_update_leaves_other_fields_untouched(self):
        """PATCH-like contract: editing only recipient_phone must never blank/alter line1, city_id, or address_type."""
        _country_repo, _country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        from apps.geo.domain.aggregates import Address

        address = Address(
            id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=city.id,
            line1="Untouched Line", recipient_name="Untouched Name", recipient_phone="+998900000000",
        )
        address_repo.save(address)
        ctx, _events = _ctx()

        updated = UpdateAddress(address_repo, city_repo, ctx).execute(address_id=address.id, recipient_phone="+998922222222")

        assert updated.recipient_phone == "+998922222222"
        assert updated.line1 == "Untouched Line"
        assert updated.recipient_name == "Untouched Name"
        assert updated.address_type == AddressType.RESIDENTIAL
        assert updated.city_id == city.id

    def test_update_address_never_creates_a_second_address_row(self):
        _country_repo, _country, city_repo, city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        from apps.geo.domain.aggregates import Address

        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=city.id, line1="Old Line")
        address_repo.save(address)
        ctx, _events = _ctx()

        UpdateAddress(address_repo, city_repo, ctx).execute(address_id=address.id, line1="New Line", recipient_name="Someone")

        assert len(address_repo.by_id) == 1
        assert address_repo.by_id[address.id].id == address.id

    def test_update_address_unknown_city_raises(self):
        _country_repo, _country, city_repo, _city = _seeded_city_and_country()
        address_repo = FakeAddressRepository()
        from apps.geo.domain.aggregates import Address

        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=uuid.uuid4(), line1="Old Line")
        address_repo.save(address)
        ctx, _events = _ctx()

        with pytest.raises(GeoEntityNotFound):
            UpdateAddress(address_repo, city_repo, ctx).execute(address_id=address.id, city_id=uuid.uuid4())

    def test_delete_missing_address_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            DeleteAddress(FakeAddressRepository(), ctx).execute(uuid.uuid4())


class TestNormalizeValidateAddress:
    def test_normalize_returns_formatted_and_signature(self):
        _country_repo, _country, city_repo, city = _seeded_city_and_country()
        formatted, signature = NormalizeAddress(city_repo).execute("123 Main St", None, city.id, None)
        assert "123 Main St" in formatted.single_line
        assert len(signature) == 64  # sha256 hex digest length

    def test_validate_passes_for_known_references(self):
        country_repo, country, city_repo, city = _seeded_city_and_country()
        assert ValidateAddress(city_repo, country_repo).execute(country.id, city.id, "123 Main St") is True

    def test_validate_unknown_country_raises(self):
        _country_repo, _country, city_repo, city = _seeded_city_and_country()
        with pytest.raises(GeoEntityNotFound):
            ValidateAddress(city_repo, FakeCountryRepository()).execute(uuid.uuid4(), city.id, "123 Main St")


@pytest.mark.django_db
class TestAssignCoordinates:
    def test_assigns_coordinates(self):
        from apps.geo.domain.aggregates import Address

        address_repo = FakeAddressRepository()
        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=uuid.uuid4(), line1="123 Main St")
        address_repo.save(address)
        ctx, _ = _ctx()

        updated = AssignCoordinates(address_repo, ctx).execute(address_id=address.id, latitude=41.3, longitude=69.2)

        assert updated.coordinate.point.coordinate.latitude.value == 41.3


class TestReverseGeocodeAndSearch:
    def test_reverse_geocode_finds_nearest_city(self):
        city_repo = FakeCityRepository()
        city = City(id=uuid.uuid4(), region_id=uuid.uuid4(), code=CityCode("TAS"), slug=LocationSlug("tashkent"), name="Tashkent", center_point=GeoPoint(coordinate=Coordinate.of(41.3, 69.2)))
        city_repo.save(city)
        ctx, _ = _ctx()

        result = ReverseGeocode(city_repo, ctx).execute(latitude=41.31, longitude=69.21)

        assert result["nearest_city"].id == city.id

    def test_search_locations_calls_gateway(self):
        class _FakeGateway:
            def search(self, query, geo_level, page, page_size):
                return [{"id": "x", "name": "Tashkent"}], 1

        ctx, _ = _ctx()
        results, total = SearchLocations(_FakeGateway(), ctx).execute(query="tash")
        assert total == 1


class TestListQueries:
    def test_list_countries(self):
        repo = FakeCountryRepository()
        repo.save(Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Uzbekistan"))
        results, total = ListCountries(repo).execute()
        assert total == 1

    def test_list_cities_filtered_by_region(self):
        repo = FakeCityRepository()
        region_id = uuid.uuid4()
        repo.save(City(id=uuid.uuid4(), region_id=region_id, code=CityCode("TAS"), slug=LocationSlug("tashkent"), name="Tashkent"))
        repo.save(City(id=uuid.uuid4(), region_id=uuid.uuid4(), code=CityCode("SAM"), slug=LocationSlug("samarkand"), name="Samarkand"))
        results, total = ListCities(repo).execute(region_id=region_id)
        assert total == 1
