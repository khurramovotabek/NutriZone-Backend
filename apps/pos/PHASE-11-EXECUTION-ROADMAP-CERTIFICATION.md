# POS Phase 11 — Execution Roadmap & Phase A Certification

## Completion Matrix

See chat for the full table. Summary: Sale lifecycle, Search, Pricing resolution (Application), permissions, and totals were all already complete. The one genuine gap was `ResolveLineItemPrice` having zero HTTP surface since Phase 7. Payment/fiscalization/inventory remain correctly out of POS's scope. Branch→PriceList mapping remains a documented product decision (Phases 7–10) — not re-investigated, per this phase's explicit instruction.

## Roadmap

One implementation phase was required, not five: **Phase A** (expose pricing resolution via HTTP) + **Phase D** (regression/freeze, folded in below). Phases B (payment) and C (batch API work) were not needed — B is out of scope, C was one endpoint.

---

## Phase A — POS Pricing HTTP Exposure

### Status
**COMPLETE**

### Implemented
- `GET /api/v1/pos/pricing` — new endpoint, `PriceResolutionView`, wrapping Phase 7's unmodified `ResolveLineItemPrice` via the existing `build_resolve_line_item_price()` composition factory.
- `PriceResolutionQuerySerializer` (7 fields, AST-cross-checked exact match against `ResolveLineItemPrice.execute()`'s real signature) and `PriceResolutionResultSerializer` (amount/currency only — no Pricing internals exposed).
- Reuses the existing `ManageSale` permission (pricing resolution feeds the `ManageSale`-gated `AddLineItem`, same reasoning already applied there) — no new permission code.
- `price_list_id` remains caller-supplied, per the documented Phase 7–10 boundary; this endpoint does not invent a mapping.

### Files Changed
`apps/pos/interfaces/api/v1/serializers.py`, `views.py`, `urls.py` (all extended in place, never deleted). `apps/pos/tests/interfaces/test_pricing_workflow_integration.py` (extended — 7 new tests + 1 existing test updated from a stale `7 routes` assertion to the now-correct `8`).

### Tests
20 tests in the extended file (13 existing + 7 new): successful resolution, price-not-found (404), price-list-not-found (404), missing-params (422), unauthenticated (401), a full HTTP-level chain (`GET /pricing` → `POST .../line-items`, real database, real `PriceList`/`ProductVariant`), and a read-only regression guard (zero `Sale` rows created). 257 total POS test functions (was 250).

### Regression
Domain/Application/Infrastructure counts confirmed byte-identical via fresh AST recount (1/1/1/4/5 Domain; 6/2/1/3 Application; 3/12 Infrastructure — all unchanged). Interfaces grew by exactly the intended amount: 7→8 views/routes, 10→12 serializers, permissions unchanged at 4 (no new code, `ManageSale` reused). Products/Pricing/Store aggregate counts unchanged (11/6/10). Repository-wide compile: 1512/1512. Both scaffold files confirmed present.

### Remaining Boundary
Branch→PriceList mapping remains a product decision, unchanged from Phase 10 — this endpoint does not attempt to resolve it automatically.

### Next Phase
None required. POS's Sale/Search/Pricing/HTTP surface is now complete for everything currently in scope. Further work is gated on either the Branch→PriceList product decision or a new, explicitly scoped capability request.

**Runtime status**: Static validation only — Django/pytest/PostgreSQL/Redis unavailable in this sandbox; no runtime test execution occurred.
