# Chat Module — Phase 2 (Infrastructure) Certification Report

**Every number in this report was counted fresh during this phase via AST parsing (top-level classes only) — no number is reused from Phase 1's report.**

---

## 1. Step 1 Architecture Review

**Fresh Domain re-verification, not trusted from Phase 1's report**: 6 enums, 4 value objects, 1 entity, 2 aggregates, 2 domain services, 2 validators, 10 exceptions, 12 events, `Conversation` 8 public methods, `Message` 5 public methods — all confirmed exactly matching the certified Phase 1 baseline.

**A real, disclosed discrepancy between this phase's own stated "canonical references" and the actual certified Domain, investigated and resolved in favor of live source**: this phase's brief states the canonical references are `Conversation.customer_id`, `Conversation.operator_id`, `Participant.user_id`, `Message.conversation_id`, `Message.sender_id`. Direct inspection of the certified `Conversation` aggregate found **no `customer_id` field and no `operator_id` field exist** — the real fields are `assigned_operator_id: uuid.UUID | None`, with customer identity represented entirely through `Participant` entities (role=CUSTOMER), never a dedicated top-level field. Per this phase's own explicit instruction ("if the prompt's expected count differs from live Infrastructure, disclose the discrepancy and test/build against the real source"), Infrastructure was built against the actual certified field names, not the phase's stated (incorrect) list. This is stated here explicitly, not silently corrected.

**Repository-wide search for existing ownership**: zero conflicts found for `Conversation`/`Message`/`Participant`/`ChatMessage` anywhere outside `apps/chat`.

**Application layer state, verified fresh**: `apps/chat/application/services/` confirmed empty; `application/ports.py` confirmed genuinely placeholder (13 lines) before this phase. Matches the identical sequencing gap already resolved in Wallet's/Loyalty's/Reviews' own Phase 2.

**Cross-aggregate ORM reference convention, verified against real precedent, not assumed from this phase's more permissive suggestion**: `apps.wallet.infrastructure.models.CashbackModel.wallet_id` — the established, verified precedent for an intra-module cross-aggregate reference — is a plain `UUIDField`, not a `ForeignKey`. `MessageModel.conversation_id` follows this real precedent exactly, rather than the FK option this phase's own brief merely allowed. `ParticipantModel`, being genuinely owned BY `Conversation` (not a separate aggregate), correctly uses a real `ForeignKey`, matching `WalletLedgerEntryModel.wallet`'s identical owned-entity pattern.

**Channels/Redis**: confirmed already configured at the platform level (`config/settings/components/channels.py`) — re-confirmed purely informational, no channel-layer-connectivity health check or gateway was built this phase (see §7).

**Step 1 completed. One disclosed field-name discrepancy (resolved in favor of live source, above) and one disclosed minimal exception (the two Repository Protocols). No other architectural inconsistency was discovered.**

---

## 2. Folder Tree

```
apps/chat/
├── application/
│   └── ports.py                    (2 Protocols -- the disclosed minimal exception)
└── infrastructure/
    ├── models.py
    ├── repositories.py
    ├── selectors.py
    ├── gateways.py
    ├── event_handlers.py
    ├── signals.py
    ├── tasks.py
    ├── health.py
    ├── composition.py
    └── admin.py
apps/chat/apps.py
shared/event_contracts/chat.py
```

---

## 3. Infrastructure Components

**Models (3 tables + 1 Outbox)**: `ConversationModel` and `MessageModel` both use `SoftDeleteModel` — a deliberate, disclosed distinction from the "aggregate root gets SoftDeleteModel, owned append-only child gets plain Model" pattern used elsewhere: `Message` is genuinely its own certified aggregate root (not an owned entity) *and* genuinely supports real mutation (`edit()`)/soft-deletion (`delete()`), unlike an append-only ledger entry. `ParticipantModel` correctly gets the plain-Model treatment, since it is the genuinely owned, append-only-shaped entity here. `message_deleted_at` (not `deleted_at`) is a deliberate naming choice, documented directly in the model's own docstring, to avoid colliding with `SoftDeleteMixin`'s own framework-level `deleted_at` field — the repository never calls the ORM's `.delete()` for a Domain-level message deletion.

**Repositories (2)**: `DjangoConversationRepository` and `DjangoMessageRepository`, together implementing all 7 Port methods across both Protocols exactly (verified by diff).

**Selectors (3)**: `ConversationSelector`, `MessageSelector`, `ChatStatisticsSelector`. **No unread-message-count selector exists**, disclosed directly in the file's own module docstring — explicitly forbidden by this phase's own anti-pattern list, since Domain's `Message.read_at` is a per-message timestamp, not a certified aggregate-level "unread count" concept.

**Gateways (2 interfaces + 2 implementations)**: `NotificationGateway` (silent no-op) / `MediaStorageGateway` (fail-loud), the identical asymmetric shape already established by Reviews' Phase 2. **No presence gateway, no WebSocket/channel-layer gateway exists** — both explicitly named in this phase's own anti-pattern list; real-time delivery over the already-platform-configured Channels layer is explicitly deferred to a future Interfaces phase's consumers/routing.

**Event Handlers**: all 12 certified events registered in the dispatch table exactly once (verified programmatically). `MessageRead` is registered but deliberately maps to an empty cache-group tuple and no metric — logged for observability, but no fabricated cache invalidation or notification side effect, since no selector currently surfaces read-state at all. This satisfies this phase's own "genuinely handled OR explicitly documented as having no side effect" requirement for every one of the 12 events, not just the ones with an obvious cache implication.

**Tasks (3)**: `relay_outbox_events`, `rebuild_chat_statistics`, `flag_stale_conversations` (a genuinely real, read-only visibility sweep over OPEN conversations with no recent activity, using no Application Service). **No auto-close/auto-archive mutating task exists**, disclosed directly in the file's own module docstring — matching the identical, already-established precedent from Loyalty's/Reviews' own Phase 2.

**Health (6 checks)**: no fixed count was assumed — derived directly from this module's actual Infrastructure dependencies. Repository connectivity, Outbox backlog, orphaned-participant consistency (a real cross-table check beyond Django's own FK enforcement), message-content integrity (verifies no TEXT/SYSTEM message has NULL content — the same invariant `Message.send()` enforces at creation, checked here against drift), composition integrity, cache round-trip. **No channel-layer-connectivity check exists** — Channels is explicitly deferred to Interfaces, and a health check for infrastructure this module doesn't yet use would be premature, not thorough.

**Composition (7 factories)**: 2 repository accessors, 3 selector accessors, 2 gateway accessors. Zero Application Service factories, explicitly disclosed.

**Admin (3 registrations)**: `ConversationModel` (inline participant editor, status badge, search/filter), `MessageModel` (**not** read-only, unlike append-only child tables elsewhere — `Message` is its own aggregate root, so admin can view/search it like any other aggregate-root table, though it still has zero bulk actions), `ChatOutboxEvent` (read-only, per MIC §9).

---

## 4. Domain Preservation

**Explicitly confirmed unchanged**: `apps/chat/domain/` was re-verified fresh at the start of Step 1 (§1) and never touched during this phase. No Domain file was modified, no aggregate method added or removed, no exception/event added or removed. The Conversation/Message aggregate boundary, `Message.conversation_id`'s plain-UUID shape, and the deliberate absence of a cross-aggregate open-check in `Message.send()` all remain exactly as certified in Phase 1.

---

## 5. Application Boundary

Exactly as certified going into this phase: **0 Application Services, 0 Application Service factories**. `application/services/` remains empty. The only change to `application/` this phase was the one disclosed minimal exception: 2 Repository Protocols (`ConversationRepository`, `MessageRepository`) added to `application/ports.py`, matching the identical precedent already established in Wallet's/Loyalty's/Reviews' own Phase 2.

---

## 6. Event Infrastructure

**Exact registration/dispatch count: 12/12.** Every one of the 12 certified Domain events is registered in `shared/event_contracts/chat.py` (verified zero duplicates) and dispatched in `event_handlers.py`'s cache-group table (verified programmatically, not assumed). `MessageDelivered` and `MessageRead` both map to empty cache-group tuples, explicitly documented as intentionally having no current Infrastructure side effect rather than a fabricated one.

---

## 7. Channels/Redis Boundary

Django Channels is confirmed already configured at the platform level (`ASGI_APPLICATION`, Redis-backed `CHANNEL_LAYERS`, `channels` in `INSTALLED_APPS`) — purely informational context from Step 1, not acted on this phase. **Deliberately deferred to a future Interfaces/WebSocket phase**: WebSocket consumers, `routing.py`, channel-layer group management, real-time message push, presence/online-status, and typing indicators. This phase built zero WebSocket-adjacent code — no consumer, no routing registration, no channel-layer gateway, no channel-layer health check. Redis is used in this phase only for the same generic cache-invalidation mechanism every other module already uses, never for Channels-specific pub/sub.

---

## 8. Validation Results

| Gate | Status |
|---|---|
| Repository-wide compile | ✓ — 1400/1400 |
| Chat-only compile | ✓ |
| Zero forward dependency (full expanded list, incl. Channels) | ✓ — AST-verified |
| Zero circular imports | ✓ |
| Zero `__import__()` | ✓ — whole module |
| Zero local imports | ✓, except `apps.py::ready()` — the identical, necessary Django framework exception already confirmed legitimate in every prior module |
| Zero unused imports | ✓ — whole module (one false-positive flag on the intentional `# noqa: F401` side-effect import, confirmed legitimate) |
| Repositories implement Ports | ✓ — 7/7 methods across both Protocols, verified by diff |
| No selector writes | ✓ |
| No repository business logic | ✓ — only 2 `raise` statements, both documented `IntegrityError → ConflictError` mappings |
| Every Domain event registered/dispatched or documented as no-op | ✓ — 12/12 |
| No deferred Domain decision reopened | ✓ |
| No Application Service fabricated | ✓ |
| Channels/Redis integration remains outside Domain | ✓ |
| No unrelated module changed | ✓ |

---

## 9. Fresh Verified Counts

| Metric | Count |
|---|---|
| Repository-wide Python files | **1400** |
| Chat-specific files | **41** |
| ORM Models (top-level) | 3 (+ 1 Outbox) |
| Repositories | 2 |
| Selectors | 3 |
| Gateways (2 interfaces + 2 implementations) | 4 |
| Ports | 2 |
| Composition Factories | 7 |
| Health Checks | 6 |
| Celery Tasks | 3 |
| Admin Registrations | 3 |
| Event Registrations | 12 |

---

## 10. Mistakes Found

Reported honestly, per this phase's explicit instruction — none hidden:

1. **A real, substantive stale-prompt-expectation discrepancy, investigated and resolved in favor of live source rather than silently accepted or silently ignored — described fully in §1.** This phase's own stated "canonical references" list included `Conversation.customer_id` and `Conversation.operator_id`, neither of which exist on the actual certified aggregate. Caught by directly inspecting `aggregates.py`'s real field list before writing any ORM model, not by assuming the prompt's list was accurate. Every model field, repository method, and selector query this phase actually built uses the real field names (`assigned_operator_id`, participant-derived customer identity).
2. **No other mistakes were found.** Every model field was cross-checked against the certified Domain contract before being written (§3's field-name verification table); the FK-vs-plain-UUID question for `Message.conversation_id` was resolved against real, verified precedent (`CashbackModel.wallet_id`) rather than this phase's own more permissive suggestion; the `message_deleted_at` naming was deliberately chosen and explained to avoid a real collision with `SoftDeleteMixin`'s own `deleted_at` field, catching what would otherwise have been a subtle, silent framework-mechanism confusion between Domain-level and framework-level "deletion."

---

## 11. Architectural Decisions Future Phases Must Preserve

- `Conversation` and `Message` remain separate aggregates; `Message.conversation_id` remains a plain `uuid.UUID`, never a `ForeignKey`-backed wrapper reference at the Domain level.
- `MessageModel`/`ConversationModel` both use `SoftDeleteModel`; `ParticipantModel` uses plain `Model`. This distinction must be preserved — Message is not an append-only ledger-style entity.
- `message_deleted_at` is the Domain-deletion-tracking field; `SoftDeleteMixin`'s own `deleted_at`/`is_deleted`/`deleted_by` fields remain reserved exclusively for genuine framework-level hard-removal administrative scenarios, never for a Domain-level `Message.delete()` call.
- No unread-count, presence, or channel-layer infrastructure exists yet — any future phase adding these must do so against a genuine, newly-certified Domain/Application contract, not by extending Infrastructure speculatively.
- Zero Application Services exist; the 2 Repository Protocols in `application/ports.py` are the only Application-layer artifact certified so far.

---

## 12. Final Certification

**What was completed**: the complete Chat Infrastructure layer (models, repositories, selectors, gateways, event handlers, signals, tasks, health, composition, admin) plus `apps.py` registration and `shared/event_contracts/chat.py`, all built strictly on top of the certified, unmodified Phase 1 Domain contract.

**What remains deferred**: all Application Services (0 exist), all Interfaces/WebSocket work (consumers, routing, real-time delivery, presence, typing indicators), unread-message-count infrastructure, and any channel-layer-specific health/gateway capability.

**Which files/layers were untouched**: `apps/chat/domain/` (all 8 files, re-verified fresh, zero modifications), `apps/chat/interfaces/` (all still 13-line placeholders), `apps/chat/tests/` (all still empty `__init__.py` scaffolding), every other bounded context.

**Whether runtime execution was possible**: no. Django remains uninstalled in this sandbox, consistent with every prior phase of this entire build. Every verification in this report is `python3 -m py_compile` (syntax only), direct AST parsing, or direct grep/regex inspection — never a live import, live query, or live test run.

**Whether tests were actually executed or only statically validated**: only statically validated. No test file exists for this module yet (Phase 4 has not begun), and none of the static validation performed this phase constitutes or claims to constitute test execution.

**Do not proceed to Phase 3 (Interfaces/WebSocket). Waiting for the next explicit instruction.**
