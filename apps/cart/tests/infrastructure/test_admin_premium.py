"""Dashboard → Savat: carts list (tabs, customer search, products view), cart card, abandoned-cart reminder, history."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.cart.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def _customer():
    from apps.identity.infrastructure.models import User

    return User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10**7:07d}", full_name="Dilshod Karimov")


def _cart(customer=None, stale=True, items=1):
    from apps.stores.tests.interfaces.test_my_store_products import _make_variant

    c = orm.CartModel.objects.create(code=f"T{uuid.uuid4().hex[:10].upper()}", cart_type="authenticated" if customer else "guest", status="active",
                                     customer_id=customer.id if customer else None)
    for _ in range(items):
        v = _make_variant(barcode=f"470{uuid.uuid4().int % 10**10:010d}", status="active")
        orm.CartItemModel.objects.create(cart=c, product_variant_id=v.id, quantity=2, status="active", added_at=timezone.now())
        orm.CartAuditEntryModel.objects.create(cart=c, action="item_added", occurred_at=timezone.now(), details={"product_variant_id": str(v.id), "quantity": 2})
    if stale:
        orm.CartModel.objects.filter(pk=c.pk).update(updated_at=timezone.now() - timedelta(days=3))
    return c


@pytest.fixture
def boss():
    client = Client()
    client.force_login(StaffUser.objects.create_superuser(username=f"cart_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))
    return client


def test_pages_render_and_search_by_customer(boss):
    customer = _customer()
    c = _cart(customer)
    _cart(None, stale=False)
    for url in ("/django-admin/cart/cartmodel/", "/django-admin/cart/cartmodel/?view=abandoned", "/django-admin/cart/cartmodel/?view=ordered",
                "/django-admin/cart/cartmodel/?view=products", "/django-admin/cart/cartmodel/?view=empty", "/django-admin/cart/cartmodel/?view=all",
                f"/django-admin/cart/cartmodel/{c.pk}/change/", "/django-admin/cart/cartauditentrymodel/", "/django-admin/cart/cartauditentrymodel/?action__exact=item_added"):
        assert boss.get(url).status_code == 200, url
    page = boss.get(f"/django-admin/cart/cartmodel/?view=all&q={customer.phone_number[-7:]}").content.decode()
    assert c.code in page
    assert "Abandoned" in boss.get("/django-admin/cart/cartmodel/?view=abandoned").content.decode()


def test_internal_tables_are_off_the_dashboard(boss):
    for model in ("cartitemmodel", "pricesnapshotreferencemodel", "attachedreservationmodel", "cartsnapshotmodel"):
        assert boss.get(f"/django-admin/cart/{model}/").status_code == 404


def test_reminder_once_a_day(boss, django_capture_on_commit_callbacks):
    from apps.notifications.infrastructure.models import NotificationModel

    customer = _customer()
    c = _cart(customer)
    with django_capture_on_commit_callbacks(execute=True):
        boss.post(f"/django-admin/cart/cartmodel/{c.pk}/remind/")
    assert NotificationModel.objects.filter(recipient_id=customer.id, kind="cart_reminder").count() == 1
    assert orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").count() == 1
    boss.post(f"/django-admin/cart/cartmodel/{c.pk}/remind/")  # second click the same day is refused
    assert orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").count() == 1
    guest = _cart(None)
    boss.post(f"/django-admin/cart/cartmodel/{guest.pk}/remind/")
    assert not orm.CartAuditEntryModel.objects.filter(cart=guest, action="reminder_sent").exists()


def test_ordered_cart_counts_as_ordered_not_abandoned(boss):
    from apps.cart.infrastructure.admin import _ordered_cart_ids
    from apps.ordering.infrastructure.models import OrderModel

    c = _cart(_customer())
    addr = {f"{k}_{f}": v for k in ("shipping", "billing") for f, v in (("recipient_name", "Ali"), ("line1", "Amir Temur 1"), ("city", "Toshkent"), ("country_code", "UZ"))}
    OrderModel.objects.bulk_create([OrderModel(order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}", cart_id=c.id, customer_id=c.customer_id, **addr)])
    assert c.id in _ordered_cart_ids([c.id])
    page = boss.get(f"/django-admin/cart/cartmodel/{c.pk}/change/").content.decode()
    assert "Ordered" in page and "Remind the customer" not in page


def test_weekly_purge_deletes_only_old_empty_guest_carts():
    from apps.cart.infrastructure.tasks import purge_empty_guest_carts
    from apps.ordering.infrastructure.models import OrderModel

    old = timezone.now() - timedelta(days=45)
    empty_old = orm.CartModel.objects.create(code=f"G{uuid.uuid4().hex[:10].upper()}", cart_type="guest", status="active")
    removed_only = _cart(None, items=1)
    orm.CartItemModel.objects.filter(cart=removed_only).update(status="removed")
    empty_new = orm.CartModel.objects.create(code=f"G{uuid.uuid4().hex[:10].upper()}", cart_type="guest", status="active")
    with_items = _cart(None)
    customer_empty = orm.CartModel.objects.create(code=f"G{uuid.uuid4().hex[:10].upper()}", cart_type="authenticated", status="active", customer_id=_customer().id)
    ordered = orm.CartModel.objects.create(code=f"G{uuid.uuid4().hex[:10].upper()}", cart_type="guest", status="active")
    addr = {f"{k}_{f}": v for k in ("shipping", "billing") for f, v in (("recipient_name", "Ali"), ("line1", "x"), ("city", "Toshkent"), ("country_code", "UZ"))}
    OrderModel.objects.bulk_create([OrderModel(order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}", cart_id=ordered.id, **addr)])
    orm.CartModel.objects.filter(id__in=[empty_old.id, removed_only.id, with_items.id, customer_empty.id, ordered.id]).update(updated_at=old)

    assert purge_empty_guest_carts() == 2
    left = set(orm.CartModel.objects.values_list("id", flat=True))
    assert empty_old.id not in left and removed_only.id not in left
    assert {empty_new.id, with_items.id, customer_empty.id, ordered.id} <= left
