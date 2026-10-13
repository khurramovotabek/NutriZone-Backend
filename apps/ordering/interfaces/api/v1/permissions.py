"""
Ordering API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern -- every class below is a
thin, named wrapper calling `common.permissions.HasPermissionCode.
resolver` with an Ordering-specific permission code. No authorization
logic is duplicated here.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class _OrderingPermission(BasePermission):
    """Base class -- subclasses set `permission_code`."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        from common.permissions import HasPermissionCode

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class CreateOrder(_OrderingPermission):
    permission_code = "ordering.order.create"


class ViewOwnOrder(_OrderingPermission):
    """Distinct from ViewAnyOrder -- a customer viewing their own order needs a narrower grant than staff viewing anyone's; object-level ownership is still checked separately by the view itself (this permission only gates whether the endpoint is reachable at all)."""

    permission_code = "ordering.order.view_own"


class ViewAnyOrder(_OrderingPermission):
    permission_code = "ordering.order.view_any"


class UpdateOrder(_OrderingPermission):
    permission_code = "ordering.order.update"


class ArchiveOrder(_OrderingPermission):
    permission_code = "ordering.order.archive"


class RestoreOrder(_OrderingPermission):
    permission_code = "ordering.order.restore"


class LockOrder(_OrderingPermission):
    permission_code = "ordering.order.lock"


class UnlockOrder(_OrderingPermission):
    permission_code = "ordering.order.unlock"


class ApproveReturn(_OrderingPermission):
    permission_code = "ordering.return.approve"


class RejectReturn(_OrderingPermission):
    permission_code = "ordering.return.reject"


class ReceiveReturn(_OrderingPermission):
    permission_code = "ordering.return.receive"


class RefundReturn(_OrderingPermission):
    permission_code = "ordering.return.refund"


class ApproveCancellation(_OrderingPermission):
    permission_code = "ordering.cancellation.approve"


class RejectCancellation(_OrderingPermission):
    permission_code = "ordering.cancellation.reject"


class IssueInvoice(_OrderingPermission):
    permission_code = "ordering.invoice.issue"


class AdminOrder(_OrderingPermission):
    """Umbrella admin permission -- used for cross-cutting admin listing/search/statistics where no narrower code applies, same role as Cart's CanManageCart/Pricing's CanManagePricing."""

    permission_code = "ordering.admin.manage"
