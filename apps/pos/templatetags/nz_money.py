"""`{{ amount|som }}` -> "1 234 567" (whole so'm, space-grouped) for dashboard money figures."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def som(value) -> str:
    try:
        n = int(round(Decimal(str(value or 0))))
    except (InvalidOperation, ValueError):
        return "—"
    return f"{n:,}".replace(",", " ")
