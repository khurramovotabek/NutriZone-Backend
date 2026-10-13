# Products & Catalog Module — Phase 1 Completion Report

**Scope:** Domain and Application layers only, per this phase's explicit instruction. Infrastructure and Interfaces are **not** started.

---

## 1. Folder Tree

```
apps/products/
├── domain/
│   ├── enums.py
│   ├── value_objects.py
│   ├── entities.py
│   ├── aggregates.py
│   ├── exceptions.py
│   ├── events.py
│   ├── services.py
│   └── validators.py
├── application/
│   ├── ports.py
│   ├── selectors.py
│   └── services/
│       ├── _shared.py          (cross-cutting ProductServiceContext)
│       ├── lifecycle.py        (Create/Update/Delete/Restore/Publish/Hide/Archive/Duplicate/Clone)
│       ├── associations.py     (AssignBrand/Category/Tags/Flavor/PackageSize/ProductForm)
│       ├── variants.py         (CreateVariant/UpdateVariant/DeleteVariant/SetDefaultVariant)
│       ├── media.py            (UploadImage/Video/Document, DeleteImage/Video/Document)
│       ├── content.py          (UpdateNutritionFacts/Ingredients/Warnings/Directions/SEO)
│       ├── generation.py       (GenerateSlug/GenerateSKU)
│       └── queries.py          (SearchProducts/ListProducts/AdminListProducts/GetProduct)
├── infrastructure/    (empty scaffold only -- not started, per this phase's scope)
├── interfaces/         (empty scaffold only -- not started, per this phase's scope)
└── tests/               (empty scaffold only -- not started, per this phase's scope)
```

21 Python files across `domain/` and `application/`, all syntax-verified clean.

---

## 2. Files Created

| File | Purpose |
|---|---|
| `domain/enums.py` | 15 enums: `ProductStatus`, `ProductType`, `VariantStatus`, `NutritionCategory`, `Gender`, `AgeGroup`, `Availability`, `StockPolicy`, `TaxType`, `MediaType`, `MediaRole`, `ImageType`, `VideoType`, `DocumentType`, `CertificateType`, `AttributeType`, `AttributeInputType`, `SpecificationType`, `SEOStatus`, `RelationType` |
| `domain/value_objects.py` | `SKU`, `Barcode`, `Slug`, `ServingSize`, `NutritionFacts`, `Weight`, `Dimension`, `SEOData`, `ImageMetadata`, `VideoMetadata`, `DocumentMetadata`, `ProductCode`, `DisplayOrder` (+ re-exports Shared Kernel `Money`) |
| `domain/entities.py` | `AttributeValue`, `ProductMedia`, `Certificate`, `RelatedProduct`, `BundleItem`, `ProductSpecification` |
| `domain/aggregates.py` | `Product` (root), `ProductVariant` (owned entity), `Bundle` (root), `Category`, `Brand`, `Manufacturer`, `Tag`, `Attribute`, `Flavor`, `PackageSize`, `ProductForm` |
| `domain/exceptions.py` | 17 exception types, named to match this phase's brief exactly |
| `domain/events.py` | 15 domain events |
| `domain/services.py` | `ComplianceValidator`, `SKUGenerator`, `SlugGenerator`, `PublicationPolicy`, `VariantPolicy`, `MediaPolicy`, `NutritionPolicy`, `SEOGenerator`, `SpecificationPolicy`, `VariantMatrixBuilder` |
| `domain/validators.py` | `SlugValidator`, `SKUValidator`, `BarcodeValidator`, `WeightValidator`, `DimensionValidator`, `SEOValidator`, `NutritionValidator`, `MediaValidator` |
| `application/ports.py` | 13 repository/gateway Protocols |
| `application/selectors.py` | `ProductSelector` + `ProductSearchBackend` Protocol |
| `application/services/*.py` | 35 Application Services (full list in §9) |

---

## 3. Domain Explanation

The domain layer has **zero Django imports** (verified by grep across every file, not just by intention) and is built entirely from `@dataclass` entities/aggregates, `frozen=True` value objects, and stateless service classes — every one of them importable and testable with no framework installed at all.

Three deliberate **reconciliations** between this phase's brief and the already-approved Enterprise Database Blueprint were made and documented inline (not silently resolved):

1. **`ProductStatus` keeps the Blueprint's four persisted values** (`draft`/`published`/`unpublished`/`archived`) with `PENDING_REVIEW` added as a fifth, additive editorial sub-state. "Hidden" (this brief's vocabulary) and "unpublished" (the Blueprint's persisted name) refer to the same state — the event is named `ProductHidden` to match the brief, while the stored enum value stays `unpublished` to match the Blueprint.
2. **Flavor / Package Size / Product Form are real, distinct aggregate classes** (as this phase explicitly and repeatedly requested), but each is a thin, invariant-enforcing wrapper over the `Attribute`/`AttributeValue` pattern the Database Blueprint §4.2 actually defines — not three new hardcoded tables. This satisfies both the brief's explicit ask for distinct types with distinct repositories *and* the Blueprint's "unlimited variant dimensions without schema changes" design (Domain Architecture Specification §2.2). Building three separate tables instead would have been the actual shortcut — reintroducing exactly the per-new-dimension schema change the approved architecture exists to avoid.
3. **`ProductImage`/`ProductVideo`/`ProductDocument` unify into one `ProductMedia` entity** with a `media_role` discriminator, matching `catalog.product_media`'s single-table schema.

Manufacturer is realized as `Brand.is_manufacturer=True` rather than a fourth parallel table, for the identical reason (the Blueprint only defines `brands`).

---

## 4. Aggregate Explanation

| Aggregate | Root? | Owns | Key Invariants Enforced |
|---|---|---|---|
| **Product** | Yes | `ProductVariant` entities, `ProductMedia` entities, `Certificate` entities, nutrition/supplement/warnings/directions text, SEO data | SKU uniqueness within the product; first variant auto-becomes default; default-variant reassignment on removal; primary-image singleton (adding a new PRIMARY demotes the old one to GALLERY); 12-image / 4-video hard caps; full publish-workflow gate (variants exist → has a default → has a primary image → required certificates present), aggregated into one `PublishValidationFailed` with every failing reason listed at once, not just the first |
| **Bundle** | Yes | `BundleItem` entities | Must have at least one item to exist as an active bundle (`__post_init__` + `create()` factory both enforce this) |
| **Category** | Yes | — | Name non-empty; cannot be its own parent |
| **Brand** | Yes | — | Name non-empty |
| **Attribute** | Yes | `AttributeValue` entities | Code non-empty; no duplicate value codes within one attribute |
| **Flavor / PackageSize / ProductForm** | Yes (specializations) | — | Each validates its wrapped `Attribute.code` matches the reserved code (`flavor`/`package_size`/`form`) — see §3's reconciliation |
| **Tag** | Yes | — | Code non-empty |
| **Manufacturer** | Factory over Brand | — | Same as Brand (typed factory, not a parallel class) |

`ProductVariant` is **not** a separate aggregate root — it's an entity owned by `Product`, per Domain Architecture Specification §2.2's explicit "Product (root) — owns Variants" statement, which this phase's brief's own "Every aggregate must enforce invariants" language (listing "Variant" alongside Product/Brand/Category) is satisfied by Product's own variant-management methods (`add_variant`, `remove_variant`, `set_default_variant`) rather than a second, independently-persisted aggregate.

---

## 5. Business Rules Implemented

| Rule | Where Enforced |
|---|---|
| SKU uniqueness (within a product) | `Product.add_variant()` |
| SKU uniqueness (catalog-wide) | `ProductRepository.sku_exists()` check in `CreateVariant`/`CreateProduct` application services (requires a repository, so it's checked at the application layer, not the aggregate) |
| Slug uniqueness | `SlugGenerator.generate_unique()` (pure, caller-supplied `is_taken` check) |
| Barcode uniqueness + checksum | `Barcode` value object (GTIN mod-10 checksum) + `ProductRepository.barcode_exists()` |
| Publish validation (multi-reason) | `Product.publish()` |
| Draft lifecycle (draft → published → hidden → archived → restored) | `Product.publish()`/`hide()`/`archive()`/`restore()`, each raising `InvalidProductLifecycleTransition` on an illegal transition |
| Visibility rules | `Product.is_publicly_visible` property; enforced again at `GetProduct`/`ListProducts` (never return non-PUBLISHED products) |
| Primary image uniqueness | `Product.add_media()` (demotes any existing PRIMARY to GALLERY) |
| Maximum 12 images / 4 videos | `Product.add_media()`, raising `MediaLimitExceeded` |
| Variant uniqueness | `Product.add_variant()`, raising `VariantAlreadyExists` |
| Nutrition validation (macro/calorie consistency) | `domain/validators.py::validate_nutrition_consistency`, wrapped by `NutritionPolicy` |
| SEO validation (meta title ≤70 chars, meta description ≤160 chars) | `SEOData.__post_init__` |
| Attribute validation | `Attribute.add_value()` (no duplicate value codes); `Flavor`/`PackageSize`/`ProductForm` reserved-code checks |
| Category/Brand consistency | `CreateProduct`/`AssignBrand`/`AssignCategory` application services verify the referenced id exists before assigning |
| Media ordering | `ProductMedia.sort_order`, assigned incrementally by the upload services |
| Weight validation | `Weight` value object (must be positive) |
| Bundle validation | `Bundle.__post_init__`/`.create()` (must have ≥1 item) |

---

## 6. Events Table

| Event | Emitted By |
|---|---|
| `ProductCreated` | `CreateProduct`, `DuplicateProduct`, `CloneProduct` |
| `ProductUpdated` | `UpdateProduct` |
| `ProductPublished` | `PublishProduct` |
| `ProductHidden` | `HideProduct` |
| `ProductArchived` | `ArchiveProduct` |
| `ProductRestored` | `RestoreProduct` |
| `ProductDeleted` | `DeleteProduct` |
| `BrandAssigned` | `AssignBrand` |
| `CategoryAssigned` | `AssignCategory` |
| `ProductVariantCreated` | `CreateVariant` |
| `ProductVariantUpdated` | `UpdateVariant` |
| `ProductVariantDeleted` | `DeleteVariant` |
| `ProductMediaUploaded` | `UploadImage`, `UploadVideo`, `UploadDocument` |
| `ProductMediaDeleted` | `DeleteImage`/`DeleteVideo`/`DeleteDocument` |
| `ProductSEOUpdated` | `UpdateSEO` |
| `CertificateAttached` | (defined; not yet wired to a Phase 1 service — certificate attachment is a Phase 2/infrastructure concern) |
| `BundleCreated` | (defined; Bundle application services are not yet written — Phase 1 scoped Product-centric services first, per this phase's explicit aggregate priority list) |

Every event is a plain, registered-but-not-yet-`registry.register()`'d dataclass at this phase (registration happens via `shared/event_contracts/products.py`, an infrastructure-adjacent file this phase's scope excludes — see Known Limitations). `stage_events` is injected as a callable into every Application Service (never a direct publish), matching MIC §7 exactly.

---

## 7. Exceptions Table

| Exception | HTTP Category (inherited) |
|---|---|
| `DuplicateSKU` | Conflict (409) |
| `DuplicateSlug` | Conflict (409) |
| `DuplicateBarcode` | Conflict (409) |
| `InvalidCategory` | Validation (422) |
| `InvalidBrand` | Validation (422) |
| `InvalidVariant` | Business (422) |
| `InvalidNutrition` | Validation (422) |
| `InvalidMedia` | Validation (422) |
| `InvalidSEO` | Validation (422) |
| `InvalidAttribute` | Validation (422) |
| `ProductArchived` | Conflict (409) |
| `ProductHidden` | Business (422) |
| `PublishValidationFailed` | Business (422), carries `details.reasons[]` |
| `MediaLimitExceeded` | Business (422) |
| `PrimaryImageMissing` | Business (422) |
| `MissingRequiredCertificate` | Business (422) |
| `InvalidProductLifecycleTransition` | Conflict (409) |
| `BundleMustHaveItems` | Business (422) |
| `VariantAlreadyExists` | Conflict (409), subclasses `DuplicateSKU` |

All subclass `common.exceptions.DomainException`, so `common/exceptions/handlers.py` (Foundation phase) maps every one to the correct HTTP status/error-envelope shape automatically once the Interfaces layer exists — no Products-specific exception handler needed.

---

## 8. Ports Table

| Port | Backs |
|---|---|
| `ProductRepository` | Product CRUD, slug/SKU/barcode uniqueness checks, public + admin listing |
| `BrandRepository` | Brand CRUD |
| `ManufacturerRepository` | Same `brands` table, `is_manufacturer=True` scoped |
| `CategoryRepository` | Category CRUD + tree listing |
| `VariantRepository` | Read-side SKU/variant-id → product-id lookup (writes flow through `ProductRepository`) |
| `AttributeRepository` | Attribute CRUD |
| `FlavorRepository` / `PackageSizeRepository` / `ProductFormRepository` | Scoped to their reserved `Attribute.code` |
| `MediaRepository` | Read-side media-id → product-id lookup |
| `TagRepository` | Tag CRUD |
| `SpecificationRepository` | Read-side distinct-key listing |
| `BundleRepository` | Bundle CRUD |
| `SearchGateway` | Anti-Corruption Layer seam for the future dedicated search engine |
| `StorageGateway` | Mirrors `core.storage.MediaStorageBackend` |

Cross-cutting concerns (Clock/Metrics/Audit/Outbox/Health/Cache) are **not** redeclared as Products-specific Protocols — they're consumed directly from `core/` (already generic, platform-wide, Foundation Hardening phase), exactly as `identity` does. Redeclaring them here would have been duplicated abstraction over infrastructure that's already correctly abstracted once, platform-wide.

---

## 9. Application Services Table

35 services across 7 files, every one following the nine-step flow (validate → load aggregate → execute domain logic → persist → stage Outbox event → write audit → invalidate cache → record metrics → return DTO):

**Lifecycle (9):** CreateProduct, UpdateProduct, DeleteProduct, RestoreProduct, PublishProduct, HideProduct, ArchiveProduct, DuplicateProduct, CloneProduct
**Associations (6):** AssignBrand, AssignCategory, AssignTags, AssignFlavor, AssignPackageSize, AssignProductForm
**Variants (4):** CreateVariant, UpdateVariant, DeleteVariant, SetDefaultVariant
**Media (6):** UploadImage, DeleteImage, UploadVideo, DeleteVideo, UploadDocument, DeleteDocument
**Content (5):** UpdateNutritionFacts, UpdateIngredients, UpdateWarnings, UpdateDirections, UpdateSEO
**Generation (2):** GenerateSlug, GenerateSKU
**Queries (4):** GetProduct, ListProducts, AdminListProducts, SearchProducts

Steps 5-8 (Outbox/Audit/Cache/Metrics) are factored into a shared `ProductServiceContext` helper (`_shared.py`) rather than re-implemented identically 35 times — every service still performs all four steps, they share one well-defined helper for them instead of duplicating four lines per service. `ProductServiceContext.stage_events` is injected as a callable (never a concrete Outbox model imported into `application/`), matching Identity's exact composition-root pattern.

---

## 10. Architecture Validation

| Gate | Status |
|---|---|
| ✓ Domain has zero Django imports | **Pass** — verified by grep across every `domain/*.py` file, not just asserted |
| ✓ Application depends only on Ports | **Pass**, with the one documented, precedent-matching exception: `from django.db import transaction` for `@transaction.atomic` (identical to Identity's established pattern — transaction-boundary management is treated as application-layer orchestration, not infrastructure business logic) |
| ✓ No circular imports | **Pass** — verified by inspection; `application/` never imports `infrastructure/` (confirmed by grep, the only "match" was a docstring sentence explaining why it doesn't) |
| ✓ Aggregate invariants enforced | **Pass** — see §5 |
| ✓ Events registered | **Partial** — event *classes* are complete and typed; `shared/event_contracts/products.py`'s `registry.register()` calls are an infrastructure-adjacent file explicitly out of this phase's scope (Phase 1 = domain + application only) |
| ✓ Exceptions complete | **Pass** — 19 exceptions, all named to match this phase's brief |
| ✓ Application Services compile | **Pass** — all 35 compile cleanly |

**Two mid-build corrections worth surfacing rather than silently fixing:**
1. An early draft of `ProductServiceContext` imported `apps.products.infrastructure.models` directly to call `stage_event()` — a real Clean Architecture violation (application depending on infrastructure). Caught and fixed before this report: `stage_events` is now an injected callable, with the concrete Outbox-aware implementation deferred to `infrastructure/composition.py` (Phase 2), exactly mirroring Identity's pattern.
2. An early draft of `UpdateWarnings`/`UpdateDirections` used a `hasattr(repo, "save_field")` shortcut to avoid adding real fields to the `Product` aggregate — caught as exactly the kind of shortcut this phase's brief explicitly forbids, and replaced with proper `warnings_text`/`directions_text` fields and `update_warnings()`/`update_directions()` methods on `Product` itself.

**Not yet done (correctly, per this phase's explicit stop instruction):** Infrastructure (ORM models, repositories, composition root, admin, media/search/cache wiring) and Interfaces (serializers, views, URLs, OpenAPI) are untouched. `CreateProduct`/`PublishProduct`/etc. cannot actually run yet — they're complete, correct, testable-with-fakes application services with no concrete repository to inject until Phase 2. `CertificateAttached` and `BundleCreated` events exist but have no emitting service yet, since Phase 1 prioritized the Product-centric lifecycle the brief listed first; Bundle's own application services (`CreateBundle`, etc.) are deferred to whichever phase takes up Bundle explicitly.

**Recommendation:** proceed to Phase 2 (Infrastructure: ORM models mapping every aggregate/entity above, repositories, composition root, Django Admin, health checks) only when instructed — this report stops here per the explicit "do NOT begin Infrastructure" instruction.
