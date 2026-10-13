"""
POS Terminal premium redesign -- real, closed gaps:
1. There was no way to change a line item's quantity (only remove);
   the cashier's +/- taps on the cart had nothing to call.
2. Barcode/SKU exact-match search results carried no name/price at
   all, only raw ids.
3. Text-search results carried no variant_id, but every downstream
   POS call (price, add_line_item) is variant-scoped.

Two real, pre-existing bugs were also found and fixed while building
this: `pos_api_add_line_item` never converted `unit_price_amount` to
Decimal (a TypeError inside Money's own comparison -- add_line_item
was silently broken for every real caller), and the new
SaleLineItemQuantityUpdated event was never registered in the Domain
Event Catalogue (a hard failure per this project's own MIC §7 rule).
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

EAN13_BARCODE = "4006381333931"  # real, checksum-valid EAN-13 (Barcode value object validates the real checksum, not just format)


@pytest.fixture
def staff_client():
    AuthUser = get_user_model()
    user = AuthUser.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


def _make_branch() -> uuid.UUID:
    """POS's own Sale domain aggregate treats branch_id as a bare UUID reference (never a foreign key) -- confirmed directly against apps/pos/domain/aggregates.py. Now that Store has been removed from the project, no real Branch model exists to create; any real UUID satisfies the same contract."""
    return uuid.uuid4()


def _make_product_with_variant(name: str, barcode: str | None = None):
    suffix = uuid.uuid4().hex[:8].upper()
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=f"{name.lower().replace(' ', '-')}-{suffix.lower()}")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix}", barcode=barcode, is_default=True)
    return product, variant


class TestBarcodeSearchReturnsRealDisplayData:
    def test_barcode_exact_match_returns_real_name_and_price(self, staff_client):
        from decimal import Decimal as D

        from apps.pricing.infrastructure import models as pricing_orm

        suffix = uuid.uuid4().hex[:8].upper()
        product, variant = _make_product_with_variant("Whey Protein 2kg", barcode=EAN13_BARCODE)
        price_list = pricing_orm.PriceListModel.objects.create(id=uuid.uuid4(), code=f"PL-{suffix}", name="Retail", currency="UZS", status="active")
        pricing_orm.PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount=D("250000.00"))

        response = staff_client.get(f"/django-admin/pos/terminal/api/search?q={EAN13_BARCODE}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["exact_match"]["name"] == "Whey Protein 2kg"
        assert data["exact_match"]["display_price"] is not None


class TestTextSearchReturnsRealVariantId:
    def test_text_search_result_carries_the_real_default_variant_id(self, staff_client):
        unique_name = f"UniqueSearchName{uuid.uuid4().hex[:8]}"
        product, variant = _make_product_with_variant(unique_name)

        response = staff_client.get(f"/django-admin/pos/terminal/api/search?q={unique_name}")
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert len(results) == 1
        assert results[0]["variant_id"] == str(variant.id)


class TestUpdateLineItemQuantity:
    def test_add_line_item_persists_with_a_real_decimal_price(self, staff_client):
        """Regression for a real, pre-existing bug: unit_price_amount was never converted to Decimal, causing a TypeError inside Money's own comparison -- add_line_item was silently broken for every real caller before this fix."""
        branch = _make_branch()
        product, _variant = _make_product_with_variant("Creatine")

        open_response = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json")
        assert open_response.status_code == 201
        sale_id = open_response.json()["data"]["id"]

        add_response = staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items",
            data=json.dumps({"product_id": str(product.id), "quantity": 1, "unit_price_amount": "250000.00", "unit_price_currency": "UZS"}),
            content_type="application/json",
        )
        assert add_response.status_code in (200, 201), add_response.content
        assert add_response.json()["data"]["line_items"][0]["quantity"] == 1

    def test_update_quantity_changes_the_same_line_item_not_a_new_one(self, staff_client):
        branch = _make_branch()
        product, _variant = _make_product_with_variant("Creatine 2")

        sale_id = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json").json()["data"]["id"]
        add_response = staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items",
            data=json.dumps({"product_id": str(product.id), "quantity": 1, "unit_price_amount": "250000.00", "unit_price_currency": "UZS"}),
            content_type="application/json",
        )
        line_item_id = add_response.json()["data"]["line_items"][0]["id"]

        update_response = staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items/{line_item_id}/quantity",
            data=json.dumps({"quantity": 5}),
            content_type="application/json",
        )
        assert update_response.status_code == 200
        data = update_response.json()["data"]
        assert len(data["line_items"]) == 1
        assert data["line_items"][0]["id"] == line_item_id
        assert data["line_items"][0]["quantity"] == 5
        assert data["total_amount"] == "1250000.00"

    def test_update_quantity_to_zero_is_rejected(self, staff_client):
        branch = _make_branch()
        product, _variant = _make_product_with_variant("Creatine 3")

        sale_id = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json").json()["data"]["id"]
        add_response = staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items",
            data=json.dumps({"product_id": str(product.id), "quantity": 1, "unit_price_amount": "250000.00", "unit_price_currency": "UZS"}),
            content_type="application/json",
        )
        line_item_id = add_response.json()["data"]["line_items"][0]["id"]

        response = staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items/{line_item_id}/quantity",
            data=json.dumps({"quantity": 0}),
            content_type="application/json",
        )
        assert response.status_code != 200

    def test_update_quantity_event_is_registered_in_the_domain_event_catalogue(self):
        """Regression for a real, pre-existing gap: this new event type must be registered, or every real emission fails with a hard EventContractError per this project's own MIC §7 rule."""
        from core.events import registry

        assert "SaleLineItemQuantityUpdated" in registry.all_event_types()


class TestPosTerminalPremiumFrontend:
    """Real, live-verified regression test for the previously disclosed frontend gaps: no quantity +/- controls (only remove), no price shown on product cards, an inline <style> block instead of the shared design system, and no loading/success feedback. Later upgraded to the full premium redesign (dedicated nutrizone-pos.css, real product images/brand/weight/stock, category navigation, customer search, cash checkout with change calculation, success screen)."""

    def test_page_renders_quantity_controls_and_price_display(self, staff_client):
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "pos-qty-inc" in content
        assert "pos-qty-dec" in content
        assert "display_price" in content

    def test_page_has_no_inline_style_block(self, staff_client):
        """Confirms the previously disclosed gap is closed: every pos-* rule lives in the dedicated nutrizone-pos.css design system, not duplicated inline."""
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        assert "<style>" not in response.content.decode()

    def test_page_has_loading_and_success_feedback_elements(self, staff_client):
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        content = response.content.decode()
        assert "pos-skeleton" in content
        assert "pos-success-overlay" in content
        assert "toast-success" in content or '"success"' in content


class TestPosDisplayInfoEnrichment:
    """Real, live-verified regression test for the full POS premium redesign spec: real product images, brand name, weight ("size"), and stock must be genuinely computed from existing data, never fabricated."""

    def test_pos_display_info_returns_real_brand_weight_and_stock(self):
        from apps.products.infrastructure.selectors import ProductDetailSelector
        from apps.products.tests.stock_helpers import put_stock

        suffix = uuid.uuid4().hex[:8].upper()
        brand = p_models.Brand.objects.create(id=uuid.uuid4(), is_active=True)
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name="Optimum Nutrition", slug=f"on-{suffix.lower()}")
        product = p_models.Product.objects.create(id=uuid.uuid4(), brand=brand, status="published")
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix}", is_default=True, weight_value=2270, weight_unit="g")
        put_stock(variant.id, 24)

        info = ProductDetailSelector().get_pos_display_info([product.id])
        result = info[str(product.id)]
        assert result["brand_name"] == "Optimum Nutrition"
        assert result["weight_value"] == 2270
        assert result["weight_unit"] == "g"
        assert result["available_quantity"] == 24

    def test_product_with_no_brand_or_stock_reports_none_not_an_error(self):
        from apps.products.infrastructure.selectors import ProductDetailSelector

        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=True)

        info = ProductDetailSelector().get_pos_display_info([product.id])
        result = info[str(product.id)]
        assert result["brand_name"] is None
        assert result["available_quantity"] is None


class TestPosBrowseByCategory:
    def test_browse_with_category_id_returns_only_matching_products(self, staff_client):
        suffix = uuid.uuid4().hex[:8].upper()
        category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True)
        product = p_models.Product.objects.create(id=uuid.uuid4(), category=category, status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=f"Category Scoped {suffix}", slug=f"cs-{suffix.lower()}")
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix}", is_default=True)

        response = staff_client.get(f"/django-admin/pos/terminal/api/browse?category_id={category.id}")
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert len(results) == 1
        assert results[0]["name"] == f"Category Scoped {suffix}"

    def test_browse_without_category_returns_all_published_products(self, staff_client):
        response = staff_client.get("/django-admin/pos/terminal/api/browse")
        assert response.status_code == 200
        assert "results" in response.json()["data"]


class TestPosCustomerSelection:
    def test_open_sale_accepts_a_real_customer_id(self, staff_client):
        from apps.identity.infrastructure.models import User

        suffix = uuid.uuid4().hex[:8].upper()
        branch = _make_branch()
        customer = User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name=f"Test Customer {suffix}")

        response = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch), "customer_id": str(customer.id)}), content_type="application/json")
        assert response.status_code == 201
        assert response.json()["data"]["customer_id"] == str(customer.id)

    def test_open_sale_without_customer_id_still_works(self, staff_client):
        branch = _make_branch()

        response = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json")
        assert response.status_code == 201
        assert response.json()["data"]["customer_id"] is None

    def test_customer_search_finds_by_partial_name(self, staff_client):
        from apps.identity.infrastructure.models import User

        suffix = uuid.uuid4().hex[:8]
        User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name=f"UniqueSearchable{suffix}")

        response = staff_client.get(f"/django-admin/pos/terminal/api/customer-search?q=UniqueSearchable{suffix}")
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 1


class TestPosTwoStepCheckoutFrontend:
    """Real, closed gap: the terminal (browse/scan/build-cart) and checkout (customer + payment) were previously one single screen -- the premium redesign's own explicit product requirement is a genuine two-step flow, matching a real cashier's own two-phase workflow."""

    def test_page_renders_both_terminal_and_checkout_screens(self, staff_client):
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="pos-step-terminal"' in content
        assert 'id="pos-step-checkout"' in content
        assert 'id="pos-goto-checkout-btn"' in content
        assert 'id="pos-checkout-back-btn"' in content

    def test_page_renders_new_customer_quick_create_form(self, staff_client):
        """Checkout collects the buyer inline: phone (required) + full name (optional) -- the customer is found-or-created when the order is completed."""
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        content = response.content.decode()
        assert 'id="pos-customer-new-form"' in content
        assert 'id="pos-customer-phone"' in content
        assert 'id="pos-customer-name"' in content
        assert "customer-create" in content


class TestPosCustomerQuickCreate:
    """Real, closed gap: `Sale.customer_id` is a real `identity.User` reference with no free-text guest name/phone fallback -- a genuinely new walk-in buyer had no way to be recorded at all before this."""

    def test_creates_a_brand_new_customer_by_phone_and_name(self, staff_client):
        from apps.identity.infrastructure.models import User

        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        response = staff_client.post(
            "/django-admin/pos/terminal/api/customer-create", data=json.dumps({"full_name": "Yangi Xaridor", "phone_number": phone}), content_type="application/json"
        )
        assert response.status_code == 201, response.content
        data = response.json()["data"]
        assert data["created"] is True
        assert User.objects.filter(id=data["id"], phone_number=phone, full_name="Yangi Xaridor").exists()

    def test_returns_the_existing_customer_when_phone_already_registered(self, staff_client):
        from apps.identity.infrastructure.models import User

        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        existing = User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", full_name="Real Existing Name")

        response = staff_client.post(
            "/django-admin/pos/terminal/api/customer-create", data=json.dumps({"full_name": "A Cashier Typo", "phone_number": phone}), content_type="application/json"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["created"] is False
        assert data["id"] == str(existing.id)
        assert data["full_name"] == "Real Existing Name"  # never overwritten by a cashier's typo


class TestPosSetSaleCustomer:
    """Real, closed gap: `Sale.customer_id` was only ever settable at `open()` time -- the premium checkout screen selects/creates the buyer well after that, once the cart is already built."""

    def test_attaches_a_real_customer_to_an_already_open_sale(self, staff_client):
        from apps.identity.infrastructure.models import User

        branch = _make_branch()
        customer = User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Checkout Customer")
        sale_id = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json").json()["data"]["id"]

        response = staff_client.post(f"/django-admin/pos/terminal/api/sales/{sale_id}/customer", data=json.dumps({"customer_id": str(customer.id)}), content_type="application/json")
        assert response.status_code == 200, response.content
        assert response.json()["data"]["customer_id"] == str(customer.id)


class TestPosInventoryDecrementOnComplete:
    """Real, closed gap: `CompleteSale` (apps/pos/application/services/sale.py) only ever persisted the Sale itself -- nothing anywhere in this codebase (POS or the regular online checkout) ever decremented real warehouse stock. A cash register that never reduces stock is not usable."""

    def test_completing_a_sale_decrements_real_warehouse_stock(self, staff_client):
        from apps.inventory.infrastructure import models as inv_models

        branch = _make_branch()
        product, variant = _make_product_with_variant("Stock-Tracked Item")
        inventory = inv_models.InventoryModel.objects.create(id=uuid.uuid4(), code=f"INV-{uuid.uuid4().hex[:8].upper()}", product_variant_id=variant.id)
        warehouse_row = inv_models.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=uuid.uuid4(), available_quantity=10)

        sale_id = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json").json()["data"]["id"]
        staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items",
            data=json.dumps({"product_id": str(product.id), "quantity": 4, "unit_price_amount": "10000.00", "unit_price_currency": "UZS"}),
            content_type="application/json",
        )

        response = staff_client.post(f"/django-admin/pos/terminal/api/sales/{sale_id}/complete", data="{}", content_type="application/json")
        assert response.status_code == 200, response.content

        warehouse_row.refresh_from_db()
        assert warehouse_row.available_quantity == 6

    def test_completing_a_sale_for_an_untracked_product_never_fails(self, staff_client):
        """A product with no InventoryModel row at all (never inventory-tracked) must never block a real, already-paid sale from completing."""
        branch = _make_branch()
        product, _variant = _make_product_with_variant("Untracked Item")
        sale_id = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json").json()["data"]["id"]
        staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items",
            data=json.dumps({"product_id": str(product.id), "quantity": 1, "unit_price_amount": "10000.00", "unit_price_currency": "UZS"}),
            content_type="application/json",
        )

        response = staff_client.post(f"/django-admin/pos/terminal/api/sales/{sale_id}/complete", data="{}", content_type="application/json")
        assert response.status_code == 200, response.content


class TestPosTerminalCardPayments:
    """Dashboard POS takes Uzcard/Humo as well as cash: the method and the full amount are recorded on the sale."""

    def _sale_with_line(self, staff_client, qty=2, price="45000.00"):
        branch = _make_branch()
        product, _variant = _make_product_with_variant("Card Paid Item")
        sale_id = staff_client.post("/django-admin/pos/terminal/api/open-sale", data=json.dumps({"branch_id": str(branch)}), content_type="application/json").json()["data"]["id"]
        staff_client.post(
            f"/django-admin/pos/terminal/api/sales/{sale_id}/line-items",
            data=json.dumps({"product_id": str(product.id), "quantity": qty, "unit_price_amount": price, "unit_price_currency": "UZS"}),
            content_type="application/json",
        )
        return sale_id

    def test_uzcard_sale_records_method_and_amount_including_delivery(self, staff_client):
        from apps.pos.infrastructure.models import SaleModel

        sale_id = self._sale_with_line(staff_client)
        body = json.dumps({"payment_method": "uzcard", "delivery_fee": 15000})
        response = staff_client.post(f"/django-admin/pos/terminal/api/sales/{sale_id}/complete", data=body, content_type="application/json")
        assert response.status_code == 200, response.content
        sale = SaleModel.objects.get(id=sale_id)
        assert sale.payment_method == "uzcard"
        assert sale.payments == [{"method": "uzcard", "amount": "105000.00"}]
        assert sale.change_amount == 0

    def test_cash_stays_the_default(self, staff_client):
        from apps.pos.infrastructure.models import SaleModel

        sale_id = self._sale_with_line(staff_client)
        assert staff_client.post(f"/django-admin/pos/terminal/api/sales/{sale_id}/complete", data="{}", content_type="application/json").status_code == 200
        assert SaleModel.objects.get(id=sale_id).payment_method == "cash"

    def test_unknown_method_is_rejected_before_completing(self, staff_client):
        from apps.pos.infrastructure.models import SaleModel

        sale_id = self._sale_with_line(staff_client)
        response = staff_client.post(f"/django-admin/pos/terminal/api/sales/{sale_id}/complete", data=json.dumps({"payment_method": "payme"}), content_type="application/json")
        assert response.status_code == 422
        assert SaleModel.objects.get(id=sale_id).status == "open"
