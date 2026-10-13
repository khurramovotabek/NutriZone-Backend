"""
Geo & Location API serializers.

Structural validation only -- format checks delegate to the same
domain value objects used elsewhere (CountryCode, Latitude, Longitude,
PostalCode), per MIC §6's "one place" rule. Matches
`apps.products.interfaces.api.v1.serializers`'s exact pattern.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.geo.domain.enums import AddressType
from apps.geo.domain.value_objects import CountryCode, Latitude, Longitude, PostalCode
from common.exceptions import ValidationFailed


def _validate_country_code(value: str) -> str:
    try:
        CountryCode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_postal_code(value: str) -> str:
    try:
        PostalCode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_latitude(value: float) -> float:
    try:
        Latitude(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_longitude(value: float) -> float:
    try:
        Longitude(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


# --- Hierarchy read shapes -----------------------------------------------


class CountrySerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    slug = serializers.CharField(required=False)


class RegionSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    country_id = serializers.CharField()


class DistrictSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    region_id = serializers.CharField()


class CitySerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    region_id = serializers.CharField()
    district_id = serializers.CharField(allow_null=True)
    center_latitude = serializers.FloatField(allow_null=True)
    center_longitude = serializers.FloatField(allow_null=True)
    timezone = serializers.CharField(allow_null=True)


class NeighborhoodSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    city_id = serializers.CharField()


class HierarchyAncestorsSerializer(serializers.Serializer):
    city = serializers.DictField()
    district = serializers.DictField(allow_null=True)
    region = serializers.DictField()
    country = serializers.DictField()


# --- Write / command shapes ------------------------------------------------


class CreateCountrySerializer(serializers.Serializer):
    code = serializers.CharField(validators=[_validate_country_code])
    name = serializers.CharField(max_length=128)
    slug = serializers.CharField(required=False, allow_null=True)


class UpdateCountrySerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=128)


class CreateRegionSerializer(serializers.Serializer):
    country_id = serializers.UUIDField()
    code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=128)
    slug = serializers.CharField(required=False, allow_null=True)


class UpdateRegionSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=128)


class CreateDistrictSerializer(serializers.Serializer):
    region_id = serializers.UUIDField()
    code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=128)
    slug = serializers.CharField(required=False, allow_null=True)


class UpdateDistrictSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=128)


class CreateCitySerializer(serializers.Serializer):
    region_id = serializers.UUIDField()
    district_id = serializers.UUIDField(required=False, allow_null=True)
    code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=128)
    slug = serializers.CharField(required=False, allow_null=True)


class UpdateCitySerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=128)


class CreateNeighborhoodSerializer(serializers.Serializer):
    city_id = serializers.UUIDField()
    code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=128)
    slug = serializers.CharField(required=False, allow_null=True)


class UpdateNeighborhoodSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=128)


# --- Address shapes -----------------------------------------------------


class AddressMetadataSerializer(serializers.Serializer):
    """Delivery details a courier needs in Uzbekistan: building / complex, podyezd, floor, flat, door code, landmark (mo'ljal)."""

    building_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    entrance = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=16)
    floor = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=16)
    unit = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=16)
    delivery_instructions = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=500)
    entrance_code = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)


class AddressSerializer(serializers.Serializer):
    id = serializers.CharField()
    owner_type = serializers.CharField()
    owner_id = serializers.CharField()
    address_type = serializers.CharField()
    line1 = serializers.CharField()
    line2 = serializers.CharField(allow_null=True)
    formatted_single_line = serializers.CharField(allow_null=True)
    city_id = serializers.CharField()
    country_id = serializers.CharField()
    coordinate_latitude = serializers.FloatField(allow_null=True)
    coordinate_longitude = serializers.FloatField(allow_null=True)
    is_default = serializers.BooleanField()
    recipient_name = serializers.CharField(allow_null=True)
    recipient_phone = serializers.CharField(allow_null=True)
    recipient_telegram_username = serializers.CharField(allow_null=True)


class CreateAddressSerializer(serializers.Serializer):
    owner_type = serializers.CharField(max_length=32)
    owner_id = serializers.UUIDField()
    address_type = serializers.ChoiceField(choices=AddressType.values())
    country_id = serializers.UUIDField()
    city_id = serializers.UUIDField()
    region_id = serializers.UUIDField(required=False, allow_null=True)
    district_id = serializers.UUIDField(required=False, allow_null=True)
    neighborhood_id = serializers.UUIDField(required=False, allow_null=True)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(required=False, allow_null=True, max_length=255)
    postal_code = serializers.CharField(required=False, allow_null=True, validators=[_validate_postal_code])
    # Real, product-required capability: who the delivery is for. Name
    # and phone are required (a delivery is meaningless without them);
    # the Telegram username is optional, since not every recipient has
    # one, or the customer may not know it.
    recipient_name = serializers.CharField(max_length=255)
    recipient_phone = serializers.CharField(max_length=32)
    recipient_telegram_username = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    metadata = AddressMetadataSerializer(required=False, allow_null=True)


class UpdateAddressSerializer(serializers.Serializer):
    """
    Real, product-required capability: a customer previously had no way
    to edit a saved address's city/type/recipient info at all -- only
    line1/line2/postal_code. Every field here is optional/PATCH-like:
    omitted means unchanged (see Address.update()'s own docstring for
    the exact contract). Coordinates are intentionally NOT included --
    the existing, separate AssignCoordinatesSerializer/
    AddressAssignCoordinatesView already handle that real, working
    pathway; never a second one here.
    """

    line1 = serializers.CharField(required=False, max_length=255)
    line2 = serializers.CharField(required=False, allow_null=True, max_length=255)
    postal_code = serializers.CharField(required=False, allow_null=True, validators=[_validate_postal_code])
    city_id = serializers.UUIDField(required=False)
    address_type = serializers.ChoiceField(required=False, choices=AddressType.values())
    recipient_name = serializers.CharField(required=False, max_length=255)
    recipient_phone = serializers.CharField(required=False, max_length=32)
    recipient_telegram_username = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    metadata = AddressMetadataSerializer(required=False)
    district_id = serializers.UUIDField(required=False)


COORDINATE_SOURCES = ("gps", "map_pin", "search", "link", "telegram_native_share", "manual")


class AssignCoordinatesSerializer(serializers.Serializer):
    latitude = serializers.FloatField(validators=[_validate_latitude])
    longitude = serializers.FloatField(validators=[_validate_longitude])
    # how the point was found -- the dashboard shows it to dispatchers (a GPS fix at 15 m vs a pin dropped by hand)
    source = serializers.ChoiceField(choices=COORDINATE_SOURCES, required=False, default="manual")
    accuracy_meters = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100000)


class ValidateAddressSerializer(serializers.Serializer):
    country_id = serializers.UUIDField()
    city_id = serializers.UUIDField()
    line1 = serializers.CharField()
    postal_code = serializers.CharField(required=False, allow_null=True)


class NormalizeAddressSerializer(serializers.Serializer):
    line1 = serializers.CharField()
    line2 = serializers.CharField(required=False, allow_null=True)
    city_id = serializers.UUIDField()
    postal_code = serializers.CharField(required=False, allow_null=True)


# --- Geocoding shapes -------------------------------------------------------


class ReverseGeocodeResultSerializer(serializers.Serializer):
    nearest_city = CitySerializer(allow_null=True)


class SearchLocationsResultSerializer(serializers.Serializer):
    id = serializers.CharField()
    geo_level = serializers.CharField()
    name = serializers.CharField()
    slug = serializers.CharField()
