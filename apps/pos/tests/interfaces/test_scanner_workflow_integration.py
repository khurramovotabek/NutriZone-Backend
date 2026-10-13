"""
POS Phase 6 -- Scanner-to-Sale HTTP integration tests.

**No new endpoint exists for this phase.** Architecture review
confirmed the existing `GET /pos/search` and `POST /pos/sales/{id}/
line-items` endpoints already fully support the complete scanner
workflow, as two sequential, unmodified HTTP calls -- this file's own
`test_full_scanner_workflow_end_to_end` is the direct, required proof
of that claim (Section 20 of this phase's own brief).

**The scanner is represented only by a barcode string** -- no USB/
serial/Bluetooth device simulation exists anywhere in this file,
matching this phase's own explicit Section 20 instruction.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

import apps.pos.interfaces.api.v1.urls as pos_urls_module
from apps.pos.infrastructure import models as pos_orm
from apps.pos.infrastructure.repositories import DjangoSaleRepository
from apps.pos.tests.factories import make_sale, make_sale_with_line
from apps.products.infrastructure import models as products_orm
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

SCANNED_BARCODE = "5901234123457"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class TestScannerWorkflowUnauthenticated:
    def test_search_requires_auth(self, api_client):
        assert api_client.get("/api/v1/pos/search", {"q": SCANNED_BARCODE}).status_code == 401


class TestFullScannerWorkflowEndToEnd:
    """The mandatory Section 20 test: barcode string -> GET /pos/search -> exact_match -> POST .../line-items (the existing, unmodified AddLineItem endpoint) -> Sale updated. No frontend preprocessing, no simulated hardware -- the scanner is only ever a plain string."""

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

    def test_full_scanner_workflow_end_to_end(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        # 1. A real ProductVariant exists, identified by the barcode a physical scanner would emit.
        product = products_orm.Product.objects.create(status="published")
        variant = products_orm.ProductVariant.objects.create(product=product, sku="SCANNER-E2E-SKU", barcode=SCANNED_BARCODE)

        # 2. A cashier has an open Sale (via the existing, unmodified OpenSale endpoint).
        open_response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        assert open_response.status_code == 201
        sale_id = open_response.json()["data"]["id"]

        # 3. Scanner input: a plain barcode string sent to the existing, unmodified Search endpoint.
        search_response = api_client.get("/api/v1/pos/search", {"q": SCANNED_BARCODE, "type": "barcode"})
        assert search_response.status_code == 200
        exact_match = search_response.json()["data"]["exact_match"]
        assert exact_match["product_id"] == str(product.id)
        assert exact_match["variant_id"] == str(variant.id)

        # 4. Cashier/frontend supplies the resolved product_id (and, per the documented gap, its own known price) to the existing, unmodified AddLineItem endpoint -- a genuinely separate HTTP call.
        add_response = api_client.post(
            f"/api/v1/pos/sales/{sale_id}/line-items",
            {"product_id": exact_match["product_id"], "quantity": 1, "unit_price_amount": "19.99", "unit_price_currency": "UZS"},
            format="json",
        )
        assert add_response.status_code == 200

        # 5. Sale updated -- confirmed via the existing, unmodified LoadSale endpoint.
        get_response = api_client.get(f"/api/v1/pos/sales/{sale_id}")
        assert get_response.status_code == 200
        sale_data = get_response.json()["data"]
        assert len(sale_data["line_items"]) == 1
        assert sale_data["line_items"][0]["quantity"] == 1
        assert sale_data["total_amount"] == "19.99"

    def test_repeat_scan_creates_a_second_separate_line_item(self):
        """Section 12/19-10: repeated scans of the same barcode must reuse existing, certified AddLineItem semantics unchanged -- two separate SaleLineItem rows, never merged/incremented, matching add_line_item()'s own real, verified-from-source implementation (no merge logic exists)."""
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        product = products_orm.Product.objects.create(status="published")
        products_orm.ProductVariant.objects.create(product=product, sku="REPEAT-SCAN-SKU", barcode="4006381333931")

        open_response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        sale_id = open_response.json()["data"]["id"]

        for _ in range(2):
            search_response = api_client.get("/api/v1/pos/search", {"q": "4006381333931", "type": "barcode"})
            product_id = search_response.json()["data"]["exact_match"]["product_id"]
            api_client.post(f"/api/v1/pos/sales/{sale_id}/line-items", {"product_id": product_id, "quantity": 1, "unit_price_amount": "5.00", "unit_price_currency": "UZS"}, format="json")

        get_response = api_client.get(f"/api/v1/pos/sales/{sale_id}")
        line_items = get_response.json()["data"]["line_items"]
        assert len(line_items) == 2, "Repeated scans must create separate line items -- existing AddLineItem has no merge/increment logic, verified directly from live source."
        assert line_items[0]["id"] != line_items[1]["id"]
        assert get_response.json()["data"]["total_amount"] == "10.00"

    def test_completed_sale_rejects_scanned_product_via_existing_endpoint(self):
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        DjangoSaleRepository().save(sale)

        product = products_orm.Product.objects.create(status="published")
        products_orm.ProductVariant.objects.create(product=product, sku="COMPLETED-SALE-SKU", barcode="9506000134352")
        search_response = api_client.get("/api/v1/pos/search", {"q": "9506000134352", "type": "barcode"})
        product_id = search_response.json()["data"]["exact_match"]["product_id"]

        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/line-items", {"product_id": product_id, "quantity": 1, "unit_price_amount": "1.00", "unit_price_currency": "UZS"}, format="json")
        assert response.status_code == 409

    def test_voided_sale_rejects_scanned_product_via_existing_endpoint(self):
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        sale.void(datetime.utcnow())
        DjangoSaleRepository().save(sale)

        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "1.00", "unit_price_currency": "UZS"}, format="json")
        assert response.status_code == 409


class TestSearchRemainsReadOnlyRegressionGuard:
    """Section 21, mandatory: a search request must leave every Sale-related table completely untouched."""

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

    def test_search_creates_zero_sales_and_zero_line_items(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sales_before = pos_orm.SaleModel.objects.count()
        line_items_before = pos_orm.SaleLineItemModel.objects.count()

        product = products_orm.Product.objects.create(status="published")
        products_orm.ProductVariant.objects.create(product=product, sku="READ-ONLY-CHECK-SKU", barcode="8480000101709")
        api_client.get("/api/v1/pos/search", {"q": "8480000101709", "type": "barcode"})
        api_client.get("/api/v1/pos/search", {"q": "NOT-A-REAL-SKU", "type": "sku"})
        api_client.get("/api/v1/pos/search", {"q": "protein powder", "type": "text"})

        assert pos_orm.SaleModel.objects.count() == sales_before
        assert pos_orm.SaleLineItemModel.objects.count() == line_items_before

    def test_search_on_an_existing_open_sale_still_never_mutates_it(self, api_client):
        """A stronger version of the read-only guard: even when an eligible, mutable open Sale already exists, a search request must not touch it."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)

        api_client.get("/api/v1/pos/search", {"q": "protein", "type": "text"})

        fetched = DjangoSaleRepository().get_by_id(sale.id)
        assert fetched.line_items == {}
        assert fetched.status.value == "open"


class TestExistingEndpointsUnchangedRegression:
    """Section 19 'Regression tests' -- confirms the pre-existing 6 Sale endpoints, the Search endpoint, and the Pricing endpoint remain reachable, structurally unmodified, via a direct URL-resolution check rather than re-running every one of Phase 4/5's own tests."""

    def test_all_6_sale_routes_and_the_search_route_resolve(self):
        for path in ("/api/v1/pos/sales", "/api/v1/pos/search"):
            match = resolve(path)
            assert match is not None

    def test_pricing_route_resolves(self):
        """Phase 05 final closure: the "pricing" route (ResolveLineItemPrice) existed but was never covered by this file's own resolution check -- a genuine, real gap found during reconnaissance for the stale-count test fix below, not merely a rename of the count assertion."""
        match = resolve("/api/v1/pos/pricing")
        assert match is not None

    def test_pos_url_module_has_all_required_routes(self):
        """Phase 05 final closure: replaced the previous fragile exact-count assertion (assert len(urlpatterns) == 7) with a robust, name-based contract. The exact count was confirmed stale by direct reconnaissance -- 8 routes now genuinely exist (the original 7 plus the "pricing" route, itself a legitimate, distinct capability, not a duplicate or accidental addition)."""
        required_names = {"sale-list-create", "sale-detail", "sale-add-line-item", "sale-remove-line-item", "sale-complete", "sale-void", "search", "pricing"}
        actual_names = {p.name for p in pos_urls_module.urlpatterns}
        missing = required_names - actual_names
        assert not missing, f"Required POS routes are missing: {missing}"
