"""
Phase 15B: Telegram webhook foundation tests.

Every scenario here was first verified live via a real HTTP request
through Django's test Client before being written as a formal test,
per this phase's own "verify, don't assume" discipline.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/telegram/webhook"
TEST_SECRET = "test-webhook-secret-only-not-real"


def _post(client, payload, secret=TEST_SECRET):
    headers = {}
    if secret is not None:
        headers["HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"] = secret
    return client.post(WEBHOOK_URL, data=json.dumps(payload), content_type="application/json", **headers)


class TestWebhookSecurity:
    def test_wrong_secret_rejected(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        r = _post(Client(), {}, secret="wrong-secret")
        assert r.status_code == 403

    def test_missing_secret_header_rejected(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        r = _post(Client(), {}, secret=None)
        assert r.status_code == 403

    def test_get_request_rejected(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        r = Client().get(WEBHOOK_URL)
        assert r.status_code == 405

    def test_malformed_json_body_does_not_crash(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        r = Client().post(WEBHOOK_URL, data="not-json{{{", content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=TEST_SECRET)
        assert r.status_code == 200

    def test_unconfigured_secret_rejects_everything(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = None
        r = _post(Client(), {}, secret="anything")
        assert r.status_code == 403


class TestStartCommand:
    def test_start_from_new_user_does_not_crash(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        update = {"message": {"message_id": 1, "from": {"id": 700100200, "first_name": "New"}, "chat": {"id": 700100200}, "text": "/start"}}
        r = _post(Client(), update)
        assert r.status_code == 200

    def test_start_from_existing_linked_user(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number="+998901234567", full_name="Existing", status="active", telegram_user_id=700100201)
        update = {"message": {"message_id": 1, "from": {"id": 700100201, "first_name": "Existing"}, "chat": {"id": 700100201}, "text": "/start"}}
        r = _post(Client(), update)
        assert r.status_code == 200


class TestContactRegistration:
    def test_new_customer_created_from_contact(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        update = {"message": {"message_id": 2, "from": {"id": 700100300, "first_name": "Contact", "last_name": "Test"}, "chat": {"id": 700100300}, "contact": {"phone_number": "998901234600", "user_id": 700100300}}}
        r = _post(Client(), update)
        assert r.status_code == 200

        user = identity_orm.User.objects.filter(telegram_user_id=700100300).first()
        assert user is not None
        assert user.phone_number == "+998901234600"
        assert user.full_name == "Contact Test"

    def test_existing_customer_by_phone_gets_linked_not_duplicated(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        existing = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number="+998901234601", full_name="Already Exists", status="active")
        update = {"message": {"message_id": 3, "from": {"id": 700100301}, "chat": {"id": 700100301}, "contact": {"phone_number": "998901234601", "user_id": 700100301}}}
        r = _post(Client(), update)
        assert r.status_code == 200

        assert identity_orm.User.objects.filter(phone_number="+998901234601").count() == 1
        existing.refresh_from_db()
        assert existing.telegram_user_id == 700100301

    def test_new_customer_gets_default_customer_role(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        update = {"message": {"message_id": 4, "from": {"id": 700100302}, "chat": {"id": 700100302}, "contact": {"phone_number": "998901234602", "user_id": 700100302}}}
        _post(Client(), update)

        user = identity_orm.User.objects.get(telegram_user_id=700100302)
        assert identity_orm.UserRole.objects.filter(user_id=user.id, role__code="customer").exists()


class TestContactOwnershipSecurity:
    def test_forged_contact_is_rejected(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        attacker_id = 700100400
        victim_phone = "998901234603"
        update = {"message": {"message_id": 5, "from": {"id": attacker_id}, "chat": {"id": attacker_id}, "contact": {"phone_number": victim_phone, "user_id": 999999999}}}
        r = _post(Client(), update)
        assert r.status_code == 200
        assert identity_orm.User.objects.filter(telegram_user_id=attacker_id).count() == 0
        assert identity_orm.User.objects.filter(phone_number=f"+{victim_phone}").count() == 0

    def test_reusing_telegram_id_for_different_phone_is_rejected(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        telegram_user_id = 700100401
        update1 = {"message": {"message_id": 6, "from": {"id": telegram_user_id}, "chat": {"id": telegram_user_id}, "contact": {"phone_number": "998901234604", "user_id": telegram_user_id}}}
        _post(Client(), update1)

        update2 = {"message": {"message_id": 7, "from": {"id": telegram_user_id}, "chat": {"id": telegram_user_id}, "contact": {"phone_number": "998901234605", "user_id": telegram_user_id}}}
        r = _post(Client(), update2)
        assert r.status_code == 200

        user = identity_orm.User.objects.get(telegram_user_id=telegram_user_id)
        assert user.phone_number == "+998901234604"
        assert not identity_orm.User.objects.filter(phone_number="+998901234605").exists()
