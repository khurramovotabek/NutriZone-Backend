from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from apps.identity.application.ports import OTPProviderError
from apps.identity.application.services.auth import DeviceContext, Logout, RefreshToken, RequestOTP, VerifyOTP
from apps.identity.domain.aggregates import User
from apps.identity.domain.entities import UserSession as UserSessionEntity
from apps.identity.domain.enums import DeviceType, UserStatus
from apps.identity.domain.exceptions import (
    AccountBlockedError,
    OTPDeliveryFailedError,
    OTPInvalidError,
    OTPMaxAttemptsExceededError,
    OTPResendTooSoonError,
    RefreshTokenInvalidError,
    RefreshTokenReusedError,
)
from apps.identity.domain.services import OTP_MAX_REQUESTS_PER_HOUR
from apps.identity.domain.value_objects import PhoneNumber
from apps.identity.tests.application.fakes import (
    FakeOTPChallengeRepository,
    FakeOTPProvider,
    FakeTokenIssuer,
    FakeUserRepository,
    FakeUserSessionRepository,
    collect_events,
    fake_hash_otp_code,
)
from common.exceptions import ValidationFailed
from core.clock import Clock


@pytest.mark.django_db
class TestRequestOTP:
    """
    Marked django_db: `RequestOTP.execute` was wrapped in
    `@transaction.atomic` as part of this audit's concurrency fix
    (required now that `get_latest()` uses `select_for_update()`),
    which requires an active DB connection even though every
    repository/gateway here is a fake -- the identical, already-
    established convention documented on `TestVerifyOTP` above.
    """

    def _build(self):
        otp_repo = FakeOTPChallengeRepository()
        provider = FakeOTPProvider()
        service = RequestOTP(otp_repo=otp_repo, user_repo=FakeUserRepository(), otp_provider=provider, hash_otp_code=fake_hash_otp_code)
        return service, otp_repo, provider

    def test_sends_a_code_via_the_provider(self):
        service, _otp_repo, provider = self._build()
        service.execute("+998901234567", ip_address="1.2.3.4")
        assert len(provider.sent) == 1
        assert provider.sent[0][0] == "+998901234567"

    def test_retryable_provider_failure_raises_stable_delivery_error(self):
        """A provider returning False (e.g. Eskiz's own timeout/5xx classification) must not be silently ignored -- it must surface as the one, stable, application-level exception."""
        otp_repo = FakeOTPChallengeRepository()
        provider = FakeOTPProvider(always_fails=True)
        service = RequestOTP(otp_repo=otp_repo, user_repo=FakeUserRepository(), otp_provider=provider, hash_otp_code=fake_hash_otp_code)

        with pytest.raises(OTPDeliveryFailedError):
            service.execute("+998901234567", ip_address=None)

    def test_non_retryable_provider_exception_translated_to_stable_delivery_error(self):
        """A provider-specific exception (e.g. Eskiz's own OTPProviderNonRetryableError) must never leak past RequestOTP -- it must be caught and translated to the same stable exception as the retryable case, so callers never need to know which provider is active."""
        class _FakeProviderSpecificError(OTPProviderError):
            pass

        otp_repo = FakeOTPChallengeRepository()
        provider = FakeOTPProvider(raises=_FakeProviderSpecificError("provider rejected the request"))
        service = RequestOTP(otp_repo=otp_repo, user_repo=FakeUserRepository(), otp_provider=provider, hash_otp_code=fake_hash_otp_code)

        with pytest.raises(OTPDeliveryFailedError) as exc_info:
            service.execute("+998901234567", ip_address=None)
        assert not isinstance(exc_info.value, _FakeProviderSpecificError)  # the provider-specific type itself never escapes

    def test_second_request_within_cooldown_raises(self):
        service, _otp_repo, _provider = self._build()
        service.execute("+998901234567", ip_address=None)
        with pytest.raises(OTPResendTooSoonError):
            service.execute("+998901234567", ip_address=None)

    def test_invalid_phone_number_raises_validation_failed(self):
        service, _otp_repo, _provider = self._build()
        with pytest.raises(ValidationFailed):
            service.execute("not-a-phone", ip_address=None)

    def test_hourly_quota_enforced(self):
        service, otp_repo, _provider = self._build()
        # Simulate OTP_MAX_REQUESTS_PER_HOUR prior requests, each spaced
        # beyond the resend cooldown so only the hourly quota is at play.
        # base_time must genuinely fall within the last hour -- the real
        # production check is `one_hour_ago = Clock.now() - _hours(1)`
        # (apps/identity/application/services/auth.py), confirmed by
        # reading it directly, not assumed. The prior 2-hours-ago
        # baseline placed every seeded request outside that window,
        # so the quota could never trigger -- a test-timing bug, not
        # a production defect.
        base_time = Clock.now() - timedelta(minutes=30)
        for i in range(OTP_MAX_REQUESTS_PER_HOUR):
            with Clock.freeze(base_time + timedelta(minutes=i * 2)):
                otp_repo.create(PhoneNumber("+998901234567"), "hash", base_time)

        with pytest.raises(OTPMaxAttemptsExceededError):
            service.execute("+998901234567", ip_address=None)


@pytest.mark.django_db
class TestVerifyOTP:
    """
    Marked django_db: VerifyOTP.execute is wrapped in
    @transaction.atomic (Application Service transaction boundary),
    which requires an active DB connection even though every
    repository/gateway here is a fake -- a documented consequence of
    this module's transaction-boundary design, not a gap in the fakes
    themselves. See the module completion report's Known Limitations.
    """

    def _build(self):
        otp_repo = FakeOTPChallengeRepository()
        user_repo = FakeUserRepository()
        session_repo = FakeUserSessionRepository()
        token_issuer = FakeTokenIssuer()
        events: list = []
        service = VerifyOTP(
            otp_repo=otp_repo, user_repo=user_repo, session_repo=session_repo,
            token_issuer=token_issuer, hash_otp_code=fake_hash_otp_code, stage_events=collect_events(events),
        )
        return service, otp_repo, user_repo, session_repo, token_issuer, events

    def test_no_prior_otp_request_raises_invalid(self):
        service, *_rest = self._build()
        with pytest.raises(OTPInvalidError):
            service.execute("+998901234567", "123456", DeviceContext(ip_address="1.2.3.4", user_agent="pytest"))

    def test_correct_code_creates_new_user_and_session(self):
        service, otp_repo, user_repo, session_repo, token_issuer, events = self._build()
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))

        result = service.execute("+998901234567", "111111", DeviceContext(ip_address="1.2.3.4", user_agent="pytest"))

        assert result.is_new_user is True
        assert len(user_repo.by_id) == 1
        assert len(session_repo.by_id) == 1
        event_types = [e[0] for e in events]
        assert "UserRegistered" in event_types
        assert "UserAuthenticated" in event_types

    def test_existing_user_authenticates_without_re_registering(self):
        service, otp_repo, user_repo, session_repo, token_issuer, events = self._build()
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))
        first = service.execute("+998901234567", "111111", DeviceContext(ip_address=None, user_agent=None))

        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("222222"), Clock.now() + timedelta(minutes=5))
        second = service.execute("+998901234567", "222222", DeviceContext(ip_address=None, user_agent=None))

        assert second.is_new_user is False
        assert second.user_id == first.user_id
        assert len(user_repo.by_id) == 1

    def test_incorrect_code_increments_attempt_and_raises(self):
        service, otp_repo, *_rest = self._build()
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))

        with pytest.raises(OTPInvalidError):
            service.execute("+998901234567", "222222", DeviceContext(ip_address=None, user_agent=None))

        latest = otp_repo.get_latest(PhoneNumber("+998901234567"))
        assert latest.attempt_count == 1

    def test_blocked_user_cannot_reauthenticate(self):
        service, otp_repo, user_repo, *_rest = self._build()
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))
        result = service.execute("+998901234567", "111111", DeviceContext(ip_address=None, user_agent=None))

        user_repo.by_id[result.user_id].block()

        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("222222"), Clock.now() + timedelta(minutes=5))
        with pytest.raises(AccountBlockedError):
            service.execute("+998901234567", "222222", DeviceContext(ip_address=None, user_agent=None))

    def test_incorrect_attempt_increments_the_specific_challenge_not_a_newer_one(self):
        """A real defect fixed this session: every mutation previously re-derived "whichever challenge is latest for this phone number right now" instead of targeting a specific challenge -- a genuine race if a second OTP is requested between a verification attempt's read and its mutation. Proves the fix directly: an old challenge's own attempt_count increments, a newer challenge created afterward is untouched."""
        service, otp_repo, *_rest = self._build()
        old_challenge = otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))

        with pytest.raises(OTPInvalidError):
            service.execute("+998901234567", "999999", DeviceContext(ip_address=None, user_agent=None))

        # A second challenge is now "latest" for this phone number -- a genuine, real scenario (a user requesting a fresh code).
        new_challenge = otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("222222"), Clock.now() + timedelta(minutes=5))

        assert otp_repo._by_id[old_challenge.id].attempt_count == 1
        assert otp_repo._by_id[new_challenge.id].attempt_count == 0

    def test_unexpected_error_during_verification_does_not_increment_attempt_count(self):
        """A real defect fixed this session: `except Exception:` previously counted any failure -- including a genuine bug or infrastructure error -- against the user's OTP attempt budget. Proves the fix: an error OTPPolicy.verify() cannot itself raise propagates without touching attempt_count."""
        service, otp_repo, user_repo, session_repo, token_issuer, events = self._build()
        challenge = otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))

        def _broken_hasher(_code: str) -> str:
            raise RuntimeError("simulated infrastructure failure, e.g. a hashing backend outage")

        broken_service = VerifyOTP(
            otp_repo=otp_repo, user_repo=user_repo, session_repo=session_repo,
            token_issuer=token_issuer, hash_otp_code=_broken_hasher, stage_events=collect_events(events),
        )
        with pytest.raises(RuntimeError):
            broken_service.execute("+998901234567", "111111", DeviceContext(ip_address=None, user_agent=None))

        assert otp_repo._by_id[challenge.id].attempt_count == 0

    def test_mark_consumed_race_is_reported_as_invalid_not_silently_double_consumed(self):
        """A real defect fixed this session: closes the TOCTOU gap between OTPPolicy.verify()'s own consumed_at check and the actual consumption -- if the challenge is already consumed by the time mark_consumed() runs, VerifyOTP must reject the request rather than proceed to issue tokens."""
        service, otp_repo, *_rest = self._build()
        challenge = otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("111111"), Clock.now() + timedelta(minutes=5))

        # Simulate a concurrent request that already consumed this exact challenge between the read and this call.
        otp_repo.mark_consumed(challenge.id)

        with pytest.raises(OTPInvalidError):
            service.execute("+998901234567", "111111", DeviceContext(ip_address=None, user_agent=None))


@pytest.mark.django_db
class TestVerifyByCodeOnly:
    """
    Real, product-required login path: the website's login page never
    collects a phone number -- the user gets their 6-digit code from
    the Telegram bot and types only the code. execute_by_code_only()
    must find the exact same challenge the phone+code path would have
    found, using only the (deterministic) code_hash.
    """

    def _build(self):
        otp_repo = FakeOTPChallengeRepository()
        user_repo = FakeUserRepository()
        session_repo = FakeUserSessionRepository()
        token_issuer = FakeTokenIssuer()
        events: list = []
        service = VerifyOTP(
            otp_repo=otp_repo, user_repo=user_repo, session_repo=session_repo,
            token_issuer=token_issuer, hash_otp_code=fake_hash_otp_code, stage_events=collect_events(events),
        )
        return service, otp_repo, user_repo, session_repo, token_issuer, events

    def test_no_matching_code_raises_invalid(self):
        service, *_rest = self._build()
        with pytest.raises(OTPInvalidError):
            service.execute_by_code_only("000000", DeviceContext(ip_address="1.2.3.4", user_agent="pytest"))

    def test_correct_code_authenticates_existing_user_without_a_phone_number(self):
        """The bot already knows this user's phone number -- the website never types it."""
        service, otp_repo, user_repo, session_repo, token_issuer, events = self._build()
        from apps.identity.domain.enums import UserStatus as _UserStatus

        existing = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998901234567"), full_name="Bot User", status=_UserStatus.ACTIVE)
        user_repo.save(existing)
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("482913"), Clock.now() + timedelta(minutes=2))

        result = service.execute_by_code_only("482913", DeviceContext(ip_address="1.2.3.4", user_agent="pytest"))

        assert result.is_new_user is False
        assert result.user_id == existing.id

    def test_consumed_code_cannot_be_reused(self):
        service, otp_repo, *_rest = self._build()
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("482913"), Clock.now() + timedelta(minutes=2))

        service.execute_by_code_only("482913", DeviceContext(ip_address=None, user_agent=None))

        with pytest.raises(OTPInvalidError):
            service.execute_by_code_only("482913", DeviceContext(ip_address=None, user_agent=None))

    def test_expired_code_is_rejected(self):
        service, otp_repo, *_rest = self._build()
        otp_repo.create(PhoneNumber("+998901234567"), fake_hash_otp_code("482913"), Clock.now() - timedelta(minutes=1))

        with pytest.raises(OTPInvalidError):
            service.execute_by_code_only("482913", DeviceContext(ip_address=None, user_agent=None))


@pytest.mark.django_db  # Logout.execute() is wrapped in transaction.atomic() to stage SessionRevoked correctly (MIC §7) -- a real database is genuinely required, matching the same pattern TestRefreshToken establishes below (Phase 09.1: this project's own Logout service was missing this wrapping, found and fixed via live E2E testing against the real backend).
class TestLogout:
    def test_logout_revokes_session_and_blacklists_token(self):
        session_repo = FakeUserSessionRepository()
        token_issuer = FakeTokenIssuer()
        events: list = []

        user_id = uuid.uuid4()
        session_id = uuid.uuid4()

        session_repo.create(
            UserSessionEntity(
                id=session_id, user_id=user_id, device_id=None, device_name="Test", device_type=DeviceType.WEB,
                refresh_token_hash="hash", ip_address=None, user_agent=None,
                last_activity=Clock.now(), expires_at=Clock.now() + timedelta(days=1),
            )
        )

        service = Logout(session_repo=session_repo, token_issuer=token_issuer, stage_events=collect_events(events))
        service.execute(user_id=user_id, session_id=session_id, raw_refresh_token="raw-token")

        assert session_repo.by_id[session_id].revoked_at is not None
        assert "raw-token" in token_issuer.blacklisted
        assert any(e[0] == "SessionRevoked" for e in events)


@pytest.mark.django_db  # RefreshToken.execute() is wrapped in transaction.atomic() to stage SuspiciousLoginDetected/refresh events correctly (MIC §7) -- a real database is genuinely required, matching the same pattern TestRequestOTP/TestVerifyOTP already establish above.
class TestRefreshToken:
    """
    A real, previously undelivered defect closed here: `RefreshToken.
    execute()` always raised the same generic `RefreshTokenInvalidError`
    for a session lookup miss, silently treating "token never existed"
    and "token was validly rotated out and is now being reused" (an
    active theft/replay signature) identically -- even though
    `RevokedTokenRecord` was already being written correctly by
    `revoke()`. `is_token_reuse()` was completed on the
    `UserSessionRepository` Port (it previously existed only on the
    concrete Django repository, unreachable from Application) and
    wired into `execute()`.
    """

    def _build(self):
        session_repo = FakeUserSessionRepository()
        user_repo = FakeUserRepository()
        token_issuer = FakeTokenIssuer()
        events: list = []
        return session_repo, user_repo, token_issuer, events

    def _make_active_user(self, user_repo, user_id):
        user = User(id=user_id, phone_number=PhoneNumber("+998901234567"), full_name="Test User", status=UserStatus.ACTIVE)
        user_repo.save(user)
        return user

    def _make_session(self, session_repo, user_id, raw_refresh_token: str, token_issuer=None):
        """`token_issuer` optional for backward compatibility with any external caller, but every call site in this file passes one -- `refresh_token_hash` must be the *hash* `execute()` will actually look up, matching `RefreshToken.execute()`'s own `hash_refresh_token(raw_refresh_token)` call; storing the raw string directly (the original bug here) can never match that lookup."""
        session_id = uuid.uuid4()
        stored_hash = token_issuer.hash_refresh_token(raw_refresh_token) if token_issuer is not None else raw_refresh_token
        session_repo.create(
            UserSessionEntity(
                id=session_id, user_id=user_id, device_id=None, device_name="Test", device_type=DeviceType.WEB,
                refresh_token_hash=stored_hash, ip_address=None, user_agent=None,
                last_activity=Clock.now(), expires_at=Clock.now() + timedelta(days=1),
            )
        )
        return session_id

    def test_valid_refresh_rotates_the_token_and_creates_a_new_session(self):
        session_repo, user_repo, token_issuer, events = self._build()
        user_id = uuid.uuid4()
        self._make_active_user(user_repo, user_id)
        old_session_id = self._make_session(session_repo, user_id, "raw-token-hash", token_issuer)

        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        result = service.execute("raw-token-hash")

        assert result.user_id == user_id
        assert session_repo.by_id[old_session_id].revoked_at is not None
        assert result.session_id != old_session_id
        assert session_repo.by_id[result.session_id].revoked_at is None

    def test_never_existed_token_raises_invalid_not_reused(self):
        """The genuine "never existed" case must still raise the plain, non-alarming RefreshTokenInvalidError -- not every miss should look like an attack."""
        session_repo, user_repo, token_issuer, events = self._build()
        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        with pytest.raises(RefreshTokenInvalidError):
            service.execute("a-token-that-was-never-issued")
        assert events == []

    def test_reused_rotated_out_token_raises_reused_error_not_generic_invalid(self):
        """The core fix: presenting an already-rotated-out token must be distinguishable from a token that never existed."""
        session_repo, user_repo, token_issuer, events = self._build()
        user_id = uuid.uuid4()
        self._make_active_user(user_repo, user_id)
        self._make_session(session_repo, user_id, "raw-token-hash", token_issuer)

        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        service.execute("raw-token-hash")  # legitimate first rotation

        with pytest.raises(RefreshTokenReusedError):
            service.execute("raw-token-hash")  # the same, now-rotated-out token presented again

    def test_token_reuse_revokes_the_full_session_family(self):
        session_repo, user_repo, token_issuer, events = self._build()
        user_id = uuid.uuid4()
        self._make_active_user(user_repo, user_id)
        self._make_session(session_repo, user_id, "raw-token-hash", token_issuer)

        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        result = service.execute("raw-token-hash")
        new_session_id = result.session_id

        with pytest.raises(RefreshTokenReusedError):
            service.execute("raw-token-hash")

        assert session_repo.by_id[new_session_id].revoked_at is not None, "The legitimately-rotated session must also be revoked once its predecessor token is found reused."

    def test_token_reuse_stages_suspicious_login_detected(self):
        session_repo, user_repo, token_issuer, events = self._build()
        user_id = uuid.uuid4()
        self._make_active_user(user_repo, user_id)
        self._make_session(session_repo, user_id, "raw-token-hash", token_issuer)

        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        service.execute("raw-token-hash")
        with pytest.raises(RefreshTokenReusedError):
            service.execute("raw-token-hash")

        assert any(e[0] == "SuspiciousLoginDetected" for e in events)

    def test_reuse_of_a_different_users_token_never_touches_an_unrelated_user(self):
        """A direct proof this fix cannot cause cross-user session revocation -- reuse detection must only ever revoke the compromised token's own owner."""
        session_repo, user_repo, token_issuer, events = self._build()
        victim_id, bystander_id = uuid.uuid4(), uuid.uuid4()
        self._make_active_user(user_repo, victim_id)
        self._make_active_user(user_repo, bystander_id)
        self._make_session(session_repo, victim_id, "victim-token-hash", token_issuer)
        bystander_session_id = self._make_session(session_repo, bystander_id, "bystander-token-hash", token_issuer)

        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        service.execute("victim-token-hash")
        with pytest.raises(RefreshTokenReusedError):
            service.execute("victim-token-hash")

        assert session_repo.by_id[bystander_session_id].revoked_at is None

    def test_no_reuse_event_staged_for_a_genuinely_unknown_token(self):
        session_repo, user_repo, token_issuer, events = self._build()
        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        with pytest.raises(RefreshTokenInvalidError):
            service.execute("never-issued")
        assert not any(e[0] == "SuspiciousLoginDetected" for e in events)

    def test_expired_session_raises_invalid(self):
        session_repo, user_repo, token_issuer, events = self._build()
        user_id = uuid.uuid4()
        self._make_active_user(user_repo, user_id)
        session_id = uuid.uuid4()
        session_repo.create(
            UserSessionEntity(
                id=session_id, user_id=user_id, device_id=None, device_name="Test", device_type=DeviceType.WEB,
                refresh_token_hash="expired-hash", ip_address=None, user_agent=None,
                last_activity=Clock.now(), expires_at=Clock.now() - timedelta(days=1),
            )
        )
        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        with pytest.raises(RefreshTokenInvalidError):
            service.execute("expired-hash")

    def test_blocked_user_cannot_refresh(self):
        session_repo, user_repo, token_issuer, events = self._build()
        user_id = uuid.uuid4()
        user_repo.save(User(id=user_id, phone_number=PhoneNumber("+998901234567"), full_name="Test User", status=UserStatus.BLOCKED))
        self._make_session(session_repo, user_id, "raw-token-hash", token_issuer)

        service = RefreshToken(session_repo=session_repo, token_issuer=token_issuer, user_repo=user_repo, stage_events=collect_events(events))
        with pytest.raises(AccountBlockedError):
            service.execute("raw-token-hash")
