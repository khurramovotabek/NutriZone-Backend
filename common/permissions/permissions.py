"""
Permission primitives (Enterprise REST API Blueprint §5/§14).

These are framework-level building blocks only. No permission *code*
(e.g. "wallet.adjustment.manual") is defined here -- the permission
catalogue lives in the `identity` app's domain layer, per the Domain
Architecture Specification §2.1. Every app's `interfaces/api/v1/
permissions.py` composes `HasPermissionCode`/`IsOwnerOrStoreScoped`
with its own module's permission codes (MIC §1 step 11).
"""
from __future__ import annotations

from typing import Any, Protocol

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class PermissionResolver(Protocol):
    """
    The interface `identity`'s application service must implement.

    Wired at app-startup via config (see config/settings/components/
    identity.py placeholder note) once the `identity` module exists --
    at foundation stage this is an interface contract only, with no
    concrete implementation, since no business modules are built yet.
    """

    def user_has_permission(self, user_id: Any, permission_code: str, store_id: Any | None = None) -> bool: ...


class HasPermissionCode(BasePermission):
    """
    Generic permission class: `permission_code` is declared per-view.

    Usage (once `identity` exists):

        class SomeView(APIView):
            permission_classes = [HasPermissionCode]
            required_permission_code = "catalog.product.create"

    A view with no `required_permission_code` declared fails closed
    (denies all access) rather than silently defaulting to "authenticated
    only" -- REST API Blueprint §5's rule that every endpoint must
    explicitly declare its permission is enforced here as a runtime
    fail-closed default, and as a lint rule at CI time (Django
    Implementation Blueprint §12).
    """

    resolver: PermissionResolver | None = None  # wired via app config at startup

    def has_permission(self, request: Request, view: APIView) -> bool:
        code = getattr(view, "required_permission_code", None)
        if code is None:
            return False
        if not request.user or not request.user.is_authenticated:
            return False
        if self.resolver is None:
            # Foundation phase: no PermissionResolver implementation
            # exists yet because `identity` is not implemented. Fail
            # closed rather than silently allow.
            return False
        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return self.resolver.user_has_permission(request.user.id, code, store_id)


class IsOwnerOrStoreScoped(BasePermission):
    """
    Object-level permission: ownership-scoped OR store-scoped access.

    A view sets `owner_field` (e.g. "user_id") and/or `store_scope_field`
    (e.g. "store_id") -- matches REST API Blueprint §5's two object-level
    permission flavors. Concrete field resolution is deferred to each
    module's implementation; this class provides the shared shape only.
    """

    owner_field: str = "user_id"
    store_scope_field: str | None = None

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        owner_id = getattr(obj, self.owner_field, None)
        if owner_id is not None and owner_id == getattr(user, "id", None):
            return True
        if self.store_scope_field:
            store_id = getattr(obj, self.store_scope_field, None)
            user_store_ids = getattr(user, "store_ids", None)
            if store_id is not None and user_store_ids and store_id in user_store_ids:
                return True
        return False
