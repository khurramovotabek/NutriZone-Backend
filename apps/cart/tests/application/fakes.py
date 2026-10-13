"""
In-memory fake implementing application/ports.py's `CartRepository`
Protocol, matching every prior module's `tests/application/fakes.py`
pattern.
"""
from __future__ import annotations


class FakeCartRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, cart_id):
        return self.by_id.get(cart_id)

    def get_by_code(self, code):
        return next((c for c in self.by_id.values() if c.code.value == code), None)

    def get_by_token(self, token):
        return next((c for c in self.by_id.values() if str(c.token) == str(token)), None)

    def get_active_for_customer(self, customer_id):
        return next((c for c in self.by_id.values() if c.customer_id == customer_id and c.status.value == "active"), None)

    def save(self, cart):
        self.by_id[cart.id] = cart
        return cart

    def delete(self, cart_id):
        self.by_id.pop(cart_id, None)

    def list_for_customer(self, customer_id, status, page, page_size):
        results = [c for c in self.by_id.values() if c.customer_id == customer_id]
        if status:
            results = [c for c in results if c.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def list_expiring_before(self, at):
        return [c for c in self.by_id.values() if c.expires_at and c.expires_at <= at]

    def list_for_admin(self, status, cart_type, page, page_size):
        results = list(self.by_id.values())
        if status:
            results = [c for c in results if c.status.value == status]
        if cart_type:
            results = [c for c in results if c.cart_type.value == cart_type]
        return results[(page - 1) * page_size : page * page_size], len(results)


def collect_events(sink: list):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
