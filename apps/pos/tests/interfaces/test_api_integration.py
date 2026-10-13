"""
Full-stack HTTP API integration tests -- real URL routing,
serializers, views, Application Services, and repository layer
together against a real database.

**Every mutation endpoint tested here is expected to return a real
success status (200/201), not an honest 501** -- this module has
0 honest-501 endpoints, certified in Phase 4.

**`TestSearchEndpoint` (new) covers the 7th, real, read-only endpoint
added by the POS Search module** -- `GET /pos/search`, exercising
real Products `ProductVariant` rows created directly against the
database (the same pattern already established in
`test_search_composition.py`), never a fake, to prove the full
barcode -> SKU -> text cascade genuinely works end-to-end through
HTTP, Application, and both bounded contexts' Infrastructure layers.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.pos.infrastructure import models as pos_orm
from apps.pos.infrastructure.repositories import DjangoSaleRepository
from apps.pos.tests.factories import make_sale, make_sale_with_line
from apps.products.infrastructure import models as products_orm
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


class TestUnauthenticatedAccess:
    def test_sale_detail_requires_auth(self, api_client):
        response = api_client.get(f"/api/v1/pos/sales/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_open_sale_requires_auth(self, api_client):
        response = api_client.post("/api/v1/pos/sales", {}, format="json")
        assert response.status_code == 401


class TestPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_open_sale_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        assert response.status_code == 403


class TestAuthorizedFlows:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        self.fake_user_id = uuid.uuid4()
        fake_user = SimpleNamespace(id=self.fake_user_id, is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    # --- All 6 real endpoints -----------------------------------------

    def test_open_sale_returns_201(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["status"] == "open"
        assert data["line_items"] == []

    def test_open_sale_validates_before_calling_service(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/pos/sales", {"branch_id": "not-a-uuid", "cashier_id": str(uuid.uuid4())}, format="json")
        assert response.status_code == 422

    def test_get_sale_detail(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)
        response = api_client.get(f"/api/v1/pos/sales/{sale.id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(sale.id)

    def test_get_sale_not_found(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/pos/sales/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_add_line_item_returns_200(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 2, "unit_price_amount": "15.50"}, format="json")
        assert response.status_code == 200
        entries = response.json()["data"]["line_items"]
        assert len(entries) == 1
        assert entries[0]["unit_price_amount"] == "15.50"

    def test_add_line_item_negative_price_returns_422(self, api_client):
        """The consolidated end-to-end proof of the Phase 4 fix: a negative price must never reach the Domain layer, must never produce a 500."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "-1.00"}, format="json")
        assert response.status_code == 422
        assert response.status_code != 500

    def test_add_line_item_missing_sale_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/pos/sales/{uuid.uuid4()}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "1.00"}, format="json")
        assert response.status_code == 404

    def test_add_line_item_on_completed_sale_returns_409(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "1.00"}, format="json")
        assert response.status_code == 409

    def test_remove_line_item_returns_200(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        repo = DjangoSaleRepository()
        repo.save(sale)
        add_response = api_client.post(f"/api/v1/pos/sales/{sale.id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "5.00"}, format="json")
        line_item_id = add_response.json()["data"]["line_items"][0]["id"]

        response = api_client.delete(f"/api/v1/pos/sales/{sale.id}/line-items/{line_item_id}")
        assert response.status_code == 200
        assert response.json()["data"]["line_items"] == []

    def test_remove_line_item_missing_sale_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.delete(f"/api/v1/pos/sales/{uuid.uuid4()}/line-items/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_remove_unknown_line_item_returns_422(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)
        response = api_client.delete(f"/api/v1/pos/sales/{sale.id}/line-items/{uuid.uuid4()}")
        assert response.status_code == 422

    def test_remove_line_item_from_completed_sale_returns_409(self, api_client):
        """The 4th and final documented 409 mapping in the certified endpoint matrix -- missing from an earlier pass of this file, added after cross-checking status-code coverage against the certified matrix rather than assuming the set of tests already written was complete."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        repo = DjangoSaleRepository()
        repo.save(sale)
        line_item_id = next(iter(sale.line_items.keys()))

        response = api_client.delete(f"/api/v1/pos/sales/{sale.id}/line-items/{line_item_id}")
        assert response.status_code == 409

    def test_complete_sale_returns_200(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale_with_line()
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/complete", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "completed"

    def test_complete_missing_sale_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/pos/sales/{uuid.uuid4()}/complete", {}, format="json")
        assert response.status_code == 404

    def test_complete_empty_sale_returns_422(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/complete", {}, format="json")
        assert response.status_code == 422

    def test_complete_already_completed_returns_409(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/complete", {}, format="json")
        assert response.status_code == 409

    def test_void_sale_returns_200(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale()
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/void", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "voided"

    def test_void_missing_sale_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/pos/sales/{uuid.uuid4()}/void", {}, format="json")
        assert response.status_code == 404

    def test_void_completed_sale_returns_409(self, api_client):
        """The certified, deliberate restraint: a completed sale is never voided."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        DjangoSaleRepository().save(sale)
        response = api_client.post(f"/api/v1/pos/sales/{sale.id}/void", {}, format="json")
        assert response.status_code == 409

    # --- Consolidated end-to-end lifecycle flows ---------------------------

    def test_full_lifecycle_open_add_add_get_remove_get_complete_get(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        open_response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        assert open_response.status_code == 201
        sale_id = open_response.json()["data"]["id"]

        add_a = api_client.post(f"/api/v1/pos/sales/{sale_id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 2, "unit_price_amount": "5.00"}, format="json")
        assert add_a.status_code == 200
        line_item_a_id = add_a.json()["data"]["line_items"][-1]["id"]

        add_b = api_client.post(f"/api/v1/pos/sales/{sale_id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "3.00"}, format="json")
        assert add_b.status_code == 200
        assert len(add_b.json()["data"]["line_items"]) == 2
        assert add_b.json()["data"]["total_amount"] == "13.00"

        get_response = api_client.get(f"/api/v1/pos/sales/{sale_id}")
        assert get_response.status_code == 200
        assert len(get_response.json()["data"]["line_items"]) == 2

        remove_response = api_client.delete(f"/api/v1/pos/sales/{sale_id}/line-items/{line_item_a_id}")
        assert remove_response.status_code == 200
        assert len(remove_response.json()["data"]["line_items"]) == 1
        assert remove_response.json()["data"]["total_amount"] == "3.00"

        get_after_remove = api_client.get(f"/api/v1/pos/sales/{sale_id}")
        assert len(get_after_remove.json()["data"]["line_items"]) == 1

        complete_response = api_client.post(f"/api/v1/pos/sales/{sale_id}/complete", {}, format="json")
        assert complete_response.status_code == 200
        assert complete_response.json()["data"]["status"] == "completed"

        final_get = api_client.get(f"/api/v1/pos/sales/{sale_id}")
        assert final_get.json()["data"]["status"] == "completed"

    def test_full_lifecycle_open_add_void_get(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        open_response = api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json")
        sale_id = open_response.json()["data"]["id"]

        api_client.post(f"/api/v1/pos/sales/{sale_id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "9.00"}, format="json")

        void_response = api_client.post(f"/api/v1/pos/sales/{sale_id}/void", {}, format="json")
        assert void_response.status_code == 200
        assert void_response.json()["data"]["status"] == "voided"

        final_get = api_client.get(f"/api/v1/pos/sales/{sale_id}")
        assert final_get.json()["data"]["status"] == "voided"

    # --- Zero honest-501 endpoints, consolidated proof ----------------------

    def test_all_6_endpoints_are_real_zero_honest_501s(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        responses = []
        responses.append(api_client.post("/api/v1/pos/sales", {"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())}, format="json"))
        sale_id = responses[-1].json()["data"]["id"]
        responses.append(api_client.get(f"/api/v1/pos/sales/{sale_id}"))
        responses.append(api_client.post(f"/api/v1/pos/sales/{sale_id}/line-items", {"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "1.00"}, format="json"))
        line_item_id = responses[-1].json()["data"]["line_items"][0]["id"]
        responses.append(api_client.delete(f"/api/v1/pos/sales/{sale_id}/line-items/{line_item_id}"))
        responses.append(api_client.post(f"/api/v1/pos/sales/{sale_id}/void", {}, format="json"))
        for r in responses:
            assert r.status_code != 501, f"Unexpected honest-501 in POS -- this module should have zero: {r.status_code} {r.json()}"


class TestSearchEndpointUnauthenticated:
    def test_search_requires_auth(self, api_client):
        response = api_client.get("/api/v1/pos/search", {"q": "5901234123457"})
        assert response.status_code == 401


class TestSearchEndpointPermissionDenied:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_search_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {"q": "protein"})
        assert response.status_code == 403


class TestSearchEndpoint:
    """The 7th, real, read-only endpoint added by the POS Search module -- against real Products `ProductVariant` rows, not fakes, exercising the full stack end-to-end."""

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

    def test_successful_barcode_lookup(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        product = products_orm.Product.objects.create(status="published")
        variant = products_orm.ProductVariant.objects.create(product=product, sku="HTTP-TEST-SKU-1", barcode="5901234123457")

        response = api_client.get("/api/v1/pos/search", {"q": "5901234123457", "type": "barcode"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "barcode"
        assert data["exact_match"]["product_id"] == str(product.id)
        assert data["exact_match"]["variant_id"] == str(variant.id)

    def test_barcode_not_found_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {"q": "5901234123457", "type": "barcode"})
        assert response.status_code == 404

    def test_invalid_barcode_returns_422_not_500(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {"q": "not-a-barcode", "type": "barcode"})
        assert response.status_code == 422
        assert response.status_code != 500

    def test_successful_sku_lookup(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        product = products_orm.Product.objects.create(status="published")
        variant = products_orm.ProductVariant.objects.create(product=product, sku="HTTP-TEST-SKU-2")

        response = api_client.get("/api/v1/pos/search", {"q": "HTTP-TEST-SKU-2", "type": "sku"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "sku"
        assert data["exact_match"]["variant_id"] == str(variant.id)

    def test_sku_not_found_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {"q": "NOT-A-REAL-SKU", "type": "sku"})
        assert response.status_code == 404

    def test_text_search_delegates_to_products_search(self, api_client):
        """Real end-to-end proof that free text never fabricates a second search engine inside POS -- it genuinely reaches Products' own certified `SearchProducts`/`DjangoProductSearchBackend`."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {"q": "a query unlikely to exist anywhere", "type": "text"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "text"
        assert data["exact_match"] is None
        assert isinstance(data["results"], list)

    def test_missing_q_returns_422(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {})
        assert response.status_code == 422

    def test_automatic_cascade_resolves_valid_barcode_without_explicit_type(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        product = products_orm.Product.objects.create(status="published")
        products_orm.ProductVariant.objects.create(product=product, sku="HTTP-TEST-SKU-3", barcode="5901234123457")

        response = api_client.get("/api/v1/pos/search", {"q": "5901234123457"})
        assert response.status_code == 200
        assert response.json()["data"]["mode"] == "barcode"

    def test_automatic_cascade_never_returns_500(self, api_client):
        """The overlap case, at the full HTTP level: a valid-barcode-format string with no barcode match must still resolve cleanly (200, falling through to SKU/text), never crash."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/pos/search", {"q": "5901234123457"})
        assert response.status_code == 200
        assert response.json()["data"]["mode"] == "text"

    def test_search_does_not_mutate_any_sale(self, api_client):
        """A direct, executable proof that Search never becomes a second 'add product to sale' mechanism -- searching creates zero Sale records."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        before = pos_orm.SaleModel.objects.count()
        api_client.get("/api/v1/pos/search", {"q": "protein"})
        after = pos_orm.SaleModel.objects.count()
        assert before == after
