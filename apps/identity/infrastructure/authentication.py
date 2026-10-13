"""
JWT authentication bridging DRF requests to `identity.User`.

Deliberately NOT `rest_framework_simplejwt.authentication.JWTAuthentication`
as-is: that class resolves the token's `user_id` claim against
`settings.AUTH_USER_MODEL`, which stays Django's built-in
`auth.User` reserved for engineering/ops Django Admin access only
(Django Implementation Blueprint §13) -- customers and staff RBAC use
this module's own `identity.User` aggregate instead, a deliberate,
documented split rather than forcing one user model to serve two very
different concerns (password-based engineering login vs. OTP-based
customer/business identity).

Wired as the platform's `DEFAULT_AUTHENTICATION_CLASSES` entry in
config/settings/base.py, replacing the generic SimpleJWT placeholder
used before this module existed.
"""
from __future__ import annotations

import uuid

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.identity.domain.exceptions import AccountBlockedError
from apps.identity.infrastructure.repositories import DjangoRoleAssignmentRepository, DjangoUserRepository


class IdentityUserProxy:
    """
    A thin, DRF-compatible wrapper around the domain `User` aggregate --
    exposes exactly the attributes DRF/permission code expects
    (`is_authenticated`, `id`) plus `store_ids` for
    `common.permissions.IsOwnerOrStoreScoped`'s store-scoping check.
    """

    is_authenticated = True

    def __init__(self, user, store_ids: set[uuid.UUID]) -> None:
        self._user = user
        self.id = user.id
        self.store_ids = store_ids
        self.status = user.status

    @property
    def pk(self):
        """
        DRF's own stock UserRateThrottle (the global
        DEFAULT_THROTTLE_CLASSES entry) calls request.user.pk directly
        in get_cache_key() -- confirmed via direct isolation testing to
        raise AttributeError without this. Any authenticated request to
        a view without an explicit throttle_classes override would 500
        on every successful request. The standard Django convention:
        pk is an alias for the primary key, which here is id.
        """
        return self.id

    def __getattr__(self, item):
        return getattr(self._user, item)


class JWTIdentityAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        """
        Without this, DRF's exception handler cannot tell this
        authenticator apart from one with no real challenge scheme,
        and falls back to 403 for missing/invalid credentials instead
        of 401 -- confirmed as a genuine defect by reproducing it
        directly against a real request. The REST API Blueprint's own
        §5 status-code table is explicit: 401 is "missing/invalid/
        expired authentication" (AUTHENTICATION_REQUIRED); 403 is
        reserved for an authenticated-but-unauthorized request. This
        is the standard DRF mechanism for that exact distinction.
        """
        return "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None

        raw_token = header[len("Bearer "):]
        try:
            token = AccessToken(raw_token)
        except (InvalidToken, TokenError) as exc:
            raise AuthenticationFailed("Token is invalid or expired.") from exc

        user_id_claim = token.get("user_id")
        if not user_id_claim:
            raise AuthenticationFailed("Token does not contain a user identity.")

        try:
            user_id = uuid.UUID(user_id_claim)
        except ValueError as exc:
            raise AuthenticationFailed("Token contains a malformed user identity.") from exc

        user_repo = DjangoUserRepository()
        user = user_repo.get_by_id(user_id)
        if user is None:
            raise AuthenticationFailed("The account for this token no longer exists.")

        try:
            user.assert_can_authenticate()
        except AccountBlockedError as exc:
            raise AuthenticationFailed(str(exc)) from exc

        assignment_repo = DjangoRoleAssignmentRepository()
        store_ids = assignment_repo.list_store_ids_for_user(user_id)

        return (IdentityUserProxy(user, store_ids), token)
