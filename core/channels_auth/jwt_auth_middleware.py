"""
JWT-over-WebSocket authentication middleware (Django Implementation
Blueprint §9).

Validates the same access token used by REST calls during the
WebSocket handshake -- no separate WebSocket-specific auth mechanism,
per REST API Blueprint §4's single authentication standard applying
uniformly across transport.

Real, closed gap: this middleware previously always resolved to
AnonymousUser regardless of the token supplied, deferred pending
`apps.identity`'s User model. That model now exists (with its own real
`JWTIdentityAuthentication` used for HTTP requests, in
apps/identity/infrastructure/authentication.py) -- this middleware
mirrors that exact same resolution (validate the token, read its
`user_id` claim, look the user up via `DjangoUserRepository`, reject a
blocked account) so a WebSocket connection is authenticated by the
identical rule an HTTP request already is, per REST API Blueprint §4's
single-authentication-standard requirement. Confirmed live: this was
the reason `apps.chat`'s ChatConsumer.connect() rejected every
connection with code 4401 (see its own module docstring), since
`scope["user"].is_authenticated` was unconditionally False.
"""
from __future__ import annotations

import uuid
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user_from_token(token: str):
    """Resolves a validated JWT access token to an `IdentityUserProxy`, or `AnonymousUser` if the token is missing, invalid, or names a blocked/nonexistent account."""
    if not token:
        return AnonymousUser()

    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError  # noqa: PLC0415
    from rest_framework_simplejwt.tokens import AccessToken  # noqa: PLC0415

    from apps.identity.domain.exceptions import AccountBlockedError  # noqa: PLC0415
    from apps.identity.infrastructure.authentication import IdentityUserProxy  # noqa: PLC0415
    from apps.identity.infrastructure.repositories import (  # noqa: PLC0415
        DjangoRoleAssignmentRepository,
        DjangoUserRepository,
    )

    try:
        access_token = AccessToken(token)
    except (InvalidToken, TokenError):
        return AnonymousUser()

    user_id_claim = access_token.get("user_id")
    if not user_id_claim:
        return AnonymousUser()

    try:
        user_id = uuid.UUID(user_id_claim)
    except (ValueError, TypeError):
        return AnonymousUser()

    user = DjangoUserRepository().get_by_id(user_id)
    if user is None:
        return AnonymousUser()

    try:
        user.assert_can_authenticate()
    except AccountBlockedError:
        return AnonymousUser()

    store_ids = DjangoRoleAssignmentRepository().list_store_ids_for_user(user_id)
    return IdentityUserProxy(user, store_ids)


class JWTAuthMiddleware:
    """ASGI middleware: resolves `?token=` (or `Authorization` header) into `scope["user"]`."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        token = self._extract_token(scope)
        scope["user"] = await _get_user_from_token(token)
        return await self.inner(scope, receive, send)

    @staticmethod
    def _extract_token(scope) -> str | None:
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization")
        if auth_header:
            decoded = auth_header.decode()
            if decoded.startswith("Bearer "):
                return decoded[len("Bearer "):]

        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token_values = query_params.get("token")
        return token_values[0] if token_values else None


def JWTAuthMiddlewareStack(inner):  # noqa: N802 - matches Channels' naming convention
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
