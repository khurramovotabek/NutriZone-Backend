# POS Phase 8 — Price List Resolution & Cashier Pricing Workflow Certification Report

**Every number in this report was freshly calculated from the live repository — none reused from Phase 7's report.**

---

## 1. Architecture Review

Every claim below was verified directly against live source, re-checking Phase 7's own conclusions rather than trusting them, per this phase's own explicit Section 1 instruction.

**POS, freshly re-inspected**: `Sale`, `SaleLineItem` (`id`/`product_id`/`quantity`/`unit_price`, unchanged), `AddLineItem.execute(sale_id, product_id, quantity, unit_price_amount, unit_price_currency)`, `LoadSale`, `SaleRepository`, `ResolveLineItemPrice`, `PricingResolver` — all confirmed present and exactly as Phase 7 certified them via fresh AST count (§16 below).

**Pricing, freshly re-inspected**: `CalculatePrice`, `PriceCalculationResult`, `PriceList`, `PriceListEntry`, `PricingRule`, `Campaign`, `Coupon`, `BundlePrice`, `PriceSnapshot` all confirmed present, unchanged. `PriceList.entry_for_variant()`, `get_active_for_region(region)` confirmed as the only region-adjacent methods.

**Store/Branch, freshly re-inspected — this is where new investigation happened beyond a repeat of Phase 7's own review**: `Branch` confirmed to have exactly `id`, `store_id`, `code`, `name`, `address_id` — no region, no price-list reference. **A genuinely new finding this phase**: `Store.settings: dict[str, StoreSetting]` exists — a free-form key/value settings bag (`StoreSetting.key: str`, `.value: str`). Its own docstring example is `'auto_accept_orders': 'true'`. A direct search confirmed **zero existing code anywhere reads or writes a price-list-related key from this mechanism** — using it to resolve a price list would mean this phase inventing a brand-new convention on top of a generic bag never intended for this purpose, not reusing an existing one. This does not qualify as Outcome A or B; it is not evidence of an authoritative mapping.

**Repository-wide search, run fresh this phase**: `price_list_id` appears only inside `apps/pricing/*` and `apps/pos/*` — the exact files Phase 7 itself wrote. `default_price_list` appears nowhere. `get_active_for_region` is only ever *defined* (in Pricing's own repository/port), never *called* with a real, branch-derived region value anywhere in the repository. No `Branch`↔`PriceList` relationship of any kind exists.

**Step 1 completed.**

---

## 2. Critical Stop Condition — Answered

**Outcome C is confirmed: no authoritative mapping from `Sale.branch_id` to `price_list_id` exists anywhere in the live repository.** This is not a repeat of Phase 7's own conclusion accepted on faith — it was re-derived independently this phase via direct inspection of `Branch`'s exact fields, a fresh repository-wide grep, and investigation of the one new candidate (`Store.settings`) that Phase 7's own report did not examine, which was found insufficient for the same reason: no existing evidence of intended use for this purpose.

**Per this phase's own explicit Section 2 instruction: implementation of automatic PriceList resolution STOPS here.** No `Branch.price_list_id`, `Store.price_list_id`, `Branch.region`, default-PriceList logic, hardcoded configuration, "first active price list" selection, hidden fallback, or speculative Store/Pricing integration was created — none was written, none was considered a viable path once the evidence was examined.

---

## 3. Findings (Section 19 of this phase's own brief, answered explicitly)

**Finding 1 — Does an authoritative `Sale/Branch → PriceList` mapping exist?** No.

**Finding 2 — Where does the mapping live?** Nowhere. No bounded context in this repository currently owns this relationship.

**Finding 3 — What exact existing contract should POS call?** None can be called for automatic resolution, since none exists. The existing, correct contract for the *manual* path remains `ResolveLineItemPrice.execute(price_list_id, variant_id, ...)`, unchanged from Phase 7.

**Finding 4 — Can the existing `ResolveLineItemPrice` service remain unchanged?** Yes — confirmed via fresh AST count (1 class, unchanged) and fresh signature re-inspection; no modification was needed or made.

**Finding 5 — Is an HTTP endpoint actually required?** No new evidence emerged this phase to justify one. Phase 7 declined for the same reason (this task's own explicit list of forbidden default endpoint names, and no specified cashier UX shape to design around); nothing this phase's investigation surfaced changes that conclusion.

**Finding 6 — What frozen contracts must remain untouched?** `AddLineItem`'s exact signature, `SaleLineItem`'s exact 4 fields, `ResolveLineItemPrice`'s exact signature, `PricingResolver`'s exact single method — all reconfirmed unchanged via fresh AST count.

**Finding 7 — What is the smallest valid implementation?** Zero new production code. The task's own Section 2 explicitly anticipates this as a valid, correct outcome, and this phase's own investigation independently arrives at the identical conclusion.

---

## 4. Existing Architecture Reused

Everything from Phase 7 — `ResolveLineItemPrice`, `PricingResolver`, `PricingResolverAdapter`, `build_pricing_resolver()`, `build_resolve_line_item_price()`, `CalculatePrice`, `build_calculate_price()` — remains exactly as certified, reused without modification.

---

## 5. Files Created / Modified

**Zero.** No production file, test file, or documentation file (other than this report) was created or modified this phase. This is the correct, source-verified outcome, not an incomplete one.

---

## 6–7. API / Application Changes

**None.** No new endpoint, service, or Port was added — Finding 5 and Finding 4 both confirm none was justified or needed.

---

## 8. Infrastructure Changes

**None.**

---

## 9. Cross-Context Integration

Unchanged from Phase 7: exactly 3 disclosed cross-context imports in POS production code (`apps.pricing.infrastructure.composition.build_calculate_price`, `apps.products.infrastructure.composition.{build_search_products, build_variant_repository}`, `apps.products.domain.value_objects.{SKU, Barcode}`) — reconfirmed present, none added, none removed.

---

## 10. PriceList Resolution Flow

**Automatic resolution: does not exist, and this phase confirms it cannot exist without work in a different bounded context than POS (a Branch→PriceList capability would need to be added to Store or Pricing, which is outside this phase's — and POS's — ownership).** Manual/caller-supplied resolution remains exactly as Phase 7 left it: the caller supplies `price_list_id` directly to `ResolveLineItemPrice`.

---

## 11. Pricing Resolution Flow

Unchanged from Phase 7 — see that report's own §8 for the full flow diagram, which remains accurate and current.

---

## 12. Variant / Product Identity

Unchanged. `variant_id` remains transient (used only to call `CalculatePrice`, never persisted); `SaleLineItem` remains exactly `id`/`product_id`/`quantity`/`unit_price`, reconfirmed via fresh AST count.

---

## 13. Currency / Money

Unchanged — `shared.value_objects.money.Money` remains the sole representation.

---

## 14. Price Snapshot Semantics

**Already proven by Phase 7's own existing test**, re-verified present this phase (§ above): `test_resolved_price_reaches_add_line_item_and_is_persisted_as_snapshot` uses this task's own exact example values (`31.50` → `99.99`), resolves a real price, persists it via the real `AddLineItem`, mutates the underlying `PriceList` afterward via Pricing's own real `SetPrice`, and re-fetches the `Sale` to confirm the stored `unit_price` is unaffected. No new test was needed to satisfy this phase's own Section 13 requirement — it was already satisfied.

---

## 15. Security

Unchanged — no new endpoint means no new authentication/authorization surface.

---

## 16. Error Mapping

Unchanged — `ResourceNotFound` (price list not found, no price configured) and `InvalidSaleTransition` (completed/voided Sale) remain the only error paths, both already tested in Phase 7's suite.

---

## 17. Test Coverage

**No new tests were added this phase — none were required.** Phase 7's existing 26 pricing-related tests already cover every applicable item in this phase's own Section 14 checklist: successful/failed resolution, quantity/coupon/region/membership/effective-date forwarding, currency/precision preservation, no-duplicated-logic (the AST-based conditional-branching check), no-Sale-mutation, the real end-to-end snapshot-immunity proof, repeated-scan regression, and completed/voided-Sale rejection. Fresh count, re-verified this phase: 22 test files, 250 test functions — identical to Phase 7's own final count, confirming nothing regressed and nothing new was needed.

---

## 18. Regression Coverage

Every count in this phase's own Section 16 baseline list was freshly re-verified and found identical to Phase 7's certified end state (§20 below) — the strongest possible form of regression proof, since nothing was touched at all.

---

## 19. Static Validation

| Gate | Status |
|---|---|
| Repository-wide compile | ✓ 1512/1512 — identical to Phase 7's own final count |
| POS test-tree compile | ✓ (unchanged files, re-verified) |
| Scaffold files present | ✓ `application/selectors.py`, `interfaces/api/v1/filters.py` both confirmed |
| All other gates (imports, dead code, duplicates, etc.) | ✓ N/A — no file was modified, so no new violation could have been introduced; Phase 7's own final clean state is unchanged |

---

## 20. Runtime Status

**Static validation only. No runtime test execution occurred.** Django, pytest, PostgreSQL, and Redis remain unavailable in this sandbox, consistent with every prior phase.

---

## 21. Mistakes Found

**None this phase.** No file was written, so no implementation mistake was possible. The one thing worth disclosing as a process note, not a mistake: this phase's investigation of `Store.settings` was a genuinely new avenue Phase 7's own report did not examine — it was checked thoroughly (exact entity shape, docstring example, repository-wide usage search) before being ruled out, rather than dismissed on the strength of its generic-sounding name alone.

---

## 22. Fresh Counts

| Metric | Fresh Count | vs. Phase 7 |
|---|---|---|
| Repository-wide Python files | 1512 | Identical |
| POS Domain aggregates/entities/VOs | 1/1/1 | Identical |
| POS Domain exceptions/events | 4/5 | Identical |
| POS Application Services (Sale/Search/Pricing) | 6/2/1 | Identical |
| POS Application Ports | 3 | Identical |
| POS ORM models | 3 | Identical |
| POS composition factories | 12 | Identical |
| POS views/serializers/permissions/routes | 7/10/4/7 | Identical |
| Products Domain aggregates/VOs | 11/13 | Identical |
| Pricing Domain aggregates | 6 | Identical |
| Pricing Ports | 7 | Identical |
| Pricing composition factories | 32 | Identical |
| POS test files/functions | 22/250 | Identical |

---

## 23. Production Freeze Re-Verification

**Unchanged / Unchanged / Unchanged.** Every count above is `unchanged` — zero `changed intentionally`, zero `unexpected`. This is the complete, freshly-verified confirmation this phase's own Section 22 requires.

---

## 24. Remaining Architectural Boundaries

**Unchanged from Phase 7, reconfirmed independently this phase**: automatic `Sale.branch_id → price_list_id` resolution remains unavailable because no authoritative mapping exists in the live repository. Closing this gap would require new capability in Store (e.g., a genuine, evidenced `Branch.region` or `Branch.price_list_id` concept) or Pricing (e.g., a real region-to-branch convention), neither of which exists today and neither of which this phase's scope authorizes inventing. `price_list_id` remains caller-supplied. No HTTP endpoint exposes `ResolveLineItemPrice`, for the same reason Phase 7 found: no strong evidence justifies choosing a specific endpoint shape over the explicitly forbidden default guesses.

---

## 25. Final Certification

**POS Phase 8 — Price List Resolution & Cashier Pricing Workflow is: DOCUMENTED STOP CONDITION.**

The architecture review — re-derived independently this phase rather than trusted from Phase 7's report — confirms Outcome C: no authoritative `Sale/Branch → PriceList` mapping exists anywhere in the live repository. One genuinely new candidate was investigated this phase (`Store.settings`, a free-form key/value bag) and found insufficient — no existing code anywhere uses it for this purpose, and adopting it would mean fabricating a convention, not reusing one. Per this phase's own explicit Section 2/27 instruction, implementation stopped there: no `Branch.price_list_id`, no default PriceList selection, no hidden fallback, no speculative Store/Pricing integration was created. Zero production files were modified. Zero new tests were required, since Phase 7's own existing 26 pricing tests already satisfy every applicable requirement in this phase's own Section 14 checklist, including the exact snapshot-immunity proof (`31.50` → `99.99`) this phase's Section 13 specifies. Every production-layer count — POS Domain/Application/Infrastructure/Interfaces, Products, and Pricing — was freshly re-verified and found identical to Phase 7's certified end state. Repository-wide compilation passes at 1512/1512, unchanged. Both required scaffold placeholders remain present.

**The correct outcome this phase was zero new production code, and that is what was produced — not a shortfall, but the architecturally honest result of the investigation this phase required.**

Waiting for the next explicit instruction.
