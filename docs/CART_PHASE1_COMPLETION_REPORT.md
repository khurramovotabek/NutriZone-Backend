# Cart Module — Phase 1 Completion Report

**Every number in this report was counted directly from source during this phase — no number is reused from any other module's report.**

---

## Step 1 — Architecture Review

Before writing any code, the following was actually inspected, not assumed:

| Item | Finding |
|---|---|
| Pricing module completion | Confirmed complete and certified across all 4 phases (re-verified by compiling `apps/pricing/` fresh) |
| Cart's placeholder module | **Did not exist at all** — no folder, no `INSTALLED_APPS` entry (see Inconsistency below) |
| Shared Kernel `Money` | Confirmed at `shared/value_objects/money.py`, a thin re-export of `common/utils/money.py`'s single canonical implementation — read directly, not assumed |
| `DomainException` hierarchy | Confirmed 8 subclasses in `common/exceptions/exceptions.py`, ready to extend |
| Cross-module reference targets | `apps.products.domain.aggregates.ProductVariant`, `apps.pricing.domain.aggregates.PriceSnapshot`, `apps.inventory.domain.aggregates.Reservation`, `apps.identity.domain.aggregates.User` all confirmed to exist as real aggregates, for Cart to reference by ID only |
| Outbox / composition-root / repository conventions | Already consistently established across 5 prior modules; no re-verification needed beyond confirming Cart's own new code follows them (see Architecture Validation, below) |

### Inconsistency discovered and resolved

**What was wrong:** `apps/cart` did not exist anywhere in the repository — no folder, no `INSTALLED_APPS` entry. This is unlike every other module built in this project (Store, Inventory, Pricing all had genuine Foundation-era placeholder scaffolding, even where mis-named, before their own Phase 1 began).

**Why it is wrong:** Foundation's original design scaffolded a fixed set of bounded-context app skeletons in advance, specifically so every later module's Phase 1 would start from an existing stub, not a blank slate. Cart's total absence broke that pattern.

**Architectural impact:** Not blocking for this phase (pure Python domain/application code needs no Django app registration), but left unresolved it would become a real blocker the moment Phase 2 (Infrastructure) tries to register ORM models against a non-existent app.

**Resolution applied:** Created `apps/cart/` with the standard scaffold shape, and added `"apps.cart"` to `INSTALLED_APPS` in `config/settings/base.py` with an inline comment explaining why it's there and why it wasn't already — a safe, additive, minimum-necessary fix.

**No other inconsistency was discovered during Step 1.**

---

## Folder Tree

```
apps/cart/
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
│       ├── _shared.py                       (CartServiceContext)
│       ├── lifecycle.py                     (CreateCart/LoadCart/SaveCart/Archive/Expire/Restore)
│       ├── items.py                         (AddItem/RemoveItem/UpdateQuantity/BulkUpdate/ClearCart)
│       ├── references.py                    (Coupon/PriceSnapshot/Reservation attach-detach)
│       ├── merge_and_ownership.py           (MergeGuestCart/AssignCustomer)
│       ├── snapshots_and_validation.py      (Snapshot create/restore, ValidateCart, CheckoutReadiness)
│       └── queries.py                       (GetCart, ListCustomerCarts, SearchCart, GetSnapshotHistory, AdminListCarts)
├── infrastructure/    (empty scaffold only)
├── interfaces/          (empty scaffold only)
└── tests/                (empty scaffold only)
```

---

## Files Created

20 Python files across `domain/` and `application/`, plus the `apps.cart` `INSTALLED_APPS` registration, all syntax-verified clean.

---

## Aggregate Design

**A single aggregate (`Cart`)** — deliberately, not several. Cart's own functional-scope statement is explicit that it "owns shopping cart state only," and every required capability (guest/authenticated/saved carts, merge, snapshots, checkout readiness) is a state or transition of one cart, not an independently life-cycled thing. `CartItem`, `CartSnapshot`, `CartAuditEntry`, `PriceReference`, `InventoryReservationReference`, `ShippingEstimateReference`, `TaxEstimateReference`, and `CartValidationIssue` are all owned directly by `Cart`, with no independent repository or identity outside their owning cart.

Key structural invariants:
- **`_assert_mutable()`** is called at the top of every item-mutating method — locked, archived, or converted carts structurally cannot be changed, not merely discouraged from being changed.
- **Version tracking**: every mutating method calls `_bump_version()` — optimistic-locking version increments are not opt-in per method, they're structural to the mutation path itself.
- **Merge is one-directional and non-destructive of the source**: `Cart.merge_guest_cart()` mutates `self` only; the guest cart is left untouched by the domain method and archived separately by the orchestrating Application Service (`MergeGuestCart`), since "a Cart aggregate doesn't reach out and mutate another Cart instance's lifecycle from within its own method" is a deliberate boundary.
- **Snapshot restoration is explicitly partial**: `restore_snapshot()` restores item quantities only — prices and reservations are never restored from a frozen snapshot, since only the caller (holding a live connection to Pricing/Inventory) can obtain a currently-valid price or reservation. This is documented in the method's own docstring, not left as a surprising omission.
- **`structural_checkout_readiness()`** is a fast, in-aggregate check using only Cart's own state; the fuller `CheckoutReadinessPolicy` (domain/services.py) layers in externally-gathered signals (e.g., reservation validity confirmed by the caller against Inventory) that the aggregate alone cannot know.

---

## Value Objects

**13 total** (verified precisely — 9 literal `@dataclass` classes plus 4 generated via a shared code-value-object factory, matching the same pattern established in every prior module's `value_objects.py`):

`CartCode`, `CurrencyCode`, `RegionCode`, `ChannelCode` (factory-generated format-validated codes), `CartToken`, `CartVersion`, `Quantity`, `CartNote`, `GiftMessage`, `EstimatedAmount`, `ExpirationPeriod`, `SnapshotToken`, `MergeResult`. `Money` is imported from the Shared Kernel, never redefined.

---

## Services (Domain)

**7 domain policy classes**: `CartMergePolicy` (recommends a `MergeStrategy` given item counts on both sides), `QuantityPolicy`, `ExpirationPolicy` (guest carts: 7-day TTL; authenticated: 30-day TTL — both named constants, not magic numbers), `SnapshotPolicy` (retention: max 20 snapshots per cart, with an oldest-first pruning helper), `CartValidationPolicy` (produces `CartValidationIssue`s from item state), `CheckoutReadinessPolicy` (layers external signals onto the aggregate's structural check), `CurrencyConversionPolicy` (validates a caller-supplied conversion is structurally sane; Cart never computes an exchange rate itself).

---

## Events

**22 domain events.** Two required an `Event` suffix to avoid colliding with a same-named domain exception — `CartArchivedEvent`/`CartArchived`, `CartExpiredEvent`/`CartExpired` — the same naming-collision category already resolved identically in `apps.inventory` (`InventoryArchivedEvent`) and `apps.pricing` (`PriceListArchivedEvent`). **A third, near-miss collision was caught and fixed during drafting, before it ever compiled**: an early version of `events.py` defined a `CartLocked` event class, which would have collided with the `CartLocked` domain exception already written in `exceptions.py` — caught by a self-check before this report, not discovered later. Renamed to `CartLockedEvent`, and the whole file was then cross-checked programmatically (`ast`-parsing both files' class names and diffing) to confirm zero remaining collisions.

---

## Exceptions

**17 exceptions**, all subclassing `common.exceptions.DomainException`: `CartLocked`, `CartAlreadyLocked`, `CartNotLocked`, `CartExpired`, `CartArchived`, `CartAlreadyConverted`, `InvalidCartLifecycleTransition`, `CartItemNotFound`, `InvalidQuantity`, `EmptyCart`, `CartNotEligibleForCheckout`, `CartOwnershipConflict`, `CartMergeConflict`, `CartSnapshotNotFound`, `CurrencyMismatch`, `CartValidationFailed`, `CartEntityNotFound`.

---

## Validators

**8 validators**: `CartCodeValidator`, `QuantityValidator`, `CartNoteValidator`, `GiftMessageValidator`, `CurrencyValidator`, `RegionValidator`, `MaxQuantityValidator`, `ItemCountValidator` (a platform-level sanity cap — max 200 distinct line items per cart — distinct from the customer-facing quantity-per-item cap).

---

## Ports

**2 Protocols**: `CartRepository` (the single repository, matching the single-aggregate design), `CartSearchGateway`.

---

## Application Services

**28 total** — the 26 explicitly named in this phase's brief (`CreateCart`, `LoadCart`, `MergeGuestCart`, `AssignCustomer`, `AddItem`, `RemoveItem`, `UpdateQuantity`, `BulkUpdateItems`, `ApplyCouponReference`, `RemoveCouponReference`, `AttachPriceSnapshot`, `DetachPriceSnapshot`, `AttachReservation`, `DetachReservation`, `SaveCart`, `ArchiveCart`, `ExpireCart`, `RestoreCart`, `CreateSnapshot`, `RestoreSnapshot`, `ValidateCart`, `CalculateCheckoutReadiness`, `SearchCart`, `ListCustomerCarts`, `GetCart`, `GetSnapshotHistory` — verified by literal count to be 26, not the 25 the brief's own summary language suggested), plus 2 justified, explicitly-flagged additions:
- **`ClearCart`** — "Clear Cart" is an explicitly required *capability* in this phase's brief, but no service in the named list reaches the aggregate's own `clear()` method. Added to close that gap.
- **`AdminListCarts`** — "admin listing across all carts" (as opposed to one customer's carts, which `ListCustomerCarts` already covers) has no other service; added following the same precedent as `Store`'s `AdminListStores`/`Inventory`'s `AdminListInventory`.

Neither addition is invented scope beyond what the phase's own functional requirements call for — both are named, flagged, and justified in their own docstrings, not silently introduced.

---

## Dependency Validation

| Check | Status |
|---|---|
| Domain contains zero Django imports | ✓ Pass |
| Application depends only on Ports (+ documented `transaction.atomic` exception) | ✓ Pass |
| No circular imports | ✓ Pass |
| **Zero forward dependency on Wallet/Loyalty/Ordering/Fulfillment/Analytics/POS/Telegram/Mobile/Frontend/Pricing/Inventory/Search** | ✓ Pass — verified by an exhaustive grep sweep across `apps/cart/domain/` and `apps/cart/application/`; the only two matches were docstring prose explaining the isolation rationale, not real imports |

---

## Architecture Validation

| Gate | Status |
|---|---|
| ✓ Domain has zero Django imports | Pass |
| ✓ Application depends only on Ports | Pass |
| ✓ No circular imports | Pass |
| ✓ No forward dependency on any not-yet-owned bounded context | Pass |
| ✓ Aggregate invariants enforced | Pass — see Aggregate Design |
| ✓ Events complete, zero naming collisions with exceptions | Pass — verified programmatically after one near-miss was caught and fixed |
| ✓ Exceptions complete | Pass — 17 |
| ✓ Validators complete | Pass — 8 |
| ✓ Services compile | Pass — all 28 |

**Two real drafting mistakes caught and fixed during this pass, not left in — reported honestly:**
1. **The `CartLocked` event/exception naming collision** described above under Events — caught before compiling, not after.
2. **Two unnecessary forward-reference string type annotations** (`"apps.cart.domain.value_objects.SnapshotToken"` in `entities.py`, `"apps.cart.domain.value_objects.MergeResult"` in `aggregates.py`) where a plain top-level import would do — there was no circular-import reason for either. Both replaced with direct imports and plain type names before this report, along with one resulting unused-import cleanup (`EmptyCart`, imported into `aggregates.py` but never actually raised there).

**No architectural inconsistency requiring a stop-and-explain cycle was found beyond the missing `apps/cart` scaffold itself (Step 1).**

---

## Compile Validation (fresh counts, this phase only)

| Metric | Count |
|---|---|
| Total repository-wide `.py` files | **1193** |
| Cart-specific `.py` files (domain + application + empty infra/interfaces/tests scaffolds) | **33** |
| Domain enums | 10 |
| Value objects (literal + factory-generated) | 13 |
| Entities | 8 |
| Domain events | 22 |
| Domain exceptions | 17 |
| Domain services (policy classes) | 7 |
| Validators | 8 |
| Ports | 2 |
| Application Services | 28 |

All 1193 repository-wide files compile cleanly via `python3 -m py_compile`.

---

## Known Limitations

1. **No Infrastructure/Interfaces/Tests** — correct and expected for Phase 1.
2. **`CurrencyConversionPolicy` validates but never performs conversion** — by design (Cart never computes FX rates itself), but this means any multi-currency cart scenario requires the caller to have already obtained a converted amount from elsewhere before calling into Cart; there is no "convert this cart to currency X" one-call Application Service in this phase, since that would require Cart to either own FX logic (against its own bounded-context rule) or synchronously call an external rate service (against the platform's async, event-driven cross-module integration style).
3. **Shipping/Tax estimate attachment (`attach_shipping_estimate`/`attach_tax_estimate`) has no dedicated domain event** — unlike every other state-changing Cart method, these two only bump the version silently. This was a deliberate choice (estimates are provisional, frequently-refreshed data, and emitting an event per refresh seemed like event-stream noise) but is flagged here as a real asymmetry with the rest of the aggregate's event-emission discipline, worth reconsidering in a future phase if downstream consumers (e.g. a future Analytics module) turn out to need to react to estimate changes.
4. **`CartMergePolicy.recommend_strategy()` is a simple heuristic** (empty-side wins outright, otherwise sum quantities) — a real storefront might want a richer UX (e.g., asking the customer to choose) which this phase does not attempt to anticipate.

**No architectural inconsistency was discovered during Cart Phase 1** beyond the missing `apps/cart` scaffold itself, identified and resolved in Step 1.

---

## Recommendations for Phase 2

- Infrastructure ORM models should mirror the single `Cart` aggregate plus its owned entities (`CartItem`, `CartSnapshot`, `CartAuditEntry`, and the two estimate-reference entities) as separate tables under one `cart_*` schema, following the same `BaseModel`/`SoftDeleteModel` pattern used throughout.
- `CartRepository.get_by_token()` is the hot read path for guest-cart access (no authentication required) — index the token column accordingly.
- `CartRepository.list_expiring_before()` backs a future Celery sweep task (mirroring `apps.inventory`'s `expire_reservations`/`apps.pricing`'s `expire_price_snapshots`) — the expiration policy constants (7-day guest, 30-day authenticated) are already centralized in `domain/services.py::ExpirationPolicy`, ready for that task to consume.
- Cache invalidation should key off `ItemAdded`/`ItemRemoved`/`ItemQuantityUpdated`/`CartMerged` etc., matching the Outbox-driven event-handler dispatch-table pattern already established in every infrastructure phase since Geo.
