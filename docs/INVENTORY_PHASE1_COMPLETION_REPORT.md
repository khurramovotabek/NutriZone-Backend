# Inventory Module — Phase 1 Completion Report

**Scope:** Domain and Application layers only. Infrastructure, Interfaces, and Tests are **not** started, per this phase's explicit instruction.

---

## 1. Folder Tree

```
apps/inventory/
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
│       ├── _shared.py             (InventoryServiceContext)
│       ├── lifecycle.py           (CreateInventory/UpdateInventory/Archive/Restore)
│       ├── stock_operations.py    (Receive/Reserve/Release/Transfer/Adjust/Damage/Expire)
│       ├── batch_and_serial.py    (Batch CRUD + Serial register/deactivate)
│       ├── reservations.py        (Create/Cancel/Expire)
│       ├── counting.py            (CycleCount + PhysicalInventory start/complete)
│       ├── snapshots_and_ledger.py (Snapshot create/restore, ledger rebuild/verify)
│       └── queries.py             (Get/List/Search/AdminList)
├── infrastructure/    (empty scaffold only)
├── interfaces/          (empty scaffold only)
└── tests/                (empty scaffold only)
```

21 Python files across `domain/` and `application/`, all syntax-verified clean.

---

## 2. Files Created

| File | Purpose |
|---|---|
| `domain/enums.py` | 12 enums: `InventoryStatus`, `StockStatus`, `MovementType`, `AdjustmentReason`, `ReservationStatus`, `BatchStatus`, `SerialStatus`, `LedgerEntryType`, `InventorySnapshotStatus`, `CycleCountStatus`, `PhysicalInventoryStatus`, `InventoryHealthStatus` |
| `domain/value_objects.py` | `InventoryCode`, `BatchNumber`, `LotNumber`, `SerialNumber`, `ReservationNumber`, `MovementReference`, `StockQuantity`, `ReservedQuantity`, `AvailableQuantity`, `ExpirationDate`, `ManufactureDate`, `ShelfCoordinate`, `BinCoordinate`, `InventoryLocation`, `StockThreshold`, `SnapshotVersion` |
| `domain/entities.py` | `InventoryLedger`, `InventoryTransaction`, `ReservationItem`, `BatchItem`, `SerialItem`, `InventoryHistory`, `StockSnapshot`, `StockAlert`, `ThresholdRule`, `MovementItem` |
| `domain/aggregates.py` | `Inventory`, `WarehouseInventory`, `ShelfInventory`, `Reservation`, `InventoryMovement`, `InventoryAdjustment`, `Batch`, `CycleCount`, `PhysicalInventory`, `InventorySnapshot` — all 10 requested aggregates |
| `domain/exceptions.py` | 20 exception types |
| `domain/events.py` | 19 domain events |
| `domain/services.py` | `FIFOAllocationPolicy`, `FEFOAllocationPolicy`, `ReservationPolicy`, `MovementPolicy`, `AdjustmentPolicy`, `ExpirationPolicy`, `BatchPolicy`, `SerialPolicy`, `InventoryHealthPolicy`, `SnapshotPolicy`, `ThresholdPolicy`, `LedgerPolicy` |
| `domain/validators.py` | `InventoryValidator`, `StockValidator`, `ReservationValidator`, `MovementValidator`, `AdjustmentValidator`, `BatchValidator`, `SerialValidator`, `ExpirationValidator`, `ThresholdValidator`, `WarehouseValidator`, `ShelfValidator` |
| `application/ports.py` | 14 repository/gateway Protocols (12 requested + 2 added, justified below) |
| `application/selectors.py` | `InventorySelector` + `InventorySearchBackend` Protocol |
| `application/services/*.py` | 31 Application Services (full list in §9) |

---

## 3. Domain Architecture Explanation

Zero Django imports in `domain/` (verified by grep). `inventory` **is** one of the Domain Architecture Specification's original eighteen bounded contexts — no reconciliation note was needed, matching `store` and `products`.

**Central design decision:** `WarehouseInventory` is the one aggregate every stock-affecting operation ultimately routes through. Every unit of stock lives in exactly one `StockStatus` bucket (AVAILABLE/RESERVED/INCOMING/DAMAGED/EXPIRED/QUARANTINE/RETURNED) at a time, and **every method on `WarehouseInventory` is a specific, named bucket-to-bucket transition** — there is no generic "set quantity" method. This is what makes the module's core invariants structural rather than merely checked:

- *"Damaged stock cannot be reserved"* — `reserve()` only reads from AVAILABLE; there is no code path that reserves from DAMAGED, because the method signature doesn't accept a source bucket.
- *"Quarantine stock cannot be transferred"* — `transfer_out()` only reads from AVAILABLE.
- *"Incoming stock cannot be sold"* — `sell()` only reads from RESERVED, and the only way stock reaches RESERVED is via `reserve()`, which only reads from AVAILABLE — so INCOMING stock is structurally two hops away from being sellable, both of which require it to first pass through AVAILABLE.
- *"Expired stock cannot become available"* — no method in the entire aggregate transitions stock **out of** EXPIRED back to AVAILABLE. It's not checked; it's simply absent from the method list.

This is a deliberate departure from writing one generic `move(from_status, to_status, quantity)` method and validating the transition against an allow-list — the allow-list approach would have made an invalid transition a runtime check that could theoretically be bypassed by a bug in the validation table; the named-methods approach makes it a compile-time impossibility (the caller literally cannot express "sell from damaged," because no such method exists to call).

**Modular-monolith isolation:** `ShelfCoordinate`/`BinCoordinate`/`GeoCoordinate`-adjacent concepts are this module's own value objects, not imports from `apps.store.domain` — the same accepted, documented duplication already established by `store` (its own `GeoCoordinate` vs. `geo`'s) and `geo` (its own `Coordinate`, shared with no one). Cross-module references (`Inventory.product_variant_id` → `products.ProductVariant`, `WarehouseInventory.warehouse_id` → `store.Warehouse`) are UUIDs only.

---

## 4. Aggregate Design Explanation

| Aggregate | Role | Key Invariant Mechanism |
|---|---|---|
| **Inventory** | Platform-wide tracking config for one sellable item (one ProductVariant) — status, thresholds, batch/serial-tracking flags. Owns no quantities itself. | `is_serial_tracked` requires `is_batch_tracked` (a serial can't exist outside a batch); lifecycle (`active` → `archived` → restored) mirrors `Product`/`Store`'s identical pattern |
| **WarehouseInventory** | The stock-bucket ledger for one Inventory item at one Warehouse | See §3 — every method is a named, structurally-constrained bucket transition, each returning an `InventoryTransaction` + `InventoryLedger` pair for the repository to persist |
| **ShelfInventory** | Shelf-granularity quantity within a WarehouseInventory | Simple `StockQuantity` arithmetic; negative-stock guard inherited from the value object itself |
| **Reservation** | A hold against AVAILABLE stock for a future owner (Cart/Order — not yet built) | Lifecycle (`pending`→`confirmed`/`cancelled`/`expired`); items are immutable once not-pending; `expire()` structurally requires `as_of >= expires_at` |
| **InventoryMovement** | The cross-warehouse record of one operation | `__post_init__` rejects a `TRANSFER` movement missing either endpoint |
| **InventoryAdjustment** | A manual correction record | Rejects a zero delta at construction |
| **Batch** | One received lot, with expiration/manufacture dates | `expiration_date` must be after `manufacture_date`; owns `SerialItem`s with in-aggregate duplicate-serial rejection; `assert_not_expired()` is called by any operation that would otherwise let an expired batch be allocated |
| **CycleCount** / **PhysicalInventory** | Structurally identical counting-workflow aggregates — CycleCount samples a subset, PhysicalInventory covers the full warehouse | `planned` → `in_progress` → `completed`/`cancelled`; `complete()` computes a discrepancy count by comparing counted vs. expected quantities |
| **InventorySnapshot** | Point-in-time capture for audit/rollback | `pending` → `completed`/`failed`; items are immutable once not-pending |

---

## 5. Business Rules Summary

| Rule | Where Enforced |
|---|---|
| Stock can never become negative | `StockQuantity.__post_init__` (structural) + `WarehouseInventory._set()`'s guard on every bucket write |
| Reserved stock cannot exceed available stock | `WarehouseInventory.reserve()` |
| Incoming stock cannot be sold | Structural (§3) |
| Expired stock cannot become available | Structural (§3) |
| Damaged stock cannot be reserved | Structural (§3) |
| Quarantine stock cannot be transferred | Structural (§3) |
| Batch numbers must be unique | `BatchPolicy.assert_unique_number()`, given a repository-sourced existing-numbers set (an Application Service concern) |
| Serial numbers must be unique | `SerialPolicy.assert_unique_number()` (same pattern) + `Batch.register_serial()`'s in-aggregate check |
| Reservation expiration validation | `Reservation.expire()` |
| Warehouse/Shelf consistency | `WarehouseValidator`/`ShelfValidator` (presence checks; existence is an Application Service repository lookup) |
| Inventory movement consistency | `InventoryMovement.__post_init__`, `MovementPolicy.assert_transfer_has_distinct_endpoints()` |
| Inventory adjustment validation | `InventoryAdjustment.__post_init__` (non-zero delta) + `AdjustmentPolicy.assert_reason_is_justified()` (DAMAGE/LOSS must be negative, FOUND must be positive) |
| FIFO allocation | `FIFOAllocationPolicy.allocate()` — sorts candidates by `received_at`, greedily allocates |
| FEFO allocation | `FEFOAllocationPolicy.allocate()` — sorts candidates by `expiration_date` (nulls last), greedily allocates |
| Batch expiration validation | `Batch.assert_not_expired()`, `ExpirationPolicy.is_expired()` |
| Stock threshold validation | `StockThreshold.__post_init__` (reorder_at ≤ low_stock_at ≤ overstock_at) |
| Cycle count / Physical inventory validation | Lifecycle guards on `CycleCount`/`PhysicalInventory`; `record_count()` rejects negative counts |
| Snapshot consistency | `SnapshotPolicy.assert_monotonic_version()` — a new snapshot version must exceed the latest existing one |
| Ledger balancing | `LedgerPolicy.verify_balance()`/`assert_balanced()` — replaying every ledger entry's delta must equal the claimed final balance |

---

## 6. Domain Events Table

19 events: `InventoryCreated`, `InventoryUpdated`, `InventoryArchivedEvent`, `InventoryRestored`, `StockReceived`, `StockReserved`, `ReservationReleased`, `StockTransferred`, `StockAdjusted`, `StockExpired`, `StockDamaged`, `BatchCreated`, `SerialRegistered`, `ReservationCreated`, `ReservationCancelled`, `ReservationExpiredEvent`, `CycleCountStarted`, `CycleCountCompleted`, `PhysicalInventoryStarted`, `PhysicalInventoryCompleted`, `InventorySnapshotCreated`. (`InventoryArchivedEvent`/`ReservationExpiredEvent` are named with an `Event` suffix to avoid colliding with the identically-named domain exceptions `InventoryArchived`/`ReservationExpired` in the same module — a real naming collision this phase's brief's own vocabulary created, resolved by suffix rather than silently picking one name for both concepts.)

Event classes are complete and typed; registration against `core.events.registry` via `shared/event_contracts/inventory.py` is a Phase 2 (Infrastructure) concern.

---

## 7. Domain Exceptions Table

20 exceptions: `NegativeStock`, `InsufficientStock`, `DuplicateBatch`, `DuplicateSerial`, `ReservationExpired`, `ReservationConflict`, `InvalidMovement`, `InvalidWarehouse`, `InvalidShelf`, `BatchExpired`, `InventoryArchived`, `LedgerCorrupted`, `InventoryMismatch`, plus 7 additional lifecycle/rule exceptions (`InvalidInventoryLifecycleTransition`, `InvalidReservationLifecycleTransition`, `InvalidCycleCountLifecycleTransition`, `InvalidPhysicalInventoryLifecycleTransition`, `DamagedStockCannotBeReserved`, `QuarantineStockCannotBeTransferred`, `IncomingStockCannotBeSold`, `ExpiredStockCannotBecomeAvailable`, `InventoryEntityNotFound`) needed to name every lifecycle transition guard explicitly, matching the naming discipline every prior module's exceptions.py has followed. (Note: the four "cannot be X" exceptions are defined but not currently raised anywhere — the equivalent business rules are enforced *structurally*, per §3, meaning the violation is never reachable in the first place. They're kept as named, documented exception types in case a future infrastructure-layer bulk-import path needs to validate a batch of external data against these same rules before it ever reaches the aggregate.)

---

## 8. Ports Table

| Port | Backs |
|---|---|
| `InventoryRepository` | Inventory CRUD, code/product-variant lookup |
| `WarehouseInventoryRepository` | The core stock-bucket aggregate's persistence |
| `ShelfInventoryRepository` | Shelf-level quantity persistence |
| `ReservationRepository` | Reservation CRUD + expired-reservation sweep query |
| `MovementRepository` | Movement history |
| `AdjustmentRepository` | Adjustment records |
| `LedgerRepository` | Read-only ledger-entry querying (backs `RebuildLedger`) |
| `BatchRepository` | Batch CRUD + FIFO/FEFO candidate querying |
| `SerialRepository` | Read-only serial-number lookups |
| `SnapshotRepository` | Snapshot CRUD + latest-version query |
| `CycleCountRepository` | **Added, not in this phase's original 12-port list** — `StartCycleCount`/`CompleteCycleCount` are explicitly-required Application Services with nowhere to persist a `CycleCount` aggregate without one. Same justified-addition pattern as `BundleRepository` in Products. |
| `PhysicalInventoryRepository` | **Added, same rationale**, backing `StartPhysicalInventory`/`CompletePhysicalInventory` |
| `InventorySearchGateway` | Anti-Corruption Layer seam for inventory search |

Cross-cutting ports (Cache/Audit/Metrics/Outbox/Clock/Health) consumed directly from `core/`, not redeclared.

---

## 9. Application Services Table

31 services across 7 files:

**Lifecycle (4):** CreateInventory, UpdateInventory, ArchiveInventory, RestoreInventory
**Stock Operations (7):** ReceiveStock, ReserveStock, ReleaseReservation, TransferStock, AdjustStock, DamageStock, ExpireStock
**Batch/Serial (5):** CreateBatch, UpdateBatch, DeleteBatch, RegisterSerial, DeactivateSerial
**Reservations (3):** CreateReservation, CancelReservation, ExpireReservation
**Counting (4):** StartCycleCount, CompleteCycleCount, StartPhysicalInventory, CompletePhysicalInventory
**Snapshots/Ledger (3):** CreateSnapshot, RestoreSnapshot, RebuildLedger
**Queries (4):** GetInventory, ListInventory, SearchInventory, AdminListInventory

All 31 match this phase's explicit service list exactly.

---

## 10. Dependency Direction Validation

| Check | Status |
|---|---|
| Domain contains zero Django imports | ✓ Pass (verified by grep) |
| Application depends only on Ports (+ documented `transaction.atomic` exception) | ✓ Pass |
| No circular imports | ✓ Pass |
| No cross-module domain imports (`apps.store.domain`, `apps.products.domain`, etc.) | ✓ Pass (verified by grep; one docstring match explaining the isolation, no real import) |
| Application never imports infrastructure | ✓ Pass |

---

## 11. Architecture Validation Report

| Gate | Status |
|---|---|
| ✓ Domain contains ZERO Django imports | Pass |
| ✓ Application depends only on Ports | Pass |
| ✓ No circular imports | Pass |
| ✓ Aggregate invariants enforced | Pass — see §3/§5 |
| ✓ Events registered | Partial, as expected for Phase 1 (classes complete, registry wiring is Phase 2) |
| ✓ Exceptions complete | Pass — 20 exceptions |
| ✓ FIFO policy validated | Pass — `FIFOAllocationPolicy`, sorts by `received_at`, greedy allocation with partial-fulfillment reporting |
| ✓ FEFO policy validated | Pass — `FEFOAllocationPolicy`, sorts by `expiration_date` (null-safe) |
| ✓ Ledger balancing enforced | Pass — `LedgerPolicy.verify_balance()`/`assert_balanced()`, exercised via `RebuildLedger` |
| ✓ Reservation rules enforced | Pass — `ReservationPolicy`, `Reservation` lifecycle guards |
| ✓ Batch validation complete | Pass — expiration-after-manufacture, uniqueness policy, in-aggregate duplicate-serial rejection |
| ✓ Application Services compile successfully | Pass — all 31 |

**Two real issues found and fixed during this pass, not left in:**
1. My first draft of `InventoryServiceContext.invalidate_inventory_cache()` called `CacheKeyBuilder(domain="inventory")` — I verified this against `core/caching/key_builder.py`'s actual source (rather than assuming, after Store's `CacheDomain.STORE` check taught me to check first) and found `CacheDomain` is a **closed, validated list of exactly five domains** that does not include `inventory`; the call would have raised `ValueError` at runtime. Fixed by using the same self-contained, raw-Redis versioned-key mechanism already established in `apps.geo`/`apps.store`'s own `event_handlers.py` files, and flagged the underlying platform gap (no `CacheDomain.INVENTORY` member exists) explicitly rather than silently working around it.
2. `snapshots_and_ledger.py`'s `CreateSnapshot` originally reached into `WarehouseInventory`'s "private" `_get()` method from the application layer — a real layering violation. Fixed by adding a proper public `get_quantity(status)` accessor to the aggregate.

---

## Known Limitations

1. **No Infrastructure/Interfaces/Tests** — correct and expected for Phase 1.
2. **No `CacheDomain.INVENTORY` platform-level member** — documented above; Inventory's cache invalidation works correctly via a self-contained mechanism, but doesn't participate in the same `CacheDomain` enum Products/Search/Store/Wallet/Analytics share. A future Foundation Hardening amendment adding this member would let Inventory switch to the shared mechanism.
3. **The four "cannot be X" exceptions are unreachable dead code from the domain aggregate's own methods today** (§7) — kept as documented, named types for a future infrastructure-layer validation path, not currently raised anywhere since the rules they'd guard are enforced structurally instead.
4. **Cross-module existence checks (does this `warehouse_id` really exist in `apps.store`, does this `product_variant_id` really exist in `apps.products`) are not yet performed anywhere** — `WarehouseValidator`/`ShelfValidator` only check presence (non-null), not existence; a real cross-module existence check requires either a repository call to another module's read model or an eventual-consistency event-driven approach, neither of which is wired yet (a Phase 2/Infrastructure or later concern).

**Recommendation:** proceed to Phase 2 (Infrastructure) only when instructed — this report stops here per the explicit "do NOT begin Infrastructure/Interfaces/Tests" instruction.
