"""
Refresh-token reuse grace window (infrastructure/refresh_grace.py): one browser's parallel requests that all carry the
same refresh token get the same new pair -- the storefront no longer has to deduplicate them inside one process.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as orm
from apps.identity.infrastructure import refresh_grace

pytestmark = pytest.mark.django_db
REFRESH = "/api/v1/identity/auth/refresh"


def _login(client: APIClient) -> dict:
    from apps.identity.infrastructure.security import hash_otp_code

    phone = "+99890" + str(uuid.uuid4().int)[:7]
    client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")
    challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
    challenge.code_hash = hash_otp_code("555555")
    challenge.save(update_fields=["code_hash"])
    return client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "555555"}, format="json").json()["data"]


@pytest.fixture
def client(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    return APIClient()


def test_same_token_twice_within_the_window_gets_the_same_pair(client):
    tokens = _login(client)
    first = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    second = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["refresh_token"] == second.json()["data"]["refresh_token"]
    assert first.json()["data"]["session_id"] == second.json()["data"]["session_id"]
    # and the session it opened is alive: the next rotation works
    third = client.post(REFRESH, {"refresh_token": first.json()["data"]["refresh_token"]}, format="json")
    assert third.status_code == 200


def test_after_the_window_reuse_still_revokes_the_family(client):
    tokens = _login(client)
    new = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json").json()["data"]
    from apps.identity.infrastructure.security import SimpleJWTTokenIssuer

    cache.delete(refresh_grace._RESULT + SimpleJWTTokenIssuer().hash_refresh_token(tokens["refresh_token"]))  # window over

    reused = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert reused.status_code == 401
    assert not orm.UserSession.objects.filter(id=new["session_id"], revoked_at__isnull=True).exists()


def test_no_grace_once_the_new_session_was_logged_out(client):
    tokens = _login(client)
    new = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json").json()["data"]
    orm.UserSession.objects.filter(id=new["session_id"]).update(revoked_at=timezone.now())  # logged out

    again = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert again.status_code == 401


def test_a_concurrent_presentation_waits_for_the_running_rotation(client, monkeypatch):
    """While another process holds the lock, this one waits and returns that process's pair."""
    from apps.identity.infrastructure.security import SimpleJWTTokenIssuer

    tokens = _login(client)
    token_hash = SimpleJWTTokenIssuer().hash_refresh_token(tokens["refresh_token"])
    first = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json").json()["data"]
    stored = cache.get(refresh_grace._RESULT + token_hash)
    cache.delete(refresh_grace._RESULT + token_hash)
    cache.set(refresh_grace._LOCK + token_hash, 1, 15)  # "another process is rotating"

    def finish_elsewhere(seconds):  # the other process commits while we wait
        cache.set(refresh_grace._RESULT + token_hash, stored, 30)

    monkeypatch.setattr(refresh_grace.time, "sleep", finish_elsewhere)
    second = client.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert second.status_code == 200 and second.json()["data"]["refresh_token"] == first["refresh_token"]
