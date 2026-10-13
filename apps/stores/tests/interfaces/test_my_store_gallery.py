"""The owner's gallery can remove a photo: the store payload carries each media item's id for DELETE /my-store/media/<id>."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.stores.infrastructure.models import StoreMedia
from apps.stores.tests.interfaces.test_my_store_products import _authenticate_as, _make_owner, _make_store

pytestmark = pytest.mark.django_db


def test_media_ids_in_my_store_and_removing_one(monkeypatch):
    owner = _make_owner(full_name="Galereya Egasi")
    store = _make_store(owner, name="Gallery Test")
    first = StoreMedia.objects.create(store=store, storage_path="image/aa/first.webp", sort_order=0)
    StoreMedia.objects.create(store=store, storage_path="image/bb/second.webp", sort_order=1)
    _authenticate_as(monkeypatch, owner)
    client = APIClient()

    media = client.get("/api/v1/my-store").json()["data"]["media"]
    assert [m["id"] for m in media] == sorted(m.id for m in store.media.all())

    assert client.delete(f"/api/v1/my-store/media/{media[0]['id']}").status_code == 204
    assert not StoreMedia.objects.filter(pk=first.pk).exists()
