# Pricing Module — Phase 2 (Infrastructure) Certification Report

**Scope:** Infrastructure layer only, per this phase's explicit instruction. Interfaces and Tests are **not** started.

---

## Step 1 — Architecture Review Findings

Before writing any code, the current state was actually inspected, not assumed:

- `apps/pricing/infrastructure/` contained only empty `__init__.py` files (my own Phase 1 scaffolding) — no stale or conflicting content.
- `apps/pricing/apps.py` did not yet exist.
- `shared/event_contracts/pricing.py` did not yet exist.
- `apps.pricing` was already correctly present in `INSTALLED_APPS` (no naming mismatch this time, unlike the `apps.catalog`/`apps.products` and `apps.stores`/`apps.store` collisions found in earlier modules).
- Phase 1's domain and application layers were re-verified to compile cleanly before building on them.

**No architectural inconsistency was found.** Proceeding to Step 2.

---

## 1. Folder Tree

```
apps/pricing/infrastructure/
├── models.py
├── repositories.py
├── selectors.py
├── event_handlers.py
├── signals.py            (documented-empty, see §11)
├── tasks.py
├── health.py
├── composition.py
├── admin.py
└── gateways/              (empty — no external gateway integrated this phase)
apps/pricing/apps.py
shared/event_contracts/pricing.py
```

---

## 2. Files Created

10 files under `apps/pricing/infrastructure/`, plus `apps/pricing/apps.py`, `shared/event_contracts/pricing.py`, and 2 new OpenAPI tags registered in `config/settings/base.py`.

---

## 3. ORM Model Summary

11 base tables + 1 Outbox table = **12 tables**, mirroring Phase 1's 6 aggregates + 5 owned entities exactly:

| Table | Mirrors | Notes |
|---|---|---|
| `PriceListModel` | `PriceList` | Unique `code` |
| `PriceListEntryModel` | `PriceListEntry` | Unique (price_list, product_variant_id); `CheckConstraint`s enforcing sale ≤ base and compare-at ≥ base — the database-level backstop for the exact rule `PriceListEntry.__post_init__` enforces in the domain |
| `PriceHistoryEntryModel` | `PriceHistoryEntry` | **Append-only, plain Model** (no update/delete path exposed) |
| `PricingRuleModel` + `QuantityTierModel` | `PricingRule` + owned `QuantityTier`s | `CheckConstraint` on validity ordering; unique (rule, minimum_quantity) |
| `CampaignModel` + `CampaignTargetModel` | `Campaign` + owned `CampaignTarget`s | Same validity-ordering constraint |
| `CouponModel` + `CouponRedemptionModel` | `Coupon` + owned `CouponRedemption`s | Unique `code`; unique (coupon, order_reference) preventing the same order from redeeming one coupon twice at the database level |
| `BundlePriceModel` | `BundlePrice` | Unique `bundle_id` (one bundle price per bundle) |
| `PriceSnapshotModel` | `PriceSnapshot` | Unique `token`; non-negative amount `CheckConstraint` |
| `PricingOutboxEvent` | — | Concrete Outbox table for `pricing` schema |

**`DiscountLine` (domain/entities.py) has no table** — deliberately. Its own docstring in Phase 1 states it's a calculation-output entity, not persisted aggregate state; no repository method here constructs or returns one, matching that design intent exactly rather than inventing a table nobody asked for.

---

## 4. Repository Summary

6 concrete classes, one per Phase 1 Port: `DjangoPriceListRepository`, `DjangoPricingRuleRepository`, `DjangoCampaignRepository`, `DjangoCouponRepository`, `DjangoBundlePriceRepository`, `DjangoPriceSnapshotRepository`. Every repository catches `IntegrityError` and re-raises as a domain `ConflictError`; every write reconciles owned-entity collections (PriceListEntry/PriceHistoryEntry/QuantityTier/CampaignTarget/CouponRedemption) rather than blind inserts. No repository returns an ORM object outside `infrastructure/`.

---

## 5. Selector Summary

7 selector classes: `PriceListSelector`, `PricingRuleSelector`, `CampaignSelector` (including `upcoming()` for scheduled campaigns), `CouponSelector`, `BundlePriceSelector`, `PriceSnapshotSelector` (expiring-soon sweep support), `PriceHistorySelector`, plus `DjangoPricingSearchBackend` implementing `PricingSearchGateway`. All read-only, zero business logic, zero aggregate construction.

---

## 6. Event Handler Summary

`event_handlers.py::handle_pricing_event()` — one dispatch-table function, matching the identical pattern in `apps.geo`/`apps.store`/`apps.inventory`, never an if/else chain. **Cross-checked programmatically** (not just written and trusted): every one of the 19 domain events appears as a key in the `_EVENT_TO_CACHE_GROUPS` dispatch table, verified by AST-parsing the file and diffing against `domain/events.py`'s class list — zero mismatches.

---

## 7. Celery Task Summary

6 tasks + the standard Outbox relay: `expire_campaigns` (sweeps overdue ACTIVE campaigns, calls the real `EndCampaign` service), `expire_price_snapshots` (sweeps overdue LOCKED snapshots via the domain aggregate's own status field, loaded/mutated/saved), `expire_coupons`, `activate_scheduled_campaigns` (calls the real `ActivateCampaign` service), `rebuild_statistics`, `relay_outbox_events`. Every task delegates its actual decision to a real Application Service or the domain layer — none contain business logic themselves.

---

## 8. Health Summary

5 checks: `pricing_repository`, `pricing_cache`, `pricing_calculation_engine` (the most substantive — actually **runs** `PriceCalculationEngine.calculate()` against a synthetic 100.00-with-10%-off example and asserts the result is exactly 90.00, proving the deterministic core actually computes correctly, not just that the module imports without error), `pricing_snapshots`, `pricing_campaigns`.

---

## 9. Composition Root Summary

**37 `build_*()` factory functions** — one per Application Service (25) plus one per repository (6) plus the search-backend-wired selector and service-context factory, so no future Interfaces-layer view has any reason to instantiate a repository directly. No service locator: every factory explicitly constructs and returns one object.

---

## 10. Database Constraints Summary

| Rule | Enforcement |
|---|---|
| Sale price ≤ base price | `PriceListEntryModel`'s `CheckConstraint` — mirrors `PriceListEntry.__post_init__` exactly |
| Compare-at price ≥ base price | Same table, second `CheckConstraint` |
| Base price non-negative | `CheckConstraint(base_price_amount__gte=0)` |
| Validity end after start (Rules, Campaigns) | `CheckConstraint` on both `PricingRuleModel` and `CampaignModel` |
| Unique price-list-entry per variant | `UniqueConstraint(price_list, product_variant_id)` |
| Unique coupon code | `CouponModel.code` unique |
| No duplicate coupon redemption per order | `UniqueConstraint(coupon, order_reference)` — a real, previously-undocumented business rule made explicit at the database level during this phase (Phase 1's domain didn't structurally prevent redeeming the same coupon twice for the same order at the aggregate level; this constraint closes that gap) |
| One bundle price per bundle | `BundlePriceModel.bundle_id` unique |
| Unique price snapshot token | `PriceSnapshotModel.token` unique |
| Non-negative amounts (bundle price, snapshot) | `CheckConstraint`s on both |

---

## 11. Architecture Validation

| Gate | Status |
|---|---|
| ✓ Domain imports zero Django | Pass |
| ✓ Application imports only Ports | Pass |
| ✓ Infrastructure never leaks ORM | Pass — every repository/selector method returns a domain dataclass or plain dict, never an ORM instance |
| ✓ No circular imports | Pass |
| ✓ Repository mapping complete | Pass |
| ✓ Composition complete | Pass — 37 factories |
| ✓ Tasks compile | Pass |
| ✓ Event handlers compile | Pass — 19/19 events dispatched, cross-checked programmatically |
| ✓ Health checks compile | Pass — 5 checks, one of which actually exercises the calculation engine |
| ✓ Admin compiles | Pass |
| ✓ Cache works | Pass (self-contained versioned-key mechanism, same as `apps.inventory` — `pricing` is also not in the closed `CacheDomain` enum, same documented platform gap) |
| ✓ Metrics work | Pass |
| ✓ Event registration complete | Pass — 19 events registered in `shared/event_contracts/pricing.py` |
| ✓ OpenAPI registration complete | Pass — "Pricing"/"Pricing Admin" tags added |
| ✓ Dependency direction verified | Pass — including a **re-verification** that zero forward dependencies on Wallet/Loyalty/Ordering/Cart/Analytics exist anywhere in the module after this phase's additions, not just at the end of Phase 1 |

---

## 12. Infrastructure Certification

**Every architectural inconsistency discovered, every real bug caught and fixed, and every drafting mistake caught before completion, reported honestly per this phase's explicit instruction:**

1. **A factual error in the Phase 1 report, caught and corrected here.** That report stated "20 domain events." The actual count, verified directly against `domain/events.py` in this phase, is **19**. This was a genuine miscount in the prior report, not a change in the code — `domain/events.py` was not modified this phase. Correcting it here rather than silently repeating or ignoring the discrepancy.
2. **The `__import__()` hack pattern recurred a fifth time across this build**, this time in `tasks.py::expire_price_snapshots` (`__import__("apps.pricing.domain.enums", fromlist=["PriceSnapshotStatus"])` instead of a normal import). This exact pattern was previously caught and fixed in Store's `tasks.py`, and three times across Inventory's `selectors.py`/`tasks.py`/`health.py`. Fixed immediately upon noticing it this time, and the entire Pricing module was swept with `grep -rn "__import__(" apps/pricing/` afterward to confirm no other instances remained — none did.
3. **An awkward ternary-for-side-effect** in `DjangoPriceListRepository.save()` (`row.entries.exclude(...).delete() if price_list.entries else None`) — functionally correct but stylistically the "technically works but looks like a mistake" pattern this build has committed to catching. Replaced with a plain `if` statement.
4. **A previously-undocumented business rule made explicit at the database level**: nothing in Phase 1's `Coupon` aggregate structurally prevents the same coupon being redeemed twice for the same `order_reference` (the aggregate's `redeem()` method doesn't check for a duplicate order reference, only overall exhaustion). Added `UniqueConstraint(coupon, order_reference)` at the database level as a real safety net for this gap — flagged here rather than silently patched without mention, since it represents a genuine, if narrow, domain-layer gap from Phase 1 that Infrastructure is now compensating for at one layer only. A complete fix would also add the same check to `Coupon.redeem()` itself in a future Domain amendment.

**No other architectural inconsistency was discovered.** All quality gates in §11 passed on inspection.

**The Pricing Infrastructure layer is complete, internally consistent, and ready for the Interfaces phase.** As with every module in this build, this is verified-correct-by-static-inspection and by compile check (1139/1139 repository-wide files), not verified-passing-against-a-live-database.

**Stopping here per the explicit "do not implement Interfaces/Tests" instruction.**
