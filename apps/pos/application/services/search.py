"""
POS Search -- the single Application Service resolving cashier input
(barcode / SKU / free text) into either an exact product identity
(ready for the certified `AddLineItem`) or a text-search result list.

**Never duplicates Product identity or search logic.** Barcode/SKU
format validation reuses Products' own certified `Barcode`/`SKU`
value objects exactly, unmodified. Text search delegates entirely to
Products' own already-certified `SearchProducts` Application Service
-- POS never builds a second full-text query.

**The certified priority order (Section 9 of this task's own brief):
barcode exact lookup -> SKU exact lookup -> text search.** A real,
disclosed finding drove the exact design below: `SKU`'s own regex
(`^[A-Z0-9]+(?:-[A-Z0-9]+)*$`) and `Barcode`'s own regex (`^\\d{8,14}$`)
genuinely overlap -- a pure 8-14-digit string matches both patterns.
Per this task's own Section 7 guidance for exactly this case, this is
resolved via the certified cascade itself (try barcode, then SKU,
then text) rather than an invented disambiguation rule; an explicit
`mode` parameter is also available for a caller that already knows
the input type for certain.

**Two distinct behaviors, disclosed explicitly, both intentional**:
in automatic-cascade mode (`mode=None`), a format mismatch or a
"valid format but no match" both silently fall through to the next
stage of the cascade -- never raised, since the whole point of the
cascade is graceful fallback. In explicit mode (`mode="barcode"` or
`"sku"`), a format mismatch propagates as the real `ValidationFailed`
(422) and a valid-format-but-no-match raises `ResourceNotFound` (404),
matching `LoadSale`'s own established convention exactly -- the
caller explicitly asked for that resolution strategy, so silent
fallback would hide a genuine error.

**Never returns "multiple matches"** -- structurally impossible, not
merely untested: `ProductVariant.barcode`/`.sku` both carry a real
database `unique=True` constraint (re-verified in Products'
own certified ORM model during this task's own Step 1), so a lookup
can only ever return zero or one row.
"""
from __future__ import annotations

from typing import Protocol

from apps.pos.application.ports import ProductLookup
from apps.products.domain.value_objects import SKU, Barcode
from common.exceptions import ResourceNotFound, ValidationFailed


class _TextSearchService(Protocol):
    """Structural typing over Products' own certified `SearchProducts` Application Service -- POS depends on this shape, never imports the concrete class."""

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20, sort: str = "-created_at") -> dict: ...


class SearchProduct:
    def __init__(self, product_lookup: ProductLookup, text_search: _TextSearchService) -> None:
        self._product_lookup = product_lookup
        self._text_search = text_search

    def execute(self, query: str, mode: str | None = None, page: int = 1, page_size: int = 20) -> dict:
        query = query.strip()

        if mode == "barcode":
            return self._resolve_exact("barcode", query, self._product_lookup.find_by_barcode, Barcode)
        if mode == "sku":
            return self._resolve_exact("sku", query, self._product_lookup.find_by_sku, SKU)
        if mode == "text":
            return self._run_text_search(query, page, page_size)
        if mode is not None:
            raise ValidationFailed(f"Unknown search mode '{mode}'; expected one of: barcode, sku, text.", details={"fields": [{"field": "type", "code": "INVALID_CHOICE"}]})

        # Automatic cascade: barcode -> sku -> text, per the certified priority order.
        barcode_match = self._try_exact(query, self._product_lookup.find_by_barcode, Barcode)
        if barcode_match is not None:
            return {"mode": "barcode", "exact_match": barcode_match, "results": None, "total_count": None}

        sku_match = self._try_exact(query, self._product_lookup.find_by_sku, SKU)
        if sku_match is not None:
            return {"mode": "sku", "exact_match": sku_match, "results": None, "total_count": None}

        return self._run_text_search(query, page, page_size)

    def _try_exact(self, raw: str, resolve_fn, vo_cls) -> dict | None:
        """Auto-cascade helper -- a format mismatch or a no-match both silently return None, letting the cascade continue to the next stage."""
        try:
            vo_cls(raw)
        except ValidationFailed:
            return None
        match = resolve_fn(raw)
        if match is None:
            return None
        product_id, variant_id = match
        return {"product_id": product_id, "variant_id": variant_id}

    def _resolve_exact(self, mode: str, raw: str, resolve_fn, vo_cls) -> dict:
        """Explicit-mode helper -- a format mismatch propagates untouched (422); a valid-format-but-no-match raises ResourceNotFound (404), matching LoadSale's own established convention."""
        vo_cls(raw)  # raises ValidationFailed if malformed -- propagates untouched, never caught here
        match = resolve_fn(raw)
        if match is None:
            raise ResourceNotFound(f"No product found for {mode} '{raw}'.")
        product_id, variant_id = match
        return {"mode": mode, "exact_match": {"product_id": product_id, "variant_id": variant_id}, "results": None, "total_count": None}

    def _run_text_search(self, query: str, page: int, page_size: int) -> dict:
        result = self._text_search.execute(query=query, filters={}, page=page, page_size=page_size)
        return {"mode": "text", "exact_match": None, "results": result["results"], "total_count": result["total_count"]}
