"""
Full-stack API integration tests -- real URL routing, serializers,
views, application services, and repository layer together against a
real database. Matches every prior module's
`tests/interfaces/test_api_integration.py` pattern.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

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
    def test_create_price_list_requires_auth(self, api_client):
        response = api_client.post("/api/v1/pricing/price-lists", {"code": "DEFAULT-UZS", "name": "Default", "currency": "UZS"}, format="json")
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

    def test_create_price_list_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/pricing/price-lists", {"code": "DEFAULT-UZS", "name": "Default", "currency": "UZS"}, format="json")
        assert response.status_code == 403


class TestAuthorizedFlows:
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

    def test_create_price_list(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-001", "name": "Test", "currency": "UZS"}, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "draft"

    def test_create_price_list_duplicate_code_returns_409(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-002", "name": "A", "currency": "UZS"}, format="json")
        response = api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-002", "name": "B", "currency": "UZS"}, format="json")
        assert response.status_code == 409

    def test_list_create_merged_endpoint_both_methods_reachable(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-003", "name": "A", "currency": "UZS"}, format="json")
        assert create_response.status_code == 201

        list_response = api_client.get("/api/v1/pricing/price-lists")
        assert list_response.status_code == 200

    def test_get_price_list_by_code(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-004", "name": "A", "currency": "UZS"}, format="json")
        price_list_id = create_response.json()["data"]["id"]
        api_client.post(f"/api/v1/pricing/admin/price-lists/{price_list_id}/activate", {}, format="json")

        response = api_client.get("/api/v1/pricing/price-lists/code/TEST-UZS-004")
        assert response.status_code == 200
        assert response.json()["data"]["code"] == "TEST-UZS-004"

    def test_response_envelope_has_request_id(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-005", "name": "A", "currency": "UZS"}, format="json")
        assert "request_id" in response.json()["meta"]

    def test_coupon_redemption_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/pricing/admin/coupons", {"code": "APITEST20", "coupon_type": "coupon", "discount_value_type": "percentage", "discount_percentage": "20"}, format="json")
        assert create_response.status_code == 201

        # Coupon starts in draft -- redeem should fail until activated at the domain/repository layer
        # (no dedicated "activate coupon" endpoint exists in this phase's explicit view list).
        from apps.pricing.infrastructure.repositories import DjangoCouponRepository

        repo = DjangoCouponRepository()
        coupon = repo.get_by_code("APITEST20")
        coupon.activate()
        repo.save(coupon)

        redeem_response = api_client.post("/api/v1/pricing/admin/coupons/APITEST20/redeem", {"redeemed_by": str(uuid.uuid4()), "order_reference": "ORDER-API-001"}, format="json", HTTP_IDEMPOTENCY_KEY="test-redeem-apitest20")
        assert redeem_response.status_code == 200
        assert redeem_response.json()["data"]["redemption_count"] == 1

    def test_campaign_lifecycle_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post(
            "/api/v1/pricing/admin/campaigns",
            {"campaign_type": "flash_sale", "name": "API Flash Sale", "discount_value_type": "percentage", "discount_percentage": "30", "starts_at": "2026-01-01T00:00:00Z"},
            format="json",
        )
        assert create_response.status_code == 201
        campaign_id = create_response.json()["data"]["id"]

        activate_response = api_client.post(f"/api/v1/pricing/admin/campaigns/{campaign_id}/activate", {}, format="json")
        assert activate_response.status_code == 200
        assert activate_response.json()["data"]["status"] == "active"

        end_response = api_client.post(f"/api/v1/pricing/admin/campaigns/{campaign_id}/end", {}, format="json")
        assert end_response.status_code == 200
        assert end_response.json()["data"]["status"] == "ended"

    def test_snapshot_lifecycle_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        lock_response = api_client.post("/api/v1/pricing/admin/snapshots", {"product_variant_id": str(uuid.uuid4()), "locked_amount": "49.99", "currency": "UZS"}, format="json")
        assert lock_response.status_code == 201
        snapshot_id = lock_response.json()["data"]["id"]

        consume_response = api_client.post(f"/api/v1/pricing/admin/snapshots/{snapshot_id}/consume", {}, format="json")
        assert consume_response.status_code == 200
        assert consume_response.json()["data"]["status"] == "consumed"

    def test_price_history_endpoint(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/pricing/price-lists", {"code": "TEST-UZS-HIST", "name": "History", "currency": "UZS"}, format="json")
        price_list_id = create_response.json()["data"]["id"]

        variant_id = str(uuid.uuid4())
        set_response = api_client.post(f"/api/v1/pricing/admin/price-lists/{price_list_id}/prices", {"product_variant_id": variant_id, "base_amount": "75.00", "currency": "UZS"}, format="json")
        assert set_response.status_code == 200

        history_response = api_client.get(f"/api/v1/pricing/admin/price-lists/{price_list_id}/history/{variant_id}")
        assert history_response.status_code == 200
        assert len(history_response.json()["data"]) == 1

    def test_full_end_to_end_pricing_workflow(self, api_client):
        """
        The explicitly-required complete workflow: Create Price List ->
        Set Prices -> Activate Price List -> Create Campaign -> Activate
        Campaign -> Create Coupon -> Calculate Price -> Redeem Coupon ->
        Create Price Snapshot -> Consume Snapshot -> Verify Price
        History. (Cashback generation is exercised as a direct domain
        policy call, per the module's own documented one-directional
        design -- there is no dedicated 'generate cashback' endpoint,
        since Pricing only computes the amount and publishes an event;
        it never triggers a wallet credit itself.)
        """
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        # 1. Create Price List
        pl_response = api_client.post("/api/v1/pricing/price-lists", {"code": "E2E-WORKFLOW", "name": "E2E Workflow", "currency": "UZS"}, format="json")
        assert pl_response.status_code == 201
        price_list_id = pl_response.json()["data"]["id"]

        # 2. Set Prices
        variant_id = str(uuid.uuid4())
        set_price_response = api_client.post(f"/api/v1/pricing/admin/price-lists/{price_list_id}/prices", {"product_variant_id": variant_id, "base_amount": "200.00", "currency": "UZS"}, format="json")
        assert set_price_response.status_code == 200

        # 3. Activate Price List
        activate_pl_response = api_client.post(f"/api/v1/pricing/admin/price-lists/{price_list_id}/activate", {}, format="json")
        assert activate_pl_response.status_code == 200
        assert activate_pl_response.json()["data"]["status"] == "active"

        # 4. Create Campaign + 5. Activate Campaign
        campaign_response = api_client.post(
            "/api/v1/pricing/admin/campaigns",
            {"campaign_type": "campaign", "name": "E2E Campaign", "discount_value_type": "percentage", "discount_percentage": "10", "starts_at": "2026-01-01T00:00:00Z", "target_variant_ids": [variant_id]},
            format="json",
        )
        assert campaign_response.status_code == 201
        campaign_id = campaign_response.json()["data"]["id"]
        activate_campaign_response = api_client.post(f"/api/v1/pricing/admin/campaigns/{campaign_id}/activate", {}, format="json")
        assert activate_campaign_response.status_code == 200

        # 6. Create Coupon
        coupon_response = api_client.post("/api/v1/pricing/admin/coupons", {"code": "E2EWORKFLOW", "coupon_type": "coupon", "discount_value_type": "fixed_amount", "discount_fixed_amount": "5.00"}, format="json")
        assert coupon_response.status_code == 201

        # 7. Calculate Price -- campaign applies (EXCLUSIVE stacking_mode is the Campaign default, so only the campaign discount is expected to apply)
        calculate_response = api_client.post("/api/v1/pricing/calculate", {"price_list_id": price_list_id, "product_variant_id": variant_id, "quantity": 1}, format="json")
        assert calculate_response.status_code == 200
        calc_data = calculate_response.json()["data"]
        assert calc_data["base_price"]["amount"] == "200.00"
        assert calc_data["final_price"]["amount"] == "180.00"  # 10% campaign discount

        # 8. Redeem Coupon (activated at the repository layer first, per the same documented gap noted in the coupon-redemption-flow test above)
        from apps.pricing.infrastructure.repositories import DjangoCouponRepository

        coupon_repo = DjangoCouponRepository()
        coupon = coupon_repo.get_by_code("E2EWORKFLOW")
        coupon.activate()
        coupon_repo.save(coupon)
        redeem_response = api_client.post("/api/v1/pricing/admin/coupons/E2EWORKFLOW/redeem", {"redeemed_by": str(uuid.uuid4()), "order_reference": "E2E-ORDER-001"}, format="json", HTTP_IDEMPOTENCY_KEY="test-redeem-e2eworkflow")
        assert redeem_response.status_code == 200

        # 9. Generate Cashback -- direct domain policy call (one-directional, no dedicated endpoint by design)
        from decimal import Decimal

        from apps.pricing.domain.services import CashbackPolicy
        from apps.pricing.domain.value_objects import Money, Percentage

        cashback = CashbackPolicy.calculate(Money(amount=Decimal("180.00"), currency="UZS"), Percentage(value=Decimal("2")))
        assert cashback.amount == Decimal("3.60")

        # 10. Create Price Snapshot
        snapshot_response = api_client.post("/api/v1/pricing/admin/snapshots", {"product_variant_id": variant_id, "locked_amount": "180.00", "currency": "UZS"}, format="json")
        assert snapshot_response.status_code == 201
        snapshot_id = snapshot_response.json()["data"]["id"]

        # 11. Consume Snapshot
        consume_response = api_client.post(f"/api/v1/pricing/admin/snapshots/{snapshot_id}/consume", {}, format="json")
        assert consume_response.status_code == 200
        assert consume_response.json()["data"]["status"] == "consumed"

        # 12. Verify Price History
        history_response = api_client.get(f"/api/v1/pricing/admin/price-lists/{price_list_id}/history/{variant_id}")
        assert history_response.status_code == 200
        assert len(history_response.json()["data"]) == 1
        assert history_response.json()["data"][0]["new_amount"] == "200.00"
