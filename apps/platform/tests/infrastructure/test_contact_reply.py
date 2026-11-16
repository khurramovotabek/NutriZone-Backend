"""Answering a contact message from the dashboard: kept on the message, delivered to the customer's inbox when the email has an account."""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.notifications.infrastructure.models import NotificationModel
from apps.platform.infrastructure.models import ContactMessage

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]


@pytest.fixture
def staff_client():
    user = get_user_model().objects.create(username=f"nz_cm_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True, first_name="Ali")
    client = Client()
    client.force_login(user)
    return client


def _post(client, msg, reply, note=""):
    return client.post(f"/django-admin/platform/contactmessage/{msg.pk}/change/", {"status": "read", "nz_reply": reply, "internal_note": note, "_continue": "1"})


def test_reply_reaches_the_customer_inbox_when_the_email_has_an_account(staff_client):
    customer = identity_orm.User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name="Mijoz", status="active", email="Mijoz@Example.com")
    msg = ContactMessage.objects.create(name="Mijoz", email="mijoz@example.com", subject="Protein", message="Bormi?")
    resp = _post(staff_client, msg, "Ha, omborda bor.", note="qayta qo'ng'iroq")
    assert resp.status_code == 302
    msg.refresh_from_db()
    assert msg.status == "replied" and msg.reply_text == "Ha, omborda bor." and msg.reply_channel == "inbox"
    assert msg.internal_note == "qayta qo'ng'iroq" and msg.replied_at and msg.replied_by
    assert NotificationModel.objects.filter(recipient_id=customer.id, kind="contact_reply").exists()


def test_reply_without_an_account_is_kept_for_an_email_answer(staff_client):
    msg = ContactMessage.objects.create(name="Guest", email="guest@example.com", subject="", message="Salom")
    _post(staff_client, msg, "Javob")
    msg.refresh_from_db()
    assert msg.status == "replied" and msg.reply_channel == "email"
    assert not NotificationModel.objects.filter(kind="contact_reply").exists()


def test_saving_without_a_reply_only_changes_status_and_note(staff_client):
    msg = ContactMessage.objects.create(name="G", email="g@example.com", message="x")
    _post(staff_client, msg, "", note="izoh")
    msg.refresh_from_db()
    assert msg.status == "read" and msg.reply_text == "" and msg.internal_note == "izoh"
