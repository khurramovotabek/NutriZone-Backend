"""
Real-DB tests for `core.channels_auth.jwt_auth_middleware._get_user_from_token`.

Real, closed gap: this middleware used to always resolve to
AnonymousUser regardless of the token supplied (see the module's own
docstring), which meant every WebSocket connection to `apps.chat` was
rejected with code 4401. These tests exercise the fixed resolution
against a real `identity.User` row and a real access token minted by
the same OTP flow apps/identity's own API tests use, not a mocked
token issuer.
"""
from __future__ import annotations

import uuid

import pytest
from channels.db import database_sync_to_async
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as orm
from apps.identity.infrastructure.authentication import IdentityUserProxy
from apps.identity.infrastructure.security import hash_otp_code
from core.channels_auth.jwt_auth_middleware import _get_user_from_token

pytestmark = [
    # `transaction=True`, not the default rollback-per-test `django_db`:
    # the OTP request/verify calls below run through `database_sync_to_async`
    # on a separate thread/connection, which does not participate in
    # pytest-django's default per-test rollback -- without this, the
    # users created here silently commit to the shared test database and
    # leak into unrelated tests (confirmed directly: apps/identity's own
    # user-statistics tests started seeing extra users without it). Same
    # pattern already used by apps/cart, apps/payment, apps/platform for
    # the identical reason (see e.g. apps/payment/tests/interfaces/test_payment_webhook.py).
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.integration,
]


def _issue_real_access_token(phone: str) -> tuple[str, uuid.UUID]:
    """Mints a real access token through the actual OTP request/verify endpoints -- the same "known challenge" pattern apps/identity/tests/interfaces/test_api_authentication_flow.py already uses -- and returns it with the resulting user's id."""
    client = APIClient()
    client.post("/api/v1/identity/auth/request-otp", {"phone_number": phone}, format="json")

    challenge = orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
    challenge.code_hash = hash_otp_code("999999")
    challenge.save(update_fields=["code_hash"])

    response = client.post("/api/v1/identity/auth/verify-otp", {"phone_number": phone, "code": "999999"}, format="json")
    access_token = response.json()["data"]["access_token"]
    return access_token, _user_id_for(phone)


def _user_id_for(phone: str) -> uuid.UUID:
    return orm.User.objects.get(phone_number=phone).id


class TestGetUserFromToken:
    async def test_valid_token_resolves_to_the_real_authenticated_user(self):
        token, user_id = await database_sync_to_async(_issue_real_access_token)("+998901112233")

        user = await _get_user_from_token(token)

        assert isinstance(user, IdentityUserProxy)
        assert user.is_authenticated is True
        assert user.id == user_id

    async def test_missing_token_resolves_to_anonymous(self):
        user = await _get_user_from_token("")

        assert getattr(user, "is_authenticated", False) is False

    async def test_garbage_token_resolves_to_anonymous(self):
        user = await _get_user_from_token("not-a-real-jwt")

        assert getattr(user, "is_authenticated", False) is False

    async def test_blocked_account_resolves_to_anonymous(self):
        token, user_id = await database_sync_to_async(_issue_real_access_token)("+998901112244")
        await database_sync_to_async(orm.User.objects.filter(id=user_id).update)(status="blocked")

        user = await _get_user_from_token(token)

        assert getattr(user, "is_authenticated", False) is False
