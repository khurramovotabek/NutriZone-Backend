"""
One stock rule for every way of buying (website, Mini App, Telegram bot): a cart line may not ask for more than the
WMS can sell (on hand minus reserved at active locations -- the same numbers the storefront shows). A variant with no
stock row anywhere counts as 0. Switched by settings.CART_STOCK_GUARD (off in tests unless a test turns it on).
"""
from __future__ import annotations


class OutOfStock(Exception):
    def __init__(self, available: int, shortages: list[dict] | None = None):
        super().__init__(f"Only {available} in stock.")
        self.available = available
        self.shortages = shortages or []


def shortages(lines) -> list[dict]:
    """[(variant_id, qty)] -> [{product_variant_id, requested, available}] for the lines the warehouse can't cover."""
    from django.conf import settings

    from apps.stores.infrastructure.availability import sellable

    if not getattr(settings, "CART_STOCK_GUARD", True):
        return []
    wanted: dict = {}
    for variant_id, qty in lines:
        wanted[variant_id] = wanted.get(variant_id, 0) + int(qty)
    if not wanted:
        return []
    have = sellable(list(wanted))
    return [{"product_variant_id": str(v), "requested": q, "available": have.get(v, 0)} for v, q in wanted.items() if q > have.get(v, 0)]


def assert_in_stock(variant_id, quantity: int) -> None:
    short = shortages([(variant_id, quantity)])
    if short:
        raise OutOfStock(short[0]["available"], short)
