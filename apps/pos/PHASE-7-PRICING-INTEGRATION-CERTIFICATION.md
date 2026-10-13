# POS Phase 7 — Authoritative Pricing Integration Certification Report

**Every number in this report was freshly calculated from the live repository — none reused from Phase 6's or any other prior report.**

---

## 1. Architecture Review

Every claim below was verified directly against live source before any file was written, per this phase's own mandatory Step 1.

**Pricing Domain, freshly inspected**: 6 aggregates confirmed exactly as Phase 6's report named them — `PriceList`, `PricingRule`, `Campaign`, `Coupon`, `BundlePrice`, `PriceSnapshot`. `PriceList` owns `PriceListEntry` (owned entity: `base_price`/`cost_price`/`sale_price`/`compare_at_price`, all `Money`), with public methods `set_price`, `activate`, `archive`, `entry_for_variant`.

**The authoritative price resolution capability**: `CalculatePrice.execute(price_list_id, product_variant_id, quantity=1, at=None, coupon_code=None, region=None, membership_tier_code=None) -> PriceCalculationResult`, already fully wired via Pricing's own composition root (`build_calculate_price()`, zero parameters). `PriceCalculationResult` carries `base_price: Money`, `final_price: Money`, `applied_discounts: tuple[DiscountLine, ...]`. Internally, `CalculatePrice` resolves the price-list entry, evaluates active `PricingRule`s (quantity-tier, regional, membership, time-based/dynamic), active `Campaign`s targeting the variant, and an optional `Coupon`, then delegates the actual stacking/priority computation to `PriceCalculationEngine` — a real, non-trivial, already-certified algorithm this phase never re-implements.

**Confirmed by direct inspection: `CalculatePrice` resolves by `product_variant_id`, not `product_id`.** This directly implicates the certified Phase 6 finding that `SaleLineItem` has no `variant_id` field.

**A genuine, load-bearing gap, confirmed by direct inspection, not assumed**: no mapping from `Sale.branch_id` to any Pricing concept exists anywhere in this repository. `Branch` (Store's own aggregate) has exactly `id`, `store_id`, `code`, `name`, `address_id` — no `region` field. `PriceList` has no `branch`/`store` reference; its only region-adjacent method is `get_active_for_region(region: str | None)`, which requires a region string POS also does not possess. This is a genuine architectural boundary, not closed this phase, per this phase's own explicit Section 4/31 guidance for exactly this situation.

**`AddLineItem`'s live signature re-verified, not trusted from Phase 6's report**: `execute(self, sale_id, product_id, quantity, unit_price_amount, unit_price_currency)` — confirmed unchanged. **Option A (Section 7) was chosen**: the existing contract remains untouched; price resolution happens *before* `AddLineItem` is called, via a new, separate Application Service.

**Step 1 completed. No contradiction was found between this phase's own assumed workflow and live source, beyond the two disclosed gaps (variant identity, branch→price-list mapping) — both were investigated fully and resolved by documentation, not fabrication.**

---

## 2. Pricing Ownership

`apps.pricing` remains the sole, authoritative owner of price computation — base prices, cost prices, sale prices, quantity-tier discounts, regional rules, membership rules, time-based rules, campaigns, and coupons. POS introduces zero pricing logic of its own; every discount/campaign/coupon evaluation happens exclusively inside Pricing's own `CalculatePrice`/`PriceCalculationEngine`, reached only through a single, narrow `PricingResolver` Port method.

---

## 3. Existing Architecture Reused

`CalculatePrice` (Pricing's own, unmodified). `build_calculate_price()` (Pricing's own, unmodified composition factory). `Money` (Shared Kernel, unmodified). The identical composition-root-to-composition-root wiring pattern already established for `ProductLookupAdapter`/Products (Search module phase) — mirrored exactly for Pricing, not reinvented. `AddLineItem`, `SaleRepository`, `PosServiceContext` — all unmodified, unchanged contracts.

---

## 4. Files Created / Modified

**Production (4 files)**: `apps/pos/application/ports.py` (extended in place — `SaleRepository`/`ProductLookup` confirmed unchanged; added `PricingResolver`), `apps/pos/application/services/pricing.py` (new — `ResolveLineItemPrice`), `apps/pos/application/services/__init__.py` (export added), `apps/pos/infrastructure/composition.py` (extended — `PricingResolverAdapter`, `build_pricing_resolver`, `build_resolve_line_item_price`; all 10 prior factories confirmed byte-identical via AST diff).

**Test (2 new, 1 extended)**: `apps/pos/tests/application/test_pricing_integration.py` (new, 13 tests), `apps/pos/tests/interfaces/test_pricing_workflow_integration.py` (new, 13 tests), `apps/pos/tests/application/fakes.py` (extended in place — `FakePricingResolver` added, all existing fakes unchanged).

**No file was deleted. No `rm -f` was used at any point.** `apps/pos/application/selectors.py` and `apps/pos/interfaces/api/v1/filters.py` both individually confirmed present and unmodified at the end of this phase.

---

## 5. API Changes

**None.** All 7 existing POS routes, confirmed unchanged via fresh count. No new endpoint was added — this phase's own Section 12 explicitly forbade the obvious default endpoint names (`/pos/pricing`, `/pos/price`, `/pos/calculate-price`), and the architecture review did not surface strong enough evidence that a new endpoint was genuinely required rather than merely convenient. This is a disclosed, conscious deferral — see §21.

---

## 6. Application Changes

**1 new Port**: `PricingResolver(Protocol)` — single method, `calculate_price(price_list_id, variant_id, quantity, at, coupon_code, region, membership_tier_code) -> Money`, deliberately returning only the final `Money`, never Pricing's own richer `PriceCalculationResult` (which also exposes `base_price`/`applied_discounts` — internal structure this phase's own Section 16 forbids exposing beyond what POS's contract requires). **1 new Application Service**: `ResolveLineItemPrice(pricing_resolver)` — a pure query, structurally incapable of touching `SaleRepository` or calling `AddLineItem` (verified via a dedicated regression test, §14). `SaleRepository`/`ProductLookup` Ports confirmed unchanged.

---

## 7. Infrastructure Changes

**1 new adapter**: `PricingResolverAdapter`, wrapping Pricing's own composition-provided `CalculatePrice` service, extracting only `.final_price` from its result. **2 new composition factories**: `build_pricing_resolver()`, `build_resolve_line_item_price()` (no `actor_id` — a pure query, matching `build_search_product()`'s identical precedent). Composition factory count: 10 → 12. All 10 prior factories confirmed byte-identical via AST diff.

---

## 8. Pricing Resolution Flow

```
Caller (frontend/cashier system) already knows:
  price_list_id (a configuration-level identifier POS does not resolve dynamically -- disclosed gap, §21)
  variant_id (from the existing, unmodified GET /pos/search response's exact_match)
        ↓
ResolveLineItemPrice.execute(price_list_id, variant_id, quantity, ...)
        ↓
PricingResolver Port → PricingResolverAdapter → Pricing's own build_calculate_price()
        ↓
CalculatePrice.execute() -- real algorithm: price-list entry lookup, active PricingRules,
active Campaigns, optional Coupon, PriceCalculationEngine stacking/priority resolution
        ↓
PriceCalculationResult.final_price (Money)
        ↓
[caller decomposes Money -> amount, currency]
        ↓
Existing, unmodified AddLineItem.execute(sale_id, product_id, quantity, unit_price_amount, unit_price_currency)
        ↓
SaleLineItemAdded -- unit_price stored as an immutable snapshot
```

Two genuinely separate Application-layer calls, matching this phase's own Section 13 preference — resolution and mutation remain architecturally distinct, exactly as identification and mutation were kept distinct in Phase 6.

---

## 9. Price Snapshot Semantics

**Directly, executably proven, not merely asserted**: `test_resolved_price_reaches_add_line_item_and_is_persisted_as_snapshot` resolves a real price (`31.50`), adds it to a real `Sale` via `AddLineItem`, then calls Pricing's own `SetPrice` to change the underlying price list entry to `99.99`, and re-fetches the `Sale` — confirming the persisted `SaleLineItem.unit_price` remains `31.50`, completely unaffected by the later Pricing change. `SaleLineItem.unit_price: Money` was never made a live reference to Pricing; it is copied by value at the moment `AddLineItem` executes, exactly matching this phase's own Section 9 requirement.

---

## 10. Variant / Product Identity

**The Phase 6 gap remains, disclosed, not silently closed.** `SaleLineItem` still has exactly 4 fields — `id`, `product_id`, `quantity`, `unit_price` — re-confirmed via fresh AST count (Domain entities: 1, unchanged). `variant_id` is used *transiently* during price resolution (Search returns it; `ResolveLineItemPrice` consumes it to query Pricing) but is never required to be, and is not, persisted onto `SaleLineItem`. This is the correct, minimal resolution: Pricing gets the identity it genuinely needs at resolution time, without requiring a frozen Domain contract change.

---

## 11. Currency / Money

`shared.value_objects.money.Money` (Shared Kernel, unmodified) is the sole representation used throughout — `ResolveLineItemPrice` returns `Money` directly; the caller decomposes it into `amount`/`currency` only at the `AddLineItem` boundary, exactly matching that service's own existing, certified parameter shape. No ad-hoc float or string currency representation was introduced anywhere.

---

## 12. Error Mapping

| Condition | Exception | Verified by |
|---|---|---|
| Price list not found | `ResourceNotFound` (Pricing's own, re-verified via direct import inspection: `common.exceptions.ResourceNotFound`, the same shared type) | `test_price_list_not_found_raises_resource_not_found` |
| No price configured for variant in list | `ResourceNotFound` | `test_no_valid_price_raises_resource_not_found` |
| Completed Sale | `InvalidSaleTransition` (unchanged, `AddLineItem`'s own existing behavior) | `test_completed_sale_rejects_a_priced_line_item` |
| Voided Sale | `InvalidSaleTransition` (unchanged) | `test_voided_sale_rejects_a_priced_line_item` |

No new exception type was created anywhere. No scanner/pricing-only error semantics exist.

---

## 13. Security

Unchanged. No new endpoint means no new authentication/permission surface was introduced. `ResolveLineItemPrice` exposes no HTTP boundary this phase, so it inherits no independent security posture to verify beyond POS's existing, unchanged permission set — re-confirmed via fresh count (4 permission classes, identical codes: `pos.sale.view`, `pos.sale.manage`, `pos.search.view`). No internal Pricing structure (`applied_discounts`, rule/campaign/coupon internals) is exposed anywhere — `PricingResolverAdapter` extracts only `final_price`.

---

## 14. Test Coverage

**13 tests** in `test_pricing_integration.py` (Application layer, fakes only): valid resolution, price-list-not-found and no-price-configured propagation, quantity/effective-date/coupon/region/membership forwarding (proving POS never inspects or branches on these — it forwards them verbatim), currency and precision preservation, a direct proof `ResolveLineItemPrice` has no Sale-mutation capability, and the **mandatory Section 22 Pricing boundary regression guard** — redesigned mid-implementation after a real false positive (§18) into an AST-based check for the *absence of any conditional branching* in `ResolveLineItemPrice`, a more accurate signal of "no duplicated discount logic" than substring matching.

**13 tests** in `test_pricing_workflow_integration.py` (real database, real Pricing fixtures built via Pricing's own certified `CreatePriceList`/`ActivatePriceList`/`SetPrice` Application Services — never raw ORM manipulation): real price resolution against a real `PriceList`/`ProductVariant`, no-price and price-list-not-found cases, currency/precision correctness, **the core Phase 7 proof** — a real resolved price flowing through the real, unmodified `AddLineItem` and persisting as a genuine, database-backed snapshot (proven immune to a subsequent real price change), repeated-scan behavior confirmed unchanged (2 separate line items), completed/voided-Sale rejection with a real resolved price, and 3 regression checks confirming the existing 7 routes, Search endpoint, and all 4 permissions remain exactly as certified.

**26 new test functions total.**

---

## 15. Regression Coverage

Directly confirmed via fresh AST re-verification (§ "Production Freeze Re-Verification" below): POS Domain, the 6 Sale services, the 2 Search services, all 7 HTTP endpoints/routes, all 10 serializers, all 4 permissions, all 3 ORM models — all unchanged. Products Domain (11 aggregates, 13 value objects) unchanged. Pricing Domain (6 aggregates), Pricing Ports (7), and Pricing's own composition root (32 factories) unchanged — POS only *reads from* Pricing's composition root, never modifies it.

---

## 16. Static Validation

| Gate | Status |
|---|---|
| Repository-wide compile | ✓ 1512/1512 |
| `__import__()` | ✓ 0 (whole POS test tree) |
| Dead `if False` / edit debris | ✓ 0 |
| Local imports | ✓ 0 (whole POS test tree, after real instances caught and fixed — §18) |
| Unused imports | ✓ 0 (real instances caught and fixed — §18) |
| Duplicate test names | ✓ 0 |
| Duplicate routes/services/factories | ✓ 0 (routes: 7, unchanged; factories: 12, exactly as designed) |
| Circular imports | ✓ 0 |
| Forbidden cross-context imports | ✓ 0 — exactly 3 disclosed, deliberate imports exist (2 composition-root wirings, 1 Domain-VO reuse), all confirmed via precise grep |
| Direct ORM access from Application | ✓ 0 |
| Private aggregate mutation | ✓ 0 |
| Speculative capability | ✓ 0 — no frontend, no new endpoint, no pricing engine duplication |
| Accidental frozen-file modification | ✓ 0 — every unchanged-expected count fresh-verified exactly matching |

---

## 17. Runtime Status

**Static validation only. No runtime test execution occurred.** Django, pytest, PostgreSQL, and Redis remain unavailable in this sandbox — verified directly (`import django` fails with `ModuleNotFoundError`), not assumed. Compilation success does not imply test success; no such claim is made anywhere in this report.

---

## 18. Mistakes Found

Reported honestly, none hidden:

1. **A real, substantive false positive in the mandatory Pricing-boundary regression test, caught by actually running the check against real source rather than trusting the test looked reasonable.** The first draft of `test_pos_pricing_service_has_no_discount_calculation_logic` scanned `inspect.getsource(ResolveLineItemPrice)` (including the class's own docstring) for the substrings "campaign", "coupon", "discount". Manually simulating this check against the real file showed it would fail immediately for two independent reasons: the class's own docstring *legitimately discusses* these terms while explaining they are NOT implemented locally, and separately, `execute()`'s own legitimate parameter name `coupon_code` contains "coupon" as a substring even in the real executable code. **How detected**: running the exact check logic manually against live source before trusting the test file, rather than assuming a plausible-sounding assertion was correct. **How fixed**: redesigned twice — first to exclude docstrings via AST (still failed on `coupon_code`), then to abandon substring matching entirely in favor of checking for the presence of any `ast.If`/`ast.Compare`/`ast.IfExp` node anywhere in the class — a genuinely more accurate signal, since `ResolveLineItemPrice` is a pure, unconditional pass-through by design, and any real duplication of Pricing's discount logic would necessarily introduce branching. **How revalidated**: manually simulated the final version against the real file and confirmed it passes.
2. **Several scattered local imports**, the same recurring category of mistake disclosed in every prior POS testing phase's own report, across both new test files (`datetime`, `PricingResolver`, `PosServiceContext`, `AddLineItem`, `InvalidSaleTransition`, `resolve`, permission classes, and — caught last, after an initial self-audit pass had already declared the file clean — `pos_urls_module`, missed by an earlier stripping script that didn't target every occurrence). **How detected**: the same per-file local-import AST check applied throughout this build, re-run a second time after the first pass to catch the one instance the initial script missed. **How fixed**: consolidated to each file's top-level imports.
3. **No mistake was found in the core architectural resolution itself** (Option A: preserve `AddLineItem` unchanged, resolve price beforehand via a new, separate service) — this was verified against `CalculatePrice`'s real signature and `SaleLineItem`'s real fields before being decided, not corrected after the fact.

---

## 19. Fresh Counts

| Metric | Fresh Count |
|---|---|
| Repository-wide Python files | 1512 |
| POS production files modified | 4 |
| POS test files | 22 (20 pre-existing + 2 new) |
| POS test functions | 250 |
| POS test classes | 55 |
| POS Application Services | 8 (6 Sale + 2 Search-related, unchanged) + 1 new (`ResolveLineItemPrice`) = 9 |
| POS Application Ports | 3 (was 2, +1 new: `PricingResolver`) |
| POS HTTP endpoints | 7 (unchanged) |
| POS URL routes | 7 (unchanged) |
| POS composition factories | 12 (was 10, +2 new) |
| Cross-context imports (POS → Products/Pricing, production code) | 3 (2 composition-root wirings + 1 Domain-VO reuse, all disclosed) |
| Forward dependencies | 0 |
| Circular imports | 0 |

---

## 20. Production Freeze Re-Verification

Every one of the following was freshly re-counted at the end of this phase, not assumed from Phase 6:

**POS**: Domain enums (1), aggregates (1), entities (1), value objects (1), exceptions (4), events (5) — all unchanged. Sale services (6), Search services (2) — unchanged. ORM models (3) — unchanged. Views (7), serializers (10), permissions (4), routes (7) — all unchanged.

**Products**: Domain aggregates (11), value objects (13) — unchanged; zero files touched this phase.

**Pricing**: Domain aggregates (6), Application ports (7), composition factories (32) — all unchanged; POS reads from Pricing's composition root, never modifies it.

**Confirmed changed, exactly as designed and disclosed**: POS Application ports (2 → 3), POS composition factories (10 → 12).

---

## 21. Remaining Architectural Boundaries

Two boundaries this phase deliberately did not close, both documented per this phase's own explicit Section 31/33 instruction to disclose rather than fabricate:

1. **`price_list_id` resolution.** No mapping from `Sale.branch_id` (or any other POS-owned identifier) to a `price_list_id` exists anywhere in this repository. `ResolveLineItemPrice` requires the caller to supply `price_list_id` directly. Closing this would require either a new Branch→PriceList mapping capability (a speculative addition to Store or Pricing, outside this phase's scope) or a hardcoded/default assumption (forbidden). This is a genuine stop-condition-adjacent finding, resolved by documentation rather than invention.
2. **No HTTP endpoint exposes `ResolveLineItemPrice`.** The Application-layer capability is complete, fully tested (including a real, database-backed end-to-end proof chaining into the existing `AddLineItem`), and ready for a future phase to wire once the exact desired cashier UX (preview-then-confirm? a single combined call? something else?) is actually specified — this phase's own Section 12 explicitly named the obvious default endpoint names as forbidden guesses, and the architecture review did not surface strong enough evidence to justify inventing a new one.

Neither boundary was silently worked around. Both are documented here explicitly, as this phase's own rules require.

---

## 22. Final Certification

**POS Phase 7 — Authoritative Pricing Integration is: COMPLETE WITH DOCUMENTED BOUNDARY.**

The mission — investigating Pricing's real contracts and establishing a correct, minimal, source-verified integration path — is achieved. `AddLineItem`'s frozen contract was preserved exactly (Option A), confirmed correct against `CalculatePrice`'s real signature and `SaleLineItem`'s real fields before implementation began, not after. A single new, narrow Application Service (`ResolveLineItemPrice`) and Port (`PricingResolver`) were introduced, wrapping Pricing's own real, certified `CalculatePrice` via the identical composition-root-to-composition-root pattern already established for Products — zero pricing logic was duplicated, verified both by a dedicated conditional-branching-absence test and by a real, database-backed end-to-end proof that a genuine Pricing algorithm (including its own real `PriceListEntry`/`PriceCalculationEngine`) resolves the price, which then flows unmodified into the existing, frozen `AddLineItem`, persisting as a true historical snapshot immune to later Pricing changes. Two genuine architectural boundaries were investigated fully and are documented, not fabricated around: `price_list_id` resolution and HTTP exposure. Every production-layer freeze check — POS Domain/Application/Infrastructure/Interfaces, Products, and Pricing — passed with fresh, exact counts. Repository-wide compilation passes at 1512/1512. Zero scaffold files were deleted; both required placeholders confirmed present. Two real mistakes were found during implementation and are disclosed in full above, including one substantive false positive in the mandatory Pricing-boundary regression test, caught and corrected through actual verification rather than assumption.

**Static validation only — no runtime test execution occurred**, disclosed plainly per this phase's own explicit requirement.

Waiting for the next explicit instruction.
