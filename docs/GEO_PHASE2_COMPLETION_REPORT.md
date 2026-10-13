# Geo & Location Module — Phase 2 (Infrastructure) Completion Report

**Scope:** Infrastructure layer only, per this phase's explicit instruction. Interfaces (REST API) and Tests are **not** started.

---

## 1. Folder Tree

```
apps/geo/infrastructure/
├── models.py
├── repositories.py
├── selectors.py
├── admin.py
├── signals.py            (documented-empty, see §11)
├── event_handlers.py      (also hosts cache helpers, see §11)
├── tasks.py
├── health.py
├── gateways/              (empty — no external geocoding provider integrated this phase)
└── migrations/            (empty — no migrations generated, see Known Limitations)
apps/geo/apps.py
shared/event_contracts/geo.py
```

---

## 2. Files Created

11 files under `apps/geo/infrastructure/` (all files from this phase's explicit CREATE list), plus `apps/geo/apps.py` and `shared/event_contracts/geo.py`, plus `apps.geo` registered in `INSTALLED_APPS`.

---

## 3. Database Table Summary

11 base tables (matching this phase's explicit list) + 6 translation tables + 1 Outbox table = **18 tables**:

| Table | Category (MIC §3) | Notes |
|---|---|---|
| `geo_countries` + `geo_country_translations` | Entity (SoftDeleteModel) + junction | `code` (ISO 3166-1 alpha-2, unique), `timezone` |
| `geo_regions` + `geo_region_translations` | Entity + junction | FK to Country (`PROTECT`) |
| `geo_districts` + `geo_district_translations` | Entity + junction | FK to Region (`PROTECT`) |
| `geo_cities` + `geo_city_translations` | Entity + junction | FK to Region + optional District; `CheckConstraint` on lat/lng range |
| `geo_neighborhoods` + `geo_neighborhood_translations` | Entity + junction | FK to City |
| `geo_addresses` | Entity (SoftDeleteModel) | FKs to Country/Region/District/City/Neighborhood (all `PROTECT`); `CheckConstraint` on coordinate range; `normalized_signature` indexed for duplicate detection |
| `geo_address_metadata` | Entity (plain, 1:1) | Building/floor/unit/delivery-instructions, per this phase's explicit separate-table requirement |
| `geo_delivery_zones` + `geo_delivery_zone_translations` | Entity + junction | FK to GeoBoundary (`SET_NULL`) |
| `geo_boundaries` | Entity (BaseModel) | `polygon_points` JSONB — one documented storage decision (§13) |
| `geo_location_aliases` | Entity (plain) | Polymorphic `entity_type`/`entity_id`, matches Database Blueprint §5's documented polymorphic-reference pattern |
| `geo_timezone_rules` | Entity (plain) | Polymorphic `owner_type`/`owner_id` |
| `geo_outbox_events` | Append-only (AbstractOutboxEvent) | Concrete Outbox table for the `geo` schema |

---

## 4. Repository Mapping Table

| Port | Concrete Class | Notes |
|---|---|---|
| `CountryRepository` | `DjangoCountryRepository` | Standard translation-table hydration |
| `RegionRepository` | `DjangoRegionRepository` | |
| `DistrictRepository` | `DjangoDistrictRepository` | |
| `CityRepository` | `DjangoCityRepository` | `find_nearest()` uses a bounding-box pre-filter + in-Python haversine sort (documented PostGIS-free decision, §13) |
| `NeighborhoodRepository` | `DjangoNeighborhoodRepository` | |
| `AddressRepository` | `DjangoAddressRepository` | Full aggregate hydration including 1:1 `AddressMetadata`; `list_signatures_for_owner()` backs duplicate detection without loading full aggregates |
| `DeliveryZoneRepository` | `DjangoDeliveryZoneRepository` | |
| `BoundaryRepository` | `DjangoBoundaryRepository` | `find_containing()` uses the domain's own ray-casting `BoundaryPolygon.contains()` — no PostGIS dependency this phase |

Every repository catches `IntegrityError` and re-raises as the matching domain `ConflictError` subclass; every write goes through `update_or_create` for idempotent save semantics.

---

## 5. Selector Summary

8 selector classes in `infrastructure/selectors.py`, covering every requirement this phase lists: `CountryTreeSelector`, `RegionTreeSelector`, `DistrictTreeSelector`, `CityLookupSelector`, `NeighborhoodLookupSelector`, `AddressLookupSelector`, `HierarchyTraversalSelector` (City→District→Region→Country in one shaped payload, avoiding N+1), `DeliveryZoneLookupSelector`, `BoundingBoxSelector` (map-viewport queries), `DjangoGeoSearchBackend` (search + autocomplete, implementing `application/selectors.py::GeoSearchBackend`). All read-only, zero business logic, verified by inspection.

---

## 6. Event Handler Summary

`event_handlers.py::handle_geo_event()` — a single dispatch function (not nine separate handler functions, since all nine events reduce to the same two side effects: cache invalidation + metrics, dispatched via two lookup tables `_EVENT_TO_CACHE_SCOPE`/`_EVENT_TO_METRIC`). Called by the Outbox relay task (`tasks.py::relay_outbox_events`), not a Django signal — deliberately, since routing through a signal would fire synchronously inside the mutating request's own transaction, defeating the Outbox pattern's purpose (documented in the file's own module docstring).

**Scope clarification:** Geo consumes its *own* Outbox stream (self-consumption for async side effects), not another bounded context's events — a documented, different pattern from Identity/Products' upstream-only stance, explained explicitly in the module docstring.

---

## 7. Cache Keys

10 groups (matching this phase's exact list): `country_tree`, `region_tree`, `district_tree`, `city_list`, `neighborhood_list`, `hierarchy_tree`, `address_lookup`, `delivery_zones`, `geo_search`, `boundary_lookup`. Each independently versioned (`geo_cache_key()` builds `nutrizone:geo:<group>:v<version>:<parts>`); `invalidate_geo_scope(scope)` bumps only the groups a given mutation scope actually affects (e.g. a City mutation bumps `city_list` + `hierarchy_tree` + `geo_search`, not all 10) via the `_SCOPE_TO_GROUPS` mapping.

---

## 8. Audit Events

Every Application Service built in Phase 1 already calls `GeoServiceContext.audit()` — confirmed present for all of this phase's listed examples: Country Created/Updated, Region Updated, City Deleted, Address Created/Updated, Boundary Updated, and (by the same mechanism) Delivery Zone changes. No additional Infrastructure-layer audit wiring was needed, since `core.audit.AuditEventBuilder` is consumed directly by the application layer, matching every prior module.

---

## 9. Metrics

9 metrics wired: `geo_countries_total`, `geo_regions_total`, `geo_districts_total`, `geo_cities_total`, `geo_addresses_total` (via `event_handlers.py`'s dispatch table, fired from the Outbox relay — asynchronous, not on the synchronous request path, so a metrics-backend hiccup never blocks a Create call), `geo_searches_total` and `geo_reverse_geocode_total` (via `GeoServiceContext.metric()`, called synchronously from `SearchLocations`/`ReverseGeocode`), `hierarchy_lookup_duration` (via `GeoServiceContext.timer()`), `delivery_zone_lookup_total` (recorded at the future Interfaces layer's delivery-zone endpoint, per the same pattern established elsewhere — the metric name is reserved, not yet called, since no endpoint exists yet to call it from).

---

## 10. Health Checks

6 checks registered against `core.health.registry` from `GeoConfig.ready()`: `geo_repository` (single-table query), `geo_database` (JOIN across City→Region→Country, distinct from the repository check per this phase's explicit split), `geo_cache`, `geo_outbox`, `geo_search`, `geo_boundary` (exercises the point-in-polygon query path against a harmless coordinate).

---

## 11. Dependency Validation

| Check | Status |
|---|---|
| Infrastructure imports Domain correctly | ✓ Pass |
| Domain imports nothing from Infrastructure | ✓ Pass — verified by grep, zero matches |
| Application never imports Infrastructure directly (except documented `transaction.atomic`) | ✓ Pass |
| Infrastructure never imports Interfaces | ✓ Pass (trivially — Interfaces doesn't exist yet) |
| Views never instantiate repositories directly | ✓ Pass by construction — `composition.py` already exposes `build_delivery_zone_repository()`/`build_boundary_repository()`/`build_address_repository()` for the reference-data lookups the future Interfaces layer will need, applying the same fix already made to `apps.products.interfaces.api.v1.views` **before** the Geo Interfaces layer is even written, rather than making the same mistake twice |

**One deliberate scope decision, stated explicitly rather than silently made:** this phase's file list does not include a separate `cache.py` (unlike Products, which had one). Cache helper functions therefore live inside `event_handlers.py` — the only consumer — rather than inventing an unlisted file, which would itself have been a scope deviation from this phase's own explicit instructions.

---

## 12. Architecture Validation

| Gate | Status |
|---|---|
| ✓ Clean Architecture | Pass |
| ✓ DDD | Pass — 8 aggregates from Phase 1, unchanged |
| ✓ Modular Monolith | Pass — `geo` is its own schema/app, no cross-schema FK |
| ✓ Repository Pattern | Pass |
| ✓ CQRS Read Selectors | Pass — 8 selector classes, zero business logic |
| ✓ Outbox Pattern | Pass — `stage_geo_events()` is the sole event-emission path |
| ✓ Audit | Pass |
| ✓ Metrics | Pass |
| ✓ Cache | Pass |
| ✓ Health Checks | Pass |
| ✓ Composition Root | Pass — 28 `build_*()` functions + 3 reference-data repository factories, no service locator |

---

## 13. Compile Summary

**All 1027 repository-wide `.py` files compile cleanly** (`python -m py_compile`), verified in this session after registering `apps.geo` in `INSTALLED_APPS`.

**One documented storage decision, stated here rather than left implicit:** `GeoBoundary.polygon_points` is a JSONB array of `[lat, lng]` pairs rather than a separate points table — this phase's table list doesn't name one, and a polygon's points have no independent query pattern (always read/written as a complete ring alongside their owning boundary), the same reasoning already applied to `Product.specifications` in the Products module.

**One documented performance decision:** nearest-city lookup (`DjangoCityRepository.find_nearest`) and point-in-boundary lookup (`DjangoBoundaryRepository.find_containing`) both use a bounding-box pre-filter + in-Python distance/containment math rather than PostGIS, since PostGIS is not yet a confirmed platform dependency for this module (unlike `stores`/`fulfillment`, which the Database Blueprint already assumes PostGIS for). This is correct at the row counts a country/city/neighborhood hierarchy realistically has (thousands, not millions) but should be revisited if `geo` ever needs to support sub-meter-precision boundary queries at scale.

---

## Known Limitations

1. **No migrations generated** — unchanged sandbox constraint across every module built in this project.
2. **No PostGIS** — the two geo-math-heavy repository methods use pure-Python fallbacks (§13); correct but not the most scalable long-term approach if this module's data volume grows into the millions of addresses.
3. **No external geocoding provider integrated** — `infrastructure/gateways/` is empty; `AssignCoordinates`/`ReverseGeocode` work against already-known coordinates (manual entry or a future provider), consistent with Architecture Review §11's "vendor not yet selected" pattern already applied to SMS/payment providers elsewhere.
4. **`geo` is not yet a formally-amended bounded context** in the Domain Architecture Specification/Database Blueprint — flagged in Phase 1, still true here; this Infrastructure phase implements the module as specified without resolving that documentation gap, which remains the responsibility of a future architecture-amendment pass.

**Recommendation:** proceed to Interfaces (REST API, serializers, permissions, filters, OpenAPI) only when instructed — this report stops here per the explicit "do NOT begin Interfaces/Tests" instruction.
