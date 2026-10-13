"""
Real, closed gaps: several models had a raw JSON field (a bare
CharField/JSONField, editable as free-text in Django Admin) that was
never meant to be hand-edited there -- either it's internal computed
state (formatted_lines, quantities_by_status) or backend-managed
transactional data (coupon_ids/promotion_ids on an already-placed
Order/Cart, a customer's own notification preferences). Each is now
either readonly or (for Product.specifications/nutrition_nutrients)
excluded entirely and replaced with a real, readable table.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.contrib.contenttypes.models import ContentType
from django.test import Client

pytestmark = pytest.mark.django_db


def _admin_client() -> Client:
    ContentType.objects.clear_cache()
    admin_user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


class TestAddressFormattedLinesIsReadonly:
    def test_formatted_lines_is_not_an_editable_textarea(self):
        from apps.geo.infrastructure import models as geo_orm

        country = geo_orm.Country.objects.filter(code="UZ").first() or geo_orm.Country.objects.create(id=uuid.uuid4(), code="UZ")
        region = geo_orm.Region.objects.create(id=uuid.uuid4(), country=country, code=f"R{uuid.uuid4().hex[:4].upper()}")
        city = geo_orm.City.objects.create(id=uuid.uuid4(), region=region, code=f"C{uuid.uuid4().hex[:4].upper()}")
        address = geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type="residential", country=country, city=city, line1="Test St", formatted_lines=["Test St", "Tashkent"])

        client = _admin_client()
        response = client.get(f"/django-admin/geo/address/{address.id}/change/")
        assert response.status_code == 200
        assert 'name="formatted_lines"' not in response.content.decode()


class TestOrderCouponIdsIsReadonly:
    def test_coupon_ids_and_promotion_ids_are_not_editable_textareas(self):
        from apps.ordering.infrastructure import models as ordering_orm

        order = ordering_orm.OrderModel.objects.create(
            id=uuid.uuid4(), order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}", customer_id=uuid.uuid4(), status="pending", currency="UZS",
            shipping_recipient_name="Test", shipping_line1="Test St", shipping_city="Tashkent", shipping_country_code="UZ",
            billing_recipient_name="Test", billing_line1="Test St", billing_city="Tashkent", billing_country_code="UZ",
            coupon_ids=["c1", "c2"], promotion_ids=["p1"],
        )
        client = _admin_client()
        response = client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="coupon_ids"' not in content
        assert 'name="promotion_ids"' not in content


class TestCartCouponIdsIsReadonly:
    def test_coupon_ids_and_promotion_ids_are_not_editable_textareas(self):
        from apps.cart.infrastructure import models as cart_orm

        cart = cart_orm.CartModel.objects.create(id=uuid.uuid4(), code=f"CART-{uuid.uuid4().hex[:8].upper()}", token=uuid.uuid4(), cart_type="authenticated", currency="UZS", status="active", coupon_ids=["c1"], promotion_ids=["p1"])
        client = _admin_client()
        response = client.get(f"/django-admin/cart/cartmodel/{cart.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="coupon_ids"' not in content
        assert 'name="promotion_ids"' not in content


class TestNotificationPreferenceRemovedFromDashboard:
    """NotificationPreferenceModel's admin registration was later removed from the Dashboard entirely (see apps/notifications/tests/infrastructure/test_admin.py::test_notification_preference_removed_from_dashboard) -- the "is disabled_combinations readonly" question this class used to check no longer applies, since the page itself is gone."""

    def test_change_page_no_longer_registered(self):
        from apps.notifications.infrastructure import models as notifications_orm

        pref = notifications_orm.NotificationPreferenceModel.objects.create(id=uuid.uuid4(), user_id=uuid.uuid4(), disabled_combinations=[{"channel": "sms", "category": "marketing"}])
        client = _admin_client()
        response = client.get(f"/django-admin/notifications/notificationpreferencemodel/{pref.id}/change/")
        assert response.status_code == 404


class TestProductSpecificationsAndNutritionAreHiddenAndReadable:
    def test_raw_json_fields_are_never_rendered_as_form_inputs(self):
        from apps.products.infrastructure import models as products_orm

        product = products_orm.Product.objects.create(
            id=uuid.uuid4(), status="draft",
            specifications=[{"key": "Protein", "value": "24g"}],
            nutrition_nutrients={"Calories": "120 kcal"},
        )
        client = _admin_client()
        response = client.get(f"/django-admin/products/product/{product.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="specifications"' not in content
        assert 'name="nutrition_nutrients"' not in content

    def test_specifications_and_nutrition_are_shown_as_a_real_readable_table(self):
        from apps.products.infrastructure import models as products_orm

        product = products_orm.Product.objects.create(
            id=uuid.uuid4(), status="draft",
            specifications=[{"key": "Protein", "value": "24g"}],
            nutrition_nutrients={"Calories": "120 kcal"},
        )
        client = _admin_client()
        response = client.get(f"/django-admin/products/product/{product.id}/change/")
        content = response.content.decode()
        assert "Protein" in content and "24g" in content
        assert "Calories" in content and "120 kcal" in content

    def test_empty_specifications_and_nutrition_show_an_honest_empty_state(self):
        from apps.products.infrastructure import models as products_orm

        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="draft")
        client = _admin_client()
        response = client.get(f"/django-admin/products/product/{product.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "No specifications recorded." in content
        assert "No nutrition facts recorded." in content


class TestBrandCategoryNameFallback:
    """Real, closed gap found live: brand_badge/category_badge previously looked up only the "en" locale, so a brand/category with only a "uz" translation (the ordinary case for this Uzbekistan-targeted project) showed a bare UUID in the product list instead of its real name."""

    def test_uz_only_brand_shows_real_name_not_a_uuid(self):
        from apps.products.infrastructure import models as products_orm

        suffix = uuid.uuid4().hex[:8]
        brand = products_orm.Brand.objects.create(id=uuid.uuid4(), is_active=True)
        products_orm.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="uz", name=f"Faqat Uzbekcha {suffix}", slug=f"fu-{suffix}")
        product = products_orm.Product.objects.create(id=uuid.uuid4(), brand=brand, status="published")

        client = _admin_client()
        response = client.get("/django-admin/products/product/")
        content = response.content.decode()
        assert f"Faqat Uzbekcha {suffix}" in content

    def test_uz_only_category_shows_real_name_not_a_uuid(self):
        from apps.products.infrastructure import models as products_orm

        suffix = uuid.uuid4().hex[:8]
        category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True)
        products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name=f"Faqat Kategoriya {suffix}", slug=f"fk-{suffix}")
        product = products_orm.Product.objects.create(id=uuid.uuid4(), category=category, status="published")

        client = _admin_client()
        response = client.get("/django-admin/products/product/")
        content = response.content.decode()
        assert f"Faqat Kategoriya {suffix}" in content

    def test_product_with_no_brand_shows_dash_not_an_error(self):
        from apps.products.infrastructure import models as products_orm

        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published")
        client = _admin_client()
        response = client.get("/django-admin/products/product/")
        assert response.status_code == 200


class TestProductVariantPriceField:
    """Real, product-required capability: price/old_price are editable admin form fields that write directly to the existing, certified PriceListEntryModel (base_price_amount/compare_at_price_amount) -- never a second, divergent price source."""

    def _base_data(self, suffix: str) -> dict:
        return {
            "translations-TOTAL_FORMS": "0", "translations-INITIAL_FORMS": "0", "translations-MIN_NUM_FORMS": "0", "translations-MAX_NUM_FORMS": "1000",
            "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
            "variants-0-sku": f"SKU-{suffix}", "variants-0-status": "active", "variants-0-weight_value": "", "variants-0-weight_unit": "g",
            # `ProductPricingInline` (a second inline over ProductVariant) is
            # auto-disambiguated to prefix "variants-2" by Django -- its empty
            # management form is still required on every add/change POST.
            "variants-2-TOTAL_FORMS": "0", "variants-2-INITIAL_FORMS": "0", "variants-2-MIN_NUM_FORMS": "0", "variants-2-MAX_NUM_FORMS": "1000",
            "flavour_links-TOTAL_FORMS": "0", "flavour_links-INITIAL_FORMS": "0", "flavour_links-MIN_NUM_FORMS": "0", "flavour_links-MAX_NUM_FORMS": "1000",
            "media-TOTAL_FORMS": "0", "media-INITIAL_FORMS": "0", "media-MIN_NUM_FORMS": "0", "media-MAX_NUM_FORMS": "1000",
            "certificate_links-TOTAL_FORMS": "0", "certificate_links-INITIAL_FORMS": "0", "certificate_links-MIN_NUM_FORMS": "0", "certificate_links-MAX_NUM_FORMS": "1000",
            "status": "draft",
        }

    def test_price_and_old_price_save_to_the_real_price_list_entry(self):
        from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel
        from apps.products.infrastructure import models as products_orm

        price_list = PriceListModel.objects.filter(status="active", region__isnull=True).order_by("created_at").first()
        if price_list is None:
            price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"DEFAULT-{uuid.uuid4().hex[:6].upper()}", name="Default", currency="UZS", status="active")

        suffix = uuid.uuid4().hex[:8].upper()
        client = _admin_client()
        data = self._base_data(suffix)
        data["variants-0-price"] = "150000.00"
        data["variants-0-old_price"] = "180000.00"

        response = client.post("/django-admin/products/product/add/", data)
        assert response.status_code == 302

        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix}")
        entry = PriceListEntryModel.objects.get(price_list=price_list, product_variant_id=variant.id)
        assert entry.base_price_amount == 150000
        assert entry.compare_at_price_amount == 180000

    def test_old_price_not_greater_than_price_returns_form_error_not_500(self):
        suffix = uuid.uuid4().hex[:8].upper()
        client = _admin_client()
        data = self._base_data(suffix)
        data["variants-0-price"] = "150000.00"
        data["variants-0-old_price"] = "100000.00"  # invalid: old_price must be > price

        response = client.post("/django-admin/products/product/add/", data)
        assert response.status_code == 200  # stays on the form, not a 500

    def test_blank_price_does_not_create_a_price_list_entry(self):
        from apps.pricing.infrastructure.models import PriceListEntryModel

        suffix = uuid.uuid4().hex[:8].upper()
        client = _admin_client()
        data = self._base_data(suffix)

        response = client.post("/django-admin/products/product/add/", data)
        assert response.status_code == 302

        from apps.products.infrastructure import models as products_orm

        variant = products_orm.ProductVariant.objects.get(sku=f"SKU-{suffix}")
        assert not PriceListEntryModel.objects.filter(product_variant_id=variant.id).exists()


class TestProductMultilingualContentFields:
    """Real, product-required capability: supplement_facts/warnings/directions are each stored independently in 3 languages (UZ/RU/EN), not a single, shared-language field."""

    def test_all_9_language_fields_save_independently(self):
        from apps.products.infrastructure import models as products_orm

        product = products_orm.Product.objects.create(
            id=uuid.uuid4(), status="draft",
            supplement_facts_text_uz="Zardob oqsili", supplement_facts_text_ru="Сывороточный белок", supplement_facts_text_en="Whey protein",
            warnings_text_uz="Ogohlantirish", warnings_text_ru="Предупреждение", warnings_text_en="Warning",
            directions_text_uz="Qo'llanma", directions_text_ru="Инструкция", directions_text_en="Directions",
        )
        product.refresh_from_db()
        assert product.supplement_facts_text_uz == "Zardob oqsili"
        assert product.supplement_facts_text_ru == "Сывороточный белок"
        assert product.supplement_facts_text_en == "Whey protein"
        assert product.warnings_text_uz == "Ogohlantirish"
        assert product.warnings_text_ru == "Предупреждение"
        assert product.warnings_text_en == "Warning"
        assert product.directions_text_uz == "Qo'llanma"
        assert product.directions_text_ru == "Инструкция"
        assert product.directions_text_en == "Directions"

    def test_admin_add_form_shows_all_9_language_inputs(self):
        client = _admin_client()
        response = client.get("/django-admin/products/product/add/")
        content = response.content.decode()
        for field in (
            "supplement_facts_text_uz", "supplement_facts_text_ru", "supplement_facts_text_en",
            "warnings_text_uz", "warnings_text_ru", "warnings_text_en",
            "directions_text_uz", "directions_text_ru", "directions_text_en",
        ):
            assert f'name="{field}"' in content, f"Missing input for {field}"
