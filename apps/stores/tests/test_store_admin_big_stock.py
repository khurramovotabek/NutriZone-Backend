"""A warehouse with many stock rows opens without the per-row stock inline (1 500 autocompletes froze the browser)."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import RequestFactory

from apps.stores.infrastructure import admin as store_admin
from apps.stores.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def test_big_warehouse_skips_stock_inline(monkeypatch):
    from django.contrib.admin.sites import site

    ma = site._registry[orm.Store]
    store = orm.Store.objects.first() or pytest.skip("no store fixture")
    request = RequestFactory().get("/")
    request.user = StaffUser(is_superuser=True, is_staff=True)
    monkeypatch.setattr(ma, "STOCK_INLINE_MAX", -1)
    assert store_admin.StoreProductStockInline not in ma.get_inlines(request, store)
    monkeypatch.setattr(ma, "STOCK_INLINE_MAX", 10**6)
    assert store_admin.StoreProductStockInline in ma.get_inlines(request, store)
