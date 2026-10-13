"""
Real, live-verified regression test for the product-detail selector's
Product-level Flavour resolution (the PDP flavour switcher). Closes a
genuine gap: the public `/api/v1/products/{slug}` response exposed a
variant's id/sku/status but never which real Flavour the whole product
actually was, making a real image-based storefront flavour switcher
impossible to build from real data. `Flavour.image_storage_path`/
`image_thumbnail_paths` (same direct-storage-fields convention as
Brand.logo_*/Category.image_*) plus the real
`catalog.product_flavours` junction (`ProductFlavour`) are what a
Flavour's real name, swatch color, and real photo now resolve from --
see `apps/products/infrastructure/selectors.py::_resolve_flavour_switcher`.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.selectors import ProductDetailSelector

pytestmark = pytest.mark.django_db


def _make_published_product() -> p_models.Product:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Gold Standard Whey", slug=f"whey-{uuid.uuid4().hex[:6]}")
    return product


def _make_price_list_entry(variant_id: uuid.UUID, amount: str, currency: str = "UZS"):
    from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

    price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{uuid.uuid4().hex[:8]}", name="Default", currency=currency)
    return PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant_id, base_price_amount=amount)


def _make_stock(variant_id: uuid.UUID, available_quantity: int):
    from apps.products.tests.stock_helpers import put_stock

    put_stock(variant_id, available_quantity)


class TestProductFlavourSwitcher:
    def test_product_exposes_real_flavour_name_color_and_image(self):
        product = _make_published_product()
        chocolate = p_models.Flavour.objects.create(
            id=uuid.uuid4(),
            slug=f"chocolate-{uuid.uuid4().hex[:6]}",
            color_hex="#4B2E1E",
            image_storage_path="flavours/chocolate.webp",
            image_thumbnail_paths={"medium": "flavours/chocolate_medium.webp"},
        )
        p_models.FlavourTranslation.objects.create(id=uuid.uuid4(), flavour=chocolate, locale_code="en", name="Double Rich Chocolate")
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=product, flavour=chocolate)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card is not None
        [flavour_data] = card["flavours"]
        assert flavour_data["id"] == str(chocolate.id)
        assert flavour_data["name"] == "Double Rich Chocolate"
        assert flavour_data["color_hex"] == "#4B2E1E"
        assert flavour_data["image_url"] == "/media/flavours/chocolate_medium.webp"
        assert flavour_data["is_current"] is True
        assert flavour_data["product_id"] == str(product.id)

    def test_product_with_no_flavours_exposes_empty_list_not_an_error(self):
        product = _make_published_product()
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card["flavours"] == []

    def test_flavour_without_an_image_exposes_null_image_url_not_a_broken_path(self):
        product = _make_published_product()
        vanilla = p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"vanilla-{uuid.uuid4().hex[:6]}", color_hex="#F5DEB3")
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=product, flavour=vanilla)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card["flavours"][0]["image_url"] is None

    def test_sibling_product_with_same_brand_category_and_weight_appears_as_a_switch_option(self):
        """The PDP flavour switcher's core capability: selecting a flavour swatch should navigate to the sibling Product carrying that Flavour at the same weight -- see selectors.py::_resolve_flavour_switcher's own docstring for why this is resolved by (brand, category, weight) rather than a parent/family FK."""
        brand = p_models.Brand.objects.create(id=uuid.uuid4())
        category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)

        chocolate_flavour = p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"chocolate-{uuid.uuid4().hex[:6]}", color_hex="#4B2E1E")
        strawberry_flavour = p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"strawberry-{uuid.uuid4().hex[:6]}", color_hex="#FFC0CB")
        p_models.FlavourTranslation.objects.create(id=uuid.uuid4(), flavour=chocolate_flavour, locale_code="en", name="Chocolate")
        p_models.FlavourTranslation.objects.create(id=uuid.uuid4(), flavour=strawberry_flavour, locale_code="en", name="Strawberry")

        this_product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand, category=category)
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=this_product, locale_code="en", name="Whey Chocolate 2.27kg", slug=f"whey-choc-{uuid.uuid4().hex[:6]}")
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=this_product, flavour=chocolate_flavour)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=this_product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True, weight_value=2.27, weight_unit="kg")

        sibling = p_models.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand, category=category)
        sibling_slug = f"whey-straw-{uuid.uuid4().hex[:6]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=sibling, locale_code="en", name="Whey Strawberry 2.27kg", slug=sibling_slug)
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=sibling, flavour=strawberry_flavour)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=sibling, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True, weight_value=2.27, weight_unit="kg")

        card = ProductDetailSelector().get_by_slug(this_product.translations.first().slug, locale="en")

        by_id = {f["id"]: f for f in card["flavours"]}
        assert by_id[str(chocolate_flavour.id)]["is_current"] is True
        assert by_id[str(strawberry_flavour.id)]["is_current"] is False
        assert by_id[str(strawberry_flavour.id)]["product_slug"] == sibling_slug

    def test_sibling_with_a_different_weight_is_not_offered_as_a_switch_option(self):
        brand = p_models.Brand.objects.create(id=uuid.uuid4())
        category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)

        chocolate_flavour = p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"chocolate-{uuid.uuid4().hex[:6]}", color_hex="#4B2E1E")
        strawberry_flavour = p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"strawberry-{uuid.uuid4().hex[:6]}", color_hex="#FFC0CB")

        this_product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand, category=category)
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=this_product, locale_code="en", name="Whey Chocolate 2.27kg", slug=f"whey-choc-{uuid.uuid4().hex[:6]}")
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=this_product, flavour=chocolate_flavour)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=this_product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True, weight_value=2.27, weight_unit="kg")

        different_weight_sibling = p_models.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand, category=category)
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=different_weight_sibling, locale_code="en", name="Whey Strawberry 900g", slug=f"whey-straw-900-{uuid.uuid4().hex[:6]}")
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=different_weight_sibling, flavour=strawberry_flavour)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=different_weight_sibling, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True, weight_value=900, weight_unit="g")

        card = ProductDetailSelector().get_by_slug(this_product.translations.first().slug, locale="en")

        assert str(strawberry_flavour.id) not in {f["id"] for f in card["flavours"]}


class TestVariantGalleryPriceAndStock:
    """Real, closed gap: the public detail response's `variants[]` had no per-variant media, price, or stock at all -- a storefront could resolve which real variant a flavor/size selection maps to, but never actually show that variant's own photo, price, or availability. All three now resolve from real, already-modeled data (ProductMedia.variant, PriceListEntryModel, InventoryModel/WarehouseInventoryModel) -- see selectors.py::_variant_summary."""

    def test_variant_tagged_photo_appears_in_that_variants_gallery_not_the_shared_one(self):
        product = _make_published_product()
        shared = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, media_role="primary", storage_path="products/shared.webp")
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=shared, media_role="primary", storage_path="products/shared-variant-photo.webp")

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card["gallery"] == ["/media/products/shared.webp"]
        assert card["variants"][0]["gallery"] == ["/media/products/shared-variant-photo.webp"]

    def test_variant_with_no_own_photo_has_an_empty_gallery_not_the_shared_one(self):
        """The frontend's own fallback (show the shared/family gallery) only works if an untagged variant's own list is genuinely empty, never silently duplicated from the shared one server-side."""
        product = _make_published_product()
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, media_role="primary", storage_path="products/shared.webp")
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card["variants"][0]["gallery"] == []

    def test_variant_video_resolves_to_a_real_url(self):
        product = _make_published_product()
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=variant, media_role="video", storage_path="products/demo.mp4")

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card["variants"][0]["video_url"] == "/media/products/demo.mp4"

    def test_two_variants_have_two_real_independent_prices(self):
        product = _make_published_product()
        chocolate = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        strawberry = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}")
        _make_price_list_entry(chocolate.id, "620000")
        _make_price_list_entry(strawberry.id, "635000")

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        by_id = {v["id"]: v for v in card["variants"]}
        assert by_id[str(chocolate.id)]["price"] == "620000.00"
        assert by_id[str(strawberry.id)]["price"] == "635000.00"
        assert by_id[str(chocolate.id)]["currency"] == "UZS"

    def test_variant_with_no_price_entry_exposes_null_not_zero(self):
        product = _make_published_product()
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert card["variants"][0]["price"] is None

    def test_stock_status_out_of_stock_low_stock_and_in_stock(self):
        product = _make_published_product()
        empty = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        low = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}")
        healthy = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}")
        _make_stock(low.id, 3)
        _make_stock(healthy.id, 500)
        # `empty` deliberately has no InventoryModel row at all.

        card = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        by_id = {v["id"]: v for v in card["variants"]}
        assert by_id[str(empty.id)]["stock_status"] == "out_of_stock"
        assert by_id[str(empty.id)]["stock_quantity"] == 0
        assert by_id[str(low.id)]["stock_status"] == "low_stock"
        assert by_id[str(low.id)]["stock_quantity"] == 3
        assert by_id[str(healthy.id)]["stock_status"] == "in_stock"
        assert by_id[str(healthy.id)]["stock_quantity"] is not None and by_id[str(healthy.id)]["stock_quantity"] > 10, "Product decision: the real count is shown for every status, not only low stock."


class TestUploadImageVariantTagging:
    """Real, closed gap: UploadImage had no way to tag a photo to a specific variant at all -- see application/services/media.py."""

    def test_upload_image_with_a_real_variant_id_tags_the_media_row(self):
        from apps.products.application.services._shared import ProductServiceContext
        from apps.products.application.services.media import UploadImage
        from apps.products.tests.application.fakes import FakeProductRepository, collect_events

        product = _domain_product_with_variant()
        repo = FakeProductRepository()
        repo.save(product)
        variant_id = next(iter(product.variants))
        events: list = []
        ctx = ProductServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4())

        class _PassingPipeline:
            def process(self, request):
                from core.media import MediaMetadata, MediaType, ProcessedMedia
                from core.result import Result

                return Result.success(ProcessedMedia(storage_path="products/x.jpg", media_type=MediaType.IMAGE, mime_type=request.mime_type, metadata=MediaMetadata(size_bytes=10, checksum_sha256="x", width_px=800, height_px=800), has_webp_variant=False, thumbnail_paths={}))

        updated = UploadImage(repo, _PassingPipeline(), ctx).execute(product_id=product.id, filename="a.jpg", content=b"data", mime_type="image/jpeg", variant_id=variant_id)

        [media] = list(updated.media.values())
        assert media.variant_id == variant_id

    def test_upload_image_rejects_a_variant_id_from_a_different_product(self):
        from apps.products.application.services._shared import ProductServiceContext
        from apps.products.application.services.media import UploadImage
        from apps.products.tests.application.fakes import FakeProductRepository, collect_events
        from common.exceptions import ValidationFailed

        product = _domain_product_with_variant()
        repo = FakeProductRepository()
        repo.save(product)
        ctx = ProductServiceContext(stage_events=collect_events([]), actor_id=uuid.uuid4())

        class _PassingPipeline:
            def process(self, request):
                raise AssertionError("must never reach the media pipeline once variant validation has already failed")

        with pytest.raises(ValidationFailed):
            UploadImage(repo, _PassingPipeline(), ctx).execute(product_id=product.id, filename="a.jpg", content=b"data", mime_type="image/jpeg", variant_id=uuid.uuid4())


def _domain_product_with_variant():
    from apps.products.domain.aggregates import Product, ProductVariant
    from apps.products.domain.value_objects import SKU, Slug

    product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
    product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU(f"SKU-{uuid.uuid4().hex[:6].upper()}")))
    return product


class TestFlavourAdminImageUpload:
    def test_flavour_with_real_image_shows_real_thumbnail_url(self):
        admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)

        p_models.Flavour.objects.create(
            id=uuid.uuid4(), slug=f"chocolate-{uuid.uuid4().hex[:6]}", color_hex="#4B2E1E",
            image_storage_path="flavours/chocolate.webp", image_thumbnail_paths={"small": "flavours/chocolate_small.webp"},
        )

        response = client.get("/django-admin/products/flavour/")
        assert response.status_code == 200
        assert "flavours/chocolate_small.webp" in response.content.decode()

    def test_flavour_without_an_image_shows_fallback_not_a_broken_image(self):
        admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)

        p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"vanilla-{uuid.uuid4().hex[:6]}", color_hex="#F5DEB3")

        response = client.get("/django-admin/products/flavour/")
        assert response.status_code == 200
        assert "nz-thumb-empty" in response.content.decode()
