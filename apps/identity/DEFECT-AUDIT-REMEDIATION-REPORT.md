# Identity Module — Defect Audit & Remediation Report

**Fifteen production/test files modified. Every claim below is either verified directly against live source or explicitly disclosed as unverified/unaddressed. No count is estimated.**

---

## A. Defects Found

### A1. Refresh token reuse never actually detected (Sections 8–9)
**File**: `apps/identity/application/services/auth.py::RefreshToken.execute()`, `apps/identity/infrastructure/repositories.py::DjangoUserSessionRepository`
**Severity**: High (security)
**Root cause**: `RevokedTokenRecord` was correctly written by `revoke()`, and `report_reuse()`/`RefreshTokenReusedError`/`SuspiciousLoginDetected` all already existed correctly implemented — but nothing ever called `is_token_reuse()` to check it. The repository's own docstring described an interfaces-layer check that was never built. A stolen, rotated-out token produced the same generic `RefreshTokenInvalidError` as a token that never existed — no theft signal, no session-family revocation.
**Also found while fixing**: `is_token_reuse()` returned the raw `orm.RevokedTokenRecord` ORM row — a real Infrastructure→Application leak, since it wasn't part of the `UserSessionRepository` Port at all.

### A2. OTP mutations targeted "whatever's latest," not a specific challenge (Sections 12–13)
**File**: `apps/identity/domain/services.py::OTPChallengeState`, `apps/identity/infrastructure/repositories.py::DjangoOTPChallengeRepository`
**Severity**: High (security/correctness)
**Root cause**: `OTPChallengeState` had no `id` field, so every mutation (`increment_attempt`, `mark_consumed`) had no choice but to re-derive "the latest challenge for this phone number" independently of whatever was actually read and verified. A second OTP requested between a verification attempt's read and its mutation caused the wrong challenge to be mutated.

### A3. OTP attempt counter: lost-update race (Section 10)
**File**: `apps/identity/infrastructure/repositories.py::DjangoOTPChallengeRepository.increment_attempt`
**Severity**: Medium (security — brute-force bypass)
**Root cause**: Python-side read-modify-write (`row.attempt_count = row.attempt_count + 1; row.save(...)`) instead of an atomic database operation. Two concurrent failed attempts could both read the same count, both compute the same increment, and one increment would be silently lost.

### A4. OTP double-consumption possible under concurrency (Section 13)
**File**: same as A3, `mark_consumed`
**Severity**: Medium (security)
**Root cause**: No atomicity or idempotency guard — nothing prevented two concurrent requests from both consuming the same challenge.

### A5. `except Exception:` masking infrastructure failures as OTP wrong-guesses (Section 11)
**File**: `apps/identity/application/services/auth.py::VerifyOTP.execute()`
**Severity**: Medium
**Root cause**: `except Exception:` around `OTPPolicy.verify()` meant a genuine bug or infrastructure failure (not one of the three real verification-failure exceptions) would still increment the user's attempt counter, silently corrupting their remaining-attempts budget.

### A6. `except Exception as exc:` in authentication, comment contradicts code (Section 19)
**File**: `apps/identity/infrastructure/authentication.py::JWTIdentityAuthentication`
**Severity**: Medium
**Root cause**: The code's own comment claimed it caught `AccountBlockedError` specifically; the actual code caught everything. A genuine bug in `assert_can_authenticate()` would have been silently converted into a generic `AuthenticationFailed`.

### A7. `birthday` type mismatch: Domain claims `datetime`, ORM/serializer use `date` (Section 5)
**File**: `apps/identity/domain/aggregates.py`
**Severity**: Low (never an actual runtime crash — Django's ORM already returns real `date` objects; this was a documentation/type-annotation gap, not a functional defect)

### A8. `FitnessProfile.goal` accepted any arbitrary string with zero validation (Section 6)
**File**: `apps/identity/domain/value_objects.py`
**Severity**: Medium (data integrity)
**Root cause**: The comment justifying `goal: str` claimed a domain/enums↔value_objects circular import. **This claim is false** — confirmed directly via AST that `enums.py` has zero dependency on `value_objects.py` anywhere.

### A9. PATCH could never clear a nullable profile field (Section 16)
**Files**: `apps/identity/domain/aggregates.py::User.update_profile`, `apps/identity/application/services/profile.py::UpdateProfile.execute`
**Severity**: Medium (API contract violation)
**Root cause**: `None` meant "not supplied" everywhere, for both the 4 direct fields (`email`/`username`/`bio`/`birthday`) and the 3 fitness-composite fields (`height_cm`/`weight_kg`/`goal`) — 7 fields total. `UpdateProfileSerializer` already declares `allow_null=True` on exactly these 7 fields, direct evidence the API contract already intended clearing to be possible.

### A10. Scattered local imports (Sections 33, general code quality)
**Files**: all 15 modified files had at least one instance; a further **43 instances remain unaddressed** across `views.py`, `staff.py`, `roles.py`, `health.py`, `gateways/otp_providers.py`, `application/selectors.py`, `interfaces/api/v1/filters.py`, `tests/conftest.py`, and several other test files not touched this session.
**Severity**: Low (style/maintainability, not correctness)

### Investigated and found NOT to be defects
- **E.164 regex** (Section 3): already correctly escaped in live source (`r"^\+[1-9]\d{1,14}$"`). The prompt's claimed defective form does not exist in this repository.
- **`Email._EMAIL_RE` ClassVar** (Section 4): confirmed via direct instantiation with `slots=True` that this has no runtime effect — fixed anyway as a typing/consistency improvement, not because it was broken.
- **Django 6 `check=` syntax** (Section 2): zero occurrences anywhere in Identity — already uses `CheckConstraint(condition=...)` throughout.
- **Soft-delete leakage** (Section 18): `User(SoftDeleteModel)`'s default `.objects` manager is `ActiveManager`, confirmed to filter `is_deleted=False` automatically — every repository query already correctly excludes soft-deleted users.
- **Unhandled `DoesNotExist`** (Section 17): zero `.objects.get()` calls anywhere in the repository layer — every query uses `.filter().first()`, which returns `None` rather than raising.
- **`ready()` side effects** (Section 30): read-only singleton/health-check wiring, no database writes, matches the identical established pattern used across every other module in this project.
- **`security.py`/`health.py`'s `except Exception`**: both legitimate, established patterns (JWT-parse no-op, health-check resilience) — not defects.

---

## B. Changes Made

| File | Change | Reason |
|---|---|---|
| `domain/aggregates.py` | Added `UNSET`/`_Unset` sentinel; `birthday: datetime→date`; `update_profile()` rewritten to distinguish UNSET/None/value for `email`/`username`/`bio`/`birthday` | A9, A7 |
| `domain/value_objects.py` | `FitnessProfile.goal: str→FitnessGoal`, auto-converts+validates raw strings | A8 |
| `domain/services.py` | Added `id: uuid.UUID` to `OTPChallengeState` | A2 |
| `application/ports.py` | Added `is_token_reuse()` to `UserSessionRepository` (returns `(user_id, session_id) | None`, never the ORM row); changed `OTPChallengeRepository.increment_attempt`/`mark_consumed` to take `challenge_id`, `mark_consumed` now returns `bool` | A1, A2 |
| `application/services/auth.py` | `RefreshToken.execute()` calls `is_token_reuse()`+`report_reuse()`; `@transaction.atomic` added to `RequestOTP.execute()` (required by A2's `select_for_update()`); `VerifyOTP.execute()` uses `challenge.id`, catches only the 3 real verification exceptions, checks `mark_consumed()`'s return value | A1, A2, A5 |
| `application/services/profile.py` | `UpdateProfile.execute()` rewritten with UNSET sentinels for all 7 clearable fields, including the fitness composite; local imports removed | A9 |
| `infrastructure/repositories.py` | `DjangoOTPChallengeRepository` rewritten: `select_for_update()`, atomic `F()` increment, atomic conditional `mark_consumed`, id-based targeting; `is_token_reuse()` returns tuple not ORM row; local imports removed | A1, A2, A3, A4, A10 |
| `infrastructure/authentication.py` | `except Exception` → `except AccountBlockedError` | A6 |
| `interfaces/api/v1/views.py` | `_client_ip(request)` threaded into `RefreshToken.execute()` call | A1 (no other change — `**serializer.validated_data` already correctly encoded the UNSET/None distinction via DRF's own `partial=True` semantics) |
| 6 test files | New/updated tests for every fix above; `FakeUserSessionRepository`/`FakeOTPChallengeRepository` redesigned to mirror the corrected, id-based real repository contracts; local imports removed throughout | Coverage for A1–A9 |

---

## C. Database Changes

**None.** No migration was created. `OTPCodeChallenge.id` already existed as the table's real primary key (`models.UUIDField(primary_key=True, ...)`) — the fix surfaces it through the Domain/Application layers, it does not add a new column. No new constraint, index, or field was added anywhere.

---

## D. Security Fixes

- **OTP brute-force protection**: A3 (atomic `F()` increment closes a lost-update race in the attempt counter) + A2 (the counter now targets the exact challenge, not "whatever's latest").
- **Refresh-token rotation/reuse detection**: A1 — this is the most significant fix in this audit. Reuse of a rotated-out token now correctly revokes the full session family and raises a distinguishable `RefreshTokenReusedError`, rather than a generic invalid-token error indistinguishable from a typo.
- **Blocked-account authentication**: verified already correct (A6 is a defect in *how* the check is expressed, not whether it functions — `AccountBlockedError` was always being raised and caught correctly before this fix; the risk was that a *different*, unexpected exception would have been silently misclassified as the same thing).
- **Concurrency protection**: A2, A3, A4 (`select_for_update()` on the OTP read path, atomic increment, atomic conditional consumption) + A1's underlying transaction correctness.

---

## E. Verification

**`python manage.py check`**: NOT EXECUTED. Django is unavailable in this sandbox (`import django` → `ModuleNotFoundError`), confirmed directly, not assumed.

**`python manage.py makemigrations --check --dry-run`**: NOT EXECUTED, same reason. No model field changed type or was added/removed at the ORM level this session (only Domain/Application-layer types and logic changed), so no migration was expected to be needed even if this could be run — but this expectation is unverified, not claimed as fact.

**`python manage.py test apps.identity`**: NOT EXECUTED, same reason.

**What was actually done instead**:
- `python3 -m py_compile` on every one of the 15 modified files individually, and on the full repository (1512/1512 files, clean) after every batch of changes.
- Direct AST-based local-import/unused-import scans on every modified file.
- Three standalone, executed runtime verifications outside the Django-dependent parts of the codebase: (1) the `Email`/`slots=True` ClassVar question, actually instantiated and exercised; (2) the `UNSET` sentinel pattern, actually exercised through all three cases (not-supplied, explicit-clear, explicit-value); (3) the `FitnessGoal` auto-conversion/validation logic, actually exercised for a raw string, an enum member, and an invalid string.
- Direct AST inspection proving `enums.py` has zero dependency on `value_objects.py` (closing the false circular-import claim).

**Static validation only — no runtime test execution occurred at any point in this session.**

---

## F. Mistakes Found (Section 25/18 disclosure)

1. **A real mid-session mistake I made and caught myself**: while editing `apps/identity/domain/aggregates.py` to fix `birthday`'s type, one `str_replace` edit accidentally deleted the `bio` and `fitness_profile` field declarations entirely (they were adjacent to the line being changed and got swept up in the replacement). **Detected**: by re-reading the file immediately after the edit rather than assuming it worked. **Fixed**: restored both fields in the same turn, before any further work built on top of the broken state. **Revalidated**: re-viewed the file and recompiled.
2. **An incorrect first design for `is_token_reuse()`'s Port signature**: initially designed it to return a plain `bool`, then had to redesign it to return `(user_id, session_id)` once I realized a bool alone wasn't enough information for `report_reuse()` to correctly identify *whose* sessions to revoke. Caught by working through the actual call site before finalizing the Port, not after.
3. **An overly narrow first version of the reuse-detection fix**: my first draft of `RefreshToken.execute()`'s reuse branch just rejected the request outright with a comment explaining that revoking sessions safely wasn't possible without more information — before I noticed that `RevokedTokenRecord` already stored `user_id`/`session_id` and the "safe" rejection was unnecessarily conservative. Corrected before it was finalized.
4. **This report's own honesty boundary**: 43 local-import instances remain unaddressed in files not modified this session (`views.py`'s remaining occurrences beyond the one line touched, `staff.py`, `roles.py`, `health.py`, `gateways/otp_providers.py`, `selectors.py`, `filters.py`, `conftest.py`, and several test files). These are disclosed explicitly in Section A10 rather than silently left out of the count, and are not claimed as fixed.

---

## Fresh Counts

| Metric | Count |
|---|---|
| Repository-wide Python files | 1512 (unchanged from before this session — no file created or deleted) |
| Identity files modified | 15 |
| Identity test files | 12 |
| Identity test functions | 128 |
| Local imports fixed this session | 21 (across the 15 modified files) |
| Local imports confirmed legitimate, not fixed | 6 (`apps.py`'s `ready()` hook — Django app-loading requirement) |
| Local imports remaining, unaddressed, disclosed | 43 |
| Real defects fixed | 9 (A1–A9) |
| Claimed defects investigated and found not to exist | 6 |

---

## Final Status

This audit is **partial, not exhaustive**, and I want to be direct about that rather than imply completeness the work doesn't have. Nine real, verified defects were found and fixed — including one significant security gap (refresh-token reuse detection, fully wired but never connected) and a cluster of genuine OTP concurrency issues traced to a single root cause (a missing identity field). Every fix was verified by direct execution where Django's absence didn't block it, and by careful compilation/static analysis everywhere else.

Sections 2, 5, 6, 8–13, 16, and parts of 17–19, 30, and 33 received genuine, source-verified attention. Sections 20–29 (DRF exception-handler branch coverage, role/store-scoping privilege-escalation review, events/outbox transaction-boundary audit, migration integrity, and a complete repository-wide static sweep beyond Identity's own module) were **not reached** this session and are not claimed as audited.

`python manage.py check`, `makemigrations --check --dry-run`, and `python manage.py test apps.identity` were **not executed** — Django is unavailable in this sandbox, confirmed directly. No claim of runtime test success appears anywhere in this report.
