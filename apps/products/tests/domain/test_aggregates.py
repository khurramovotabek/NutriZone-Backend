from __future__ import annotations

import uuid

import pytest

from apps.products.domain.aggregates import (
    Brand,
    Category,
    Flavour,
    Manufacturer,
    Package,
    Product,
    ProductVariant,
    Tag,
)
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole, ProductStatus
from apps.products.domain.exceptions import (
    InvalidAttribute,
    InvalidBrand,
    InvalidCategory,
    InvalidFlavour,
    InvalidPackage,
    InvalidProductLifecycleTransition,
    MediaLimitExceeded,
    PrimaryImageMissing,
    PublishValidationFailed,
    VariantAlreadyExists,
)
from apps.products.domain.value_objects import SKU, Slug

pytestmark = pytest.mark.unit


def _product(status: ProductStatus = ProductStatus.DRAFT) -> Product:
    return Product(id=uuid.uuid4(), slug=Slug("test-product"), name="Test Product", status=status)


def _variant(sku: str = "SKU-1") -> ProductVariant:
    return ProductVariant(id=uuid.uuid4(), sku=SKU(sku))


def _primary_media() -> ProductMedia:
    return ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY)


class TestProductVariantManagement:
    def test_first_variant_becomes_default_automatically(self):
        product = _product()
        product.add_variant(_variant())
        assert next(iter(product.variants.values())).is_default is True

    def test_duplicate_sku_raises(self):
        product = _product()
        product.add_variant(_variant("SKU-1"))
        with pytest.raises(VariantAlreadyExists):
            product.add_variant(_variant("SKU-1"))

    def test_removing_default_variant_promotes_another(self):
        product = _product()
        v1 = _variant("SKU-1")
        v2 = _variant("SKU-2")
        product.add_variant(v1)
        product.add_variant(v2)
        product.remove_variant(v1.id)
        assert product.variants[v2.id].is_default is True

    def test_set_default_variant(self):
        product = _product()
        v1 = _variant("SKU-1")
        v2 = _variant("SKU-2")
        product.add_variant(v1)
        product.add_variant(v2)
        product.set_default_variant(v2.id)
        assert product.variants[v1.id].is_default is False
        assert product.variants[v2.id].is_default is True

    def test_set_default_variant_unknown_id_raises(self):
        product = _product()
        with pytest.raises(Exception):  # InvalidVariant
            product.set_default_variant(uuid.uuid4())


class TestProductMediaManagement:
    def test_new_primary_demotes_existing_primary_to_gallery(self):
        product = _product()
        first = _primary_media()
        second = ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY)
        product.add_media(first)
        product.add_media(second)
        assert product.media[first.id].media_role == MediaRole.GALLERY
        assert product.media[second.id].media_role == MediaRole.PRIMARY

    def test_max_12_images_enforced(self):
        product = _product()
        for _ in range(12):
            product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.GALLERY))
        with pytest.raises(MediaLimitExceeded):
            product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.GALLERY))

    def test_max_4_videos_enforced(self):
        product = _product()
        for _ in range(4):
            product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.VIDEO))
        with pytest.raises(MediaLimitExceeded):
            product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.VIDEO))

    def test_assert_has_primary_image_raises_when_missing(self):
        product = _product()
        with pytest.raises(PrimaryImageMissing):
            product.assert_has_primary_image()

    def test_assert_has_primary_image_passes_when_present(self):
        product = _product()
        product.add_media(_primary_media())
        product.assert_has_primary_image()  # should not raise


class TestProductPublishWorkflow:
    def test_cannot_publish_without_variants(self):
        product = _product()
        product.add_media(_primary_media())
        with pytest.raises(PublishValidationFailed) as exc_info:
            product.publish()
        assert any(r["code"] == "NO_VARIANTS" for r in exc_info.value.details["reasons"])

    def test_cannot_publish_without_primary_image(self):
        product = _product()
        product.add_variant(_variant())
        with pytest.raises(PublishValidationFailed) as exc_info:
            product.publish()
        assert any(r["code"] == "NO_PRIMARY_IMAGE" for r in exc_info.value.details["reasons"])

    def test_publish_aggregates_every_failing_reason_at_once(self):
        product = _product()
        with pytest.raises(PublishValidationFailed) as exc_info:
            product.publish()
        reasons = {r["code"] for r in exc_info.value.details["reasons"]}
        assert "NO_VARIANTS" in reasons
        assert "NO_PRIMARY_IMAGE" in reasons

    def test_publish_succeeds_when_all_requirements_met(self):
        product = _product()
        product.add_variant(_variant())
        product.add_media(_primary_media())
        event = product.publish()
        assert product.status == ProductStatus.PUBLISHED
        assert event.product_id == product.id

    def test_cannot_publish_archived_product(self):
        product = _product(status=ProductStatus.ARCHIVED)
        with pytest.raises(InvalidProductLifecycleTransition):
            product.publish()

    def test_publish_fails_with_missing_required_certificate(self):
        product = _product()
        product.add_variant(_variant())
        product.add_media(_primary_media())
        with pytest.raises(PublishValidationFailed) as exc_info:
            product.publish(required_certificate_types=frozenset({"gmp"}))
        assert any(r["code"] == "MISSING_REQUIRED_CERTIFICATE" for r in exc_info.value.details["reasons"])


class TestProductLifecycleTransitions:
    def _published(self) -> Product:
        product = _product()
        product.add_variant(_variant())
        product.add_media(_primary_media())
        product.publish()
        return product

    def test_hide_from_published(self):
        product = self._published()
        event = product.hide()
        assert product.status == ProductStatus.UNPUBLISHED
        assert event.product_id == product.id

    def test_hide_from_draft_raises(self):
        product = _product()
        with pytest.raises(InvalidProductLifecycleTransition):
            product.hide()

    def test_archive_from_any_non_archived_status(self):
        product = _product()
        event = product.archive()
        assert product.status == ProductStatus.ARCHIVED
        assert event.product_id == product.id

    def test_archive_already_archived_raises(self):
        product = _product(status=ProductStatus.ARCHIVED)
        with pytest.raises(InvalidProductLifecycleTransition):
            product.archive()

    def test_restore_from_archived(self):
        product = _product(status=ProductStatus.ARCHIVED)
        event = product.restore()
        assert product.status == ProductStatus.DRAFT
        assert event.product_id == product.id

    def test_restore_non_archived_raises(self):
        product = _product()
        with pytest.raises(InvalidProductLifecycleTransition):
            product.restore()

    def test_is_publicly_visible_only_when_published(self):
        assert _product(status=ProductStatus.DRAFT).is_publicly_visible is False
        assert self._published().is_publicly_visible is True


class TestProductAssociationsAndContent:
    def test_assign_brand_returns_event(self):
        product = _product()
        brand_id = uuid.uuid4()
        event = product.assign_brand(brand_id)
        assert product.brand_id == brand_id
        assert event.brand_id == brand_id

    def test_assign_category_returns_event(self):
        product = _product()
        category_id = uuid.uuid4()
        event = product.assign_category(category_id)
        assert product.category_id == category_id
        assert event.category_id == category_id

    def test_update_core_fields_partial(self):
        product = _product()
        event = product.update_core_fields(name="New Name")
        assert product.name == "New Name"
        assert event.before["name"] == "Test Product"
        assert event.after["name"] == "New Name"

    def test_update_warnings_and_directions(self):
        product = _product()
        product.update_warnings("Do not exceed dose.")
        product.update_directions("Take with water.")
        assert product.warnings_text_uz == "Do not exceed dose."
        assert product.directions_text_uz == "Take with water."

    def test_update_warnings_and_directions_in_a_specific_locale(self):
        """Real, product-required capability: each of the 3 languages is stored independently."""
        product = _product()
        product.update_warnings("Не превышайте дозу.", locale="ru")
        product.update_directions("Take with water.", locale="en")
        assert product.warnings_text_ru == "Не превышайте дозу."
        assert product.directions_text_en == "Take with water."
        assert product.warnings_text_uz is None
        assert product.directions_text_uz is None

    def test_update_seo_returns_event(self):
        from apps.products.domain.value_objects import SEOData

        product = _product()
        event = product.update_seo(SEOData(meta_title="Title"))
        assert product.seo.meta_title == "Title"
        assert event.product_id == product.id


class TestCategoryAggregate:
    def test_valid_category(self):
        Category(id=uuid.uuid4(), slug=Slug("supplements"), name="Supplements")

    def test_empty_name_raises(self):
        with pytest.raises(InvalidCategory):
            Category(id=uuid.uuid4(), slug=Slug("supplements"), name="")

    def test_self_parent_raises(self):
        cid = uuid.uuid4()
        with pytest.raises(InvalidCategory):
            Category(id=cid, slug=Slug("supplements"), name="Supplements", parent_id=cid)

    def test_rename(self):
        category = Category(id=uuid.uuid4(), slug=Slug("supplements"), name="Supplements")
        category.rename("New Name")
        assert category.name == "New Name"

    def test_rename_empty_raises(self):
        category = Category(id=uuid.uuid4(), slug=Slug("supplements"), name="Supplements")
        with pytest.raises(InvalidCategory):
            category.rename("")


class TestBrandAggregate:
    def test_valid_brand(self):
        Brand(id=uuid.uuid4(), slug=Slug("optimum-nutrition"), name="Optimum Nutrition")

    def test_empty_name_raises(self):
        with pytest.raises(InvalidBrand):
            Brand(id=uuid.uuid4(), slug=Slug("on"), name="")

    def test_deactivate_activate(self):
        brand = Brand(id=uuid.uuid4(), slug=Slug("on"), name="ON")
        brand.deactivate()
        assert brand.is_active is False
        brand.activate()
        assert brand.is_active is True


class TestManufacturerFactory:
    def test_create_returns_brand_with_manufacturer_flag(self):
        manufacturer = Manufacturer.create(uuid.uuid4(), Slug("glanbia"), "Glanbia")
        assert isinstance(manufacturer, Brand)
        assert manufacturer.is_manufacturer is True


class TestFlavourAggregate:
    def test_valid_flavour(self):
        Flavour(id=uuid.uuid4(), slug=Slug("chocolate"), name="Chocolate")

    def test_empty_name_raises(self):
        with pytest.raises(InvalidFlavour):
            Flavour(id=uuid.uuid4(), slug=Slug("chocolate"), name="")

    def test_deactivate_activate(self):
        flavour = Flavour(id=uuid.uuid4(), slug=Slug("chocolate"), name="Chocolate")
        flavour.deactivate()
        assert flavour.is_active is False
        flavour.activate()
        assert flavour.is_active is True


class TestPackageAggregate:
    def test_valid_package(self):
        Package(id=uuid.uuid4(), slug=Slug("bottle"), name="Bottle")

    def test_empty_name_raises(self):
        with pytest.raises(InvalidPackage):
            Package(id=uuid.uuid4(), slug=Slug("bottle"), name="")

    def test_deactivate_activate(self):
        package = Package(id=uuid.uuid4(), slug=Slug("bottle"), name="Bottle")
        package.deactivate()
        assert package.is_active is False
        package.activate()
        assert package.is_active is True


class TestProductVariantPackageAssignment:
    def test_package_id_defaults_to_none(self):
        variant = ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1"))
        assert variant.package_id is None

    def test_package_id_can_be_set(self):
        package_id = uuid.uuid4()
        variant = ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1"), package_id=package_id)
        assert variant.package_id == package_id


class TestProductFlavourAssignment:
    def test_assign_flavours_sets_ids(self):
        product = _product()
        flavour_ids = frozenset({uuid.uuid4(), uuid.uuid4()})
        product.assign_flavours(flavour_ids)
        assert product.flavour_ids == flavour_ids


class TestTagAggregate:
    def test_valid_tag(self):
        Tag(id=uuid.uuid4(), code="vegan", name="Vegan")

    def test_empty_code_raises(self):
        with pytest.raises(InvalidAttribute):
            Tag(id=uuid.uuid4(), code="", name="Vegan")
