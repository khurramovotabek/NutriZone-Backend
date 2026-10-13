# Chat Module — Phase 1 (Domain) Certification Report

**Every number in this report was counted fresh during this phase via AST parsing — no number is reused from any prior module's report.**

---

## 1. Step 1 Review

**Scaffold status**: `apps/chat/` confirmed to be full-layer placeholder scaffolding — every content file exactly 13 lines, README explicitly stated "This module has not been implemented yet," citing Domain Architecture Specification §2.12. Safe to build on, not an existing implementation.

**Existing ownership investigation**: a repository-wide search for `Conversation`/`Message`/`Chat`/`Thread`/`ChatMessage` classes anywhere outside `apps/chat` found zero matches. `apps/notifications` — the one plausible adjacent concern — is also confirmed genuinely placeholder (286 lines total, standard 13-line-per-file pattern), so no ownership ambiguity exists.

**Relevant bounded-context findings**: Django Channels is already configured at the platform level (`config/settings/components/channels.py`, `channels` in `INSTALLED_APPS`, Redis-backed `CHANNEL_LAYERS`) — its own docstring explicitly anticipates `chat` adding an `interfaces/routing.py` in a future phase. This is purely informational for Step 1; it does not change Domain design in any way, since Domain must remain framework-independent regardless of what Infrastructure eventually builds on top of it.

**Canonical identity decisions**: `apps.identity.domain.aggregates.User` re-confirmed as the canonical Identity aggregate, `id: uuid.UUID`. No wrapper reference value objects are created anywhere in this module — every cross-aggregate reference (`Message.conversation_id`, `Message.sender_id`, `Participant.user_id`) is a plain `uuid.UUID`, matching the identical convention already established by every prior module in this build.

**The central architectural decision this phase, reasoned explicitly, not assumed**: the Conversation/Message aggregate boundary. This phase's own brief listed four possible options; **Option D — separate aggregates linked by ID — was chosen explicitly**, on the grounds that Message creation is high-frequency and does not require the full conversation/message history to be loaded for correctness (unlike Wallet's Ledger, where balance genuinely must be derived by summing every entry). `Message.conversation_id` is a plain `uuid.UUID`, the identical intra-module cross-aggregate reference pattern already established by Wallet's `Cashback.wallet_id`.

**A direct, disclosed consequence of this boundary decision**: `Message.send()` does not and cannot check whether its parent `Conversation` is currently OPEN — that cross-aggregate invariant is out of scope for Domain and belongs to a future Application layer, which will load both aggregates and coordinate the check. This mirrors the identical, already-established pattern for Reviews' `verified_purchase` (an externally-supplied fact) and Wallet's `Cashback.award()` (which does not itself credit the Wallet).

**Step 1 completed. No architectural inconsistency was discovered. Proceeding to Phase 1.**

---

## 2. Folder Tree

```
apps/chat/domain/
├── enums.py
├── value_objects.py
├── entities.py
├── exceptions.py
├── events.py
├── services.py
├── validators.py
└── aggregates.py
```

Written and self-audited one file at a time, per this phase's explicit instruction — each file was compiled and checked (Django/Channels/Redis/Celery imports, `__import__()`, local imports, unused imports, cross-bounded-context imports) immediately after being written, not batched.

---

## 3. Domain Model Summary

**Two aggregate roots**: `Conversation` (lifecycle + participant management; owns `Participant` entities directly, since participant cardinality is small, unlike Message's high-frequency creation pattern) and `Message` (individual message lifecycle, referencing its parent by plain `uuid.UUID`). 1 owned entity (`Participant`). 6 enums, 4 value objects.

**`Conversation` lifecycle state machine**: `OPEN → CLOSED` (`close()`), `CLOSED → OPEN` (`reopen()`), `OPEN/CLOSED → ARCHIVED` (`archive()`). **`ARCHIVED` is deliberately terminal** — reopening an archived conversation always raises `InvalidConversationTransition`. This is a documented, disclosed boundary resolution (this phase's own Step 1 found no repository evidence dictating either choice), not a fabricated certainty. 8 public methods: `open` (factory), `add_participant`, `remove_participant`, `assign_operator`, `close`, `reopen`, `archive`, `record_activity`.

**`Message` lifecycle state machine**: `SENT → EDITED` (`edit()`, repeatable), `SENT/EDITED → DELETED` (`delete()`, terminal). 5 public methods: `send` (factory), `edit`, `delete`, `mark_delivered`, `mark_read` — the latter two are deliberately idempotent no-ops on a repeat call (returning `None` rather than raising or re-emitting), matching the established "a repeated signal is a safe no-op" precedent already used by Loyalty's `evaluate_tier` no-change case, since a real WebSocket delivery/read acknowledgment may legitimately arrive more than once.

---

## 4. Domain Service Summary

**2 policy classes**: `MessageEditPolicy` (`can_edit`, hand-traced and confirmed correct: only TEXT-type messages in SENT/EDITED status are editable), `ParticipantPolicy` (`is_role_valid_for_conversation_type`, hand-traced against all three cases: CUSTOMER blocked in INTERNAL_SUPPORT, OPERATOR allowed everywhere, CUSTOMER allowed in CUSTOMER_SALES/CUSTOMER_SUPPORT).

**A deliberate, disclosed scope decision**: neither `ConversationAssignmentPolicy` nor `ConversationRoutingPolicy` was created, despite being listed as "potential examples" in this phase's own brief. Deciding *which* operator to assign (round-robin, least-busy, skill-based) genuinely requires knowledge of other conversations and operator workload — repository/cross-aggregate knowledge that cannot be a pure Domain service without either fabricating that knowledge or reaching outside the aggregate boundary. Documented in `services.py`'s own module docstring, not silently omitted.

---

## 5. Validator Summary

2 thin, intention-revealing wrappers: `MessageContentValidator`, `AttachmentMetadataValidator`.

---

## 6. Exception Summary

**10 exceptions**, all subclassing `common.exceptions.DomainException`, every one confirmed genuinely raised somewhere in Domain (verified programmatically, not by eye): `InvalidConversationTransition`, `ParticipantAlreadyExists`, `ParticipantNotFound`, `InvalidParticipantRole`, `EmptyMessageContent`, `MessageContentTooLong`, `AttachmentRequired`, `MessageEditNotAllowed`, `MessageAlreadyDeleted`, `MessageNotOwnedBySender`.

**A real mistake caught and fixed during this phase, described fully in §11**: an 11th exception, `InvalidMessageTransition`, was initially defined as a generic fallback but was never actually needed — every real Message wrong-state case is already covered by the more specific `MessageEditNotAllowed`/`MessageAlreadyDeleted`. Removed entirely as genuine dead code before certification, matching the precedent already established by Wallet's `WalletEntityNotFound` removal.

---

## 7. Domain Event Summary

**12 events**, zero duplicates, zero collisions with exceptions (verified programmatically): `ConversationOpened`, `ParticipantAdded`, `ParticipantRemoved`, `ConversationAssigned`, `ConversationClosedEvent`, `ConversationReopened`, `ConversationArchivedEvent`, `MessageSent`, `MessageEdited`, `MessageDeleted`, `MessageDelivered`, `MessageRead`. Every event confirmed genuinely emitted somewhere in `aggregates.py` — verified programmatically. `ConversationClosedEvent`/`ConversationArchivedEvent` carry the defensive `Event` suffix, matching this build's established naming convention for events sitting near plausible exception-name collisions.

---

## 8. Architecture Compliance

Every gate re-verified fresh after all 8 files were written: zero Django/Channels/Redis/Celery/HTTP/WebSocket imports anywhere in `apps/chat/domain/`; zero forward dependency on any other bounded context (the complete expanded list, including the two genuinely real modules — `apps.identity`, `apps.reviews` — that a naive design could plausibly have imported from); zero circular imports (`exceptions.py` imports nothing from `apps.chat` itself, so `value_objects.py`'s dependency on it is safely one-directional); every aggregate mutation on both `Conversation` and `Message` reachable only through a public method.

---

## 9. Validation Results

| Gate | Status |
|---|---|
| Domain compile | ✓ |
| Framework independence | ✓ — zero Django/Channels/Redis/Celery imports |
| Aggregate lifecycle | ✓ — both state machines explicit, every invalid transition raises a specific exception |
| Event coverage | ✓ — 12/12 declared events genuinely emitted |
| Exception usage | ✓ — 10/10 genuinely raised (after removing 1 dead exception, §11) |
| Zero circular imports | ✓ |
| Zero forward dependency | ✓ — AST-verified against the full expanded forbidden list |
| Zero `__import__()` | ✓ |
| Zero local imports | ✓ |
| Zero unused imports | ✓ — one real instance found and fixed (§11) |

---

## 10. Fresh Verified Counts

| Metric | Count |
|---|---|
| Repository-wide Python files | **1395** |
| Chat domain files | **9** (8 content files + `__init__.py`) |
| Enums | 6 |
| Value Objects | 4 |
| Entities | 1 |
| Aggregates | 2 |
| Domain Services | 2 |
| Validators | 2 |
| Events | 12 |
| Exceptions | 10 |
| `Conversation` public methods | 8 |
| `Message` public methods | 5 |

---

## 11. Mistakes Found

Reported honestly, per this phase's explicit instruction — none hidden, none silently corrected:

1. **A real, substantive mistake: an exception defined but never used, caught before it became dead code.** `InvalidMessageTransition` was initially added to `exceptions.py` as a "generic fallback for wrong-status message transitions," mirroring `Conversation`'s own `InvalidConversationTransition`. After writing `aggregates.py`, a direct programmatic check (`raise {ExceptionName}(` search across the file) found it was never actually raised — every real Message wrong-state case Domain needed was already covered by the more specific `MessageEditNotAllowed` (edit attempted on a non-editable message) and `MessageAlreadyDeleted` (double-delete), unlike `Conversation`, which genuinely has multiple distinct wrong-state scenarios (close-from-wrong-state, reopen-from-wrong-state, archive-from-archived) that a single fallback legitimately covers. **Why it happened**: pattern-matching Conversation's own exception design onto Message without checking whether Message's simpler, more linear state machine actually needed an equivalent generic fallback. **How it was detected**: a direct AST-based "is every exception genuinely raised somewhere" check run immediately after writing `aggregates.py`, per this phase's own mandatory self-audit requirement, not deferred to the end. **How it was fixed**: removed entirely from both `exceptions.py` and the now-unneeded import in `aggregates.py`, matching the established precedent (Wallet's `WalletEntityNotFound`) of removing genuinely dead exceptions rather than either leaving them or inventing a contrived usage just to justify keeping them.
2. **A second, related mistake, of the exact same category already caught once in this same build's Reviews Phase 1**: `MessageContent`'s own `__post_init__` (in `value_objects.py`) was initially written raising generic `ValidationFailed` for both its empty-string and too-long checks, even though `EmptyMessageContent` and `MessageContentTooLong` had already been defined in `exceptions.py` with exactly those cases in mind. **Why it happened**: the two files were drafted with the intent already decided, but the actual wiring between them was never completed before moving to the next file — the identical root cause already documented in Reviews' own Phase 1 certification report. **How it was detected**: the same "is every exception genuinely raised somewhere" check that caught mistake #1 also flagged `MessageContentTooLong` as unraised, prompting a direct comparison of `value_objects.py`'s actual `raise` statements against `exceptions.py`'s stated intent. **How it was fixed**: `value_objects.py` now imports and raises `EmptyMessageContent`/`MessageContentTooLong` specifically; `AttachmentMetadata`'s own three checks remain generic `ValidationFailed`, since no more specific exception exists (or is needed) for those cases — a deliberate, not-every-check-needs-a-bespoke-exception decision, not an oversight.
3. **No other mistakes were found.** `ParticipantPolicy` and `MessageEditPolicy`'s logic were both verified correct by direct hand-trace against every relevant input combination, not by execution (see §12 for the full runtime-availability disclosure).

---

## 12. Final Certification

Chat Phase 1 (Domain) is complete.

**Exact files changed**: 8 files under `apps/chat/domain/` (all newly written this phase, replacing 13-line placeholders).

**Exact architectural boundaries respected**: zero Django/Channels/Redis/Celery/HTTP/WebSocket dependency anywhere in Domain; zero forward dependency on any other bounded context; the Conversation/Message aggregate split and its direct consequence (no cross-aggregate open-check in `Message.send()`) both explicitly reasoned and disclosed, not assumed.

**What remains untouched**: `apps/chat/application/`, `apps/chat/infrastructure/`, `apps/chat/interfaces/`, `apps/chat/tests/`, and `apps/chat/apps.py` all remain exactly as they were — genuine 13-line placeholders, none created, modified, or even inspected beyond the read-only Step 1 review of `apps/chat/apps.py`'s own placeholder content.

**Disclosed limitations**: "duplicate conversation" prevention (whether two OPEN conversations between the same customer/operator pair are allowed) is explicitly left unresolved by Domain — this would require a repository query ("does an open conversation already exist for X"), which Domain cannot honestly answer in isolation; this is deferred to a future Application layer, not fabricated here. Similarly, no distributed-system message-deduplication/idempotency guarantee is provided by Domain — that is explicitly an Infrastructure/Application concern (e.g. a client-supplied idempotency key), and inventing one here would have violated this phase's own explicit prohibition on fabricating distributed-system guarantees inside Domain.

**Whether runtime testing was possible**: no. Consistent with every prior phase of this entire build, Django is not installed in this sandbox. Every verification in this report is `python3 -m py_compile` (syntax only), direct AST parsing, or direct grep/regex inspection. `MessageEditPolicy` and `ParticipantPolicy`'s logic were verified correct by manual hand-trace against representative inputs, not by execution, and that distinction is stated plainly here rather than implied away.

**Do not begin Phase 2 unless explicitly instructed. Waiting for the next instruction.**
