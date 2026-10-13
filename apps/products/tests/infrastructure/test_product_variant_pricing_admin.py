"""
Real, closed bug regression tests: `ProductVariantAdminForm`'s
Price/Old price fields previously wrote nothing at all whenever no
active, region-less price list existed yet (`_default_price_list()`
returned `None`, and `_save_price()` just `return`ed) -- confirmed as
the exact reason zero `PriceListEntryModel` rows existed anywhere in
the database despite this form looking fully functional. Now lazily
creates+activates a default price list on first use and writes
through the real `SetPrice` Application Service (real PriceHistory,
real cache invalidation) instead of a raw, silently-failing ORM call.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from apps.pricing.infrastructure.models import PriceHistoryEntryModel, PriceListEntryModel, PriceListModel
from apps.products.infrastructure import models as products_orm

pytestmark = pytest.mark.django_db


def _admin_client(suffix: str) -> Client:
    admin_user = AuthUser.objects.create_superuser(username=f"admin_{suffix}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


def _base_add_data(suffix: str, **variant_overrides) -> dict:
    sku_suffix = suffix.upper()
    data = {
        "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
        "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
        "variants-0-sku": f"SKU-{sku_suffix}",
        "variants-0-status": "active",
        "variants-0-weight_value": "",
        "variants-0-weight_unit": "g",
        # `ProductPricingInline` (a second inline over the same ProductVariant
        # model -- see its docstring in admin.py) gets auto-disambiguated to
        # prefix "variants-2" by Django; price/old_price/base_cost_price are
        # explicitly-declared ProductVariantAdminForm fields, so they still
        # validate correctly when submitted under the first inline's own
        # "variants-0-*" prefix below -- only this empty management form is
        # additionally required now.
        "variants-2-TOTAL_FORMS": "0", "variants-2-INITIAL_FORMS": "0", "variants-2-MIN_NUM_FORMS": "0", "variants-2-MAX_NUM_FORMS": "1000",
        "flavour_links-TOTAL_FORMS": "0", "flavour_links-INITIAL_FORMS": "0", "flavour_links-MIN_NUM_FORMS": "0", "flavour_links-MAX_NUM_FORMS": "1000",
        "media-TOTAL_FORMS": "0", "media-INITIAL_FORMS": "0", "media-MIN_NUM_FORMS": "0", "media-MAX_NUM_FORMS": "1000",
        "certificate_links-TOTAL_FORMS": "0", "certificate_links-INITIAL_FORMS": "0", "certificate_links-MIN_NUM_FORMS": "0", "certificate_links-MAX_NUM_FORMS": "1000",
        "status": "draft",
    }
    for key, value in variant_overrides.items():
        data[f"variants-0-{key}"] = value
    return data


class TestProductVariantPricingAdmin:
    def test_setting_a_price_auto_creates_and_activates_a_default_price_list(self):
        """The real, closed gap: previously this silently did nothing at all when no price list existed."""
        assert PriceListModel.objects.count() == 0

        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()
        data = _base_add_data(suffix, price="1120000", old_price="1450000")

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 302
        price_list = PriceListModel.objects.get()
        assert price_list.status == "active"
        assert price_list.region is None
        assert price_list.currency == "UZS"

        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix.upper()}")
        entry = PriceListEntryModel.objects.get(price_list=price_list, product_variant_id=variant.id)
        assert entry.base_price_amount == 1120000
        assert entry.compare_at_price_amount == 1450000

    def test_a_second_products_price_reuses_the_same_default_price_list(self):
        suffix1, suffix2 = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
        client = _admin_client(suffix1)
        ContentType.objects.clear_cache()
        client.post("/django-admin/products/product/add/", _base_add_data(suffix1, price="500000"))
        client.post("/django-admin/products/product/add/", _base_add_data(suffix2, price="750000"))

        assert PriceListModel.objects.count() == 1

    def test_base_cost_price_is_stored_separately_from_selling_price(self):
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()
        data = _base_add_data(suffix, price="1120000", base_cost_price="850000")

        client.post("/django-admin/products/product/add/", data)

        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix.upper()}")
        entry = PriceListEntryModel.objects.get(product_variant_id=variant.id)
        assert entry.cost_price_amount == 850000
        assert entry.base_price_amount == 1120000

    def test_setting_a_price_records_real_price_history(self):
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()
        client.post("/django-admin/products/product/add/", _base_add_data(suffix, price="1000000"))

        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix.upper()}")
        history = PriceHistoryEntryModel.objects.filter(product_variant_id=variant.id)
        assert history.count() == 1
        assert history.first().new_amount == 1000000

    def test_blank_price_fields_do_not_create_a_price_list_entry(self):
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()
        client.post("/django-admin/products/product/add/", _base_add_data(suffix))

        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix.upper()}")
        assert not PriceListEntryModel.objects.filter(product_variant_id=variant.id).exists()
        assert PriceListModel.objects.count() == 0

    def test_old_price_not_greater_than_price_is_rejected_with_a_form_error_not_http_500(self):
        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()
        data = _base_add_data(suffix, price="1000000", old_price="900000")

        response = client.post("/django-admin/products/product/add/", data)

        assert response.status_code == 200
        assert "old price" in response.content.decode().lower()
        assert not products_orm.Product.objects.filter(variants__sku=f"SKU-{suffix.upper()}").exists()
