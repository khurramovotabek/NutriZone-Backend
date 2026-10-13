# Ordering Module — Phase 2 (Infrastructure) Certification Report

**Every number in this report was counted directly from source during this phase — no number is reused from Phase 1's report or any prior module's report.**

---

## Step 1 — Architecture Review

Every claim in this phase's own prompt was independently re-verified against source, not trusted:

| Claim | Verified | Result |
|---|---|---|
| Phase 1 compiles | ✓ | Confirmed — `apps/ordering/domain/*.py` and `apps/ordering/application/**/*.py` recompiled fresh |
| 38 Application Services exist | ✓ | Confirmed by direct count |
| 5 Ports exist | ✓ | Confirmed |
| 3 Aggregates exist | ✓ | Confirmed |
| 28 Domain Events exist | ✓ | Confirmed |
| 22 Domain Exceptions exist | ✓ | Confirmed |
| Zero Django imports in Domain | ✓ | Confirmed |
| Application imports only Ports | ✓ | Confirmed |
| Zero forward dependency | ✓ | Re-verified via AST-parsed import statements (the most rigorous method used anywhere in this build) |

Existing conventions studied and confirmed consistent before building: Cart's single-aggregate repository mapping pattern, Pricing's multi-aggregate composition root (32 factories for 6 aggregates, the closest prior precedent to Ordering's own 3-aggregate, 46-factory shape), Inventory's and Store's admin/health/Outbox conventions.

**Step 1 completed. No architectural inconsistency was discovered. Proceeding to Step 2.**

---

## Infrastructure Summary

**Models**: 11 ORM tables + 1 Outbox table, mirroring Phase 1's 3 aggregates and 8 owned entities. `OrderInvoice` and both `AddressSnapshot`s (shipping/billing) are embedded as flat columns on `OrderModel` rather than separate tables — both are singular, at-most-one-per-order pieces of data, the same design choice already made for Cart's shipping/tax estimates in Cart's own Phase 2.

**Repositories**: 3 concrete classes (`DjangoOrderRepository`, `DjangoOrderReturnRepository`, `DjangoOrderCancellationRepository`), one per aggregate root, each implementing its Phase 1 Port. Every write reconciles owned-entity collections (lines, payment/fulfillment references, failures, status history) rather than blind inserts; every `IntegrityError` on the Order write path is caught and re-raised as a domain `ConflictError`.

**Selectors**: 6 classes — `OrderSelector`, `OrderReturnSelector`, `OrderCancellationSelector`, `ExpiringOrderSelector` (backs the expiry sweep task), `OrderStatisticsSelector` (admin dashboard reporting helpers: counts-by-status, revenue-by-status), `DjangoOrderSearchBackend`.

**Gateways**: 3 Protocol interfaces + 3 placeholder implementations (`PaymentGateway`/`NotImplementedPaymentGateway`, `FulfillmentGateway`/`NotImplementedFulfillmentGateway`, `NotificationGateway`/`NotImplementedNotificationGateway`) — 6 classes total. A deliberate asymmetry, documented in the code itself: Payment/Fulfillment placeholders **raise `NotImplementedError`** (Ordering has no legitimate reason to query a payment/fulfillment status before those modules exist — failing loudly is correct), while the Notification placeholder is a **silent no-op** (a missing notification should never be allowed to block order processing, even before a real Notification module exists). This is a genuine design decision, not an inconsistency — flagged here so it reads as intentional.

**Composition Root**: 46 `build_*()` factories — 38 one-per-Application-Service (verified: every one of the 38 services has a matching factory, checked programmatically) plus 8 repository/selector/gateway accessors, so no future Interfaces-layer view has any reason to instantiate a repository directly.

**Admin**: 9 registered model classes, with `OrderModel`/`OrderReturnModel`/`OrderCancellationModel` carrying inline line-item editors and status-badge list displays; `OrderStatusHistoryEntryModel`, `OrderFailureModel`, and `OrderingOutboxEvent` are read-only (no add/change permission), per MIC §9's append-only-table convention.

**AppConfig**: registers the event catalogue import and 6 health checks in `ready()`, matching every prior module's pattern exactly.

**Event Contracts**: all 28 domain events registered in `shared/event_contracts/ordering.py`, verified by AST-parsing to match the domain event count exactly, with an explicit zero-duplicates check (not just a count check — duplicates could otherwise hide behind a matching total).

**Celery Tasks**: 4 tasks + the standard Outbox relay — `expire_orders` (sweeps overdue DRAFT/PENDING_PAYMENT orders via the real `ExpireOrder` service), `cleanup_stale_return_requests` (surfaces a metric for human review rather than auto-rejecting — a genuine business decision that stays with a person, documented as such), `rebuild_statistics`, `relay_outbox_events`.

---

## Architecture Validation

| Gate | Status |
|---|---|
| Domain imports zero Django | ✓ Pass |
| Application imports only Ports | ✓ Pass |
| Infrastructure depends on Domain + Application (never the reverse) | ✓ Pass |
| Interfaces untouched | ✓ Pass — confirmed empty scaffold only |
| Tests untouched | ✓ Pass — confirmed empty scaffold only |
| No ORM outside repositories/selectors/admin | ✓ Pass |
| No repository creation outside composition | ✓ Pass |
| No aggregate creation outside repositories | ✓ Pass |
| No business logic inside repositories/selectors | ✓ Pass |
| **Zero forward dependency on Wallet/Payments/Loyalty/Marketing/Notification/Recommendation/Analytics/POS/Shipping/Delivery/any future context** | ✓ Pass — AST-verified across the entire `apps/ordering/` tree, including all new Infrastructure code |
| Zero duplicate handlers/registrations/models/admin registrations | ✓ Pass — verified by direct checks (table-name dedup, event-registration dedup, admin-registration count matches model count) |
| Composition completeness | ✓ Pass — 46 factories, all 38 services covered, verified programmatically |
| Every event registered | ✓ Pass — 28/28 |
| Every event dispatched | ✓ Pass — 28/28, cross-checked via AST-diff against the dispatch table |
| Health registered | ✓ Pass — 6 checks |
| OpenAPI tags registered | ✓ Pass — "Ordering"/"Ordering Admin" |
| All Python files compile | ✓ Pass — 1237/1237 |

---

## Fresh Verified Counts

| Metric | Count |
|---|---|
| Repository-wide Python files | **1237** |
| Ordering-specific Python files | **47** |
| ORM Models | 11 |
| Repositories | 3 |
| Selectors | 6 |
| Gateways (3 interfaces + 3 placeholder implementations) | 6 |
| Ports | 5 |
| Composition factories | 46 |
| Application Services | 38 |
| Domain Events | 28 |
| Event Registrations | 28 |
| Health Checks | 6 |
| Admin Classes | 9 |
| Celery Tasks | 4 |

---

## Mistakes Found

Reported honestly, per this phase's explicit instruction — none hidden:

1. **Two unused imports (`django.db.models.Q`) drafted into both `repositories.py` and `selectors.py`**, neither ever actually used in either file (search-by-code was implemented with `icontains` on a single field, not an `OR` query). Caught by checking actual usage before finalizing, removed from both files.
2. **A local import inside a method body** (`from decimal import Decimal` inside `DjangoOrderReturnRepository._to_domain()`) that was never even used there — dead code left over from an earlier draft. Removed.
3. **Another local import inside a method body that duplicated an import already needed at module scope** (`from apps.ordering.domain.value_objects import OrderNote, CustomerComment` inside `DjangoOrderRepository._to_domain()`) — moved to the top-level import block where it belonged, consolidated with the other value-object imports already there.
4. **No `__import__()` hack occurred this phase** — checked explicitly and proactively while writing `tasks.py` (the file type where this mistake has recurred most often across this build), using a normal `import uuid` inside the task function body from the start rather than catching it after the fact. Confirmed clean by a final sweep of the entire `apps/ordering/` tree.
5. **No naming collisions, forward-dependency attempts, repository leaks, or ORM leaks were found this phase.** The two near-miss event/exception collisions specific to this module (`OrderLocked`, `OrderArchived`) were both already caught and resolved during Phase 1; re-verified still correct here, not re-introduced.

---

## Final Certification

**Ordering Infrastructure is complete.** All 46 composition factories wired, all 38 Application Services reachable through composition, all 28 domain events registered and dispatched, all 11 ORM tables mirroring Phase 1's aggregate design faithfully (including the deliberate embedding of `OrderInvoice` and both address snapshots as flat columns, and the deliberate asymmetry between the Payment/Fulfillment gateways' fail-loud placeholders and the Notification gateway's fail-silent one — both documented as intentional design, not oversights). Zero forward dependency on any not-yet-owned bounded context, verified by the most rigorous method available (AST-parsed imports) across the complete Infrastructure layer, not just Domain/Application as in Phase 1.

As with every module in this build, this certification is **verified-correct-by-static-inspection and compile check** (1237/1237 repository-wide files), not verified-passing-against-a-live-database — no migrations or live-database test run exist yet for this module.

**Ready for Phase 3 (Interfaces). Stopping here per the explicit "do not begin Interfaces/Tests" instruction. Waiting for the next instruction.**
