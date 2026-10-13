"""
Geo & Location domain exceptions.

All subclass common/exceptions/exceptions.py's DomainException
hierarchy, matching the pattern established across every prior module.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class DuplicateCountryCode(ConflictError):
    code = "COUNTRY_CODE_ALREADY_EXISTS"


class DuplicateRegionCode(ConflictError):
    code = "REGION_CODE_ALREADY_EXISTS"


class DuplicateDistrictCode(ConflictError):
    code = "DISTRICT_CODE_ALREADY_EXISTS"


class DuplicateCityCode(ConflictError):
    code = "CITY_CODE_ALREADY_EXISTS"


class DuplicateNeighborhoodCode(ConflictError):
    code = "NEIGHBORHOOD_CODE_ALREADY_EXISTS"


class DuplicatePostalCode(ConflictError):
    code = "POSTAL_CODE_ALREADY_EXISTS"


class DuplicateSlug(ConflictError):
    code = "SLUG_COLLISION"


class InvalidHierarchy(ValidationFailed):
    """Country->Region->District->City->Neighborhood parent-reference violation (e.g. a Region assigned to a nonexistent Country)."""

    code = "INVALID_HIERARCHY"


class InvalidCoordinate(ValidationFailed):
    code = "INVALID_COORDINATE"


class InvalidTimezone(ValidationFailed):
    code = "INVALID_TIMEZONE"


class InvalidAddress(ValidationFailed):
    code = "INVALID_ADDRESS"


class DuplicateAddressDetected(ConflictError):
    """Raised by NormalizeAddress/CreateAddress when an address with an identical normalized signature already exists for the same owner scope."""

    code = "DUPLICATE_ADDRESS_DETECTED"


class GeoEntityNotFound(ValidationFailed):
    code = "GEO_ENTITY_NOT_FOUND"


class GeoEntityInactive(BusinessRuleViolation):
    """Raised when an operation requires an ACTIVE parent geo entity (e.g. creating a City under an INACTIVE Region)."""

    code = "GEO_ENTITY_INACTIVE"
