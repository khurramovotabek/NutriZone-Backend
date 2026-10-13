"""
Composition root for the `products` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors (dependency injection at the entrypoint, per
Django Implementation Blueprint §4) -- matching
`apps/identity/infrastructure/composition.py`'s exact pattern. No
service locator: every `build_*()` function explicitly constructs and
returns one fully-wired Application Service, nothing is resolved by
name/lookup at call time.
"""
from __future__ import annotations

import uuid

from apps.products.application.selectors import ProductSelector
from apps.products.application.services._shared import ProductServiceContext
from apps.products.application.services.associations import (
    AssignBrand,
    AssignCategory,
    AssignFlavours,
    AssignTags,
)
from apps.products.application.services.content import (
    UpdateDirections,
    UpdateIngredients,
    UpdateNutritionFacts,
    UpdateSEO,
    UpdateWarnings,
)
from apps.products.application.services.generation import GenerateSKU, GenerateSlug
from apps.products.application.services.lifecycle import (
    ArchiveProduct,
    CloneProduct,
    CreateProduct,
    DeleteProduct,
    DuplicateProduct,
    HideProduct,
    PublishProduct,
    RestoreProduct,
    UpdateProduct,
)
from apps.products.application.services.media import (
    DeleteDocument,
    DeleteImage,
    DeleteVideo,
    UploadDocument,
    UploadImage,
    UploadVideo,
)
from apps.products.application.services.queries import (
    AdminListProducts,
    GetProduct,
    ListProducts,
    SearchProducts,
)
from apps.products.application.services.variants import (
    CreateVariant,
    DeleteVariant,
    SetDefaultVariant,
    UpdateVariant,
)
from apps.products.infrastructure import models as orm
from apps.products.infrastructure.repositories import (
    DjangoBrandRepository,
    DjangoCategoryRepository,
    DjangoFlavourRepository,
    DjangoPackageRepository,
    DjangoProductRepository,
    DjangoTagRepository,
    DjangoVariantRepository,
)
from apps.products.infrastructure.selectors import DjangoProductSearchBackend, ProductDetailSelector
from core.media import MediaPipeline, NoOpVirusScanner, PillowImageOptimizer
from core.outbox import stage_event
from core.storage import get_storage_backend


def stage_products_events(events: list[tuple[str, dict]]) -> None:
    """The `stage_events` callable every Products Application Service is constructed with -- the concrete Outbox-aware implementation, kept out of `application/` per Clean Architecture (see application/services/_shared.py's docstring)."""
    for event_type, payload in events:
        stage_event(orm.ProductsOutboxEvent, event_type, payload)


def build_context(actor_id: uuid.UUID | None = None) -> ProductServiceContext:
    return ProductServiceContext(stage_events=stage_products_events, actor_id=actor_id)


def build_media_pipeline() -> MediaPipeline:
    return MediaPipeline(storage=get_storage_backend(), virus_scanner=NoOpVirusScanner(), image_optimizer=PillowImageOptimizer())


# --- Lifecycle ---------------------------------------------------------

def build_create_product(actor_id=None) -> CreateProduct:
    return CreateProduct(DjangoProductRepository(), DjangoBrandRepository(), DjangoCategoryRepository(), build_context(actor_id))


def build_update_product(actor_id=None) -> UpdateProduct:
    return UpdateProduct(DjangoProductRepository(), build_context(actor_id))


def build_delete_product(actor_id=None) -> DeleteProduct:
    return DeleteProduct(DjangoProductRepository(), build_context(actor_id))


def build_restore_product(actor_id=None) -> RestoreProduct:
    return RestoreProduct(DjangoProductRepository(), build_context(actor_id))


def build_publish_product(actor_id=None) -> PublishProduct:
    return PublishProduct(DjangoProductRepository(), DjangoCategoryRepository(), build_context(actor_id))


def build_hide_product(actor_id=None) -> HideProduct:
    return HideProduct(DjangoProductRepository(), build_context(actor_id))


def build_archive_product(actor_id=None) -> ArchiveProduct:
    return ArchiveProduct(DjangoProductRepository(), build_context(actor_id))


def build_duplicate_product(actor_id=None) -> DuplicateProduct:
    return DuplicateProduct(DjangoProductRepository(), build_context(actor_id))


def build_clone_product(actor_id=None) -> CloneProduct:
    return CloneProduct(DjangoProductRepository(), build_context(actor_id))


# --- Associations ------------------------------------------------------

def build_assign_brand(actor_id=None) -> AssignBrand:
    return AssignBrand(DjangoProductRepository(), DjangoBrandRepository(), build_context(actor_id))


def build_assign_category(actor_id=None) -> AssignCategory:
    return AssignCategory(DjangoProductRepository(), DjangoCategoryRepository(), build_context(actor_id))


def build_assign_tags(actor_id=None) -> AssignTags:
    return AssignTags(DjangoProductRepository(), DjangoTagRepository(), build_context(actor_id))


def build_assign_flavours(actor_id=None) -> AssignFlavours:
    return AssignFlavours(DjangoProductRepository(), DjangoFlavourRepository(), build_context(actor_id))


# --- Variants ------------------------------------------------------------

def build_create_variant(actor_id=None) -> CreateVariant:
    return CreateVariant(DjangoProductRepository(), DjangoPackageRepository(), build_context(actor_id))


def build_update_variant(actor_id=None) -> UpdateVariant:
    return UpdateVariant(DjangoProductRepository(), DjangoPackageRepository(), build_context(actor_id))


def build_delete_variant(actor_id=None) -> DeleteVariant:
    return DeleteVariant(DjangoProductRepository(), build_context(actor_id))


def build_set_default_variant(actor_id=None) -> SetDefaultVariant:
    return SetDefaultVariant(DjangoProductRepository(), build_context(actor_id))


# --- Media --------------------------------------------------------------

def build_upload_image(actor_id=None) -> UploadImage:
    return UploadImage(DjangoProductRepository(), build_media_pipeline(), build_context(actor_id))


def build_delete_image(actor_id=None) -> DeleteImage:
    return DeleteImage(DjangoProductRepository(), build_context(actor_id))


def build_upload_video(actor_id=None) -> UploadVideo:
    return UploadVideo(DjangoProductRepository(), build_media_pipeline(), build_context(actor_id))


def build_delete_video(actor_id=None) -> DeleteVideo:
    return DeleteVideo(DjangoProductRepository(), build_context(actor_id))


def build_upload_document(actor_id=None) -> UploadDocument:
    return UploadDocument(DjangoProductRepository(), build_media_pipeline(), build_context(actor_id))


def build_delete_document(actor_id=None) -> DeleteDocument:
    return DeleteDocument(DjangoProductRepository(), build_context(actor_id))


# --- Content --------------------------------------------------------------

def build_update_nutrition_facts(actor_id=None) -> UpdateNutritionFacts:
    return UpdateNutritionFacts(DjangoProductRepository(), build_context(actor_id))


def build_update_ingredients(actor_id=None) -> UpdateIngredients:
    return UpdateIngredients(DjangoProductRepository(), build_context(actor_id))


def build_update_warnings(actor_id=None) -> UpdateWarnings:
    return UpdateWarnings(DjangoProductRepository(), build_context(actor_id))


def build_update_directions(actor_id=None) -> UpdateDirections:
    return UpdateDirections(DjangoProductRepository(), build_context(actor_id))


def build_update_seo(actor_id=None) -> UpdateSEO:
    return UpdateSEO(DjangoProductRepository(), build_context(actor_id))


# --- Generation ------------------------------------------------------------

def build_generate_slug() -> GenerateSlug:
    return GenerateSlug(DjangoProductRepository())


def build_generate_sku() -> GenerateSKU:
    return GenerateSKU(DjangoProductRepository())


# --- Queries --------------------------------------------------------------

def build_get_product() -> GetProduct:
    return GetProduct(DjangoProductRepository())


def build_list_products() -> ListProducts:
    return ListProducts(DjangoProductRepository())


def build_admin_list_products() -> AdminListProducts:
    return AdminListProducts(DjangoProductRepository())


def build_search_products() -> SearchProducts:
    return SearchProducts(ProductSelector(DjangoProductSearchBackend()), variant_repo=build_variant_repository(), detail_reader=ProductDetailSelector())


def build_variant_repository() -> DjangoVariantRepository:
    """New this phase -- `DjangoVariantRepository` had no composition factory before (it was never consumed cross-context). Added as the necessary, minimal companion to `get_by_barcode()` so the POS Search module can obtain this dependency through Products' own composition root, never by importing `apps.products.infrastructure.repositories` directly."""
    return DjangoVariantRepository()


# --- Reference-data repositories (read-only lookups the interfaces
# layer needs directly, e.g. flavour/tag listing) -- wired here rather
# than instantiated in views.py, since these classes implement
# swappable application/ports.py Protocols (unlike the Selector
# classes in infrastructure/selectors.py, which have no Port/Protocol
# behind them and are the accepted exception: a pure, non-swappable
# read-model builder is fine to call directly from an interfaces-layer
# view per Django Implementation Blueprint §3's CQRS-lite framing --
# a Repository implementing a Port is not).

def build_flavour_repository() -> DjangoFlavourRepository:
    return DjangoFlavourRepository()


def build_package_repository() -> DjangoPackageRepository:
    return DjangoPackageRepository()


def build_tag_repository() -> DjangoTagRepository:
    return DjangoTagRepository()


def build_product_repository() -> DjangoProductRepository:
    return DjangoProductRepository()


def build_add_to_wishlist(actor_id: uuid.UUID | None = None) -> AddToWishlist:
    from apps.products.application.services.wishlist import AddToWishlist

    return AddToWishlist(build_context(actor_id))


def build_remove_from_wishlist(actor_id: uuid.UUID | None = None) -> RemoveFromWishlist:
    from apps.products.application.services.wishlist import RemoveFromWishlist

    return RemoveFromWishlist(build_context(actor_id))


def build_list_wishlist() -> ListWishlist:
    from apps.products.application.services.wishlist import ListWishlist

    return ListWishlist()
