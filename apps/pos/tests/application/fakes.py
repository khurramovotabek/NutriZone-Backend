"""
Fake implementations of POS' Application-layer Ports, plus a
`collect_events` helper for building a testable `PosServiceContext`
-- matches Analytics' own identical `tests/application/fakes.py`
pattern.

**`FakeProductLookup` and `FakeTextSearch` are new, for the POS
Search module.** `FakeProductLookup` satisfies POS's own
`ProductLookup` Port directly -- it never touches Products'
Infrastructure, matching the same fake-over-mock precedent already
established throughout this module's own Phase 3/4/5 tests.
`FakeTextSearch` satisfies the structural shape `SearchProduct`
expects from Products' own `SearchProducts` service, without
importing that concrete class.
**`FakePricingResolver` is new, for POS Phase 7 (Authoritative
Pricing Integration).** Satisfies POS's own `PricingResolver` Port
directly -- it never touches Pricing's Infrastructure or duplicates
any part of Pricing's own real discount-calculation algorithm, which
remains entirely untested here (that algorithm is Pricing's own,
already-certified concern); these tests only prove POS correctly
calls through to and handles the results/exceptions of whatever the
Port returns.
"""
from __future__ import annotations


def collect_events(sink: list):
    """Returns a `stage_events` function that appends every staged (event_type, payload) tuple onto `sink`, so a test can assert exactly which events a service call emitted."""

    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage


class FakeSaleRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, sale_id):
        return self.by_id.get(sale_id)

    def save(self, sale):
        self.by_id[sale.id] = sale
        return sale


class FakeProductLookup:
    def __init__(self) -> None:
        self.by_barcode: dict = {}
        self.by_sku: dict = {}

    def find_by_barcode(self, barcode: str):
        return self.by_barcode.get(barcode)

    def find_by_sku(self, sku: str):
        return self.by_sku.get(sku)


class FakeTextSearch:
    """Records every call it receives and returns a deterministic, fixed result -- never a live Products query."""

    def __init__(self, result: dict | None = None) -> None:
        self.calls: list[dict] = []
        self._result = result or {"results": [], "total_count": 0, "facets": {}}

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20, sort: str = "-created_at") -> dict:
        self.calls.append({"query": query, "filters": filters, "page": page, "page_size": page_size, "sort": sort})
        return self._result


class FakePricingResolver:
    """Records every call it receives; returns a configured `Money` or raises a configured exception -- never a live Pricing query, never a duplicated discount algorithm."""

    def __init__(self, result=None, exception: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._result = result
        self._exception = exception

    def calculate_price(self, price_list_id, variant_id, quantity=1, at=None, coupon_code=None, region=None, membership_tier_code=None):
        self.calls.append({"price_list_id": price_list_id, "variant_id": variant_id, "quantity": quantity, "at": at, "coupon_code": coupon_code, "region": region, "membership_tier_code": membership_tier_code})
        if self._exception is not None:
            raise self._exception
        return self._result
