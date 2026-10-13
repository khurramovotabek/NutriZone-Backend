"""
POS API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern. Fails closed by default.

**A deliberate, disclosed simplicity, matching Analytics' own
precedent**: POS has no per-user ownership concept -- `Sale` has no
field representing "belongs to this specific end user" the way a
Notification does; `cashier_id`/`customer_id` are recorded facts, not
authorization scopes. There is therefore no object-level "is this
mine" check anywhere in this module's views -- every permission here
is a plain, generic capability check, matching Analytics' identical
precedent exactly (re-verified this phase, not assumed).

**Only 2 named permissions exist** -- POS has exactly 1 aggregate,
so `ViewSale`/`ManageSale` covers the full certified surface (`View`
for `LoadSale`; `Manage` for `OpenSale`/`AddLineItem`/
`RemoveLineItem`/`CompleteSale`/`VoidSale`), matching the identical
View/Manage split pattern already established for every single-
aggregate-operation-class in this build.

**A 3rd permission, `SearchProducts`, added for the POS Search
module**: a genuinely distinct read-only capability from viewing an
existing `Sale` -- resolving a barcode/SKU/text query does not
require an existing `Sale` to view at all, so reusing `ViewSale`
would conflate two different authorization concerns.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from common.permissions import HasPermissionCode


class BasePosPermission(BasePermission):
    """Base class -- subclasses set `permission_code`. Fails closed if no code is set."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class ViewSale(BasePosPermission):
    permission_code = "pos.sale.view"


class ManageSale(BasePosPermission):
    """Covers open/add-line-item/remove-line-item/complete/void -- the full Sale lifecycle."""

    permission_code = "pos.sale.manage"


class SearchProducts(BasePosPermission):
    permission_code = "pos.search.view"
