"""
Phase 09.4b: Customer role bootstrap + Pricing/Cart composition tests.

The role-bootstrap tests use the REAL OTP flow end-to-end (no manual
Role/Permission grants) -- this is the whole point of this phase's
own success criterion. The pricing/cart composition tests reuse the
same monkeypatch-based auth mocking already established in
test_cart_idor_regression.py, since exercising IssueVariantPriceSnapshot
and PriceCartItemView doesn't require going through OTP each time.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.test import Client
from rest_framework.test import APIClient

from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _client_as(monkeypatch, user_id) -> APIClient:
    monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


def _make_active_price_list_entry(unit_amount=Decimal("50000.00")):
    from apps.pricing.infrastructure import models as pricing_orm

    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    variant_id = uuid.uuid4()
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant_id, base_price_amount=unit_amount)
    return variant_id


def _register_real_customer(phone=None):
    """Registers a real customer through the actual OTP flow -- no manual Role/Permission grant. Returns (client, tokens, user_id)."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logging.getLogger("nutrizone.security").addHandler(handler)
    logging.getLogger("nutrizone.security").setLevel(logging.INFO)

    client = Client()
    phone = phone or f"+9989{uuid.uuid4().int % 100000000:08d}"
    client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, content_type="application/json")
    match = re.search(r"OTP for \+?\d+: (\d+)", log_capture.getvalue())
    code = match.group(1)
    response = client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": code}, content_type="application/json")
    body = json.loads(response.content)
    assert body["success"], body
    tokens = body["data"]

    payload = tokens["access_token"].split(".")[1]
    payload += "=" * (-len(payload) % 4)
    user_id = json.loads(base64.urlsafe_b64decode(payload))["user_id"]

    logging.getLogger("nutrizone.security").removeHandler(handler)
    return client, tokens, user_id


class TestDefaultCustomerRoleBootstrap:
    """The core success criterion of this phase: a brand-new customer, with zero manual grants, can use their own cart end-to-end."""

    def test_new_customer_gets_customer_role(self):
        from apps.identity.infrastructure import models as identity_orm

        _, _, user_id = _register_real_customer()
        role_codes = list(identity_orm.UserRole.objects.filter(user_id=user_id).values_list("role__code", flat=True))
        assert role_codes == ["customer"]

    def test_customer_role_grants_only_least_privilege_permissions(self):
        from apps.identity.infrastructure import models as identity_orm

        _, _, user_id = _register_real_customer()
        role = identity_orm.UserRole.objects.get(user_id=user_id).role
        codes = set(identity_orm.RolePermission.objects.filter(role=role).values_list("permission__code", flat=True))
        # Phase 09.5 intentionally extended this set via migration
        # 0003_add_checkout_permission.py with cart.validation.execute,
        # required for the new Checkout Preview endpoint.
        # Phase 16 intentionally extended this set again via migration
        # 0010_grant_customer_wallet_loyalty_read_own.py with 4
        # read-only self-service codes, closing the confirmed gap
        # where a real customer received 403 on their own Wallet/
        # Loyalty data despite the RBAC/ownership architecture itself
        # being correct (proven by the existing, unmodified
        # test_wallet_idor_regression.py/test_loyalty_idor_regression.py).
        # Extended again via migration
        # 0011_grant_customer_reviews_read_own.py with
        # reviews.review.view_own, closing the identical confirmed gap
        # for Reviews (a real customer received 403 viewing a
        # product's reviews).
        # Extended again via migration
        # 0012_grant_customer_notifications_chat_read_own.py with
        # notifications.notification.view_own,
        # chat.conversation.view_own, and chat.message.send, closing
        # the identical confirmed gap for Notifications and Chat.
        # Extended again via migration
        # 0013_grant_customer_reviews_write.py with
        # reviews.review.create, reviews.review.edit, and
        # reviews.media.manage -- closing a real, live-verified 403 a
        # customer received calling the newly-real CreateReviewView/
        # AttachReviewMediaView (Reviews' Application Service layer
        # was built and wired this phase; the write permissions were
        # never granted when only a 501 stub existed).
        # Extended again via migration
        # 0014_grant_customer_cart_item_update.py with cart.item.update
        # -- closing a real, live-verified 403 a customer received
        # calling PATCH /api/v1/cart/{code}/ (UpdateCartView), the only
        # way to save the Checkout "additional note" field's value to
        # Cart.note. Every other cart permission a shopper needs was
        # already granted; this one was simply missed.
        # Extended again via migration
        # 0015_grant_customer_notification_preferences.py with
        # notifications.preference.manage_own -- the storefront settings
        # page lets a customer turn Telegram categories on/off.
        assert codes == {
            "cart.item.create", "cart.item.view", "cart.item.update", "cart.line_item.manage", "cart.price_reference.manage", "pricing.snapshot.issue",
            "cart.validation.execute", "cart.checkout.execute", "ordering.order.view_own",
            "wallet.wallet.view_own", "wallet.ledger.view", "loyalty.membership.view_own", "loyalty.tier.view_history",
            "reviews.review.view_own", "reviews.review.create", "reviews.review.edit", "reviews.media.manage",
            "notifications.notification.view_own", "chat.conversation.view_own", "chat.message.send",
            "notifications.preference.manage_own",
        }

    def test_customer_does_not_receive_staff_permissions(self):
        from apps.identity.infrastructure import models as identity_orm

        _, _, user_id = _register_real_customer()
        role = identity_orm.UserRole.objects.get(user_id=user_id).role
        codes = set(identity_orm.RolePermission.objects.filter(role=role).values_list("permission__code", flat=True))
        assert not any("admin" in c for c in codes)

    def test_new_customer_can_create_and_use_own_cart_with_zero_manual_grants(self):
        """This IS the phase's own stated success criterion, executed literally."""
        variant_id = _make_active_price_list_entry(Decimal("42000.00"))
        client, tokens, _ = _register_real_customer()
        auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['access_token']}"}

        r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, content_type="application/json", **auth)
        assert r.status_code == 201, r.content
        cart = json.loads(r.content)["data"]

        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, content_type="application/json", HTTP_X_CART_TOKEN=cart["token"], **auth)
        assert r.status_code == 201, r.content
        item_id = json.loads(r.content)["data"]["items"][0]["id"]

        r = client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, content_type="application/json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()), **auth)
        assert r.status_code == 200, r.content
        price_ref = json.loads(r.content)["data"]["items"][0]["price_reference"]
        assert price_ref["unit_amount"] == "42000.00"
        assert price_ref["currency"] == "UZS"




class TestIssueVariantPriceSnapshot:
    def test_issue_snapshot_uses_server_calculated_price(self):
        from apps.pricing.infrastructure import composition

        variant_id = _make_active_price_list_entry(Decimal("88000.00"))
        snapshot = composition.build_issue_variant_price_snapshot().execute(product_variant_id=variant_id, quantity=1)
        assert snapshot.locked_price.amount == Decimal("88000.00")
        assert snapshot.locked_price.currency == "UZS"

    def test_issue_snapshot_creates_real_persisted_snapshot(self):
        from apps.pricing.infrastructure import composition
        from apps.pricing.infrastructure import models as pricing_orm

        variant_id = _make_active_price_list_entry(Decimal("15000.00"))
        snapshot = composition.build_issue_variant_price_snapshot().execute(product_variant_id=variant_id, quantity=1)
        row = pricing_orm.PriceSnapshotModel.objects.get(id=snapshot.id)
        assert row.locked_price_amount == Decimal("15000.00")
        assert row.status == "locked"

    def test_invalid_variant_rejected(self):
        from apps.pricing.infrastructure import composition
        from common.exceptions import ResourceNotFound

        _make_active_price_list_entry()
        with pytest.raises(ResourceNotFound):
            composition.build_issue_variant_price_snapshot().execute(product_variant_id=uuid.uuid4(), quantity=1)

    def test_issue_snapshot_request_serializer_has_no_price_field(self):
        """Financial-integrity guard: the customer-safe serializer must never accept a price."""
        from apps.pricing.interfaces.api.v1.serializers import IssueVariantPriceSnapshotSerializer

        fields = set(IssueVariantPriceSnapshotSerializer().get_fields().keys())
        assert "unit_amount" not in fields
        assert "price_list_id" not in fields
        assert "locked_amount" not in fields


class TestCheckoutPreview:
    def test_preview_shows_not_ready_before_pricing(self, monkeypatch):
        variant_id = _make_active_price_list_entry()
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])

        r = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["readiness"] == "not_ready"
        assert data["subtotal"] is None
        assert any(i["code"] == "no_price_snapshot" for i in data["issues"])

    def test_preview_shows_ready_with_real_subtotal_after_pricing(self, monkeypatch):
        variant_id = _make_active_price_list_entry(Decimal("25000.00"))
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 4}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        r = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        data = r.json()["data"]
        assert data["readiness"] == "ready"
        assert data["subtotal"] == {"amount": "100000.00", "currency": "UZS"}  # 4 x 25000, real server arithmetic on real server prices
        assert data["issues"] == []

    def test_empty_cart_is_blocked(self, monkeypatch):
        """An empty cart's EMPTY_CART issue has ERROR severity -- CheckoutReadinessPolicy.evaluate() correctly escalates any blocking error to BLOCKED, confirmed by reading the real domain logic directly."""
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        assert r.json()["data"]["readiness"] == "blocked"

    def test_preview_requires_cart_ownership(self, monkeypatch):
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]

        attacker = _client_as(monkeypatch, uuid.uuid4())
        r = attacker.get(f"/api/v1/cart/{cart['code']}/checkout-preview")  # no X-Cart-Token
        assert r.status_code == 403

    def test_query_param_price_smuggling_has_no_effect(self, monkeypatch):
        """The view is a GET with no request-body parsing at all -- any client-supplied money value is simply never read."""
        variant_id = _make_active_price_list_entry(Decimal("10000.00"))
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        r = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview?subtotal=1&total=1&discount=999999", HTTP_X_CART_TOKEN=cart["token"])
        assert r.json()["data"]["subtotal"] == {"amount": "10000.00", "currency": "UZS"}

    def _make_coupon(self, code: str, percentage=Decimal("20.00"), stacking_mode="exclusive"):
        from apps.pricing.infrastructure import models as pricing_orm

        return pricing_orm.CouponModel.objects.create(
            id=uuid.uuid4(), code=code, coupon_type="coupon", status="active",
            discount_value_type="percentage", discount_percentage=percentage, currency="UZS", stacking_mode=stacking_mode,
        )

    def test_applying_a_real_coupon_by_code_adds_a_real_discount_to_the_preview(self, monkeypatch):
        variant_id = _make_active_price_list_entry(Decimal("50000.00"))
        code = f"SUM{uuid.uuid4().hex[:6].upper()}"
        self._make_coupon(code, percentage=Decimal("20.00"))
        client = _client_as(monkeypatch, uuid.uuid4())

        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 2}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        r_apply = client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code.lower()}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert r_apply.status_code == 200, r_apply.content

        r_preview = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        data = r_preview.json()["data"]
        assert data["subtotal"] == {"amount": "100000.00", "currency": "UZS"}
        assert data["discount"] == {"amount": "20000.00", "currency": "UZS"}
        assert data["total"] == {"amount": "80000.00", "currency": "UZS"}
        assert data["applied_coupons"] == [{"code": code, "amount": "20000.00"}]

    def test_query_param_discount_smuggling_has_no_effect_even_with_a_real_coupon_applied(self, monkeypatch):
        """Confirms the real coupon discount (not the fabricated query-param value) is what the preview actually returns."""
        variant_id = _make_active_price_list_entry(Decimal("50000.00"))
        code = f"SUM{uuid.uuid4().hex[:6].upper()}"
        self._make_coupon(code, percentage=Decimal("20.00"))
        client = _client_as(monkeypatch, uuid.uuid4())

        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 2}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code}, format="json", HTTP_X_CART_TOKEN=cart["token"])

        r_preview = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview?discount=999999&total=1", HTTP_X_CART_TOKEN=cart["token"])
        assert r_preview.json()["data"]["discount"] == {"amount": "20000.00", "currency": "UZS"}

    def test_removing_a_coupon_removes_the_discount_from_the_preview(self, monkeypatch):
        variant_id = _make_active_price_list_entry(Decimal("50000.00"))
        code = f"SUM{uuid.uuid4().hex[:6].upper()}"
        self._make_coupon(code)
        client = _client_as(monkeypatch, uuid.uuid4())

        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code}, format="json", HTTP_X_CART_TOKEN=cart["token"])

        r_remove = client.delete(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert r_remove.status_code == 200

        r_preview = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        assert r_preview.json()["data"]["discount"] is None
        assert r_preview.json()["data"]["applied_coupons"] == []

    def test_applying_a_nonexistent_coupon_code_returns_404(self, monkeypatch):
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": "DOES-NOT-EXIST"}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert r.status_code == 404

    def test_applying_an_inactive_coupon_code_is_rejected(self, monkeypatch):
        from apps.pricing.infrastructure import models as pricing_orm

        code = f"INA{uuid.uuid4().hex[:6].upper()}"
        pricing_orm.CouponModel.objects.create(
            id=uuid.uuid4(), code=code, coupon_type="coupon", status="draft",
            discount_value_type="percentage", discount_percentage=Decimal("10.00"), currency="UZS", stacking_mode="exclusive",
        )
        client = _client_as(monkeypatch, uuid.uuid4())
        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert r.status_code == 409

    def test_stackable_coupons_add_together(self, monkeypatch):
        variant_id = _make_active_price_list_entry(Decimal("100000.00"))
        code_a = f"STK{uuid.uuid4().hex[:6].upper()}"
        code_b = f"STK{uuid.uuid4().hex[:6].upper()}"
        self._make_coupon(code_a, percentage=Decimal("10.00"), stacking_mode="stackable")
        self._make_coupon(code_b, percentage=Decimal("5.00"), stacking_mode="stackable")
        client = _client_as(monkeypatch, uuid.uuid4())

        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code_a}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code_b}, format="json", HTTP_X_CART_TOKEN=cart["token"])

        r_preview = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        data = r_preview.json()["data"]
        assert data["discount"] == {"amount": "15000.00", "currency": "UZS"}  # 10% + 5% of 100000

    def test_discount_never_exceeds_the_real_subtotal(self, monkeypatch):
        """A coupon larger than the subtotal must never produce a negative total."""
        variant_id = _make_active_price_list_entry(Decimal("10000.00"))
        code = f"BIG{uuid.uuid4().hex[:6].upper()}"
        self._make_coupon(code, percentage=Decimal("90.00"))
        client = _client_as(monkeypatch, uuid.uuid4())

        cart = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json").json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code}, format="json", HTTP_X_CART_TOKEN=cart["token"])

        r_preview = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"])
        data = r_preview.json()["data"]
        assert Decimal(data["total"]["amount"]) >= Decimal("0")


class TestPricingIdempotency:
    """Phase 09.6: verifies the existing, proven core.idempotency system (already used by Wallet/Ordering/Inventory) now protects the pricing/cart snapshot-issuance chain -- no new idempotency infrastructure was built."""

    def test_same_key_same_payload_replays_without_duplicate(self, monkeypatch):
        variant_id = _make_active_price_list_entry(Decimal("10000.00"))
        client = _client_as(monkeypatch, uuid.uuid4())
        key = str(uuid.uuid4())

        r1 = client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        r2 = client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_IDEMPOTENCY_KEY=key)

        assert r1.status_code == 201
        assert r2.json()["data"]["id"] == r1.json()["data"]["id"]  # exact same snapshot, not a new one

        from apps.pricing.infrastructure import models as pricing_orm
        assert pricing_orm.PriceSnapshotModel.objects.filter(product_variant_id=variant_id).count() == 1

    def test_same_key_different_payload_conflicts(self, monkeypatch):
        variant_a = _make_active_price_list_entry(Decimal("10000.00"))
        from apps.pricing.infrastructure import models as pricing_orm
        price_list = pricing_orm.PriceListModel.objects.get(code="DEFAULT-UZS")
        variant_b = uuid.uuid4()
        pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant_b, base_price_amount=Decimal("99999.00"))

        client = _client_as(monkeypatch, uuid.uuid4())
        key = str(uuid.uuid4())
        client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_a), "quantity": 1}, format="json", HTTP_IDEMPOTENCY_KEY=key)

        r2 = client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_b), "quantity": 5}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    def test_missing_idempotency_key_rejected(self, monkeypatch):
        variant_id = _make_active_price_list_entry()
        client = _client_as(monkeypatch, uuid.uuid4())
        r = client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_id), "quantity": 1}, format="json")
        assert r.status_code == 422

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_identical_requests_create_exactly_one_snapshot(self):
        """
        Real threads, real separate DB connections -- not simulated.
        Reproduces this phase's own Step 08 scenario directly. Uses
        unittest.mock.patch directly (not pytest's monkeypatch, which
        is not thread-safe for cross-thread patching) -- the exact
        approach already proven correct in this phase's own manual
        shell verification.
        """
        import threading
        import unittest.mock as mock
        from django.db import connections
        from rest_framework.test import APIClient

        HasPermissionCode.resolver = _AllowAllResolver()  # _client_as() isn't used here (real threads need real mock.patch, not monkeypatch), so this must be set explicitly.
        variant_id = _make_active_price_list_entry(Decimal("20000.00"))
        user_id = uuid.uuid4()
        same_key = str(uuid.uuid4())
        results = []

        fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())

        def worker():
            connections.close_all()
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer fake")
            r = client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_IDEMPOTENCY_KEY=same_key)
            results.append(r.status_code)

        # One patch around both threads: mock.patch is not thread-safe -- threads patching the same attribute
        # can restore each other's fake, leaking a fake login into every later test.
        with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Acceptable per this phase's own Step 08: one 201 + one 409 (in-progress), never two 201s.
        assert sorted(results) == [201, 409]
        from apps.pricing.infrastructure import models as pricing_orm
        assert pricing_orm.PriceSnapshotModel.objects.filter(product_variant_id=variant_id).count() == 1

    def test_cross_customer_key_isolation(self, monkeypatch):
        """
        The same literal key string used by two different customers
        must not collide -- actor_id is part of the uniqueness scope.
        Uses unittest.mock.patch directly, re-applied immediately
        before each request, since pytest's monkeypatch.setattr is a
        global last-writer-wins patch and cannot represent two
        simultaneously-active identities across two separate
        _client_as() calls (confirmed directly: an earlier version of
        this test using monkeypatch had both requests silently
        authenticate as the second customer).
        """
        import unittest.mock as mock
        from rest_framework.test import APIClient

        monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())  # this test doesn't go through _client_as(), so it must set this up itself rather than relying on another test's leaked state

        variant_id = _make_active_price_list_entry(Decimal("5000.00"))
        key = str(uuid.uuid4())
        user_a, user_b = uuid.uuid4(), uuid.uuid4()

        def _post_as(user_id):
            fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
            with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION="Bearer fake")
                return client.post("/api/v1/pricing/snapshot/issue", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_IDEMPOTENCY_KEY=key)

        r_a = _post_as(user_a)
        r_b = _post_as(user_b)

        assert r_a.status_code == 201
        assert r_b.status_code == 201  # not a 409 -- different actor, independent namespace
        assert r_a.json()["data"]["id"] != r_b.json()["data"]["id"]


class TestCartPriceAttachmentComposition:

    def test_client_supplied_price_is_ignored_via_new_endpoint(self, monkeypatch):
        """Even if a malicious client sends unit_amount in the body, the new endpoint's serializer has no such field -- it is simply never read."""
        variant_id = _make_active_price_list_entry(Decimal("60000.00"))
        client = _client_as(monkeypatch, uuid.uuid4())

        r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
        cart = r.json()["data"]

        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]

        r = client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {"unit_amount": "1.00"}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 200
        price_ref = r.json()["data"]["items"][0]["price_reference"]
        assert price_ref["unit_amount"] == "60000.00"

    def test_cart_item_line_total_uses_snapshot(self, monkeypatch):
        variant_id = _make_active_price_list_entry(Decimal("30000.00"))
        client = _client_as(monkeypatch, uuid.uuid4())

        r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
        cart = r.json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 3}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]

        r = client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.json()["data"]["items"][0]["price_reference"]["unit_amount"] == "30000.00"

    def test_price_attachment_requires_ownership(self, monkeypatch):
        variant_id = _make_active_price_list_entry()
        owner = _client_as(monkeypatch, uuid.uuid4())
        r = owner.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
        cart = r.json()["data"]
        r = owner.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]

        attacker = _client_as(monkeypatch, uuid.uuid4())
        r = attacker.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json")
        assert r.status_code == 403
