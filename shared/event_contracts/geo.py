"""
Geo & Location's Domain Event Catalogue registration.

Imported once from `apps/geo/apps.py::GeoConfig.ready()` -- importing
this module IS the act of registering these event contracts against
`core.events.registry.registry`, matching
`shared/event_contracts/identity.py` and
`shared/event_contracts/products.py`'s exact pattern.
"""
from __future__ import annotations

from apps.geo.domain.events import (
    AddressCreated,
    AddressDeleted,
    AddressUpdated,
    CityCreated,
    CountryCreated,
    DistrictCreated,
    GeoEntityDeleted,
    GeoEntityUpdated,
    NeighborhoodCreated,
    RegionCreated,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("CountryCreated", CountryCreated),
    ("RegionCreated", RegionCreated),
    ("DistrictCreated", DistrictCreated),
    ("CityCreated", CityCreated),
    ("NeighborhoodCreated", NeighborhoodCreated),
    ("AddressCreated", AddressCreated),
    ("AddressUpdated", AddressUpdated),
    ("AddressDeleted", AddressDeleted),
    ("GeoEntityUpdated", GeoEntityUpdated),
    ("GeoEntityDeleted", GeoEntityDeleted),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="geo", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
