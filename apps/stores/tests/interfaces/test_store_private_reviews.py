"""A store review (written comment) is private feedback: saved with the rating, visible only to its author and to
superadmins in the Dashboard -- never on the public storefront API."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from apps.stores.infrastructure.models import StoreRating
from apps.stores.tests.interfaces.test_store_rating import _authenticate_as, _make_customer, _make_store

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_review_is_saved_private_and_marked_unread(monkeypatch):
    owner, customer = _make_customer(), _make_customer()
    store = _make_store(owner, slug=f"s-{uuid.uuid4().hex[:6]}")
    _authenticate_as(monkeypatch, customer)
    api = APIClient()

    r = api.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 4, "comment": "  Sotuvchi juda xushmuomala, lekin navbat uzun.  "}, format="json")
    assert r.status_code == 200, r.content
    row = StoreRating.objects.get(store=store, customer=customer)
    assert row.comment == "Sotuvchi juda xushmuomala, lekin navbat uzun." and not row.is_read and row.commented_at

    assert api.get(f"/api/v1/stores/{store.slug}/rating").json()["data"]["comment"] == row.comment  # the author sees their own text
    api.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 5}, format="json")  # re-rating without text keeps the review
    row.refresh_from_db()
    assert row.rating == 5 and row.comment

    public = APIClient().get(f"/api/v1/stores/{store.slug}").content.decode() + APIClient().get("/api/v1/stores").content.decode()
    assert "navbat uzun" not in public  # never on the storefront


def test_reviews_admin_is_superadmin_only():
    User = get_user_model()
    staff = User.objects.create_user(username=f"staff{uuid.uuid4().hex[:5]}", password="x", is_staff=True)
    from django.contrib.auth.models import Permission

    staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_storerating", "change_storerating"]))
    boss = User.objects.create_superuser(username=f"boss{uuid.uuid4().hex[:5]}", password="x", email="b@example.com")
    c = Client()
    c.force_login(staff)
    assert c.get("/django-admin/stores/storerating/").status_code in (302, 403)
    c.force_login(boss)
    assert c.get("/django-admin/stores/storerating/").status_code == 200
