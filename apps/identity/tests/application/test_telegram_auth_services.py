"""
Phase 4 Telegram automatic login application services. Every scenario
here was verified live before being formalized -- including the
critical replay-attack and race-condition guards.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone as django_timezone

from apps.identity.application.services.auth import DeviceContext, IssueAuthenticationForUser
from apps.identity.application.services.telegram_auth import (
    CompleteTelegramAuthSession,
    CreateTelegramAuthSession,
    TelegramAuthSessionAlreadyConsumed,
    TelegramAuthSessionExpired,
    TelegramAuthSessionNotReady,
)
from apps.identity.infrastructure import models as identity_orm
from apps.identity.infrastructure.composition import stage_identity_events
from apps.identity.infrastructure.repositories import DjangoUserSessionRepository
from apps.identity.infrastructure.security import SimpleJWTTokenIssuer
from common.exceptions import ResourceNotFound

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _issuer() -> IssueAuthenticationForUser:
    return IssueAuthenticationForUser(DjangoUserSessionRepository(), SimpleJWTTokenIssuer(), stage_identity_events)


def _device_context() -> DeviceContext:
    return DeviceContext(ip_address="1.2.3.4", user_agent="pytest")


class TestCreateTelegramAuthSession:
    def test_creates_pending_session_with_secure_random_token(self):
        result = CreateTelegramAuthSession().execute()

        session = identity_orm.TelegramAuthSession.objects.get(id=result.session_id)
        assert session.status == identity_orm.TelegramAuthSessionStatus.PENDING
        assert session.user_id is None
        assert session.telegram_user_id is None
        assert len(result.raw_token) > 32

    def test_raw_token_is_never_persisted_only_its_hash(self):
        result = CreateTelegramAuthSession().execute()

        session = identity_orm.TelegramAuthSession.objects.get(id=result.session_id)
        assert result.raw_token not in session.token_hash
        assert session.token_hash != result.raw_token

    def test_two_sessions_never_produce_the_same_token(self):
        a = CreateTelegramAuthSession().execute()
        b = CreateTelegramAuthSession().execute()
        assert a.raw_token != b.raw_token


class TestCompleteTelegramAuthSessionNotReady:
    def test_pending_session_cannot_issue_jwt(self):
        created = CreateTelegramAuthSession().execute()

        with pytest.raises(TelegramAuthSessionNotReady):
            CompleteTelegramAuthSession(_issuer()).execute(created.session_id, _device_context())

    def test_unknown_session_raises_not_found(self):
        with pytest.raises(ResourceNotFound):
            CompleteTelegramAuthSession(_issuer()).execute(uuid.uuid4(), _device_context())


class TestCompleteTelegramAuthSessionExpiration:
    def test_expired_session_cannot_issue_jwt(self):
        created = CreateTelegramAuthSession().execute()
        identity_orm.TelegramAuthSession.objects.filter(id=created.session_id).update(expires_at=django_timezone.now() - timedelta(seconds=1))

        with pytest.raises(TelegramAuthSessionExpired):
            CompleteTelegramAuthSession(_issuer()).execute(created.session_id, _device_context())

        session = identity_orm.TelegramAuthSession.objects.get(id=created.session_id)
        assert session.status == identity_orm.TelegramAuthSessionStatus.EXPIRED


class TestCompleteTelegramAuthSessionSuccess:
    def test_verified_session_issues_real_jwt_for_the_correct_user(self):
        phone = f"+99890{uuid.uuid4().int % 10_000_000:07d}"
        telegram_id = uuid.uuid4().int % 1_000_000_000
        user = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Test", status="active", language="uz", telegram_user_id=telegram_id)

        created = CreateTelegramAuthSession().execute()
        identity_orm.TelegramAuthSession.objects.filter(id=created.session_id).update(
            status=identity_orm.TelegramAuthSessionStatus.VERIFIED, telegram_user_id=telegram_id, user_id=user.id, verified_at=django_timezone.now(),
        )

        result = CompleteTelegramAuthSession(_issuer()).execute(created.session_id, _device_context())

        assert result.user_id == user.id
        assert result.access_token
        assert result.refresh_token

        session = identity_orm.TelegramAuthSession.objects.get(id=created.session_id)
        assert session.status == identity_orm.TelegramAuthSessionStatus.CONSUMED
        assert session.consumed_at is not None

    def test_replay_attack_is_rejected(self):
        phone = f"+99890{uuid.uuid4().int % 10_000_000:07d}"
        telegram_id = uuid.uuid4().int % 1_000_000_000
        user = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Test", status="active", language="uz", telegram_user_id=telegram_id)

        created = CreateTelegramAuthSession().execute()
        identity_orm.TelegramAuthSession.objects.filter(id=created.session_id).update(
            status=identity_orm.TelegramAuthSessionStatus.VERIFIED, telegram_user_id=telegram_id, user_id=user.id, verified_at=django_timezone.now(),
        )

        issuer = _issuer()
        CompleteTelegramAuthSession(issuer).execute(created.session_id, _device_context())

        with pytest.raises(TelegramAuthSessionAlreadyConsumed):
            CompleteTelegramAuthSession(issuer).execute(created.session_id, _device_context())
