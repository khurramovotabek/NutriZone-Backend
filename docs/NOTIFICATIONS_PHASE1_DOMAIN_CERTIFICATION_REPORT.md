# Notifications Module — Phase 1 (Domain) Certification Report

**Every number in this report was counted fresh during this phase via AST parsing — no number is reused from any prior module's report.**

---

## 1. Step 1 Architecture Review

**Scaffold state**: `apps/notifications/` confirmed genuine, uniform 13-line placeholder throughout every layer (Domain, Application, Infrastructure, Interfaces, Tests). README explicitly stated "This module has not been implemented yet," citing Domain Architecture Specification §2.13.

**No literal specification document exists**: a repository-wide search for an actual Domain Architecture Specification artifact found none — only per-module READMEs referencing section numbers, and this build's own prior certification reports. Consistent with every prior module in this build; not a new discrepancy requiring resolution.

**Ownership investigation**: a repository-wide search for `Notification`/`NotificationPreference`/`NotificationChannel`/`NotificationTemplate`/`NotificationDelivery`/`NotificationRecipient` classes found zero matches outside `apps/notifications`. `apps.identity` and `apps.chat` contain no pre-existing notification concept.

**Real evidence justifying `NotificationChannel.TELEGRAM`, not fabricated**: `apps.identity.domain.aggregates.User.telegram_username: str | None` genuinely exists as captured contact data.

**Chat's own `NotificationGateway.notify_chat_event(conversation_id, event_type, payload)`** (confirmed by direct inspection) establishes the real, repository-wide pattern: other bounded contexts already trigger notifications generically through their own thin placeholder gateways, not by importing Notifications' Domain objects directly. This directly informed the decision to keep `NotificationType` broad (transactional/promotional/system) rather than a per-source-module taxonomy.

**Identity's `User.id: uuid.UUID`** re-confirmed canonical — no wrapper reference objects created; `Notification.recipient_id`/`NotificationPreference.user_id` are both plain `uuid.UUID`.

**The central aggregate-boundary decision, reasoned explicitly, not chosen by convenience**: **two aggregate roots** — `Notification` (one message to one recipient) and `NotificationPreference` (one per user, configuration state). These have fundamentally different cardinality and mutation-frequency profiles — the same reasoning shape already applied to Chat's `Conversation`/`Message` split, but reaching a *different* conclusion for the third candidate concept, `NotificationDelivery`: unlike Chat's `Message` (a separate aggregate, justified by high-frequency independent creation), `NotificationDelivery` is modeled as an **owned entity** of `Notification` — its cardinality is small and bounded (typically 1–5 channels per notification, never unbounded), it is tightly consistency-coupled to its parent, and it has no independent query need. This contrast is documented directly in `entities.py`'s own module docstring, not left for a reader to infer.

**A significant, disclosed finding, not an empty file left unexplained**: **zero Domain Services are justified this phase.** Every candidate considered during Step 1 was rejected for a concrete, specific reason (documented in full in `services.py`'s own module docstring and §4 below), not merely deferred as "not needed yet."

**Step 1 completed. No architectural inconsistency was discovered. Proceeding to Phase 1.**

---

## 2. Folder Tree

```
apps/notifications/domain/
├── enums.py
├── value_objects.py
├── exceptions.py
├── entities.py
├── events.py
├── services.py
├── validators.py
└── aggregates.py
```

**A deliberate reordering from this phase's own suggested file order, disclosed rather than left implicit**: `exceptions.py` was written immediately after `value_objects.py`, not after `entities.py`. `value_objects.py` was written to import its specific exceptions (`EmptyNotificationContent`, `NotificationContentTooLong`) directly from the start — applying the lesson already learned the hard way in both Reviews' and Chat's own Phase 1, where generic `ValidationFailed` was initially left in place and had to be fixed retroactively after certification found the specific exceptions were dead code. Getting the dependency order right proactively here, rather than fixing it after the fact a third time, required writing `exceptions.py` second.

---

## 3. Domain Model Summary

**Two aggregate roots**: `Notification` (7 public methods: `create`, `record_delivery_attempt`, `confirm_delivery`, `mark_delivery_failed`, `mark_seen`, `mark_read`, `cancel`) and `NotificationPreference` (4 public methods: `create`, `is_enabled`, `disable`, `enable`). 1 owned entity (`NotificationDelivery`). 5 enums, 2 value objects.

**`Notification`'s recipient-facing lifecycle**: `UNSEEN → SEEN → READ` (both `mark_seen`/`mark_read` are idempotent no-ops on repeat calls, matching Chat's own `Message.mark_delivered`/`mark_read` precedent), plus a separately-reachable `CANCELLED` terminal state guarded by three distinct, hand-traced conditions: already cancelled (raises `NotificationAlreadyCancelled`), already read (raises `InvalidNotificationTransition`), or already delivered through any channel (raises `NotificationAlreadyDelivered`).

**`NotificationDelivery`'s per-channel lifecycle**: `SENT → DELIVERED` or `SENT → FAILED`, both terminal. `record_delivery_attempt()` deliberately creates a delivery record directly in `SENT` status (no separate `PENDING` pre-attempt state) — Domain never itself performs a send, so "pending" before an attempt is simply "no delivery record exists yet," not a state worth representing.

**`NotificationPreference`'s opt-out model**: every `(channel, notification_type)` combination is enabled by default; `disabled_combinations` records only explicit exceptions, avoiding a combinatorial default-row-per-user-per-combination design. `disable()`/`enable()` are both idempotent (verified by hand-trace: calling either when already in the target state returns `None` and emits nothing).

**Cross-aggregate references**: `Notification.recipient_id` and `NotificationPreference.user_id` are both plain `uuid.UUID` — no wrapper value objects anywhere in this module.

**A real bug caught and fixed during this phase's own self-audit, not left in**: `mark_seen(at)`/`mark_read(at)` initially accepted a timestamp parameter but never stored it anywhere — a genuine design gap, not a superficial unused-parameter issue, since Chat's own `Message.mark_delivered`/`mark_read` do genuinely persist their equivalent timestamps. Fixed by adding `seen_at`/`read_at` fields to `Notification` and actually assigning them; re-verified all 9 events still emit correctly after the fix.

---

## 4. Domain Service Summary

**Zero Domain Services exist in this phase — a deliberate, reasoned conclusion, not an oversight.** Three candidates were considered and rejected, each for a distinct reason:

1. **`NotificationEligibilityPolicy`** — rejected as genuinely redundant: it would have done nothing but call `NotificationPreference.is_enabled()`, which already exists as that aggregate's own read-only query method. A wrapping service would be exactly the "service merely to move one aggregate method elsewhere" anti-pattern this build's rules explicitly forbid.
2. **`NotificationRoutingPolicy`/`NotificationChannelPolicy`** — rejected because genuine channel routing requires external knowledge (operator/provider availability, cost, rate limits) that Domain does not and should not have, explicitly named as out of scope by this phase's own instructions.
3. **A hypothetical `NotificationPriorityEscalationPolicy`** — rejected as fabricated: no repository evidence or specification establishes priority escalation as a real business rule for this module.

---

## 5. Validator Summary

2 thin, intention-revealing wrappers: `NotificationTitleValidator`, `NotificationBodyValidator`.

---

## 6. Exception Summary

**7 exceptions**, all subclassing `common.exceptions.DomainException`, every one confirmed genuinely raised somewhere in Domain (verified programmatically, not by eye — across both `aggregates.py` and `value_objects.py`): `InvalidNotificationTransition`, `NotificationAlreadyCancelled`, `NotificationAlreadyDelivered`, `DeliveryNotFound`, `InvalidDeliveryTransition`, `EmptyNotificationContent`, `NotificationContentTooLong`. The latter two are deliberately shared between both `NotificationTitle` and `NotificationBody` — both fields fail the identical two cases, and duplicating near-identical exception classes per-field would add no real distinction.

**100% genuinely raised — confirmed programmatically.**

---

## 7. Domain Event Summary

**9 events**, zero duplicates, zero collisions with exceptions (verified programmatically): `NotificationCreated`, `NotificationDeliverySent`, `NotificationDelivered`, `NotificationDeliveryFailed`, `NotificationSeen`, `NotificationRead`, `NotificationCancelled`, `NotificationChannelEnabled`, `NotificationChannelDisabled`.

**100% genuinely emitted — confirmed programmatically, re-verified after the `seen_at`/`read_at` fix.** `NotificationPreference.create()` deliberately emits no event — creating a record with all-default (fully enabled) settings is not itself a meaningful business fact; only actual configuration changes (`disable`/`enable`) emit events.

---

## 8. Architecture Compliance

Zero Django/Channels/Redis/Celery/HTTP/WebSocket/ORM imports anywhere in `apps/notifications/domain/` (AST-verified). Zero forward dependency on any other bounded context, including the two genuinely real, adjacent modules a naive design could have imported from (`apps.identity`, `apps.chat`) — AST-verified against the full expanded forbidden list. Zero circular imports (`exceptions.py` imports nothing from `apps.notifications` itself). Every aggregate mutation on both `Notification` and `NotificationPreference` reachable only through a public method.

---

## 9. Validation Results

| Gate | Status |
|---|---|
| Domain compile | ✓ |
| Framework independence | ✓ — zero Django/Channels/Redis/Celery imports |
| Aggregate lifecycle | ✓ — both state machines explicit, every invalid transition raises a specific exception, all guard conditions hand-traced |
| Event coverage | ✓ — 9/9 declared events genuinely emitted |
| Exception usage | ✓ — 7/7 genuinely raised |
| Circular imports | ✓ |
| Forward dependency | ✓ — AST-verified against the full expanded forbidden list |
| Local imports | ✓ |
| Unused imports | ✓ — one real design bug found and fixed during self-audit (§3, §11) |
| Aggregate encapsulation | ✓ |

---

## 10. Fresh Verified Counts

| Metric | Count |
|---|---|
| Repository-wide Python files | **1425** |
| Notifications Python files | **9** (this phase's Domain layer; Application/Infrastructure/Interfaces/Tests remain untouched 13-line placeholders) |
| Domain files | 8 content files + `__init__.py` |
| Enums | 5 |
| Value Objects | 2 |
| Entities | 1 |
| Aggregate roots | 2 |
| Domain Services | 0 |
| Validators | 2 |
| Exceptions | 7 |
| Events | 9 |
| `Notification` public methods | 7 |
| `NotificationPreference` public methods | 4 |

---

## 11. Mistakes Found

Reported honestly, per this phase's explicit instruction — none hidden, none invented to populate this section:

1. **A real design bug, not a superficial unused-parameter issue: `mark_seen(at)`/`mark_read(at)` accepted a timestamp but never stored it.** Both methods took an `at: datetime` parameter, correctly named and typed as if it would be persisted, but the initial implementation only updated `self.status` — the timestamp was silently discarded. **Why it happened**: the method bodies were written focused on the status-transition logic (matching the idempotency pattern from Chat's `Message.mark_delivered`/`mark_read`) without carrying over that those same Chat methods also genuinely persist their equivalent timestamp fields. **How it was detected**: a direct, manual re-read of both method bodies immediately after writing `aggregates.py`, specifically checking "is every parameter actually used for something," not merely relying on an automated unused-import checker (which would not have caught this, since `at` is a used parameter — it's used in the method signature and type-checked, just never assigned to state). **How it was fixed**: added `seen_at: datetime | None` and `read_at: datetime | None` fields to `Notification`, and both methods now assign `self.seen_at = at` / `self.read_at = at` before returning their event. **How verified**: recompiled, re-ran the full "every event still emitted" and unused-import checks — both passed unchanged, confirming the fix was additive and didn't disturb anything else.
2. **No other mistakes were found.** Every exception was confirmed genuinely raised, every event genuinely emitted, and the deliberate proactive reordering of `exceptions.py` before `entities.py` (§2) prevented the exact category of mistake (specific exception defined but generic exception left in place) that was found and fixed retroactively in both Reviews' and Chat's own Phase 1 reports.

---

## 12. Architectural Decisions Future Phases Must Preserve

- `Notification` and `NotificationPreference` remain separate aggregate roots, linked only by `user_id`/`recipient_id: uuid.UUID`. Neither aggregate reaches into the other's state; cross-aggregate coordination (e.g. checking preferences before recording a delivery attempt) belongs to a future Application layer.
- `NotificationDelivery` remains an owned entity of `Notification`, never promoted to a separate aggregate — its cardinality and consistency-coupling profile genuinely differs from Chat's `Message`, and this must not be "corrected" to match that precedent mechanically.
- `record_delivery_attempt()` creates a delivery directly in `SENT` status; no `PENDING` pre-attempt state exists and should not be added without new evidence.
- Domain never sends anything — no email/SMS/push/Telegram/webhook call exists or should exist in this layer; those are Infrastructure/Application responsibilities for a future phase.
- No distributed idempotency, retry count, scheduling, or external provider reference validation exists in Domain — all explicitly deferred, per this phase's own instructions.
- Zero Domain Services exist; any future service must be a genuine cross-aggregate rule, not a wrapper around `NotificationPreference.is_enabled()`.

---

## 13. Final Certification

**What was completed**: the complete Notifications Domain layer (8 files) — 5 enums, 2 value objects, 1 entity, 2 aggregate roots, 0 domain services (a reasoned conclusion), 2 validators, 7 exceptions, 9 events.

**Exact files changed**: `apps/notifications/domain/enums.py`, `value_objects.py`, `exceptions.py`, `entities.py`, `events.py`, `services.py`, `validators.py`, `aggregates.py` — all newly written this phase, replacing 13-line placeholders.

**What remains untouched**: `apps/notifications/application/`, `apps/notifications/infrastructure/`, `apps/notifications/interfaces/`, `apps/notifications/tests/`, and `apps/notifications/apps.py` all remain exactly as they were before this phase — genuine 13-line placeholders, none created, modified, or implemented. Every other bounded context (Chat, Wallet, Loyalty, Reviews, Identity, and all others) confirmed untouched.

**What remains deferred**: all Infrastructure (ORM models, repositories, selectors, gateways, event handlers, tasks, health checks, composition, admin), all Application Services, all Interfaces (HTTP, WebSocket, serializers, permissions), and all Testing.

**Whether Domain was runtime-tested or only statically validated**: only statically validated. Django is not installed in this sandbox, consistent with every prior phase of this entire build. Every verification in this report is `python3 -m py_compile` (syntax only), direct AST parsing, or direct grep/regex inspection — never a live import or live execution.

**Whether actual tests were executed**: no — no test file exists for this module yet (Phase 4 has not begun), and no claim in this report represents runtime test execution.

**Whether any platform limitations were discovered**: none new this phase. The absence of a literal Domain Architecture Specification document (§1) is consistent with every prior module, not a newly discovered limitation.

**Notifications Phase 1 (Domain) is complete.**

**Do not begin Phase 2 unless explicitly instructed.**
