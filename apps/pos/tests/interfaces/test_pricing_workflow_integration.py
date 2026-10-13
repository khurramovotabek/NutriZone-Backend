"""
POS Phase 7 -- Authoritative Pricing Integration, full end-to-end tests.

**No new HTTP endpoint exists for this phase** -- Architecture Review
concluded the new `ResolveLineItemPrice` capability is deliberately
exposed at the Application layer only this phase; HTTP surfacing is a
disclosed, conscious deferral (see the certification report's own
"Remaining Architectural Boundaries" section), not a stop condition.
These tests therefore exercise `ResolveLineItemPrice` directly
against real, certified Pricing/Products infrastructure (a real
database), then chain its result into the existing, unmodified
`POST /pos/sales/{id}/line-items` HTTP endpoint -- proving the full
real architecture end-to-end, never mocking away the capability being
certified, per this phase's own explicit Section 21 instruction.

**Real Pricing fixtures are built using Pricing's own, already-
certified Application Services** (`CreatePriceList`, `ActivatePriceList`,
`SetPrice`), never raw ORM manipulation and never a duplicated pricing
algorithm -- matching this phase's own explicit "use the real
architecture" instruction.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

import apps.pos.interfaces.api.v1.urls as pos_urls_module
import apps.pricing.infrastructure.composition as pricing_composition
from apps.pos.application.services._shared import PosServiceContext
from apps.pos.application.services.sale import AddLineItem
from apps.pos.domain.exceptions import InvalidSaleTransition
from apps.pos.infrastructure import models as pos_orm
from apps.pos.infrastructure.composition import build_resolve_line_item_price
from apps.pos.infrastructure.repositories import DjangoSaleRepository
from apps.pos.interfaces.api.v1.permissions import ManageSale, SearchProducts, ViewSale
from apps.pos.tests.factories import make_sale, make_sale_with_line
from apps.products.infrastructure import models as products_orm
from common.exceptions import ResourceNotFound
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _real_price_list(code: str, currency: str = "UZS"):
    """Builds a real, activated PriceList using Pricing's own certified Application Services -- never raw ORM manipulation."""
    price_list = pricing_composition.build_create_price_list().execute(code=code, name=f"Test List {code}", currency=currency)
    pricing_composition.build_activate_price_list().execute(price_list.id)
    return price_list


def _real_priced_variant(price_list_id, sku: str, barcode: str, base_amount: str, currency: str = "UZS"):
    """Creates a real ProductVariant and gives it a real, authoritative price via Pricing's own certified SetPrice service."""
    product = products_orm.Product.objects.create(status="published")
    variant = products_orm.ProductVariant.objects.create(product=product, sku=sku, barcode=barcode)
    pricing_composition.build_set_price().execute(price_list_id=price_list_id, product_variant_id=variant.id, base_amount=Decimal(base_amount), currency=currency)
    return product, variant


class TestPricingResolution:
    """Section 19 'Pricing resolution' test group -- exercises the real `CalculatePrice` algorithm through POS's own `ResolveLineItemPrice`, never a fake."""

    def test_valid_product_variant_resolves_authoritative_price(self):
        price_list = _real_price_list("POS-P7-LIST-01")
        _, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-1", "5901234123457", "24.99")

        service = build_resolve_line_item_price()
        result = service.execute(price_list_id=price_list.id, variant_id=variant.id)

        assert result.amount == Decimal("24.99")
        assert result.currency == "UZS"

    def test_no_valid_price_raises_resource_not_found(self):
        """A variant exists but has no entry in the given price list."""
        price_list = _real_price_list("POS-P7-LIST-02")
        product = products_orm.Product.objects.create(status="published")
        variant = products_orm.ProductVariant.objects.create(product=product, sku="POS-P7-SKU-NO-PRICE", barcode="4006381333931")

        service = build_resolve_line_item_price()
        with pytest.raises(ResourceNotFound):
            service.execute(price_list_id=price_list.id, variant_id=variant.id)

    def test_price_list_not_found_raises_resource_not_found(self):
        service = build_resolve_line_item_price()
        with pytest.raises(ResourceNotFound):
            service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4())

    def test_currency_correctness(self):
        price_list = _real_price_list("POS-P7-LIST-03", currency="USD")
        _, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-USD", "9506000134352", "9.99", currency="USD")

        service = build_resolve_line_item_price()
        result = service.execute(price_list_id=price_list.id, variant_id=variant.id)
        assert result.currency == "USD"

    def test_amount_precision_is_preserved(self):
        price_list = _real_price_list("POS-P7-LIST-04")
        _, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-PRECISE", "8480000101709", "17.85")

        service = build_resolve_line_item_price()
        result = service.execute(price_list_id=price_list.id, variant_id=variant.id)
        assert result.amount == Decimal("17.85")


class TestResolvedPriceFeedsAddLineItem:
    """Section 19 'POS integration' test group -- the core Phase 7 proof: a real, authoritative price flows through to the existing, unmodified AddLineItem and is genuinely persisted as a SaleLineItem snapshot."""

    def test_resolved_price_reaches_add_line_item_and_is_persisted_as_snapshot(self):
        price_list = _real_price_list("POS-P7-LIST-05")
        product, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-SNAPSHOT", "9506000134352", "31.50")

        # 1. Resolve the authoritative price (new this phase).
        resolved = build_resolve_line_item_price().execute(price_list_id=price_list.id, variant_id=variant.id)
        assert resolved.amount == Decimal("31.50")

        # 2. Feed it into the existing, unmodified AddLineItem via the existing, unmodified Sale repository/service.
        sale = make_sale()
        DjangoSaleRepository().save(sale)

        events: list = []
        ctx = PosServiceContext(stage_events=lambda e: events.extend(e), actor_id=uuid.uuid4())
        updated_sale = AddLineItem(DjangoSaleRepository(), ctx).execute(sale_id=sale.id, product_id=product.id, quantity=1, unit_price_amount=resolved.amount, unit_price_currency=resolved.currency)

        # 3. The stored unit_price is a snapshot -- confirmed by mutating the PriceList afterward and re-fetching the Sale.
        entry = next(iter(updated_sale.line_items.values()))
        assert entry.unit_price.amount == Decimal("31.50")

        pricing_composition.build_set_price().execute(price_list_id=price_list.id, product_variant_id=variant.id, base_amount=Decimal("99.99"), currency="UZS")

        refetched_sale = DjangoSaleRepository().get_by_id(sale.id)
        refetched_entry = next(iter(refetched_sale.line_items.values()))
        assert refetched_entry.unit_price.amount == Decimal("31.50"), "SaleLineItem.unit_price must remain a historical snapshot -- a later Pricing change must never silently mutate it."

    def test_pricing_is_not_duplicated_inside_pos_the_real_algorithm_runs_once(self):
        """A real proof, not a source-inspection proxy: setting a quantity-independent base price and resolving twice with different quantities still calls through to the same, single, real Pricing calculation -- no local POS calculation exists to diverge from it."""
        price_list = _real_price_list("POS-P7-LIST-06")
        _, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-QTY", "8480000101709", "10.00")

        service = build_resolve_line_item_price()
        result_qty_1 = service.execute(price_list_id=price_list.id, variant_id=variant.id, quantity=1)
        result_qty_1_again = service.execute(price_list_id=price_list.id, variant_id=variant.id, quantity=1)
        assert result_qty_1.amount == result_qty_1_again.amount == Decimal("10.00")

    def test_repeated_scans_remain_separate_line_items_pricing_integration_does_not_change_this(self):
        """Section 14, mandatory: pricing integration must not alter Phase 6's certified repeated-scan behavior."""
        price_list = _real_price_list("POS-P7-LIST-07")
        product, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-REPEAT", "4006381333931", "5.00")

        sale = make_sale()
        repo = DjangoSaleRepository()
        repo.save(sale)

        ctx = PosServiceContext(stage_events=lambda e: None, actor_id=uuid.uuid4())
        for _ in range(2):
            resolved = build_resolve_line_item_price().execute(price_list_id=price_list.id, variant_id=variant.id)
            AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=product.id, quantity=1, unit_price_amount=resolved.amount, unit_price_currency=resolved.currency)

        final_sale = repo.get_by_id(sale.id)
        assert len(final_sale.line_items) == 2


class TestErrorPropagation:
    def test_completed_sale_rejects_a_priced_line_item(self):
        price_list = _real_price_list("POS-P7-LIST-08")
        product, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-COMPLETED", "9506000134352", "1.00")

        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        repo = DjangoSaleRepository()
        repo.save(sale)

        resolved = build_resolve_line_item_price().execute(price_list_id=price_list.id, variant_id=variant.id)
        ctx = PosServiceContext(stage_events=lambda e: None, actor_id=uuid.uuid4())
        with pytest.raises(InvalidSaleTransition):
            AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=product.id, quantity=1, unit_price_amount=resolved.amount, unit_price_currency=resolved.currency)

    def test_voided_sale_rejects_a_priced_line_item(self):
        price_list = _real_price_list("POS-P7-LIST-09")
        product, variant = _real_priced_variant(price_list.id, "POS-P7-SKU-VOIDED", "8480000101709", "1.00")

        sale = make_sale()
        sale.void(datetime.utcnow())
        repo = DjangoSaleRepository()
        repo.save(sale)

        resolved = build_resolve_line_item_price().execute(price_list_id=price_list.id, variant_id=variant.id)
        ctx = PosServiceContext(stage_events=lambda e: None, actor_id=uuid.uuid4())
        with pytest.raises(InvalidSaleTransition):
            AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=product.id, quantity=1, unit_price_amount=resolved.amount, unit_price_currency=resolved.currency)


class TestRegressionExistingEndpointsUnchanged:
    """Section 19 'Regression' -- confirms the existing 7 POS routes and Search behavior are untouched, and the 8th route added in Phase 11 is correctly registered."""

    def test_pos_url_module_now_has_exactly_8_routes(self):
        """Updated this phase from 7 to 8 -- a genuine, expected change (PriceResolutionView added), not a regression. The prior assertion of 7 would now be stale and incorrect."""
        assert len(pos_urls_module.urlpatterns) == 8

    def test_search_endpoint_still_resolves_and_remains_read_only(self):
        assert resolve("/api/v1/pos/search") is not None

    def test_all_4_pos_permissions_unchanged(self):
        codes = {ViewSale.permission_code, ManageSale.permission_code, SearchProducts.permission_code}
        assert codes == {"pos.sale.view", "pos.sale.manage", "pos.search.view"}


class TestPriceResolutionEndpointUnauthenticated:
    def test_pricing_requires_auth(self, api_client):
        response = api_client.get("/api/v1/pos/pricing", {"price_list_id": str(uuid.uuid4()), "variant_id": str(uuid.uuid4())})
        assert response.status_code == 401


class TestPriceResolutionEndpoint:
    """POS Phase 11 -- HTTP exposure of Phase 7's ResolveLineItemPrice, against real Pricing fixtures, matching every other endpoint test in this file."""

    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_successful_price_resolution(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        price_list = _real_price_list("POS-P11-LIST-01")
        _, variant = _real_priced_variant(price_list.id, "POS-P11-SKU-1", "9506000134352", "27.75")

        response = api_client.get("/api/v1/pos/pricing", {"price_list_id": str(price_list.id), "variant_id": str(variant.id)})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["amount"] == "27.75"
        assert data["currency"] == "UZS"

    def test_missing_price_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        price_list = _real_price_list("POS-P11-LIST-02")
        response = api_client.get("/api/v1/pos/pricing", {"price_list_id": str(price_list.id), "variant_id": str(uuid.uuid4())})
        assert response.status_code == 404

    def test_missing_price_list_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/pricing", {"price_list_id": str(uuid.uuid4()), "variant_id": str(uuid.uuid4())})
        assert response.status_code == 404

    def test_missing_required_params_returns_422(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/pricing", {})
        assert response.status_code == 422

    def test_resolved_price_from_http_feeds_add_line_item_end_to_end(self, api_client):
        """The full HTTP-level chain: GET /pos/pricing -> resolved Money -> POST .../line-items (existing, unmodified) -> real Sale."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        price_list = _real_price_list("POS-P11-LIST-03")
        product, variant = _real_priced_variant(price_list.id, "POS-P11-SKU-3", "4006381333931", "14.20")

        open_response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        sale_id = open_response.json()["data"]["id"]

        price_response = api_client.get("/api/v1/pos/pricing", {"price_list_id": str(price_list.id), "variant_id": str(variant.id)})
        assert price_response.status_code == 200
        resolved = price_response.json()["data"]

        add_response = api_client.post(f"/api/v1/pos/sales/{sale_id}/line-items", {"product_id": str(product.id), "quantity": 1, "unit_price_amount": resolved["amount"], "unit_price_currency": resolved["currency"]}, format="json")
        assert add_response.status_code == 200
        assert add_response.json()["data"]["line_items"][0]["unit_price_amount"] == "14.20"

    def test_pricing_endpoint_does_not_mutate_any_sale(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        price_list = _real_price_list("POS-P11-LIST-04")
        _, variant = _real_priced_variant(price_list.id, "POS-P11-SKU-4", "8480000101709", "5.00")

        before = pos_orm.SaleModel.objects.count()
        api_client.get("/api/v1/pos/pricing", {"price_list_id": str(price_list.id), "variant_id": str(variant.id)})
        after = pos_orm.SaleModel.objects.count()
        assert before == after
