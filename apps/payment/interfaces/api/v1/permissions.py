from __future__ import annotations

from rest_framework.permissions import BasePermission


class CanCreatePayment(BasePermission):
    """Phase 10: any authenticated customer may create a payment for their own order -- ownership is enforced inside CreatePayment itself (order.customer_id check), matching this project's own established self-service pattern (e.g. geo.Address's AddressOwnerPermission)."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and getattr(request.user, "is_authenticated", False))
