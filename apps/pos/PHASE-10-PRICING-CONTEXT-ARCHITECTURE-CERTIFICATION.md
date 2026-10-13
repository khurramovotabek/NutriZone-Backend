# POS Phase 10 — Explicit Sale-Time Pricing Context & Branch-to-Price-List Architecture Certification Report

**Every number in this report was freshly calculated from the live repository — none copied from Phase 9.**

---

## 1. Architecture Review

Re-verified fresh, not trusted from Phase 9's report, per this phase's own explicit instruction.

**POS**: `Sale` (9 fields, unchanged), `SaleLineItem` (`id`/`product_id`/`quantity`/`unit_price`, unchanged), `AddLineItem.execute(sale_id, product_id, quantity, unit_price_amount, unit_price_currency)` (unchanged), `ResolveLineItemPrice.execute(price_list_id, variant_id, quantity, at, coupon_code, region, membership_tier_code)` (unchanged), `PricingResolver` (single method, unchanged).

**Store, exhaustively re-enumerated this phase beyond Phase 9's narrower field-level check**: every Application Service across all 6 service files inspected — `GetStore`/`ListStores`/`AdminListStores`/`SearchStores` (queries), `UploadMedia`/`DeleteMedia`/`UpdateSettings` (content — the same generic `StoreSetting` mechanism already ruled out in Phase 8/9), `UpdateSchedule`/`AddHoliday`/`RemoveHoliday`/`UpdateCoverage` (schedule), `AssignEmployee`/`RemoveEmployee`/`AssignManager` (staffing), `CreateBranch`/`UpdateBranch`/`DeleteBranch`/`CreateWarehouse`/`UpdateWarehouse`/`DeleteWarehouse`/`CreateShelf`/`UpdateShelf`/`DeleteShelf` (facilities), `CreateStore`/`UpdateStore`/`ActivateStore`/`SuspendStore`/`CloseStore`/`ArchiveStore`/`RestoreStore` (lifecycle). **`CreateBranch.execute(store_id, code, name)` and `UpdateBranch.execute(branch_id, name=None)` confirmed to carry zero pricing-related parameter of any kind** — not even an `address_id` is required at creation. No service resembling "AssignPriceList"/"ConfigurePricing"/"SetCommercialContext" exists anywhere in Store.

**Pricing, re-verified**: `PriceSnapshot`/`ConsumePriceSnapshot` confirmed to have **zero code-level integration with POS anywhere** — the only repository matches for these terms outside `apps/pricing/` are this project's own prior certification report *markdown files*, never Python source. This directly answers this phase's own Section 3, questions 4–5: no, `PriceSnapshot` is never used by POS; no, `ConsumePriceSnapshot` participates in no existing POS workflow.

**Geo, independently re-verified** (not merely re-reading Phase 9's conclusion): the same 4 files matched for "apps.geo" inside Pricing as Phase 9 found — `signals.py`, `event_handlers.py`, `_shared.py`, `value_objects.py` — all confirmed still docstring-prose-only, no new file, no migration-level reference. Pricing's own migrations were checked directly this phase (not merely inferred from the ORM model) and contain zero `branch`/`store`/`geo` reference of any kind.

**Step 1 completed.**

---

## 2. Ownership Decision

This phase's real question is materially different from Phase 8/9's: not "does a mapping exist" (conclusively no), but **"can the repository's existing architecture safely justify designing and introducing a new one?"** Each candidate ownership model was evaluated on its merits, not dismissed by default:

**Option A — Store owns `Branch → PriceList`.** Rejected. No existing Store field, service, or Port shows any awareness of Pricing anywhere (confirmed exhaustively above). Every established cross-context pattern in this repository has a *consumer* reaching outward through its own composition root (POS → Products, POS → Pricing) — never has a foundational context like Store been made to depend on a commercial context like Pricing. Beyond the directional concern, this option requires deciding a genuine business rule with zero evidentiary basis anywhere in this repository: does each Branch have exactly one active PriceList? Can it change? Is there an override mechanism? None of this is answerable from source.

**Option B — Pricing owns a `PricingContext(branch_id, price_list_id)` mapping.** The most architecturally *plausible* of the four, because it would use the identical established pattern already proven throughout this build — a plain cross-context ID reference (matching, for example, `PriceListEntry.product_variant_id`, itself a bare UUID reference to Products' own entity). **Still rejected**, for the same underlying reason as Option A: designing this aggregate requires inventing the same unproven business semantics — cardinality, override rules, what happens on Branch archival or Store closure — none of which this repository's existing `Branch`/`Store` lifecycle (`CreateBranch`, `ArchiveStore`, etc., all re-inspected above) gives any hint of. A technically clean design is not the same thing as an evidenced one; this phase's own Section 23 explicitly names this exact trap.

**Option C — A dedicated configuration/integration bounded context.** Rejected immediately per this phase's own explicit instruction not to invent a new bounded context to avoid choosing between the other options, and no evidence anywhere in this well-organized, already-extensive module list suggests one is anticipated.

**Option D — `Sale` receives an explicit `price_list_id` at open-time.** Rejected. Investigated directly against Section 3's own questions: `SaleLineItem.unit_price` already provides complete historical protection (re-confirmed valid, §9 below) — a stored `price_list_id` on `Sale` would be informationally redundant for that purpose, since `PriceSnapshot` (Pricing's own dedicated mechanism for exactly this kind of historical linkage) has zero existing POS integration to build on. More fundamentally, this option doesn't actually resolve the ownership question — it only relocates the caller's burden from `AddLineItem`-time to `Sale.open()`-time, without ever answering *where* that `price_list_id` value should legitimately come from. It would also be a frozen-contract change (`Sale.open()`'s signature) this phase's own Section 7 requires strong justification for, which the investigation above does not provide.

**Option E — The caller remains responsible for `price_list_id`.** This is the status quo, already certified in Phase 7, and — after evaluating and rejecting A through D on their own evidentiary merits, not by default — remains the only option this repository's actual architecture supports today.

---

## 3. Mapping Investigation

Identical structure to Phase 9's table, with two rows freshly re-verified this phase rather than merely re-cited:

| Candidate | Result |
|---|---|
| `Sale` carrying sufficient context directly | No — 9 fields, unchanged |
| `Store.settings` | No existing pricing usage — reconfirmed |
| Store's complete Application layer (all 6 service files, new this phase) | No configuration/commercial/channel concept beyond the already-ruled-out generic settings bag |
| `Branch` lifecycle (`CreateBranch`/`UpdateBranch`, new this phase) | Zero pricing parameters of any kind |
| Pricing's 25 Application-layer classes | No branch/store/region/channel-based resolver |
| `PriceListModel` / Pricing migrations | No FK to Branch/Store at Domain, ORM, or migration level |
| `PriceSnapshot`/`ConsumePriceSnapshot` (re-verified this phase per Section 3's own new questions) | Zero POS integration anywhere in code |
| `apps.geo`'s `Region`/`RegionCode` | Real but executionally disconnected from Pricing — reconfirmed |

---

## 4. Implementation Outcome

**Outcome C — ownership still cannot be established**, but arrived at through a materially different, deeper question than Phase 9's: not merely "does a mapping exist" but "can one be safely designed." The answer to the harder question is also no — every technically viable design (Options A, B, D) requires inventing unproven business rules this repository's evidence does not support, and Option C (a new bounded context) is explicitly out of scope. This is the correct, disciplined conclusion per this phase's own Section 23: a clean-looking design is not evidence of business ownership.

---

## 5. Production Changes

**Zero production files modified.**

---

## 6. Test Changes

**Zero files modified, zero tests added.** Per this phase's own Section 8/Outcome C instruction: "modify zero tests unless a test is genuinely necessary to preserve an existing guarantee." Phase 7's existing suite already provides that guarantee (§9 below); no new test was necessary.

---

## 7. Pricing Resolution Architecture

Unchanged from Phase 7: `ResolveLineItemPrice.execute(price_list_id, variant_id, ...)` requires the caller to supply `price_list_id` directly. No new architecture was introduced.

---

## 8. Variant Boundary

Unchanged and reconfirmed. `variant_id` remains transient — resolved by Search, consumed only by `ResolveLineItemPrice`'s call into `CalculatePrice`, never persisted onto `SaleLineItem`. The distinction between `product_id` (what `AddLineItem`/`SaleLineItem` carry) and `variant_id`/`product_variant_id` (what Pricing requires) remains explicit and undisturbed, per this phase's own Section 13.

---

## 9. Snapshot Semantics

**Confirmed still present and valid**, directly re-read this phase: `test_resolved_price_reaches_add_line_item_and_is_persisted_as_snapshot` in `apps/pos/tests/interfaces/test_pricing_workflow_integration.py` still resolves `31.50`, persists it via the real `AddLineItem`, mutates the underlying price to `99.99` via Pricing's own real `SetPrice`, and confirms the stored `SaleLineItem.unit_price` remains `31.50` after re-fetch. Not duplicated, not weakened, exactly matching this phase's own Section 14 instruction.

---

## 10. Security

No new surface — zero files were modified.

---

## 11. Error Handling

Unchanged — `ResourceNotFound` and `InvalidSaleTransition` remain the only relevant, already-tested paths.

---

## 12. Test Coverage

Unchanged from Phase 9's own final count (§17 below) — 250 test functions across 22 files, all already covering every applicable item in this phase's own Section 11 checklist that has a real, non-speculative referent (Application-layer resolution behavior, snapshot immunity, regression guards). Domain/lifecycle-rule categories for a mapping that doesn't exist have no meaningful test to write.

---

## 13. Regression Coverage

Every count in this phase's own Section 15 baseline list was freshly re-verified and found identical to Phase 9's certified end state (§18 below) — proof by construction, since nothing was touched.

---

## 14. Static Validation

| Gate | Status |
|---|---|
| Repository-wide compile | ✓ 1512/1512 — identical to Phase 9's final count |
| POS/Store/Pricing/Products/Geo compile | ✓ (all unchanged files, confirmed syntactically valid as part of the full repo compile) |
| Scaffold files present | ✓ `application/selectors.py`, `interfaces/api/v1/filters.py` both confirmed |
| All import/duplicate/dead-code/circular-dependency gates | ✓ N/A by construction — no file was modified |

---

## 15. Runtime Status

**Static validation only — no runtime test execution occurred.** Django, pytest, PostgreSQL, and Redis remain unavailable in this sandbox, consistent with every prior phase.

---

## 16. Mistakes Found

**One real mistake, caught by the final sanity check rather than trusted as correct.** While enumerating Store's Application layer in §1, the running tally arrived at 26 total services and that number was carried into the draft report. The mandatory final sanity check — independently recounting every number against live source before delivery, the same discipline applied at the end of every phase in this build — recomputed the total directly via AST across all 6 files (`queries.py`: 4, `content.py`: 3, `schedule.py`: 4, `staffing.py`: 3, `facilities.py`: 9, `lifecycle.py`: 7) and found **30**, not 26. **Why it happened**: a manual running count while reading six separate files in sequence, rather than a single programmatic tally, is exactly the kind of arithmetic this build has gotten wrong before (Phase 9 undercounted Pricing's services by one for the same underlying reason). **How detected**: the standard end-of-phase independent recount, run specifically because this build's own history shows manual tallies are unreliable. **How corrected**: the figure was updated to 30 in the fresh-counts table above. **How revalidated**: the AST-based recount was re-run a second time after the fix to confirm 30 is stable. This mistake does not affect §2's ownership-decision reasoning or §4's outcome — the conclusion never depended on the exact count of Store's services, only on the *absence* of any pricing-related one among them, which remains independently and separately confirmed.

---

## 17. Fresh Counts

| Metric | Fresh Count | vs. Phase 9 |
|---|---|---|
| Total Python files | 1512 | Identical |
| POS production files changed | 0 | — |
| POS test files / functions | 22 / 250 | Identical |
| POS Domain aggregates/entities/VOs | 1/1/1 | Identical |
| POS Domain exceptions/events | 4/5 | Identical |
| POS Application Services (Sale/Search/Pricing) | 6/2/1 | Identical |
| POS Application Ports | 3 | Identical |
| POS ORM models | 3 | Identical |
| POS composition factories | 12 | Identical |
| POS views/serializers/permissions/routes | 7/10/4/7 | Identical |
| Store Domain aggregates/entities | 10/11 | New this phase — first fresh count |
| Store Application Services (all 6 service files, exhaustive) | 30 | New this phase — first fresh count; corrected after an initial miscount (§16) |
| Products Domain aggregates/VOs | 11/13 | Identical |
| Pricing Domain aggregates | 6 | Identical |
| Pricing Application Ports | 7 | Identical |
| Pricing composition factories | 32 | Identical |
| Geo Domain aggregates | 8 | New this phase — first fresh count |
| Cross-context imports (POS → Products/Pricing, production code) | 3 | Identical |
| Forward dependencies | 0 | Identical |
| Circular imports | 0 | Identical |

---

## 18. Production Freeze Re-Verification

**Unchanged / Unchanged / Unchanged**, freshly re-verified across POS, Store, Pricing, Products, and Geo. Every count above matches Phase 9's certified end state exactly. `unexpectedly changed = 0`, confirmed.

---

## 19. Remaining Architectural Boundaries

Identical in substance to Phase 8/9, now backed by a genuinely different and deeper investigation: automatic `Sale.branch_id → price_list_id` resolution remains unavailable, and — new this phase — **the repository does not yet contain the business decision required to safely design one either.** The specific missing decision, stated precisely: *does a Branch (or Store) have a well-defined, single, current commercial PriceList, and if so, who assigns it, does it change over time, and what happens to open Sales when it does?* Until that product/business question is answered by someone with the authority to answer it, no technically clean Domain design (Option A or B above) can be implemented without POS or Pricing engineering unilaterally inventing retail commercial policy. `price_list_id` remains caller-supplied; no HTTP endpoint exposes `ResolveLineItemPrice`.

---

## 20. Final Certification

**POS Phase 10 — Explicit Sale-Time Pricing Context & Branch-to-Price-List Architecture is: DOCUMENTED STOP CONDITION.**

This phase asked a harder question than Phase 8 or 9 — not whether a mapping exists, but whether the repository's architecture justifies *designing* one — and answered it by evaluating four concrete ownership options (Store-owned, Pricing-owned, a new dedicated context, Sale-embedded) against fresh, direct evidence rather than a repeat of the prior existence check. Every option was found to require inventing an unproven business rule (mapping cardinality, override semantics, branch/store lifecycle interaction) that no part of this repository — Store's complete Application layer, Pricing's complete Domain/Application/Infrastructure/migrations, or `PriceSnapshot`'s own real but POS-disconnected mechanism — provides evidence for. Zero production files were modified. Zero new tests were needed, since Phase 7's existing snapshot-immunity proof and regression suite remain valid and sufficient, both re-confirmed by direct reading rather than assumption. Every production-layer count across POS, Store, Products, Pricing, and Geo was freshly calculated (Store and Geo for the first time in this investigation sequence) and found identical to Phase 9's certified end state. Repository-wide compilation passes at 1512/1512, unchanged. Both required scaffold placeholders remain present.

**The correct outcome remains zero new production code — this time because the deeper question this phase specifically asked ("can a safe design be introduced") was answered honestly as no, not because the shallower question ("does one exist") was merely asked again.**

Waiting for the next explicit instruction.
