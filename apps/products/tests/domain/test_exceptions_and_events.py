from __future__ import annotations

import uuid

import pytest

from apps.products.domain import exceptions as exc
from apps.products.domain.events import (
    BrandAssigned,
    CategoryAssigned,
    ProductArchived,
    ProductCreated,
    ProductHidden,
    ProductPublished,
    ProductSEOUpdated,
    ProductVariantCreated,
)
from common.exceptions import DomainException

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.DuplicateSKU, exc.DuplicateSlug, exc.DuplicateBarcode, exc.InvalidCategory, exc.InvalidBrand,
        exc.InvalidVariant, exc.InvalidNutrition, exc.InvalidMedia, exc.InvalidSEO, exc.InvalidAttribute,
        exc.ProductArchived, exc.ProductHidden, exc.PublishValidationFailed, exc.MediaLimitExceeded,
        exc.PrimaryImageMissing, exc.MissingRequiredCertificate, exc.InvalidProductLifecycleTransition,
        exc.VariantAlreadyExists,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code  # every exception has a non-empty machine-readable code


def test_variant_already_exists_is_a_duplicate_sku_subclass():
    assert issubclass(exc.VariantAlreadyExists, exc.DuplicateSKU)


class TestEventPayloads:
    def test_product_created_payload_shape(self):
        pid = uuid.uuid4()
        event = ProductCreated(product_id=pid, slug="whey", name="Whey")
        payload = event.to_payload()
        assert payload["product_id"] == str(pid)
        assert payload["slug"] == "whey"

    def test_product_published_payload_shape(self):
        pid = uuid.uuid4()
        assert ProductPublished(product_id=pid).to_payload() == {"product_id": str(pid)}

    def test_product_hidden_payload_shape(self):
        pid = uuid.uuid4()
        assert ProductHidden(product_id=pid).to_payload() == {"product_id": str(pid)}

    def test_product_archived_payload_shape(self):
        pid = uuid.uuid4()
        assert ProductArchived(product_id=pid).to_payload() == {"product_id": str(pid)}

    def test_brand_assigned_handles_null_brand(self):
        pid = uuid.uuid4()
        payload = BrandAssigned(product_id=pid, brand_id=None).to_payload()
        assert payload["brand_id"] is None

    def test_category_assigned_serializes_uuid(self):
        pid, cid = uuid.uuid4(), uuid.uuid4()
        payload = CategoryAssigned(product_id=pid, category_id=cid).to_payload()
        assert payload["category_id"] == str(cid)

    def test_variant_created_payload_shape(self):
        pid, vid = uuid.uuid4(), uuid.uuid4()
        payload = ProductVariantCreated(product_id=pid, variant_id=vid, sku="SKU-1").to_payload()
        assert payload["sku"] == "SKU-1"
        assert payload["variant_id"] == str(vid)

    def test_seo_updated_payload_shape(self):
        pid = uuid.uuid4()
        assert ProductSEOUpdated(product_id=pid).to_payload() == {"product_id": str(pid)}

    def test_all_events_are_frozen_dataclasses(self):
        event = ProductPublished(product_id=uuid.uuid4())
        with pytest.raises(Exception):
            event.product_id = uuid.uuid4()  # type: ignore[misc]
