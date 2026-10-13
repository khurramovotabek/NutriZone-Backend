"""
Real, closed bug regression tests: Django Admin's ProductVariantInline
previously had no form override at all, so an invalid-checksum
barcode saved without error and only crashed later (as an unrelated
HTTP 500 during image upload) when the domain's own Barcode value
object ran during Product reconstruction. ProductVariantAdminForm's
clean_barcode() now rejects an invalid barcode at save time, using
the exact same, unmodified domain Barcode value object.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.test import Client

from apps.products.infrastructure import models as products_orm

pytestmark = pytest.mark.django_db


def _admin_client(suffix: str) -> Client:
    admin_user = AuthUser.objects.create_superuser(username=f"admin_{suffix}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


def _base_add_data(suffix: str) -> dict:
    sku_suffix = suffix.upper()
    return {
        "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
        "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
        "variants-0-sku": f"SKU-{sku_suffix}",
        "variants-0-status": "active",
        "variants-0-weight_value": "",
        "variants-0-weight_unit": "g",
        # Real, product-required simplification: `ProductPricingInline` is a
        # second TabularInline over the same ProductVariant model, so Django's
        # own formset-prefix disambiguation renames it "variants-2" (see
        # `ProductPricingInline`'s own docstring in admin.py) -- its empty
        # management form is still required on every Product add/change POST.
        "variants-2-TOTAL_FORMS": "0", "variants-2-INITIAL_FORMS": "0", "variants-2-MIN_NUM_FORMS": "0", "variants-2-MAX_NUM_FORMS": "1000",
        "flavour_links-TOTAL_FORMS": "0", "flavour_links-INITIAL_FORMS": "0", "flavour_links-MIN_NUM_FORMS": "0", "flavour_links-MAX_NUM_FORMS": "1000",
        "media-TOTAL_FORMS": "0", "media-INITIAL_FORMS": "0", "media-MIN_NUM_FORMS": "0", "media-MAX_NUM_FORMS": "1000",
        "certificate_links-TOTAL_FORMS": "0", "certificate_links-INITIAL_FORMS": "0", "certificate_links-MIN_NUM_FORMS": "0", "certificate_links-MAX_NUM_FORMS": "1000",
        "status": "draft",
    }


class TestProductVariantBarcodeAdminValidation:
    def test_invalid_checksum_barcode_returns_form_error_not_http_500(self):
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        data = _base_add_data(suffix)
        data["variants-0-barcode"] = "1234567890123"  # deliberately wrong check digit

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 200  # stays on the form, not a 500
        assert "checksum" in response.content.decode().lower()
        assert not products_orm.Product.objects.filter(variants__sku=f"SKU-{suffix.upper()}").exists()

    def test_empty_barcode_remains_valid(self):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        data = _base_add_data(suffix)
        data["variants-0-barcode"] = ""

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 302
        assert products_orm.ProductVariant.objects.filter(sku=f"SKU-{suffix.upper()}").exists()

    def test_valid_checksum_barcode_saves_correctly(self):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        data = _base_add_data(suffix)
        data["variants-0-barcode"] = "1234567890128"  # real, valid EAN-13 checksum

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 302
        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix.upper()}")
        assert variant.barcode == "1234567890128"

    def test_invalid_format_barcode_also_returns_form_error(self):
        """Too-short/non-numeric barcodes hit Barcode's own format check (not just the checksum check) -- same clean_barcode() path."""
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        data = _base_add_data(suffix)
        data["variants-0-barcode"] = "ABC123"

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 200
        assert not products_orm.Product.objects.filter(variants__sku=f"SKU-{suffix.upper()}").exists()


class TestProductVariantSkuAdminValidation:
    """Real, closed bug found live during this phase's own testing: SKU had the exact same gap as barcode -- the domain's own SKU value object never ran in the admin form, only crashing later during image upload's identical get_by_id() reconstruction path."""

    def test_lowercase_sku_returns_form_error_not_http_500(self):
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        data = _base_add_data(suffix)
        data["variants-0-sku"] = f"sku-lowercase-{suffix}"  # domain SKU requires uppercase

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 200
        assert not products_orm.ProductVariant.objects.filter(sku__iexact=f"sku-lowercase-{suffix}").exists()

    def test_valid_uppercase_sku_saves_correctly(self):
        suffix = uuid.uuid4().hex[:6].upper()
        client = _admin_client(suffix.lower())
        data = _base_add_data(suffix)

        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 302
        assert products_orm.ProductVariant.objects.filter(sku=f"SKU-{suffix.upper()}").exists()
