# Cart Module — Phase 2 (Infrastructure) Certification Report

**Every number in this report was counted directly from source during this phase, not reused from Phase 1's report or any other module's report. One counting error was found in this pass's own first-draft numbers and corrected before this report — see §12.**

---

## Step 1 — Architecture Review Findings

Verified directly, not assumed:

| Check | Result |
|---|---|
| `apps/cart/` scaffold exists | ✓ Confirmed — full Phase 1 domain/application tree present |
| `apps.cart` in `INSTALLED_APPS` | ✓ Confirmed — present with the explanatory comment added during Phase 1 |
| Phase 1 compiles | ✓ Confirmed — `apps/cart/domain/*.py` and `apps/cart/application/**/*.py` recompiled fresh before any new code was written |
| Composition-root convention | ✓ Confirmed against Pricing's (most recently built) `composition.py` — explicit `build_*()` factories, no service locator |
| Shared Kernel usage | ✓ `Money` imported from `shared.value_objects.money`, never redefined (inherited correctly from Phase 1) |
| Cache convention | ✓ Cart's own `_shared.py::invalidate_cart_cache()` already uses the self-contained versioned-key mechanism (written correctly in Phase 1, confirmed still consistent) |
| Event registration convention | ✓ Confirmed against `shared/event_contracts/pricing.py`'s structure |

**No architectural inconsistency was discovered during Step 1 of Phase 2.** The single inconsistency for this module (the missing `apps/cart` scaffold) was already found and resolved in Phase 1; this phase's review confirmed that fix is still in place and correct.

---

## 1. Folder Tree

```
apps/cart/infrastructure/
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
apps/cart/apps.py
shared/event_contracts/cart.py
```

---

## 2. Files Created

10 files under `apps/cart/infrastructure/`, plus `apps/cart/apps.py`, `shared/event_contracts/cart.py`, and 2 new OpenAPI tags ("Cart"/"Cart Admin") registered in `config/settings/base.py`.

---

## 3. ORM Model Summary

**7 tables** (verified by direct class listing, not a fragile grep pattern — see §12 for the counting mistake this caught): `CartModel`, `CartItemModel`, `PriceSnapshotReferenceModel`, `AttachedReservationModel`, `CartSnapshotModel`, `CartAuditEntryModel`, `CartOutboxEvent`.

| Table | Mirrors | Notes |
|---|---|---|
| `CartModel` | `Cart` (root) | Unique `code`, unique `token`; shipping/tax estimates embedded as flat columns (singular, at-most-one-per-cart fields, unlike the genuinely per-item reference tables below); `CheckConstraint(version >= 1)` |
| `CartItemModel` | `CartItem` | `CheckConstraint(quantity >= 0)` — the database-level backstop for the same rule `Quantity.__post_init__` enforces in the domain |
| `PriceSnapshotReferenceModel` | `PriceReference` | OneToOne with `CartItemModel` — this phase's explicitly-named "PriceSnapshotReference" persistence expectation, modeled as its own table (not flattened columns) since it has real, independent structure |
| `AttachedReservationModel` | `InventoryReservationReference` | OneToOne with `CartItemModel` — this phase's explicitly-named "AttachedReservation" persistence expectation |
| `CartSnapshotModel` | `CartSnapshot` | Append-only, no update path exposed |
| `CartAuditEntryModel` | `CartAuditEntry` | Append-only, no update path exposed |
| `CartOutboxEvent` | — | Concrete Outbox table for `cart` schema |

`CartValidationIssue` has **no table** — its own Phase 1 docstring is explicit that it's computed fresh on demand, never persisted; no repository method here constructs or returns one, matching that design intent exactly.

---

## 4. Repository Summary

**1 concrete class** (matching Cart's single-aggregate design): `DjangoCartRepository`, implementing the single `CartRepository` Port. Handles the full owned-entity graph on every `save()` — items (with their nested, at-most-one `PriceSnapshotReferenceModel`/`AttachedReservationModel`), snapshots, and audit entries — reconciling each collection (delete-stale, upsert-current) rather than blind inserts. Catches `IntegrityError` and re-raises as `ConflictError`. No repository method returns an ORM object outside `infrastructure/`.

---

## 5. Selector Summary

**6 selector classes**: `CartSelector` (list/detail with item-count annotation), `CartItemSelector`, `CartSnapshotSelector`, `CartAuditSelector` (paginated), `AbandonedCartSelector` (backs the abandoned-cart cleanup task), plus `DjangoCartSearchBackend` implementing `CartSearchGateway`. All read-only, zero business logic, zero aggregate construction.

**One real bug caught and fixed during drafting, before this report:** an early draft of `DjangoCartSearchBackend.search()` attempted `token__icontains` filtering against `CartModel.token`, a `UUIDField`. `icontains` against a native UUID column is dubious at the Postgres level (UUID columns aren't stored as text, so a substring match either fails outright or requires an implicit cast Django doesn't automatically provide) and isn't realistic search UX in the first place (nobody searches a cart by a partial UUID). Removed before compiling against a real database could have surfaced it as a runtime failure; search now filters on `code` only.

---

## 6. Event Handler Summary

`event_handlers.py::handle_cart_event()` — one dispatch-table function, matching the identical pattern in every prior module's infrastructure phase, never an if/else chain. **Cross-checked programmatically**: all 22 domain events appear as keys in the `_EVENT_TO_CACHE_GROUPS` dispatch table, verified by AST-parsing the file and diffing against `domain/events.py`'s class list — zero mismatches.

---

## 7. Celery Task Summary

**5 tasks** + the standard Outbox relay: `expire_carts` (sweeps overdue ACTIVE/SAVED carts, calls the real `ExpireCart` service), `cleanup_abandoned_carts` (sweeps inactive carts, calls the real `ArchiveCart` service), `cleanup_expired_reservations` (detaches Cart's own stale reservation references via the real `DetachReservation` service — Cart never talks to Inventory directly, consistent with the "reference by ID only" rule), `rebuild_statistics`, `relay_outbox_events`.

**One real mistake caught and fixed during drafting, not left in:** the first draft of `cleanup_abandoned_carts` contained `__import__("uuid").UUID(entry["id"])` instead of a normal `import uuid` — the same `__import__()` hack pattern already caught and fixed five times earlier across this build (Store, three places in Inventory, once in Pricing). This is the **sixth** occurrence of this exact mistake, caught immediately upon writing it this time rather than after the fact, and the entire `apps/cart/` tree was then swept with `grep -rn "__import__(" apps/cart/` to confirm no other instance remained. None did.

---

## 8. Health Summary

**5 checks**, each executing real logic, not merely an import test: `check_cart_repository`, `check_cart_cache`, `check_cart_state_consistency` (flags any cart that is archived/converted while still marked locked — a real structural inconsistency a live query can actually catch), `check_reservation_cleanup` (flags overdue `AttachedReservation` rows the sweep task hasn't yet processed), `check_snapshot_validity` (inspects the 20 most recent `CartSnapshotModel` rows' `items_snapshot` JSON for the expected shape, catching silent corruption from a future migration or manual edit).

---

## 9. Composition Root Summary

**31 `build_*()` factory functions** for 28 Application Services (verified by direct count, not reused from Phase 1's report) — the 3 additional factories (`build_cart_repository`, `build_cart_selector`, `build_cart_service_context`) are infrastructure/context accessors, not services, added so no future Interfaces-layer view has any reason to instantiate a repository directly.

---

## 10. Database Constraints Summary

| Rule | Enforcement |
|---|---|
| Cart version always ≥ 1 | `CheckConstraint` on `CartModel` |
| Item quantity never negative | `CheckConstraint` on `CartItemModel` |
| Unique cart code | `CartModel.code` unique |
| Unique cart token (guest access) | `CartModel.token` unique |
| Unique snapshot token | `CartSnapshotModel.token` unique |
| Price snapshot amount non-negative | `CheckConstraint` on `PriceSnapshotReferenceModel` |
| At most one price reference per item | `OneToOneField(CartItemModel)` on `PriceSnapshotReferenceModel` |
| At most one reservation reference per item | `OneToOneField(CartItemModel)` on `AttachedReservationModel` |

---

## 11. Architecture Validation

| Gate | Status |
|---|---|
| ✓ Domain imports zero Django | Pass |
| ✓ Application imports only Ports | Pass |
| ✓ Infrastructure never leaks ORM | Pass — every repository/selector method returns a domain dataclass or plain dict |
| ✓ No circular imports | Pass |
| ✓ Repository mapping complete | Pass |
| ✓ Composition complete | Pass — 31 factories for 28 services |
| ✓ Tasks compile | Pass |
| ✓ Event handlers compile | Pass — 22/22 events dispatched, cross-checked programmatically |
| ✓ Health checks compile | Pass — 5 checks, each executing real logic |
| ✓ Admin compiles | Pass — 7 registered models |
| ✓ Cache integration works | Pass (self-contained versioned-key mechanism, same documented `CacheDomain` gap as `apps.inventory`/`apps.pricing` — `cart` is also not in the closed enum) |
| ✓ Metrics compile | Pass |
| ✓ Event registration complete | Pass — 22 events registered in `shared/event_contracts/cart.py`, count-verified to match `domain/events.py` exactly |
| ✓ OpenAPI registration complete | Pass — "Cart"/"Cart Admin" tags added |
| ✓ Zero forward dependency on Wallet/Loyalty/Ordering/Fulfillment/Analytics/POS | Pass — re-verified fresh across the entire `apps/cart/` tree including the new infrastructure code, zero matches |

**No architectural inconsistency, layering violation, repository leak, or duplicated mapping was discovered this phase beyond the two drafting mistakes reported below.**

---

## 12. Infrastructure Certification

**Every mistake found during this phase, reported honestly, per this phase's explicit instruction:**

1. **A dubious `UUIDField.icontains` filter caught and removed before it could fail at runtime** — see §5.
2. **A sixth occurrence of the `__import__()` hack, caught immediately and fixed** — see §7. This pattern has now appeared in Store, three places in Inventory, once in Pricing, and once here. The fix is identical each time (a normal top-level import); the value of reporting the recurrence count is to make the pattern itself visible across this build's history, not just each individual instance.
3. **A genuine counting mistake in this report's own first draft**: an initial grep (`^class.*models\.`) for the ORM model count returned 4, undercounting the real total of 7 — the pattern only matched classes with `models.` literally appearing on the class-declaration line (i.e., `class X(models.Model):`), missing `CartModel`/`CartItemModel` (which inherit from `BaseModel`, not `models.Model` directly) and `CartOutboxEvent` (which inherits from `AbstractOutboxEvent`). Caught by switching to a direct, unfiltered class-listing grep before this report was finalized, not after. This is the same category of mistake (trusting a first-pass count without verifying the counting method itself) already found in Pricing's Phase 3 review (Application Services miscounted as 25 instead of 24, factories as 37 instead of 32) — this time caught within the same phase it occurred, before the wrong number ever left this document.

**No other architectural inconsistency was discovered.**

**The Cart Infrastructure layer is complete, internally consistent, and ready for the Interfaces phase.** As with every module in this build, this is verified-correct-by-static-inspection and by compile check (1204/1204 repository-wide files), not verified-passing-against-a-live-database.

**Stopping here per the explicit "do not begin Phase 3/Phase 4" instruction.**
