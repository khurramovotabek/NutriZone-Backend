"""
Real, live-verified regression test for a genuine cross-formset data
loss bug found while adding `ProductVariant.package`: `ProductVariantInline`
and `ProductPricingInline` are two separate `TabularInline`s over the
identical `ProductVariant` model (see both classes' own docstrings in
admin.py). Django admin constructs each inline's formset from its own
independent queryset, so on the CHANGE view both hold their own stale
in-memory Python copy of the same row. Before `ProductVariantAdminForm.
save()` was fixed to scope its UPDATE to only the fields the specific
bound form actually declares, whichever inline's formset saved second
silently reverted any field the OTHER inline had just written (e.g. a
newly assigned Package or weight) back to its own stale value --
confirmed live via a real admin edit before this fix.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from apps.products.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def _admin_client(suffix: str) -> Client:
    admin_user = AuthUser.objects.create_superuser(username=f"admin_{suffix}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


def _change_form_data(product: orm.Product, variant: orm.ProductVariant, **variant_overrides) -> dict:
    data = {
        "status": product.status,
        "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
        "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "1", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
        "variants-0-id": str(variant.id),
        "variants-0-product": str(product.id),
        "variants-0-sku": variant.sku,
        "variants-0-status": variant.status,
        "variants-0-weight_value": str(variant.weight_value) if variant.weight_value is not None else "",
        "variants-0-weight_unit": variant.weight_unit,
        # `ProductPricingInline` (prefix "variants-2") over the same variant
        # -- its own fields (base_cost_price/price/old_price) are
        # intentionally left blank here, matching a real editor who opens
        # the Product change form only to set the Package, never touching
        # Pricing at all.
        "variants-2-TOTAL_FORMS": "1", "variants-2-INITIAL_FORMS": "1", "variants-2-MIN_NUM_FORMS": "0", "variants-2-MAX_NUM_FORMS": "1000",
        "variants-2-0-id": str(variant.id),
        "variants-2-0-product": str(product.id),
        "flavour_links-TOTAL_FORMS": "0", "flavour_links-INITIAL_FORMS": "0", "flavour_links-MIN_NUM_FORMS": "0", "flavour_links-MAX_NUM_FORMS": "1000",
        "media-TOTAL_FORMS": "0", "media-INITIAL_FORMS": "0", "media-MIN_NUM_FORMS": "0", "media-MAX_NUM_FORMS": "1000",
        "certificate_links-TOTAL_FORMS": "0", "certificate_links-INITIAL_FORMS": "0", "certificate_links-MIN_NUM_FORMS": "0", "certificate_links-MAX_NUM_FORMS": "1000",
    }
    for key, value in variant_overrides.items():
        data[f"variants-0-{key}"] = value
    return data


class TestVariantPackageSurvivesTheSiblingPricingInlineSave:
    def test_assigning_a_package_via_the_admin_change_form_persists(self):
        """
        A real, existing price entry is deliberately set up here (not
        left blank): with no existing price, `ProductPricingInline`'s
        own sub-form for this variant would compare "blank submitted"
        against "blank initial" and Django would consider it unchanged,
        skipping its save entirely and accidentally sidestepping the
        bug this test exists to catch. A real, already-priced variant
        (the ordinary case) has "blank submitted" differ from "500000
        initial", which is exactly the state that triggered the real,
        live-reproduced clobber.
        """
        from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()

        product = orm.Product.objects.create(id=uuid.uuid4(), status="draft")
        variant = orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix.upper()}", status="active")
        package = orm.Package.objects.create(id=uuid.uuid4(), slug=f"bottle-{suffix}")
        price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{suffix}", name="Default", currency="UZS", status="active")
        PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount="500000")

        data = _change_form_data(product, variant, package=str(package.id))
        response = client.post(f"/django-admin/products/product/{product.id}/change/", data)

        assert response.status_code in (200, 302), response.content.decode()[:2000]
        variant.refresh_from_db()
        assert variant.package_id == package.id

    def test_editing_weight_via_the_admin_change_form_persists_and_price_is_untouched(self):
        from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

        suffix = uuid.uuid4().hex[:6]
        client = _admin_client(suffix)
        ContentType.objects.clear_cache()

        product = orm.Product.objects.create(id=uuid.uuid4(), status="draft")
        variant = orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix.upper()}", status="active", weight_value=250, weight_unit="g")
        price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{suffix}", name="Default", currency="UZS", status="active")
        PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount="500000")

        data = _change_form_data(product, variant, weight_value="900", weight_unit="g")
        response = client.post(f"/django-admin/products/product/{product.id}/change/", data)

        assert response.status_code in (200, 302), response.content.decode()[:2000]
        variant.refresh_from_db()
        assert variant.weight_value == 900
        entry = PriceListEntryModel.objects.get(product_variant_id=variant.id)
        assert entry.base_price_amount == 500000, "The sibling ProductPricingInline's own stale (blank) submission must never wipe out a real, existing price."
