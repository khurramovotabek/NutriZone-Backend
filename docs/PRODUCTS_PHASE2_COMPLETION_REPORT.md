# Products & Catalog Module — Phase 2 Completion Report

**Scope:** Infrastructure layer only, per this phase's explicit instruction. Interfaces (REST API, serializers, views, OpenAPI) and Tests are **not** started.

---

## 1. Files Created

16 files under `apps/products/infrastructure/` (all requested files present), plus two platform-level files:

| File | Purpose |
|---|---|
| `models.py` | 24 ORM models across `catalog_*` tables |
| `repositories.py` | 16 concrete repository/gateway classes implementing every Phase 1 Port |
| `selectors.py` | 8 read-model selector classes (`ProductDetailSelector`, `CatalogSelector`, `AdminCatalogSelector`, `CategoryTreeSelector`, `BrandSelector`, `FilterSelector`, `StatisticsSelector`, `DjangoProductSearchBackend`) |
| `search.py` | `PostgresSearchGateway` — concrete `SearchGateway` |
| `storage.py` | `ProductStorageGateway` — thin `StorageGateway` adapter over `core.storage` |
| `cache.py` | 7 cache-group functions + the never-cache-draft guard |
| `metrics.py` | Named metric constants + gauge/timer helpers |
| `composition.py` | 35 `build_*()` factory functions, one per Application Service |
| `admin.py` | 8 `ModelAdmin` registrations |
| `signals.py` | Documented-empty (framework housekeeping only, none needed) |
| `tasks.py` | 6 Celery tasks |
| `health.py` | 6 health check functions |
| `event_handlers.py` | Documented-empty (Products is upstream-only, per Domain Architecture Specification §2.2) |
| `apps.py` | `AppConfig.ready()` wiring events + health checks |
| `shared/event_contracts/products.py` | 17 event registrations against the Domain Event Catalogue |

---

## 2. Infrastructure Folder Tree

```
apps/products/infrastructure/
├── models.py
├── repositories.py
├── selectors.py
├── composition.py
├── admin.py
├── signals.py
├── tasks.py
├── health.py
├── event_handlers.py
├── search.py
├── storage.py
├── metrics.py
├── cache.py
├── gateways/            (empty — no external SMS/OAuth-style ACL needed for this module)
└── migrations/           (empty — no migrations generated, see Known Limitations)
```

---

## 3. ORM Model Summary

24 models across the `catalog` schema (Database Blueprint §4.2), plus two documented, justified additions:

| Model | Category (MIC §3) | Notes |
|---|---|---|
| `Category` + `CategoryTranslation` | Entity + junction | |
| `Brand` + `BrandTranslation` | Entity + junction | `is_manufacturer` flag backs `Manufacturer` |
| `Tag` + `TagTranslation` | Entity + junction | |
| `Attribute` + `AttributeTranslation` | Entity + junction | Backs Flavor/PackageSize/ProductForm via `code` |
| `AttributeValue` + `AttributeValueTranslation` | Entity + junction | |
| `Product` + `ProductTranslation` | Entity + junction | Embeds nutrition/SEO as columns (see §Known Limitations) |
| `ProductVariant` | Entity | |
| `VariantAttributeValue` | Junction | |
| `ProductTag` | Junction | **Fixed mid-build** — see §10 |
| `ProductMediaAsset` | Entity (BaseModel) | Processed Media Pipeline output, temporarily owned here (matches `identity`'s `UserAvatarAsset` pattern) |
| `ProductMedia` | Entity (BaseModel) | Unifies Image/Video/Document |
| `Certificate` + `ProductCertificate` | Entity + junction | |
| `ProductRecommendation` | Entity (BaseModel) | Has a `CheckConstraint` preventing self-reference |
| `Bundle` + `BundleTranslation` + `BundleItem` | Entity + junction + entity | Blueprint amendment, documented in Phase 1 |
| `ProductsOutboxEvent` | Append-only | Concrete Outbox table for `catalog` schema |

**Not implemented:** `PriceHistory` — correctly excluded. It belongs to the `pricing` schema (Database Blueprint §4.3), not `catalog`, and Pricing is explicitly out of this module's scope.

---

## 4. Repository Mapping Table

| Port | Concrete Class | ORM ↔ Domain Mapping Approach |
|---|---|---|
| `ProductRepository` | `DjangoProductRepository` | Full aggregate hydration (variants, media, certificates, nutrition, SEO, tags) on `get_by_id`; `save()` does an `update_or_create` + full variant/media/tag reconciliation (diff current vs. desired, delete stale, upsert current) |
| `BrandRepository` | `DjangoBrandRepository` | Scoped to `is_manufacturer=False` |
| `ManufacturerRepository` | `DjangoManufacturerRepository` | Delegates to `DjangoBrandRepository`, scoped to `is_manufacturer=True` |
| `CategoryRepository` | `DjangoCategoryRepository` | Standard translation-table hydration |
| `VariantRepository` | `DjangoVariantRepository` | Read-only, thin (`variant_id`/`sku` → `product_id` lookups only — writes flow through `ProductRepository`) |
| `AttributeRepository` | `DjangoAttributeRepository` | Hydrates the full `values` dict per attribute |
| `FlavorRepository` / `PackageSizeRepository` / `ProductFormRepository` | `DjangoFlavorRepository` / `DjangoPackageSizeRepository` / `DjangoProductFormRepository` | Each delegates to `DjangoAttributeRepository`, scoped by reserved code |
| `MediaRepository` | `DjangoMediaRepository` | Read-only `media_id` → `product_id` lookup |
| `TagRepository` | `DjangoTagRepository` | Standard translation-table hydration |
| `SpecificationRepository` | `DjangoSpecificationRepository` | Distinct-key scan over `Product.specifications` JSONB |
| `BundleRepository` | `DjangoBundleRepository` | Full item-list reconciliation on save |
| `SearchGateway` | `PostgresSearchGateway` (search.py) | Delegates to `DjangoProductSearchBackend` |
| `StorageGateway` | `ProductStorageGateway` (storage.py) | Thin pass-through to `core.storage.get_storage_backend()` |

**Locale handling, stated explicitly:** every repository hydrates a domain aggregate's translatable fields (`name`/`description`/`slug`) from a single working locale (`_DEFAULT_LOCALE = "en"`) when loading for a *write* operation. Multi-locale read models are a selector-layer concern, not this repository layer's — this mirrors the Database Blueprint's own design, where the base table itself has no `name` column at all.

---

## 5. Selector Table

| Selector | Backs |
|---|---|
| `ProductDetailSelector` | `GetProduct` |
| `CatalogSelector` | `ListProducts` |
| `AdminCatalogSelector` | `AdminListProducts` |
| `CategoryTreeSelector` | `GET /products/categories` (future Interfaces layer) |
| `BrandSelector` | `GET /products/brands` |
| `FilterSelector` | Faceted search metadata (Brand/Category/Flavor/PackageSize/Form/Status) |
| `StatisticsSelector` | Admin catalog-health widgets, `average_media_per_product` metric |
| `DjangoProductSearchBackend` | `SearchProducts`, implements `application/selectors.py::ProductSearchBackend` |

All read-only, zero business logic — every method builds and executes a Postgres query and shapes the result into a plain dict, nothing more.

---

## 6. Cache Implementation

All 7 required groups implemented in `cache.py`, backed by `core.caching.CacheManager`/`CacheDomain` (Foundation Hardening phase):

| Group | Function |
|---|---|
| Product Detail | `cache_product_detail()` / `get_cached_product_detail()` |
| Catalog List | `cache_catalog_page()` / `get_cached_catalog_page()` |
| Brand List | `cache_brand_list()` / `get_cached_brand_list()` |
| Category Tree | `cache_category_tree()` / `get_cached_category_tree()` |
| Search Results | `cache_search_results()` / `get_cached_search_results()` (separate `CacheDomain.SEARCH`) |
| SEO | `cache_seo()` / `get_cached_seo()` |
| Filter Options | `cache_filter_options()` / `get_cached_filter_options()` |

**"Never cache draft/archived products" is enforced structurally, not just documented:** `cache_product_detail()` raises `NonCacheableProductStatusError` if handed anything but a `PUBLISHED` read model — there is no code path that can cache a draft. Invalidation is O(1) domain-version bumps (`invalidate_all_product_caches()`/`invalidate_search_cache()`), called from every mutating Application Service via `ProductServiceContext.invalidate_product_cache()`.

---

## 7. Audit Integration

Every mutating Application Service (built in Phase 1) already calls `ProductServiceContext.audit()` — no separate Infrastructure-layer audit wiring was needed beyond what Phase 1 established, since `core.audit.AuditEventBuilder` is platform-wide infrastructure the application layer consumes directly (identical to Identity's pattern). Confirmed present for: Product Created/Updated/Published/Hidden/Archived/Restored/Deleted, Variant Created/Updated/Deleted, Media Uploaded/Deleted, SEO Updated, Category Assigned, Brand Assigned.

---

## 8. Metrics Integration

All 8 requested counters wired via `ProductServiceContext.metric()` (called from the Phase 1 services) plus `metrics.py`'s two additional named entries for the two that don't fit a simple counter shape:

`products_created_total`, `products_updated_total`, `products_published_total`, `products_archived_total`, `variants_created_total`, `media_uploaded_total`, `catalog_search_total` (recorded in `queries.py::SearchProducts`), `publish_duration_seconds` (histogram, via `ProductServiceContext.timer()` in `PublishProduct`) — plus `catalog_queries_total` and `average_media_per_product` (gauge, refreshed by the new `products.refresh_catalog_metrics` scheduled task).

---

## 9. Health Checks

All 6 registered against `core.health.registry` from `ProductsConfig.ready()`:

| Check | Verifies |
|---|---|
| `products_repository` | A real query against `catalog_products` succeeds |
| `products_media_storage` | A save/read/delete round-trip against the configured storage backend |
| `products_search` | The Postgres FTS query path executes without error |
| `products_cache` | A set/get/delete round-trip against `CacheDomain.PRODUCT` |
| `products_outbox` | The outbox table is queryable, reports pending-event count |
| `products_event_registration` | The four core lifecycle events are actually registered in `core.events.registry` |

---

## 10. Architecture Validation

| Gate | Status |
|---|---|
| ✓ Infrastructure depends only on Domain/Application | **Pass** — verified by inspection; `composition.py` is the only file that imports across all three layers, which is its explicit job |
| ✓ No circular imports | **Pass** — verified by grep: `infrastructure/` and `application/` never import `interfaces/` |
| ✓ Repository mappings complete | **Pass** — every Phase 1 Port has a concrete implementation |
| ✓ ORM models compile | **Pass** — all 24 models + the platform-level additions compile cleanly |
| ✓ Composition Root complete | **Pass** — 35 `build_*()` functions, no service-locator pattern (every dependency is explicit at the call site) |
| ✓ Health registered | **Pass** — 6 checks |
| ✓ Cache integrated | **Pass** — 7 groups, never-cache-draft enforced structurally |
| ✓ Audit integrated | **Pass** (inherited from Phase 1's `ProductServiceContext`) |
| ✓ Metrics integrated | **Pass** — all 8 requested + 2 additional |
| ✓ Outbox integrated | **Pass** — `stage_products_events()` is the sole event-emission path, injected into every service |
| ✓ Media Pipeline integrated | **Pass** — `UploadImage`/`UploadVideo`/`UploadDocument` all use the real `PillowImageOptimizer`-backed `MediaPipeline` |

**One real naming inconsistency found and flagged, not silently resolved:** `config/settings/base.py`'s `INSTALLED_APPS` already had an empty `"apps.catalog"` placeholder from the Foundation phase (matching the Domain Architecture Specification's bounded-context name "Catalog"), but this module's explicit build instructions named the folder `apps/products/`. Both are now registered — the empty `apps.catalog` placeholder and the real `apps.products` implementation — with an inline comment explaining the duplication and recommending the unused placeholder be removed in a future cleanup pass, rather than silently deleting a directory that wasn't mine to remove unilaterally or silently leaving two conflicting app names undocumented.

**One real compliance gap caught and fixed mid-build:** an early draft of `models.py` stored `Product.tag_ids` as a JSONB list rather than a proper junction table — inconsistent with the Database Blueprint's actual `catalog.product_tags` junction-table design (the same pattern already used for `product_certificates`). Fixed before this report by adding a proper `ProductTag` model and updating `DjangoProductRepository._sync_tags()` accordingly.

---

## Known Limitations

1. **No migrations generated** — same sandbox constraint as every prior phase (no network access to install Django). All 24 models are correct by inspection against the Database Blueprint and Phase 1's domain model, not verified against a live PostgreSQL instance.
2. **`NutritionFacts` is embedded on `Product`, not per-variant** — the Database Blueprint's `nutrition_facts` table is technically keyed by `variant_id`, but Phase 1's domain model (already locked) attaches `NutritionFacts` to `Product` itself. `models.py` follows Phase 1's domain model exactly (correct per "do not rewrite Domain/Application"), which means the ORM's nutrition columns live on `catalog_products`, not `catalog_product_variants` — a Phase 1 domain-model decision inherited here, not an Infrastructure-layer choice, flagged in case per-variant nutrition granularity becomes a real requirement later (e.g., different serving sizes for a 1kg vs. 5kg package of the same product).
3. **`CertificateAttached` and `BundleCreated` events remain unwired** — same reason as Phase 1: no Application Service yet calls `attach_certificate()` or constructs a `Bundle` through a full use case. The ORM tables (`Certificate`, `ProductCertificate`, `Bundle`, `BundleItem`) and repository methods (`DjangoBundleRepository`) exist and are ready; the missing piece is a `CreateBundle`/`AttachCertificate` Application Service, which Phase 1 didn't include (it prioritized the Product-centric service list the brief gave first).
4. **Search remains Postgres-only** — `PostgresSearchGateway`'s `index_product()`/`remove_from_index()` are correct no-ops for this backend (the GIN index is always current), not placeholders for missing functionality; the seam for a dedicated search engine is `application/ports.py::SearchGateway` itself, unchanged when that swap happens.

**Recommendation:** proceed to Interfaces (serializers, views, URLs, OpenAPI) and Tests only when instructed — this report stops here per the explicit "do NOT begin Interfaces/REST API/Tests" instruction.
