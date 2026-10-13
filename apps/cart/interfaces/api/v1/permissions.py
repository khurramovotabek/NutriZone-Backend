"""
Cart API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern -- every class below is a
thin, named wrapper calling `common.permissions.HasPermissionCode.
resolver` with a Cart-specific permission code. No authorization logic
is duplicated here.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class _CartPermission(BasePermission):
    """
    Base class -- subclasses set `permission_code`.

    `allow_anonymous` (real, closed gap): CanManageGuestCart's own
    docstring already stated the intent -- "guest-cart operations
    (create, add items) are deliberately permissive (any anonymous
    session can act on its own guest cart)" -- but every subclass,
    including that one, inherited this base's unconditional
    `not request.user.is_authenticated -> False`, so no anonymous
    request could ever pass any Cart permission check at all. Real
    per-object ownership for a guest cart is enforced separately and
    already existed: `_require_cart_ownership()` validates the
    `X-Cart-Token` header against `Cart.token` with a timing-safe
    comparison. This flag only lets an anonymous request reach that
    real ownership check -- it grants no broader access.
    """

    permission_code: str = ""
    allow_anonymous: bool = False

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return self.allow_anonymous

        from common.permissions import HasPermissionCode

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class CanViewCart(_CartPermission):
    permission_code = "cart.item.view"
    allow_anonymous = True  # real, product-required: a guest must be able to view their own cart, ownership enforced by _require_cart_ownership().


class CanManageCart(_CartPermission):
    """Umbrella admin permission -- used only where no narrower code applies (e.g. cross-cutting admin listing)."""

    permission_code = "cart.item.manage"


class CanCreateCart(_CartPermission):
    permission_code = "cart.item.create"
    allow_anonymous = True  # real, product-required: an anonymous session must be able to create its own guest cart.


class CanUpdateCart(_CartPermission):
    permission_code = "cart.item.update"
    allow_anonymous = True  # real, product-required: a guest must be able to update their own cart's note/gift-message, ownership enforced by _require_cart_ownership().


class CanDeleteCart(_CartPermission):
    permission_code = "cart.item.delete"
    allow_anonymous = True  # real, product-required: a guest must be able to delete/clear their own cart, ownership enforced by _require_cart_ownership().


class CanManageCartItems(_CartPermission):
    permission_code = "cart.line_item.manage"
    allow_anonymous = True  # real, product-required: adding/updating/removing line items (and clearing the cart) must work for a guest, ownership enforced by _require_cart_ownership().


class CanMergeCart(_CartPermission):
    permission_code = "cart.merge.execute"


class CanLockCart(_CartPermission):
    permission_code = "cart.lock.manage"


class CanConvertCart(_CartPermission):
    """Gates transitioning a cart to CONVERTED status -- a future Ordering module's checkout flow would call this; Cart itself has no 'convert' Application Service (that would require Cart to know an Order was created, which it structurally cannot), so this permission currently gates the closest analogous action reachable today: locking a cart for checkout (`CanLockCart`'s CHECKOUT_IN_PROGRESS reason). See Known Limitations in the certification report."""

    permission_code = "cart.convert.execute"


class CanAttachCoupon(_CartPermission):
    permission_code = "cart.coupon_reference.manage"


class CanAttachReservation(_CartPermission):
    permission_code = "cart.reservation_reference.manage"


class CanAttachPriceSnapshot(_CartPermission):
    permission_code = "cart.price_reference.manage"


class CanValidateCart(_CartPermission):
    permission_code = "cart.validation.execute"


class CanViewCartAudit(_CartPermission):
    permission_code = "cart.audit.view"


class CanManageGuestCart(_CartPermission):
    """Distinct from CanManageCart -- guest-cart operations (create, add items) are deliberately permissive (any anonymous session can act on its own guest cart), while admin/support operations on ANY cart require the broader CanManageCart. This code exists so a future policy can grant 'guest self-service' without granting 'staff cart administration.'"""

    permission_code = "cart.guest.manage"
    allow_anonymous = True


class CanSearchCart(_CartPermission):
    permission_code = "cart.search.execute"


class CanCheckoutCart(_CartPermission):
    """Phase 09.7: the new, narrow, customer-safe permission for the checkout-to-order composition -- gates POST /cart/{code}/checkout."""

    permission_code = "cart.checkout.execute"
