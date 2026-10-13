# POS Phase 9 — Sale-Time Price Context & Branch-to-Price-List Resolution Investigation Certification Report

**Every number in this report was freshly calculated from the live repository — none copied from Phase 8.**

---

## 1. Architecture Review

Every claim below was independently re-derived from live source this phase, not accepted from Phase 8's report, per this phase's own explicit instruction.

**Sale context, freshly re-inspected**: `Sale`'s complete field set confirmed via fresh AST parse — exactly `id`, `branch_id`, `cashier_id`, `customer_id`, `status`, `line_items`, `created_at`, `completed_at`, `voided_at`. No channel, region, store, or pricing-context field exists beyond `branch_id`. `Sale.open()`'s creation contract carries nothing further.

**Pricing Application layer, exhaustively enumerated this phase** (all 4 service files + `selectors.py`, not just `queries.py` as Phase 7/8's narrower searches implicitly favored): **25 total Application-layer classes** (24 real services + `PricingSelector`; `PricingSearchBackend` in `selectors.py` is a `Protocol`, not a service, and is excluded from this count) — `CreateCoupon`, `RedeemCoupon`, `RevokeCoupon`, `CreateBundlePrice`, `ActivateBundlePrice`, `LockPrice`, `ConsumePriceSnapshot`, `ReleasePriceSnapshot` (`coupons_bundles_snapshots.py`); `CreatePriceList`, `ActivatePriceList`, `ArchivePriceList`, `SetPrice` (`price_lists.py`); `CalculatePrice`, `GetPriceHistory`, `GetPriceList`, `ListPriceLists`, `SearchPricing` (`queries.py`); `CreatePricingRule`, `ActivatePricingRule`, `ArchivePricingRule`, `CreateCampaign`, `ActivateCampaign`, `EndCampaign`, `CancelCampaign` (`rules_and_campaigns.py`); `PricingSelector` (`selectors.py`, text-search only, mirroring Products' own `SearchProducts` pattern). **None** resembles `GetPriceListForBranch`/`ResolvePriceList`/`SelectPriceList` or any branch/store/channel-based resolver. `GetPriceList.execute(code: str)` resolves by an arbitrary string code, not a branch reference. `ListPriceLists.execute(status, page, page_size)` has no location filter at all.

**`PriceListModel` (ORM, database level), freshly inspected**: exactly `code`, `name`, `currency`, `status`, `region` — the last a plain, unconstrained `CharField(max_length=16)`, not a foreign key. No `branch`/`store`/`branch_id`/`store_id` field exists anywhere on this model. This confirms, at the database level, the identical conclusion already reached at the Domain level.

**A genuinely new investigation this phase, not covered by Phase 7 or 8**: `apps.geo`, a real, substantial bounded context (`Country`, `Region`, `District`, `City`, `Neighborhood`, `Address`, `GeoBoundary`, `DeliveryZone`) was discovered and investigated specifically because `Branch.address_id` plausibly could have chained through it. `Geo.Region` has a real, structured `RegionCode` value object (`^[A-Z0-9]{2,10}$`) — superficially resembling Pricing's own free-string `region` field closely enough to be a tempting inference. **A direct search confirmed Pricing never imports or references `apps.geo` anywhere in executable code** — every occurrence of "apps.geo" inside Pricing's own source is docstring prose comparing implementation *patterns* (e.g., "matching apps.geo's own X convention"), never an actual import or data dependency. `Branch.address_id` was separately confirmed to be consumed only by Store's own `application/services/lifecycle.py` (address management), never by Pricing. This is precisely the "two tables contain similar identifiers, but no executable relationship connects them" trap this phase's own Section 9 explicitly warned against — checking it directly, rather than either assuming the similarity was meaningful or dismissing it without looking, is what this phase's deeper investigation actually added beyond Phase 8's own search.

**Configuration/seed-data/migration search, run fresh this phase**: zero `PRICE_LIST`/`PRICING_` environment variables in any settings module; zero migrations referencing both `branch`/`store` and pricing concepts together; zero seed data connecting the two.

**Step 1 completed. Every avenue this phase's own Sections 4–10 required was investigated directly, including one genuinely new candidate Phase 8 did not examine.**

---

## 2. Mapping Investigation

| Candidate | Investigated | Result |
|---|---|---|
| `Sale` carrying sufficient pricing context directly | ✓ | No — exactly 9 fields, none pricing-related beyond `branch_id` |
| `Store.settings` generic key/value bag | ✓ (Phase 8) | No existing pricing usage; re-confirmed unchanged this phase |
| `Branch.region`/`Branch.price_list_id` | ✓ | Neither field exists — `Branch` has exactly `id`, `store_id`, `code`, `name`, `address_id` |
| Pricing Application layer (all 24 services, not just `queries.py`) | ✓ (new this phase — exhaustive) | No branch/store/region/channel-based resolver exists anywhere |
| `PriceListModel` ORM/database relations | ✓ | No FK to Branch/Store; `region` is an unconnected plain string |
| `apps.geo`'s real `Region`/`RegionCode` concept | ✓ (new this phase) | Real and structured, but zero executable connection to Pricing anywhere |
| Environment variables / settings modules | ✓ | None found |
| Migrations / seed data | ✓ | None found |

---

## 3. Outcome

**Outcome C — No mapping exists.** This is a re-derivation, not a restatement of Phase 8's conclusion: this phase's own investigation covered strictly more ground (the complete Pricing Application layer across all 4 service files, the database-level `PriceListModel` schema, and the `apps.geo` bounded context) and arrived at the identical answer through independent evidence.

Per this phase's own explicit Section 12/26 instruction: **implementation stops here.** No `Branch.price_list_id`, `Store.settings["price_list_id"]`, `default_price_list`, hardcoded UUID, "first active price list" selection, region inference from `Geo`, or any other speculative bridge was created — each was considered and rejected on the evidence above, not merely unconsidered.

---

## 4. Production Changes

**Production code: 0 files modified.**

---

## 5. Test Changes

**0 files modified, 0 tests added.** Phase 7's existing 26 pricing-related tests (part of the 250 POS test functions re-confirmed present this phase) already satisfy every applicable requirement in this phase's own test-policy sections — including the exact snapshot-immunity proof required by Section 15 (see §8 below). No test could meaningfully "prove" a mapping that does not exist; adding tests asserting the *absence* of a capability was judged unnecessary noise beyond what this report's own evidence already demonstrates directly.

---

## 6. Price Resolution Architecture

Not applicable — no existing legitimate mapping was found (Outcome C). The architecture remains exactly as Phase 7 certified: `ResolveLineItemPrice.execute(price_list_id, variant_id, ...)` requires the caller to supply `price_list_id` directly.

---

## 7. Variant Boundary

Unchanged. `variant_id` remains transient — used only to call `CalculatePrice` via `ResolveLineItemPrice`, never persisted onto `SaleLineItem`. `SaleLineItem`'s fields (`id`, `product_id`, `quantity`, `unit_price`) were re-confirmed unchanged via fresh AST count this phase. No Domain modification occurred or was needed.

---

## 8. Snapshot Semantics

**Confirmed still present and valid.** `test_resolved_price_reaches_add_line_item_and_is_persisted_as_snapshot` (in `apps/pos/tests/interfaces/test_pricing_workflow_integration.py`, part of Phase 7's certified suite) was directly re-read this phase: it resolves a real price of `31.50`, persists it via the real, unmodified `AddLineItem`, then calls Pricing's own real `SetPrice` to change the underlying price to `99.99`, re-fetches the `Sale`, and asserts the stored `unit_price` remains `31.50` — exactly the `31.50 → 99.99` behavior this phase's own Section 15 requires. Not duplicated; the existing test remains sufficient and was not weakened.

---

## 9. Security

No new security surface was introduced — zero production files were modified, so no new endpoint, permission, or authentication path exists to evaluate.

---

## 10. Error Handling

Unchanged from Phase 7 — `ResourceNotFound` (price list/price not found) and `InvalidSaleTransition` (completed/voided Sale) remain the only relevant, already-tested error paths. No new error behavior was introduced or needed to be reported.

---

## 11. Static Validation

| Gate | Status |
|---|---|
| Repository-wide compile | ✓ 1512/1512 — identical to Phase 8's own final count |
| POS test-tree compile | ✓ (unchanged files, re-verified present and syntactically valid) |
| Scaffold files present | ✓ `application/selectors.py`, `interfaces/api/v1/filters.py` both confirmed |
| Duplicate tests/routes/factories, unused/local imports, `__import__()`, dead code, circular imports, forbidden cross-context imports | ✓ N/A by construction — no file was modified, so no new violation could have been introduced; Phase 8's own clean state is unchanged |

---

## 12. Runtime Status

**Static validation only. No runtime test execution occurred.** Django, pytest, PostgreSQL, and Redis remain unavailable in this sandbox, consistent with every prior phase. No claim of runtime test execution is made anywhere in this report.

---

## 13. Mistakes Found

**None this phase.** No file was written, so no implementation mistake was possible. One process note, disclosed for transparency rather than as an error: the investigation into `apps.geo`'s `Region`/`RegionCode` initially looked like a promising lead precisely because of its structural resemblance to Pricing's own `region` field — the correct discipline was to verify the *executable* connection (or lack thereof) directly via grep rather than treating the resemblance itself as evidence, which is what was ultimately done.

---

## 14. Fresh Counts

| Metric | Fresh Count | vs. Phase 8 |
|---|---|---|
| Total Python files | 1512 | Identical |
| POS production files changed | 0 | — |
| POS test files | 22 | Identical |
| POS test functions | 250 | Identical |
| POS Domain aggregates/entities/VOs | 1/1/1 | Identical |
| POS Domain exceptions/events | 4/5 | Identical |
| POS Application Services (Sale/Search/Pricing) | 6/2/1 | Identical |
| POS Application Ports | 3 | Identical |
| POS ORM models | 3 | Identical |
| POS composition factories | 12 | Identical |
| POS HTTP endpoints/routes | 7/7 | Identical |
| POS serializers/permissions | 10/4 | Identical |
| Products Domain aggregates/VOs | 11/13 | Identical |
| Pricing Domain aggregates | 6 | Identical |
| Pricing Application Ports | 7 | Identical |
| Pricing Application-layer classes (all files, exhaustive) | 25 | New this phase — first exhaustive count across all 4 service files + selectors.py |
| Pricing composition factories | 32 | Identical |
| Cross-context imports (POS → Products/Pricing, production code) | 3 | Identical |
| Forward dependencies | 0 | Identical |
| Circular imports | 0 | Identical |

---

## 15. Production Freeze Re-Verification

**Unchanged / Unchanged / Unchanged**, freshly re-verified across POS, Products, and Pricing — every count above matches Phase 8's certified end state exactly. Zero `changed intentionally`, zero `unexpected`.

---

## 16. Remaining Architectural Boundaries

Identical to Phase 8, reconfirmed through independent, broader investigation rather than accepted on faith: automatic `Sale.branch_id → price_list_id` resolution remains unavailable. This phase additionally rules out `apps.geo` as a viable bridge, closing off the one plausible-looking avenue that had not previously been checked. Closing this boundary would require new, explicitly-designed capability in Store, Pricing, or a genuinely new integration layer between them — none of which exists today, and none of which this phase's scope authorizes inventing. `price_list_id` remains caller-supplied; no HTTP endpoint exposes `ResolveLineItemPrice`.

---

## 17. Final Certification

**POS Phase 9 — Sale-Time Price Context & Branch-to-Price-List Resolution Investigation is: DOCUMENTED STOP CONDITION.**

This phase re-derived Outcome C independently rather than trusting Phase 8's report, and did so with materially broader evidence: an exhaustive enumeration of all 25 Pricing Application-layer classes (not just `queries.py`), a database-level inspection of `PriceListModel`'s actual schema, and — genuinely new this phase — a full investigation of `apps.geo`'s real `Region`/`RegionCode` concept, which was found structurally tempting but executionally disconnected from Pricing. No production file was modified. No new test was needed, since Phase 7's existing suite already satisfies every applicable requirement, including the exact `31.50 → 99.99` snapshot-immunity proof this phase's own Section 15 specifies. Every production-layer count across POS, Products, and Pricing was freshly re-verified and found identical to Phase 8's certified end state. Repository-wide compilation passes at 1512/1512, unchanged. Both required scaffold placeholders remain present.

**The correct outcome remains zero new production code — not because the investigation was shallow, but because it was thorough enough to confidently rule out every candidate the repository actually contains, including the one this phase was specifically asked to check more carefully than before.**

Waiting for the next explicit instruction.
