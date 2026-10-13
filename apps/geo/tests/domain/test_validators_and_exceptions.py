from __future__ import annotations

import pytest

from apps.geo.domain import exceptions as exc
from apps.geo.domain.validators import (
    CoordinateValidator,
    CountryCodeValidator,
    LatitudeValidator,
    LongitudeValidator,
    PostalCodeValidator,
    RegionCodeValidator,
    TimezoneFormatValidator,
    validate_hierarchy_not_self_referential,
)
from common.exceptions import DomainException, ValidationFailed

pytestmark = pytest.mark.unit


def test_latitude_validator():
    assert LatitudeValidator(45).value == 45


def test_longitude_validator():
    assert LongitudeValidator(-120).value == -120


def test_coordinate_validator():
    coord = CoordinateValidator(41.3, 69.2)
    assert coord.latitude.value == 41.3


def test_postal_code_validator():
    assert PostalCodeValidator("100000").value == "100000"


def test_country_code_validator():
    assert CountryCodeValidator("UZ").value == "UZ"


def test_region_code_validator():
    assert RegionCodeValidator("TASH").value == "TASH"


def test_timezone_format_validator():
    assert TimezoneFormatValidator("Asia/Tashkent").value == "Asia/Tashkent"


def test_validate_hierarchy_not_self_referential_passes():
    validate_hierarchy_not_self_referential("id-1", "id-2")


def test_validate_hierarchy_not_self_referential_raises():
    with pytest.raises(exc.InvalidHierarchy):
        validate_hierarchy_not_self_referential("id-1", "id-1")


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.DuplicateCountryCode, exc.DuplicateRegionCode, exc.DuplicateDistrictCode, exc.DuplicateCityCode,
        exc.DuplicateNeighborhoodCode, exc.DuplicatePostalCode, exc.DuplicateSlug, exc.InvalidHierarchy,
        exc.InvalidCoordinate, exc.InvalidTimezone, exc.InvalidAddress,
        exc.DuplicateAddressDetected, exc.GeoEntityNotFound, exc.GeoEntityInactive,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code
