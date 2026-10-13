"""
Phase 09.7b: Order Creation hardening tests.

Reuses the exact same monkeypatch/mock.patch auth-mocking conventions
already established in test_pricing_cart_composition.py. Real
database behavior throughout -- transaction.atomic, idempotency, and
DB uniqueness are never mocked, since those are exactly what these
tests prove.
"""
from __future__ import annotations

import threading
import unittest.mock as mock
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _make_geo(country_code="UZ", city_code="CHKCITY1"):
    from apps.geo.infrastructure import models as geo_orm

    country, _ = geo_orm.Country.objects.get_or_create(code=country_code, defaults={"status": "active"})
    region, _ = geo_orm.Region.objects.get_or_create(country=country, code=f"{city_code}R", defaults={"status": "active"})
    city, _ = geo_orm.City.objects.get_or_create(region=region, code=city_code, defaults={"status": "active"})
    geo_orm.CityTranslation.objects.get_or_create(city=city, locale_code="en", defaults={"name": "Test City", "slug": "test-city"})
    return country, city


def _make_user(user_id, phone_suffix):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=user_id, phone_number=f"+99890{phone_suffix:07d}", full_name="Test Customer", status="active")


def _make_address(user_id, country, city, line1="1 Test Street", latitude=None, longitude=None):
    from apps.geo.infrastructure import models as geo_orm

    kwargs = {}
    if latitude is not None:
        kwargs.update(coordinate_latitude=latitude, coordinate_longitude=longitude, coordinate_source="gps")
    return geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=user_id, address_type="residential", country=country, city=city, line1=line1, **kwargs)


def _make_active_price_list_entry(unit_amount=Decimal("40000.00")):
    from apps.pricing.infrastructure import models as pricing_orm

    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    variant_id = uuid.uuid4()
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant_id, base_price_amount=unit_amount)
    return variant_id


def _client_as(monkeypatch, user_id) -> APIClient:
    """Uses pytest's monkeypatch fixture for both patches, which auto-reset after each test -- unlike a raw attribute assignment or an unmatched mock.patch(...).start(), either of which leaks globally across the entire test suite (a real bug this fix corrects, found via 38 unrelated test failures in Store/Wallet)."""
    monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake")
    return client


def _priced_cart(client, variant_id, quantity=1):
    r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
    cart = r.json()["data"]
    r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": quantity}, format="json", HTTP_X_CART_TOKEN=cart["token"])
    item_id = r.json()["data"]["items"][0]["id"]
    r = client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    snapshot_id = r.json()["data"]["items"][0]["price_reference"]["price_snapshot_id"]
    return cart, item_id, snapshot_id


class TestCheckoutHappyPath:
    def test_checkout_carries_the_cart_note_to_the_order(self, monkeypatch):
        """Regression: the note typed at checkout stayed on the cart; staff never saw it on the order."""
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 7)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))
        client = _client_as(monkeypatch, user_id)
        cart, _item_id, _snapshot_id = _priced_cart(client, variant_id)
        r = client.patch(f"/api/v1/cart/{cart['code']}", {"note": "Call before arriving, 3rd floor"}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert r.status_code == 200, r.json()

        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201, r.json()
        assert ordering_orm.OrderModel.objects.get(id=r.json()["data"]["id"]).customer_comment == "Call before arriving, 3rd floor"

    def test_checkout_creates_order_with_correct_data(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 1)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id, quantity=2)

        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201, r.json()
        data = r.json()["data"]

        order_row = ordering_orm.OrderModel.objects.get(id=data["id"])
        assert order_row.order_number == data["order_number"]
        assert order_row.customer_id == user_id
        assert order_row.currency == "UZS"
        assert order_row.status == "pending_payment"
        lines = ordering_orm.OrderLineItemModel.objects.filter(order=order_row)
        assert lines.count() == 1
        line = lines.first()
        assert line.quantity == 2
        assert line.unit_price_amount == Decimal("40000.00")

    def test_checkout_with_an_applied_coupon_creates_an_order_not_a_500(self, monkeypatch):
        """
        Real, closed production bug: `cart.coupon_ids` (apps.cart.domain.
        aggregates.Cart) is a set of real uuid.UUID objects --
        apply_coupon_reference()'s own signature only ever takes
        `coupon_id: uuid.UUID`, confirmed directly against the aggregate.
        `_create_order()` in views.py re-wrapped each already-UUID value
        in `uuid.UUID(c)`, crashing with `AttributeError: 'UUID' object
        has no attribute 'replace'` (uuid.UUID's constructor expects a
        string) the moment any real cart with a coupon applied reached
        checkout -- a real HTTP 500 in production. No prior test in this
        suite or test_coupon_stacking_integration.py exercised checkout
        with a coupon actually attached, which is exactly how this
        shipped unnoticed.
        """
        from apps.ordering.infrastructure import models as ordering_orm
        from apps.pricing.infrastructure import composition as pricing_composition

        country, city = _make_geo(city_code="CHKCITY3")
        user_id = uuid.uuid4()
        _make_user(user_id, 3)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))

        coupon = pricing_composition.build_create_coupon().execute(
            code="CHECKOUT10", coupon_type="coupon", discount_value_type="percentage",
            discount_percentage=Decimal("10"), currency="UZS", stacking_mode="exclusive",
        )
        coupon_repo = pricing_composition.build_coupon_repository()
        live_coupon = coupon_repo.get_by_id(coupon.id)
        live_coupon.activate()
        coupon_repo.save(live_coupon)

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id, quantity=1)

        coupon_resp = client.post(f"/api/v1/cart/{cart['code']}/coupon", {"coupon_id": str(coupon.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert coupon_resp.status_code == 200, coupon_resp.json()

        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201, r.json()  # was a 500 before the fix

        order_row = ordering_orm.OrderModel.objects.get(id=r.json()["data"]["id"])
        assert order_row.status == "pending_payment"

    def test_checkout_copies_real_gps_coordinate_from_address_to_order(self, monkeypatch):
        """Real, closed gap: geo.Address's own coordinate_latitude/longitude previously was never copied into the Order snapshot at all -- OrderModel had no field to hold it."""
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo(city_code="CHKCITY2")
        user_id = uuid.uuid4()
        _make_user(user_id, 2)
        address = _make_address(user_id, country, city, latitude=41.311081, longitude=69.240562)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id, quantity=1)

        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201, r.json()

        order_row = ordering_orm.OrderModel.objects.get(id=r.json()["data"]["id"])
        assert order_row.shipping_latitude == 41.311081
        assert order_row.shipping_longitude == 69.240562

    def test_checkout_without_gps_coordinate_leaves_order_fields_null(self, monkeypatch):
        """An address with no coordinate must not fabricate one on the order."""
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo(city_code="CHKCITY3")
        user_id = uuid.uuid4()
        _make_user(user_id, 3)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id, quantity=1)

        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201, r.json()

        order_row = ordering_orm.OrderModel.objects.get(id=r.json()["data"]["id"])
        assert order_row.shipping_latitude is None
        assert order_row.shipping_longitude is None

    def test_checkout_consumes_price_snapshot(self, monkeypatch):
        from apps.pricing.infrastructure import models as pricing_orm

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 2)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)
        assert pricing_orm.PriceSnapshotModel.objects.get(id=snapshot_id).status == "locked"

        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201

        assert pricing_orm.PriceSnapshotModel.objects.get(id=snapshot_id).status == "consumed"


class TestCheckoutIdempotency:
    def test_same_key_replays_order_without_duplicate(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 3)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)
        key = str(uuid.uuid4())

        before = ordering_orm.OrderModel.objects.count()
        r1 = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=key)
        r2 = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=key)
        after = ordering_orm.OrderModel.objects.count()

        assert r1.status_code == 201
        assert r2.json()["data"]["id"] == r1.json()["data"]["id"]
        assert after == before + 1

    def test_same_key_different_payload_conflicts(self, monkeypatch):
        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 4)
        address_a = _make_address(user_id, country, city, "Address A")
        address_b = _make_address(user_id, country, city, "Address B")
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)
        key = str(uuid.uuid4())

        r1 = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address_a.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=key)
        assert r1.status_code == 201

        r2 = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address_b.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=key)
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    def test_missing_idempotency_key_rejected(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 5)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)

        before = ordering_orm.OrderModel.objects.count()
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        assert r.status_code == 422
        assert ordering_orm.OrderModel.objects.count() == before

    def test_cross_customer_key_isolation(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        _make_user(user_a, 6)
        _make_user(user_b, 7)
        address_a = _make_address(user_a, country, city)
        address_b = _make_address(user_b, country, city)
        variant_id = _make_active_price_list_entry()
        key = str(uuid.uuid4())

        client_a = _client_as(monkeypatch, user_a)
        cart_a, item_a, _ = _priced_cart(client_a, variant_id)
        r_a = client_a.post(f"/api/v1/cart/{cart_a['code']}/checkout", {"shipping_address_id": str(address_a.id)}, format="json", HTTP_X_CART_TOKEN=cart_a["token"], HTTP_IDEMPOTENCY_KEY=key)

        client_b = _client_as(monkeypatch, user_b)
        cart_b, item_b, _ = _priced_cart(client_b, variant_id)
        r_b = client_b.post(f"/api/v1/cart/{cart_b['code']}/checkout", {"shipping_address_id": str(address_b.id)}, format="json", HTTP_X_CART_TOKEN=cart_b["token"], HTTP_IDEMPOTENCY_KEY=key)

        assert r_a.status_code == 201
        assert r_b.status_code == 201
        assert r_a.json()["data"]["id"] != r_b.json()["data"]["id"]
        assert ordering_orm.OrderModel.objects.filter(customer_id__in=[user_a, user_b]).count() == 2


class TestCheckoutOwnership:
    def test_customer_cannot_checkout_using_other_customers_address(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        _make_user(user_a, 8)
        _make_user(user_b, 9)
        address_b = _make_address(user_b, country, city)
        variant_id = _make_active_price_list_entry()

        client_a = _client_as(monkeypatch, user_a)
        cart_a, item_a, _ = _priced_cart(client_a, variant_id)

        before = ordering_orm.OrderModel.objects.count()
        r = client_a.post(f"/api/v1/cart/{cart_a['code']}/checkout", {"shipping_address_id": str(address_b.id)}, format="json", HTTP_X_CART_TOKEN=cart_a["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 404
        assert ordering_orm.OrderModel.objects.count() == before

    def test_checkout_requires_cart_ownership_token(self, monkeypatch):
        country, city = _make_geo()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        _make_user(user_a, 10)
        _make_user(user_b, 11)
        address_a = _make_address(user_a, country, city)
        variant_id = _make_active_price_list_entry()

        client_a = _client_as(monkeypatch, user_a)
        cart_a, item_a, _ = _priced_cart(client_a, variant_id)

        client_b = _client_as(monkeypatch, user_b)
        r = client_b.post(f"/api/v1/cart/{cart_a['code']}/checkout", {"shipping_address_id": str(address_a.id)}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 403


class TestCheckoutFinancialIntegrity:
    def test_client_supplied_financial_fields_are_ignored(self, monkeypatch):
        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 12)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id, quantity=1)

        malicious_body = {
            "shipping_address_id": str(address.id),
            "unit_price": "1.00", "unit_amount": "1.00", "subtotal": "1.00", "total": "1.00",
            "discount": "999999", "discount_amount": "999999", "delivery_fee": "0", "currency": "USD",
        }
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", malicious_body, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201
        assert r.json()["data"]["currency"] == "UZS"

        from apps.ordering.infrastructure import models as ordering_orm
        line = ordering_orm.OrderLineItemModel.objects.get(order_id=r.json()["data"]["id"])
        assert line.unit_price_amount == Decimal("40000.00")


class TestCheckoutConcurrency:
    @pytest.mark.django_db(transaction=True)
    def test_concurrent_same_key_checkout_creates_exactly_one_order(self, monkeypatch):
        from django.db import connections
        from apps.ordering.infrastructure import models as ordering_orm

        monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 13)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        setup_client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(setup_client, variant_id)
        same_key = str(uuid.uuid4())
        results = []

        fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())

        def worker():
            connections.close_all()
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer fake")
            r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=same_key)
            results.append(r.status_code)

        # One patch around both threads: mock.patch is not thread-safe -- threads patching the same attribute
        # can restore each other's fake, leaking a fake login into every later test.
        with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert sorted(results) == [201, 409]
        assert ordering_orm.OrderModel.objects.filter(cart_id=cart["id"]).count() == 1


class TestCheckoutRollback:
    """Phase 09.7c Steps 04-08: mandatory rollback/failure-injection testing."""

    def test_snapshot_consumption_failure_rolls_back_order(self, monkeypatch):
        """
        Forces ConsumePriceSnapshot.execute() to fail AFTER
        CreateOrderFromCart has already persisted the Order within the
        same outer transaction (the idempotency executor's own
        transaction, per its documented contract). Proves Django's
        nested transaction.atomic() savepoint rollback actually works
        end-to-end for this specific call chain -- not assumed from
        reading the decorator alone.
        """
        from apps.ordering.infrastructure import models as ordering_orm
        from apps.pricing.infrastructure import models as pricing_orm
        from apps.pricing.application.services.coupons_bundles_snapshots import ConsumePriceSnapshot

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 15)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)

        def _boom(self, snapshot_id):
            raise RuntimeError("Simulated failure: snapshot consumption service unavailable.")

        monkeypatch.setattr(ConsumePriceSnapshot, "execute", _boom)

        orders_before = ordering_orm.OrderModel.objects.count()
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        # The request must fail cleanly -- not with a fabricated success.
        assert r.status_code >= 400

        # Complete rollback: no Order was committed, despite CreateOrderFromCart's own save() having run before the injected failure.
        assert ordering_orm.OrderModel.objects.count() == orders_before

        # The snapshot must remain LOCKED -- the failed consume attempt must not have partially committed.
        assert pricing_orm.PriceSnapshotModel.objects.get(id=snapshot_id).status == "locked"

    def test_retry_after_failed_checkout_is_allowed(self, monkeypatch):
        """
        Idempotency contract CASE E (core/idempotency/contract.py's own
        docstring): a failed operation's record is marked FAILED, not
        left permanently blocking. A retry with the SAME key after a
        genuine failure must be allowed to succeed once the underlying
        problem is gone -- not permanently locked out by one failed
        attempt. This is the real, documented contract, not invented
        behavior.
        """
        from apps.ordering.infrastructure import models as ordering_orm
        from apps.pricing.application.services.coupons_bundles_snapshots import ConsumePriceSnapshot

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 16)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)
        key = str(uuid.uuid4())

        real_execute = ConsumePriceSnapshot.execute

        def _boom(self, snapshot_id):
            raise RuntimeError("Simulated transient failure.")

        monkeypatch.setattr(ConsumePriceSnapshot, "execute", _boom)
        r1 = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=key)
        assert r1.status_code >= 400
        assert ordering_orm.OrderModel.objects.count() == 0

        # "Fix" the transient failure and retry with the SAME key.
        monkeypatch.setattr(ConsumePriceSnapshot, "execute", real_execute)
        r2 = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=key)
        assert r2.status_code == 201
        assert ordering_orm.OrderModel.objects.count() == 1

    def test_failed_checkout_does_not_stage_order_created_event(self, monkeypatch):
        """A failed checkout must never leave a committed OrderCreated outbox event -- a future Payment module consuming this event must never see a phantom success."""
        from apps.ordering.infrastructure.models import OrderingOutboxEvent
        from apps.pricing.application.services.coupons_bundles_snapshots import ConsumePriceSnapshot

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 17)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)

        events_before = OrderingOutboxEvent.objects.filter(event_type="OrderCreated").count()

        def _boom(self, snapshot_id):
            raise RuntimeError("Simulated failure.")

        monkeypatch.setattr(ConsumePriceSnapshot, "execute", _boom)
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code >= 400

        events_after = OrderingOutboxEvent.objects.filter(event_type="OrderCreated").count()
        assert events_after == events_before  # no phantom success event committed



    def test_checkout_rejects_cart_not_ready(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 14)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
        cart = r.json()["data"]
        client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])

        before = ordering_orm.OrderModel.objects.count()
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CART_NOT_READY"
        assert ordering_orm.OrderModel.objects.count() == before


class TestCheckoutSecurityMatrix:
    def test_anonymous_checkout_denied(self):
        """
        Does NOT call _client_as() at all -- monkeypatch.setattr patches
        authenticate globally for the whole test function's duration, so
        any client created after it (even one with zero credentials)
        would still hit the patched method. Anonymous access must be
        rejected by the permission layer before the cart is even looked
        up, so no real cart needs to exist for this test.
        """
        from apps.ordering.infrastructure import models as ordering_orm
        from rest_framework.test import APIClient

        anon = APIClient()
        before = ordering_orm.OrderModel.objects.count()
        r = anon.post("/api/v1/cart/SOME-CART-CODE/checkout", {"shipping_address_id": str(uuid.uuid4())}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 401
        assert ordering_orm.OrderModel.objects.count() == before

    def test_malformed_cart_code_fails_cleanly(self, monkeypatch):
        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 19)
        address = _make_address(user_id, country, city)

        client = _client_as(monkeypatch, user_id)
        for bad_code in ["not-a-real-code", "X" * 500, "..%2F..%2Fetc%2Fpasswd"]:
            r = client.post(f"/api/v1/cart/{bad_code}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            assert r.status_code < 500, f"cart_code={bad_code!r} produced a real 500: {r.content}"

    def test_malformed_address_id_fails_cleanly(self, monkeypatch):
        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 20)
        variant_id = _make_active_price_list_entry()

        client = _client_as(monkeypatch, user_id)
        cart, item_id, snapshot_id = _priced_cart(client, variant_id)

        for bad_address in ["not-a-uuid", str(uuid.uuid4())]:
            r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": bad_address}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            assert r.status_code < 500, f"address_id={bad_address!r} produced a real 500: {r.content}"
            assert r.status_code in (404, 422)

    def test_order_summary_idor_blocked(self, monkeypatch):
        """Uses the real, already-built OrderSummaryView (GET /orders/{number}/summary) to verify Customer B cannot view Customer A's real order."""
        country, city = _make_geo()
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        _make_user(user_a, 21)
        _make_user(user_b, 22)
        address_a = _make_address(user_a, country, city)
        variant_id = _make_active_price_list_entry()

        client_a = _client_as(monkeypatch, user_a)
        cart_a, item_a, _ = _priced_cart(client_a, variant_id)
        r = client_a.post(f"/api/v1/cart/{cart_a['code']}/checkout", {"shipping_address_id": str(address_a.id)}, format="json", HTTP_X_CART_TOKEN=cart_a["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        order_number = r.json()["data"]["order_number"]

        client_b = _client_as(monkeypatch, user_b)
        r2 = client_b.get(f"/api/v1/ordering/orders/{order_number}/summary")
        assert r2.status_code in (403, 404)
