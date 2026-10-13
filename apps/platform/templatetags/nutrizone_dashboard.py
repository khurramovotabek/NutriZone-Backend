"""
Phase 17.0: closes a real, precise gap in the otherwise-complete
dashboard home template (templates/admin/index.html) -- the Recent
Orders table rendered {{ order.status }} as the raw domain enum value
(e.g. "pending_payment") directly, not a translated, human-readable
label. Matches this project's own established principle (already
applied correctly elsewhere, e.g. Telegram's own order-status
messages): map enum values to semantic translation keys, never
translate the raw value itself.
"""
from __future__ import annotations

from django import template
from django.utils.translation import gettext_lazy as _

register = template.Library()

_ORDER_STATUS_LABELS = {
    "draft": _("Draft"),
    "pending_payment": _("Pending Payment"),
    "confirmed": _("Confirmed"),
    "processing": _("Processing"),
    "shipped": _("Shipped"),
    "delivered": _("Delivered"),
    "completed": _("Completed"),
    "cancelled": _("Cancelled"),
    "returned": _("Returned"),
    "failed": _("Failed"),
}


@register.filter(name="order_status_label")
def order_status_label(value: str) -> str:
    """Maps a real OrderStatus enum value to its translated, human-readable label. Falls back to the raw value if genuinely unrecognized, rather than crashing or showing a blank string."""
    return str(_ORDER_STATUS_LABELS.get(value, value))
