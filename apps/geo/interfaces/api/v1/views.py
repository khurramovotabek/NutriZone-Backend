"""
Geo & Location API views.

Thin per Django Implementation Blueprint §3: each view deserializes,
calls exactly one Application Service (built via
infrastructure/composition.py), and returns through the standard
response envelope. Matches
`apps.products.interfaces.api.v1.views`'s exact pattern -- including
its two hard-learned lessons: never register two views on the same
URL path (merge into one collection view), and never instantiate a
repository directly in a view (always go through composition.py).
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.geo.infrastructure import composition
from apps.geo.infrastructure.selectors import (
    AddressLookupSelector,
    BoundingBoxSelector,
    CityLookupSelector,
    CountryTreeSelector,
    DistrictTreeSelector,
    HierarchyTraversalSelector,
    NeighborhoodLookupSelector,
    RegionTreeSelector,
)
from apps.geo.interfaces.api.v1.filters import (
    parse_bounding_box_params,
    parse_pagination,
    parse_reverse_geocode_params,
    parse_search_params,
    parse_uuid_param,
)
from apps.geo.interfaces.api.v1.permissions import (
    AddressOwnerPermission,
    GeoAddressPermission,
    GeoManagePermission,
    GeoViewPermission,
)
from apps.geo.interfaces.api.v1.serializers import (
    AssignCoordinatesSerializer,
    CitySerializer,
    CreateAddressSerializer,
    CreateCitySerializer,
    CreateCountrySerializer,
    CreateDistrictSerializer,
    CreateNeighborhoodSerializer,
    CreateRegionSerializer,
    NormalizeAddressSerializer,
    UpdateAddressSerializer,
    UpdateCitySerializer,
    UpdateCountrySerializer,
    UpdateDistrictSerializer,
    UpdateNeighborhoodSerializer,
    UpdateRegionSerializer,
    ValidateAddressSerializer,
)
from common.exceptions import ResourceNotFound, ValidationFailed
from common.responses import paginated_response, success_response
from core.observability import timed
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class GeoAdminThrottle(ScopedRateLimitThrottle):
    scope = "geo.admin_operation"
    limit = 300
    window_seconds = 3600
    identifier_source = "user"


class GeoSearchThrottle(ScopedRateLimitThrottle):
    scope = "geo.search"
    limit = 120
    window_seconds = 60
    identifier_source = "ip"


class AddressWriteThrottle(ScopedRateLimitThrottle):
    scope = "geo.address_write"
    limit = 60
    window_seconds = 3600
    identifier_source = "user"


def _country_payload(country) -> dict:
    return {"id": str(country.id), "code": country.code.value, "name": country.name, "slug": country.slug.value}


def _region_payload(region) -> dict:
    return {"id": str(region.id), "code": region.code.value, "name": region.name, "country_id": str(region.country_id)}


def _district_payload(district) -> dict:
    return {"id": str(district.id), "code": district.code.value, "name": district.name, "region_id": str(district.region_id)}


def _city_payload(city) -> dict:
    return {
        "id": str(city.id), "code": city.code.value, "name": city.name, "region_id": str(city.region_id),
        "district_id": str(city.district_id) if city.district_id else None,
        "center_latitude": city.center_point.coordinate.latitude.value if city.center_point else None,
        "center_longitude": city.center_point.coordinate.longitude.value if city.center_point else None,
        "timezone": str(city.timezone) if city.timezone else None,
    }


def _neighborhood_payload(neighborhood) -> dict:
    return {"id": str(neighborhood.id), "code": neighborhood.code.value, "name": neighborhood.name, "city_id": str(neighborhood.city_id)}


def _address_payload(address) -> dict:
    return {
        "id": str(address.id), "owner_type": address.owner_type, "owner_id": str(address.owner_id), "address_type": address.address_type.value,
        "line1": address.line1, "line2": address.line2, "formatted_single_line": address.formatted.single_line if address.formatted else None,
        "city_id": str(address.city_id), "country_id": str(address.country_id),
        "coordinate_latitude": address.coordinate.point.coordinate.latitude.value if address.coordinate else None,
        "coordinate_longitude": address.coordinate.point.coordinate.longitude.value if address.coordinate else None,
        "is_default": address.is_default,
        "recipient_name": address.recipient_name, "recipient_phone": address.recipient_phone,
        "recipient_telegram_username": address.recipient_telegram_username,
        "region_id": str(address.region_id) if address.region_id else None, "district_id": str(address.district_id) if address.district_id else None,
        "coordinate_accuracy_meters": address.coordinate.point.accuracy_meters if address.coordinate else None,
        "coordinate_source": address.coordinate.source if address.coordinate else None,
        "metadata": {f: getattr(address.metadata, f, None) for f in ("building_name", "entrance", "floor", "unit", "entrance_code", "delivery_instructions")},
    }


# ============================================================
# Public: hierarchy read endpoints
# ============================================================


class CountryListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="List active countries", responses={200: OpenApiResponse(description="Country list"), **_responses(422)})
    def get(self, request):
        return success_response(data=CountryTreeSelector().tree())


class RegionListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="List regions for a country", responses={200: OpenApiResponse(description="Region list"), **_responses(422)})
    def get(self, request, country_id: str):
        return success_response(data=RegionTreeSelector().tree(uuid.UUID(country_id)))


class DistrictListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="List districts for a region")
    def get(self, request, region_id: str):
        return success_response(data=DistrictTreeSelector().tree(uuid.UUID(region_id)))


class CityListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="List cities", responses={200: CitySerializer(many=True), **_responses(422)})
    def get(self, request):
        pagination = parse_pagination(request.query_params)
        region_id = parse_uuid_param(request.query_params.get("filter[region_id]"), "filter[region_id]")
        cards, total = CityLookupSelector().list(region_id=region_id, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=cards, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class CityDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="Get a city by id", responses={200: CitySerializer, **_responses(404)})
    def get(self, request, city_id: str):
        card = CityLookupSelector().get_by_id(uuid.UUID(city_id))
        if card is None:
            raise ResourceNotFound("City not found.")
        return success_response(data=card)


class NeighborhoodListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="List neighborhoods for a city")
    def get(self, request, city_id: str):
        pagination = parse_pagination(request.query_params)
        cards, total = NeighborhoodLookupSelector().list(uuid.UUID(city_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=cards, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class CityAncestorsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="Get a city's full administrative hierarchy (District/Region/Country)", responses={200: OpenApiResponse(description="Hierarchy ancestors"), **_responses(404)})
    def get(self, request, city_id: str):
        result = HierarchyTraversalSelector().ancestors_of_city(uuid.UUID(city_id))
        if result is None:
            raise ResourceNotFound("City not found.")
        return success_response(data=result)


class LocationSearchView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [GeoSearchThrottle]

    @extend_schema(tags=["Geo"], summary="Search locations across the administrative hierarchy", responses={200: OpenApiResponse(description="Search results"), **_responses(422, 429)})
    def get(self, request):
        params = parse_search_params(request.query_params)
        with timed("geo.search_duration"):
            results, total = composition.build_search_locations().execute(query=params.query, geo_level=params.geo_level, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=results, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})


class LocationAutocompleteView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [GeoSearchThrottle]

    @extend_schema(tags=["Geo"], summary="Autocomplete a partial location name")
    def get(self, request):
        partial = request.query_params.get("q", "")
        limit = int(request.query_params.get("limit", 10))
        results = composition.build_geo_selector().autocomplete(partial, limit=limit)
        return success_response(data=results)


class ReverseGeocodeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [GeoSearchThrottle]

    @extend_schema(tags=["Geo"], summary="Reverse-geocode a coordinate to the nearest city", responses={200: OpenApiResponse(description="Reverse geocode result"), **_responses(422, 429)})
    def get(self, request):
        lat, lng = parse_reverse_geocode_params(request.query_params)
        result = composition.build_reverse_geocode().execute(latitude=lat, longitude=lng)
        payload = {
            "nearest_city": _city_payload(result["nearest_city"]) if result["nearest_city"] else None,
        }
        return success_response(data=payload)


def _point(params) -> tuple[float, float]:
    from common.exceptions import ValidationFailed

    try:
        lat, lng = float(params.get("lat")), float(params.get("lng"))
    except (TypeError, ValueError):
        raise ValidationFailed("lat and lng are required numbers.", details={"fields": [{"field": "lat", "code": "INVALID"}]}) from None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationFailed("Coordinates are out of range.", details={"fields": [{"field": "lat", "code": "OUT_OF_RANGE"}]})
    return lat, lng


class LocateView(APIView):
    """A point (GPS fix, map pin, pasted link) → city / region / country / district ids from our data + street and house."""

    permission_classes = [AllowAny]
    throttle_classes = [GeoSearchThrottle]

    @extend_schema(tags=["Geo"], summary="Resolve a point to our city / region / district and its street address", responses={200: OpenApiResponse(description="Location"), **_responses(422, 429)})
    def get(self, request):
        from apps.geo.infrastructure.gateways import geocoder

        lat, lng = _point(request.query_params)
        return success_response(data=geocoder.locate(lat, lng, geocoder.query_language(request), with_street=request.query_params.get("street", "1") != "0"))


class GeocodeView(APIView):
    """Free-text search for a place or street in Uzbekistan ("Chorsu", "Amir Temur 15") → points to pick on the map."""

    permission_classes = [AllowAny]
    throttle_classes = [GeoSearchThrottle]

    @extend_schema(tags=["Geo"], summary="Search places / streets in Uzbekistan", responses={200: OpenApiResponse(description="Places"), **_responses(429)})
    def get(self, request):
        from apps.geo.infrastructure.gateways import geocoder

        near = None
        if request.query_params.get("lat") and request.query_params.get("lng"):
            try:
                near = _point(request.query_params)
            except Exception:  # noqa: BLE001 - "near" is only a sort hint
                near = None
        return success_response(data=geocoder.geocode(request.query_params.get("q", ""), geocoder.query_language(request), near=near))


class ParseMapLinkView(APIView):
    """A link shared from Yandex / Google / Apple Maps / 2GIS (short links too) or "lat, lng" → coordinates."""

    permission_classes = [AllowAny]
    throttle_classes = [GeoSearchThrottle]

    @extend_schema(tags=["Geo"], summary="Read coordinates from a map link", responses={200: OpenApiResponse(description="Point"), **_responses(422, 429)})
    def post(self, request):
        from apps.geo.infrastructure.gateways import geocoder
        from common.exceptions import ValidationFailed

        point = geocoder.parse_map_link(str(request.data.get("text") or ""))
        if point is None:
            raise ValidationFailed("No location found in this link.", details={"fields": [{"field": "text", "code": "NO_LOCATION"}]})
        return success_response(data=point)


class BoundingBoxCitiesView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo"], summary="List cities within a map viewport bounding box")
    def get(self, request):
        box = parse_bounding_box_params(request.query_params)

        results = BoundingBoxSelector().cities_within(box["ne_lat"], box["ne_lng"], box["sw_lat"], box["sw_lng"])
        return success_response(data=results)


# ============================================================
# Admin: hierarchy CRUD
# ============================================================


class AdminCountryListCreateView(APIView):
    """Combined GET (list) + POST (create) at one path -- see module docstring on why these must never be two separate views on the same URL."""

    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()] if self.request.method == "POST" else [GeoViewPermission()]

    @extend_schema(tags=["Geo Admin"], summary="List countries (staff)", responses={200: OpenApiResponse(description="Country list"), **_responses(401, 403)})
    def get(self, request):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        countries, total = composition.build_list_countries().execute(page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_country_payload(c) for c in countries], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Geo Admin"], summary="Create a country", request=CreateCountrySerializer, responses={201: OpenApiResponse(description="Country created"), **_responses(401, 403, 409, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateCountrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        country = composition.build_create_country(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_country_payload(country), status_code=201)


class AdminCountryDetailView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()]

    @extend_schema(tags=["Geo Admin"], summary="Update a country", request=UpdateCountrySerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, country_id: str):
        _attach_identity(request)
        serializer = UpdateCountrySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        country = composition.build_update_country(_actor_id(request)).execute(country_id=uuid.UUID(country_id), **serializer.validated_data)
        return success_response(data=_country_payload(country))

    @extend_schema(tags=["Geo Admin"], summary="Delete a country", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404)})
    def delete(self, request, country_id: str):
        _attach_identity(request)
        composition.build_delete_country(_actor_id(request)).execute(uuid.UUID(country_id))
        return success_response(data=None, status_code=204)


class AdminRegionListCreateView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()] if self.request.method == "POST" else [GeoViewPermission()]

    @extend_schema(tags=["Geo Admin"], summary="List regions for a country (staff)")
    def get(self, request, country_id: str):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        regions, total = composition.build_list_regions().execute(country_id=uuid.UUID(country_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_region_payload(r) for r in regions], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Geo Admin"], summary="Create a region", request=CreateRegionSerializer, responses={201: OpenApiResponse(description="Region created"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, country_id: str):
        _attach_identity(request)
        serializer = CreateRegionSerializer(data={**request.data, "country_id": country_id})
        serializer.is_valid(raise_exception=True)
        region = composition.build_create_region(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_region_payload(region), status_code=201)


class AdminRegionDetailView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()]

    @extend_schema(tags=["Geo Admin"], summary="Update a region", request=UpdateRegionSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, region_id: str):
        _attach_identity(request)
        serializer = UpdateRegionSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        region = composition.build_update_region(_actor_id(request)).execute(region_id=uuid.UUID(region_id), **serializer.validated_data)
        return success_response(data=_region_payload(region))

    @extend_schema(tags=["Geo Admin"], summary="Delete a region", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404)})
    def delete(self, request, region_id: str):
        _attach_identity(request)
        composition.build_delete_region(_actor_id(request)).execute(uuid.UUID(region_id))
        return success_response(data=None, status_code=204)


class AdminDistrictListCreateView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()] if self.request.method == "POST" else [GeoViewPermission()]

    @extend_schema(tags=["Geo Admin"], summary="List districts for a region (staff)")
    def get(self, request, region_id: str):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        districts, total = composition.build_list_districts().execute(region_id=uuid.UUID(region_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_district_payload(d) for d in districts], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Geo Admin"], summary="Create a district", request=CreateDistrictSerializer, responses={201: OpenApiResponse(description="District created"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, region_id: str):
        _attach_identity(request)
        serializer = CreateDistrictSerializer(data={**request.data, "region_id": region_id})
        serializer.is_valid(raise_exception=True)
        district = composition.build_create_district(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_district_payload(district), status_code=201)


class AdminDistrictDetailView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()]

    @extend_schema(tags=["Geo Admin"], summary="Update a district", request=UpdateDistrictSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, district_id: str):
        _attach_identity(request)
        serializer = UpdateDistrictSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        district = composition.build_update_district(_actor_id(request)).execute(district_id=uuid.UUID(district_id), **serializer.validated_data)
        return success_response(data=_district_payload(district))

    @extend_schema(tags=["Geo Admin"], summary="Delete a district", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404)})
    def delete(self, request, district_id: str):
        _attach_identity(request)
        composition.build_delete_district(_actor_id(request)).execute(uuid.UUID(district_id))
        return success_response(data=None, status_code=204)


class AdminCityListCreateView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()] if self.request.method == "POST" else [GeoViewPermission()]

    @extend_schema(tags=["Geo Admin"], summary="List cities (staff)")
    def get(self, request):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        region_id = parse_uuid_param(request.query_params.get("filter[region_id]"), "filter[region_id]")
        cities, total = composition.build_list_cities().execute(region_id=region_id, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_city_payload(c) for c in cities], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Geo Admin"], summary="Create a city", request=CreateCitySerializer, responses={201: OpenApiResponse(description="City created"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateCitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        city = composition.build_create_city(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_city_payload(city), status_code=201)


class AdminCityDetailView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()]

    @extend_schema(tags=["Geo Admin"], summary="Update a city", request=UpdateCitySerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, city_id: str):
        _attach_identity(request)
        serializer = UpdateCitySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        city = composition.build_update_city(_actor_id(request)).execute(city_id=uuid.UUID(city_id), **serializer.validated_data)
        return success_response(data=_city_payload(city))

    @extend_schema(tags=["Geo Admin"], summary="Delete a city", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404)})
    def delete(self, request, city_id: str):
        _attach_identity(request)
        composition.build_delete_city(_actor_id(request)).execute(uuid.UUID(city_id))
        return success_response(data=None, status_code=204)


class AdminNeighborhoodListCreateView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()] if self.request.method == "POST" else [GeoViewPermission()]

    @extend_schema(tags=["Geo Admin"], summary="List neighborhoods for a city (staff)")
    def get(self, request, city_id: str):
        _attach_identity(request)
        pagination = parse_pagination(request.query_params)
        neighborhoods, total = composition.build_list_neighborhoods().execute(city_id=uuid.UUID(city_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_neighborhood_payload(n) for n in neighborhoods], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Geo Admin"], summary="Create a neighborhood", request=CreateNeighborhoodSerializer, responses={201: OpenApiResponse(description="Neighborhood created"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, city_id: str):
        _attach_identity(request)
        serializer = CreateNeighborhoodSerializer(data={**request.data, "city_id": city_id})
        serializer.is_valid(raise_exception=True)
        neighborhood = composition.build_create_neighborhood(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_neighborhood_payload(neighborhood), status_code=201)


class AdminNeighborhoodDetailView(APIView):
    throttle_classes = [GeoAdminThrottle]

    def get_permissions(self):
        return [GeoManagePermission()]

    @extend_schema(tags=["Geo Admin"], summary="Update a neighborhood", request=UpdateNeighborhoodSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, neighborhood_id: str):
        _attach_identity(request)
        serializer = UpdateNeighborhoodSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        neighborhood = composition.build_update_neighborhood(_actor_id(request)).execute(neighborhood_id=uuid.UUID(neighborhood_id), **serializer.validated_data)
        return success_response(data=_neighborhood_payload(neighborhood))

    @extend_schema(tags=["Geo Admin"], summary="Delete a neighborhood", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404)})
    def delete(self, request, neighborhood_id: str):
        _attach_identity(request)
        composition.build_delete_neighborhood(_actor_id(request)).execute(uuid.UUID(neighborhood_id))
        return success_response(data=None, status_code=204)


# ============================================================
# Addresses (self-service + staff override)
# ============================================================


class AddressListCreateView(APIView):
    throttle_classes = [AddressWriteThrottle]

    def get_permissions(self):
        return [AddressOwnerPermission()]

    @extend_schema(tags=["Geo Addresses"], summary="List the current user's addresses")
    def get(self, request):
        _attach_identity(request)
        addresses = composition.build_address_repository().list_for_owner("user", request.identity.id)
        return success_response(data=[_address_payload(a) for a in addresses])

    @extend_schema(tags=["Geo Addresses"], summary="Create an address for the current user", request=CreateAddressSerializer, responses={201: OpenApiResponse(description="Address created"), **_responses(401, 404, 409, 422, 429)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateAddressSerializer(data={**request.data, "owner_type": "user", "owner_id": str(request.identity.id)})
        serializer.is_valid(raise_exception=True)
        address = composition.build_create_address(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_address_payload(address), status_code=201)


class AddressDetailView(APIView):
    throttle_classes = [AddressWriteThrottle]

    def get_permissions(self):
        return [AddressOwnerPermission()]

    @extend_schema(tags=["Geo Addresses"], summary="Update an address", request=UpdateAddressSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, address_id: str):
        _attach_identity(request)
        existing = composition.build_address_repository().get_by_id(uuid.UUID(address_id))
        if existing is None:
            raise ResourceNotFound("Address not found.")
        self.check_object_permissions(request, existing)
        serializer = UpdateAddressSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        address = composition.build_update_address(_actor_id(request)).execute(address_id=uuid.UUID(address_id), **serializer.validated_data)
        return success_response(data=_address_payload(address))

    @extend_schema(tags=["Geo Addresses"], summary="Delete an address", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404)})
    def delete(self, request, address_id: str):
        _attach_identity(request)
        existing = composition.build_address_repository().get_by_id(uuid.UUID(address_id))
        if existing is None:
            raise ResourceNotFound("Address not found.")
        self.check_object_permissions(request, existing)
        composition.build_delete_address(_actor_id(request)).execute(uuid.UUID(address_id))
        return success_response(data=None, status_code=204)


class AddressAssignCoordinatesView(APIView):
    throttle_classes = [AddressWriteThrottle]

    def get_permissions(self):
        return [AddressOwnerPermission()]

    @extend_schema(tags=["Geo Addresses"], summary="Assign coordinates to an address", request=AssignCoordinatesSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, address_id: str):
        _attach_identity(request)
        existing = composition.build_address_repository().get_by_id(uuid.UUID(address_id))
        if existing is None:
            raise ResourceNotFound("Address not found.")
        self.check_object_permissions(request, existing)
        serializer = AssignCoordinatesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = composition.build_assign_coordinates(_actor_id(request)).execute(address_id=uuid.UUID(address_id), **serializer.validated_data)
        return success_response(data=_address_payload(address))


class ValidateAddressView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo Addresses"], summary="Validate address fields without saving", request=ValidateAddressSerializer, responses={200: OpenApiResponse(description="Valid"), **_responses(404, 422)})
    def post(self, request):
        serializer = ValidateAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        composition.build_validate_address().execute(**serializer.validated_data)
        return success_response(data={"valid": True})


class NormalizeAddressView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Geo Addresses"], summary="Preview the formatted address without saving", request=NormalizeAddressSerializer, responses={200: OpenApiResponse(description="Formatted address"), **_responses(404, 422)})
    def post(self, request):
        serializer = NormalizeAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        formatted, signature = composition.build_normalize_address().execute(**serializer.validated_data)
        return success_response(data={"single_line": formatted.single_line, "lines": list(formatted.lines), "signature": signature})
