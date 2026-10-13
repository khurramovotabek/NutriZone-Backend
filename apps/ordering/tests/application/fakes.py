"""
In-memory fakes implementing application/ports.py's Protocols, plus
fake gateways and a fake search backend, matching every prior
module's `tests/application/fakes.py` pattern and this phase's
explicit "Create Fake Gateways" / "Create Fake Search Backend"
instruction.
"""
from __future__ import annotations


class FakeOrderRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, order_id):
        return self.by_id.get(order_id)

    def get_by_order_number(self, order_number):
        return next((o for o in self.by_id.values() if o.order_number.value == order_number), None)

    def get_by_cart_id(self, cart_id):
        return next((o for o in self.by_id.values() if o.cart_id == cart_id), None)

    def save(self, order):
        self.by_id[order.id] = order
        return order

    def list_for_customer(self, customer_id, status, page, page_size):
        results = [o for o in self.by_id.values() if o.customer_id == customer_id]
        if status:
            results = [o for o in results if o.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def list_expiring_before(self, at):
        return [o for o in self.by_id.values() if o.placed_at and o.placed_at <= at]

    def list_for_admin(self, status, page, page_size):
        results = list(self.by_id.values())
        if status:
            results = [o for o in results if o.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeOrderReturnRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, return_id):
        return self.by_id.get(return_id)

    def get_by_return_number(self, return_number):
        return next((r for r in self.by_id.values() if r.return_number.value == return_number), None)

    def list_for_order(self, order_id):
        return [r for r in self.by_id.values() if r.order_id == order_id]

    def save(self, order_return):
        self.by_id[order_return.id] = order_return
        return order_return


class FakeOrderCancellationRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, cancellation_id):
        return self.by_id.get(cancellation_id)

    def list_for_order(self, order_id):
        return [c for c in self.by_id.values() if c.order_id == order_id]

    def save(self, cancellation):
        self.by_id[cancellation.id] = cancellation
        return cancellation


class FakePaymentGateway:
    def __init__(self, statuses: dict | None = None) -> None:
        self._statuses = statuses or {}

    def get_payment_status(self, payment_id):
        return self._statuses.get(payment_id)


class FakeFulfillmentGateway:
    def __init__(self, statuses: dict | None = None) -> None:
        self._statuses = statuses or {}

    def get_fulfillment_status(self, fulfillment_id):
        return self._statuses.get(fulfillment_id)


class FakeNotificationGateway:
    def __init__(self) -> None:
        self.notifications: list = []

    def notify_order_event(self, order_id, event_type, payload):
        self.notifications.append((order_id, event_type, payload))


class FakeOrderSearchGateway:
    def __init__(self, results: list | None = None) -> None:
        self._results = results or []

    def search(self, query, filters, page, page_size):
        return self._results, len(self._results)


def collect_events(sink: list):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
