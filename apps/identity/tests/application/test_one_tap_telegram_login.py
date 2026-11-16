"""One-tap website login from the bot: completing the bot's ready link signs in the tab that asked; Cancel kills both."""
from __future__ import annotations

import uuid

import pytest

from apps.identity.application.services import telegram_auth as ta
from apps.identity.infrastructure import models as orm

pytestmark = pytest.mark.django_db

S = orm.TelegramAuthSessionStatus


def _user(tg_id: int):
    return orm.User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name="Tap", status="active", telegram_user_id=tg_id)


def _request(tg_id: int | None = None):
    created = ta.CreateTelegramAuthSession().execute()
    if tg_id is not None:
        orm.TelegramAuthSession.objects.filter(id=created.session_id).update(telegram_user_id=tg_id)
    return created.session_id


def test_completing_the_ready_link_signs_in_the_asking_tab():
    user = _user(7001)
    req = _request(7001)
    ready = ta.CreateBotInitiatedAuthSession().execute(customer_id=user.id, telegram_user_id=7001)
    ta.pair_login_sessions(req, ready.session_id)

    assert ta.verify_paired_request(ready.session_id) is True
    row = orm.TelegramAuthSession.objects.get(id=req)
    assert row.status == S.VERIFIED and row.user_id == user.id
    assert ta.verify_paired_request(ready.session_id) is False  # one use only


def test_another_telegram_user_can_not_sign_in_someone_elses_tab():
    user = _user(7002)
    req = _request(9999)  # the request was opened by a different Telegram account
    ready = ta.CreateBotInitiatedAuthSession().execute(customer_id=user.id, telegram_user_id=7002)
    ta.pair_login_sessions(req, ready.session_id)

    assert ta.verify_paired_request(ready.session_id) is False
    assert orm.TelegramAuthSession.objects.get(id=req).status == S.PENDING


def test_cancel_kills_the_ready_link():
    user = _user(7003)
    req = _request(7003)
    ready = ta.CreateBotInitiatedAuthSession().execute(customer_id=user.id, telegram_user_id=7003)
    ta.pair_login_sessions(req, ready.session_id)

    ta.cancel_paired_bot_session(req)
    assert orm.TelegramAuthSession.objects.get(id=ready.session_id).status == S.FAILED
    assert ta.verify_paired_request(ready.session_id) is False


def test_device_label_is_remembered_for_the_prompt():
    req = _request()
    ta.remember_login_request(req, "Chrome · Android")
    assert ta.login_request_device(req) == "Chrome · Android"
