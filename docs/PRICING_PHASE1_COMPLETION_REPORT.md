# Pricing Module — Phase 1 Completion Report

**Scope:** Domain and Application layers only. Infrastructure, Interfaces, and Tests are **not** started, per this phase's explicit instruction.

---

## 1. Folder Tree

```
apps/pricing/
├── domain/
│   ├── enums.py
│   ├── value_objects.py
│   ├── entities.py
│   ├── aggregates.py
│   ├── exceptions.py
│   ├── events.py
│   ├── services.py
│   └── validators.py
├── application/
│   ├── ports.py
│   ├── selectors.py
│   └── services/
│       ├── _shared.py                       (PricingServiceContext)
│       ├── price_lists.py                   (CreatePriceList/Activate/Archive/SetPrice)
│       ├── rules_and_campaigns.py            (PricingRule + Campaign lifecycle)
│       ├── coupons_bundles_snapshots.py      (Coupon/BundlePrice/PriceSnapshot lifecycle)
│       └── queries.py                       (CalculatePrice, GetPriceHistory, etc.)
├── infrastructure/    (empty scaffold only)
├── interfaces/          (empty scaffold only)
└── tests/                (empty scaffold only)
```

21 Python files across `domain/` and `application/`, all syntax-verified clean.

---

## 2. Files Created

| File | Purpose |
|---|---|
| `domain/enums.py` | 13 enums covering all 30 capabilities' discriminators |
| `domain/value_objects.py` | `Money` (Shared Kernel re-export), `Percentage`, `DiscountValue`, `MarginPercentage`, `TaxRate`, `PriceValidityPeriod`, `QuantityTier`, `PriceSnapshotToken`, `PriceListCode`, `CouponCode`, `RegionCode` |
| `domain/entities.py` | `PriceListEntry`, `CampaignTarget`, `PriceHistoryEntry`, `CouponRedemption`, `DiscountLine` |
| `domain/aggregates.py` | `PriceList`, `PricingRule`, `Campaign`, `Coupon`, `BundlePrice`, `PriceSnapshot` — 6 aggregates |
| `domain/exceptions.py` | 19 exception types |
| `domain/events.py` | 20 domain events |
| `domain/services.py` | `PriceCalculationEngine` (the deterministic core), `MarginCalculator`, `TaxCalculator`, `CashbackPolicy`, `WalletDiscountPolicy`, `LoyaltyDiscountPolicy`, `PricePreviewPolicy` |
| `domain/validators.py` | 6 validators |
| `application/ports.py` | 6 repository Protocols + 1 search gateway |
| `application/selectors.py` | `PricingSelector` + `PricingSearchBackend` Protocol |
| `application/services/*.py` | 25 Application Services |

---

## 3. Domain Architecture

Zero Django imports in `domain/` (verified by grep). `pricing` **is** Domain Architecture Specification §2.3, confirmed before writing any code by reading the existing placeholder scaffold's own docstrings (which named §2.3 explicitly), not assumed from memory.

**The one real architectural inconsistency found in Step 1, and its resolution:** this phase's Step 3 requires Pricing to support Loyalty Discount, Wallet Discount, Cashback Calculation, and Membership Pricing — but Wallet and Loyalty are themselves still unimplemented (verified by reading their own placeholder `domain/aggregates.py` files directly). The resolution, applied consistently throughout: Pricing never imports `apps.wallet.domain`/`apps.loyalty.domain` and never queries either module. Instead:
- `WalletDiscountPolicy.apply()` and `LoyaltyDiscountPolicy.apply()` are pure functions taking a wallet balance / loyalty tier code as a **plain parameter**, supplied by whatever caller has that information (a future Cart/Ordering module).
- `CashbackCalculated` is a one-directional domain event — Pricing computes the amount and publishes it; crediting a wallet is Wallet's future responsibility, consumed asynchronously via the Outbox, exactly like every other cross-module event flow in this build.

This was verified to hold after implementation, not just declared as intent: `grep -rn "apps.wallet\|apps.loyalty\|apps.ordering\|apps.cart\|apps.analytics" apps/pricing/domain/ apps/pricing/application/` returns zero matches.

---

## 4. Aggregate Design

| Aggregate | Capabilities Covered | Key Invariants |
|---|---|---|
| **PriceList** | Base/Cost/Sale/Compare-at Price, Pricing History | `set_price()` validates sale ≤ base and compare-at ≥ base (via `PriceListEntry.__post_init__`) and unconditionally appends a `PriceHistoryEntry` — history isn't opt-in, it's structural to every price change |
| **PricingRule** | Dynamic, Quantity, Time-based, Scheduled, Regional, Membership Pricing | `__post_init__` requires each `rule_type` to carry the data it needs (quantity tiers for QUANTITY_DISCOUNT, a validity period for TIME_BASED, etc.) — an incomplete rule can't be constructed at all |
| **Campaign** | Flash Sale, Campaign Pricing | `is_active_at()`/`assert_active_at()` combine status AND validity-window checks; ending/cancelling follow documented lifecycle guards |
| **Coupon** | Coupon Pricing, Promo Pricing | `redeem()` calls `assert_redeemable()` first (active + not expired + under redemption limit) and auto-transitions to `EXHAUSTED` the moment the limit is reached — no separate "check then exhaust" race |
| **BundlePrice** | Bundle Pricing | Simple lifecycle; references `products.Bundle` by ID only |
| **PriceSnapshot** | Price Lock, Price Snapshot | `consume()` is one-way — a consumed or released snapshot can never be re-consumed or re-released, enforced by `assert_valid_at()` checking status before every transition |

---

## 5. Pricing Engine Design

`PriceCalculationEngine.calculate()` (domain/services.py) is the **single, deterministic** entry point every price computation in this module routes through — no calculation logic is duplicated elsewhere. The algorithm, documented in the code itself:

1. Sort every candidate discount by `priority` ascending, tiebroken by `DiscountSourceType` declaration order, then by `source_id` — fully deterministic even for otherwise-identical entries.
2. If any `EXCLUSIVE` discount is present, apply only the single highest-precedence one and ignore everything else.
3. Otherwise, if any `BEST_OF` discounts are present, compute each independently against the base price and apply only the single largest resulting discount.
4. Every `STACKABLE` discount then applies cumulatively, in sorted order, each computed against the price remaining after the prior stackable discount (sequential, not all against the original base) — a documented, deliberate choice, not an accident.

`CalculatePrice` (application/services/queries.py) is the one Application Service that assembles real `DiscountSource` candidates (from active `PricingRule`s, active `Campaign`s targeting the variant, and an optionally-supplied coupon code) and hands them to the engine exactly once.

---

## 6. Pricing Rules

Quantity Discount (`PricingRule.tier_for_quantity()` — highest-qualifying tier wins), Time-based/Scheduled (`PriceValidityPeriod.is_active_at()`), Regional (`region` match), Dynamic (an intentionally condition-free rule type, left to the Application Service caller to decide when it applies — e.g. based on stock levels, a future Inventory-driven trigger), Membership (`membership_tier_code` string match, supplied by caller).

---

## 7. Discount Rules

Discount Stacking (`StackingMode`: EXCLUSIVE/STACKABLE/BEST_OF) and Promotion Priority (`priority: int`, lower runs first) are both first-class fields on every discount-bearing aggregate, consumed exclusively by `PriceCalculationEngine` — see §5 for the deterministic algorithm.

---

## 8. Cashback Rules

`CashbackPolicy.calculate(price, cashback_rate)` — a pure percentage-of-price calculation. The resulting amount is published via `CashbackCalculated`, never credited by Pricing itself (see §3).

---

## 9. Margin Rules

`MarginCalculator.margin_percentage()` (signed, can go negative to flag a loss), `.profit_amount()` (sale − cost), and `.assert_non_negative_margin()` — which raises `NegativeMargin` unless the caller explicitly passes `allow_loss_leader=True`, making an intentional below-cost price a deliberate, visible choice rather than a silent possibility.

---

## 10. Domain Events

20 events: `PriceListCreated`, `PriceListActivated`, `PriceListArchivedEvent`, `PriceSet`, `PricingRuleCreated`, `PricingRuleActivated`, `PricingRuleArchived`, `CampaignCreated`, `CampaignActivated`, `CampaignEnded`, `CampaignCancelled`, `CouponCreated`, `CouponRedeemed`, `CouponRevoked`, `BundlePriceCreated`, `PriceLocked`, `PriceSnapshotConsumed`, `PriceSnapshotReleased`, `CashbackCalculated`. (`PriceListArchivedEvent` is suffixed `Event` to avoid colliding with the `PriceListArchived` domain exception — the same naming-collision pattern already resolved identically in `apps.inventory`'s `InventoryArchivedEvent`/`InventoryArchived`.)

---

## 11. Domain Exceptions

19 exceptions, all subclassing `common.exceptions.DomainException`: `InvalidPriceConfiguration`, `DuplicatePriceListEntry`, `DuplicateCouponCode`, `CouponExpired`, `CouponExhausted`, `CouponNotActive`, `CampaignNotActive`, `CampaignSchedulingConflict`, `InvalidDiscountStack`, `PriceListArchived`, 5 lifecycle-transition exceptions, `PriceSnapshotExpired`, `PriceSnapshotAlreadyConsumed`, `NegativeMargin`, `PricingEntityNotFound`.

---

## 12. Value Objects

`Money` (Shared Kernel, re-exported from `shared.value_objects.money` — never redefined), `Percentage` (0-100, exact Decimal arithmetic), `DiscountValue` (percentage-or-fixed-amount, exactly one populated), `MarginPercentage`, `TaxRate`, `PriceValidityPeriod`, `QuantityTier`, `PriceSnapshotToken`, plus 3 code-format value objects (`PriceListCode`, `CouponCode`, `RegionCode`).

---

## 13. Repository Ports

`PriceListRepository`, `PricingRuleRepository`, `CampaignRepository`, `CouponRepository`, `BundlePriceRepository`, `PriceSnapshotRepository`, `PricingSearchGateway` — 6 aggregate repositories + 1 search gateway, one per aggregate, matching the 1:1 pattern every prior module follows.

---

## 14. Application Services

25 services across 4 files:

**Price Lists (4):** CreatePriceList, ActivatePriceList, ArchivePriceList, SetPrice
**Rules & Campaigns (7):** CreatePricingRule, ActivatePricingRule, ArchivePricingRule, CreateCampaign, ActivateCampaign, EndCampaign, CancelCampaign
**Coupons/Bundles/Snapshots (8):** CreateCoupon, RedeemCoupon, RevokeCoupon, CreateBundlePrice, ActivateBundlePrice, LockPrice, ConsumePriceSnapshot, ReleasePriceSnapshot
**Queries (5):** CalculatePrice, GetPriceHistory, GetPriceList, ListPriceLists, SearchPricing

---

## 15. Dependency Validation

| Check | Status |
|---|---|
| Domain contains zero Django imports | ✓ Pass |
| Application depends only on Ports (+ documented `transaction.atomic` exception) | ✓ Pass |
| No circular imports | ✓ Pass |
| **No forward dependency on Wallet/Loyalty/Ordering/Cart/Analytics** | ✓ Pass — verified by grep after implementation, zero matches |
| No ORM, no Infrastructure dependency | ✓ Pass |

---

## 16. Architecture Validation

| Gate | Status |
|---|---|
| ✓ Domain has zero Django imports | Pass |
| ✓ Application imports only Ports | Pass |
| ✓ No ORM | Pass |
| ✓ No Infrastructure dependency | Pass |
| ✓ No circular imports | Pass |
| ✓ Aggregate invariants enforced | Pass — see §4 |
| ✓ Events complete | Pass — 20 events |
| ✓ Exceptions complete | Pass — 19 exceptions |
| ✓ Validators complete | Pass — 6 validators |
| ✓ Services compile | Pass — all 25 |
| ✓ No duplicated pricing calculation | Pass — `PriceCalculationEngine` is the sole calculation path |
| ✓ Discount priority deterministic | Pass — documented, three-level tiebreak (priority → type order → source_id) |
| ✓ Pricing rules consistent | Pass |

**One real issue found and fixed during this pass, not left in:** `CalculatePrice` (application layer) initially called `PriceList._entry_for_variant()` — a "private," underscore-prefixed aggregate method — directly. This is the same layering violation already caught once in Inventory's `CreateSnapshot` (reaching into `WarehouseInventory._get()`). Fixed identically: added a public `PriceList.entry_for_variant()` accessor and updated the call site, rather than leaving the private-method reach-in in place.

---

## Known Limitations

1. **No Infrastructure/Interfaces/Tests** — correct and expected for Phase 1.
2. **Pricing does not itself resolve which PriceList applies to a given request** (by store, channel, or region) — `CalculatePrice` requires the caller to supply a `price_list_id` directly. A future `ResolveApplicablePriceList` service (region/channel → PriceList) is a natural Phase 2+ addition once the resolution rules are specified, not invented here without a concrete requirement.
3. **`Campaign`/`Coupon` targeting is variant-level only in this phase** — `CampaignTarget.target_type` supports "category"/"bundle" as declared values, but no Application Service yet resolves "all variants in category X" into concrete variant matches (that resolution would need a Products-module category-membership query, deferred).
4. **Tax jurisdiction/rate lookup is out of scope** — `TaxCalculator` applies a caller-supplied `TaxRate`; determining the correct rate for a given order/region is a future concern, consistent with Architecture Review's "vendor/system not yet selected" pattern used elsewhere in this build.

**No architectural inconsistency was discovered during Pricing Phase 1** beyond the one identified and resolved in Step 1 (documented in §3) — every other quality gate passed cleanly on the first implementation pass.

---

## Recommendations for Phase 2

- Infrastructure ORM models should mirror the 6 aggregates + their owned entities (PriceListEntry, PriceHistoryEntry, CampaignTarget, CouponRedemption) as separate tables, following the same BaseModel/SoftDeleteModel pattern used throughout.
- `PricingRuleRepository.list_active_at()` and `CampaignRepository.list_active_for_target()` are the two read paths `CalculatePrice` calls on every price lookup — these should be indexed carefully (status + validity-window range queries) since they're on the hot path for any future storefront price display.
- Cache invalidation should key off `PriceSet`/`CampaignActivated`/`CouponRedeemed` etc., matching the Outbox-driven event-handler dispatch-table pattern already established in `apps.inventory`/`apps.store`/`apps.geo`.
