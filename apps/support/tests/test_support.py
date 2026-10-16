import json
from unittest.mock import patch

import pytest

from apps.support.infrastructure import services
from apps.support.infrastructure.models import SupportCase, SupportProfile

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("raw,phone", [("90 123 45 67", "+998901234567"), ("8 90 123 45 67", "+998901234567"), ("+998 (90) 123-45-67", "+998901234567")])
def test_normalize_phone(raw, phone):
    assert services.normalize_phone(raw) == phone


def test_bad_phone_rejected():
    with pytest.raises(services.SupportError):
        services.normalize_phone("12345")


def test_case_creates_unknown_customer_and_logs_notes():
    case = services.create_case(phone="90 111 22 33", summary="Gold Standard narxini so'radi", staff="Operator")
    assert case.number == "SUP-00001" and case.display_name == "Noma'lum"
    assert case.customer.phone_number == "+998901112233" and SupportProfile.objects.filter(user=case.customer, confirmed_at__isnull=True).exists()
    assert [n.kind for n in case.notes.all()] == ["call", "status"]
    second = services.create_case(phone="+998901112233", name="Aziz", summary="Qayta qo'ng'iroq qildi")
    assert second.customer_id == case.customer_id and second.number == "SUP-00002"
    case.customer.refresh_from_db()
    assert case.customer.full_name == "Aziz"  # an empty name is filled from the later call


def test_move_records_history_and_closes():
    case = services.create_case(phone="901112233", summary="x")
    services.move(case, "callback", "Op")
    case.refresh_from_db()
    assert case.next_contact_at is not None and case.closed_at is None
    services.move(case, "ordered", "Op", "ORD-000123")
    case.refresh_from_db()
    assert case.closed_at is not None and "Buyurtma berdi: ORD-000123" in case.notes.last().text


def test_board_endpoints(admin_client):
    r = admin_client.post("/django-admin/support/supportcase/board/create/", json.dumps({"phone": "93 555 66 77", "summary": "Kreatin haqida", "topic": "product"}), content_type="application/json")
    assert r.json()["ok"] is True
    case = SupportCase.objects.get()
    data = admin_client.get("/django-admin/support/supportcase/board/data.json").json()
    assert [c["number"] for c in next(col for col in data["columns"] if col["key"] == "new")["cards"]] == [case.number]
    assert admin_client.post("/django-admin/support/supportcase/board/move/", json.dumps({"id": str(case.id), "status": "thinking"}), content_type="application/json").json()["ok"]
    assert admin_client.get("/django-admin/support/supportcase/board/").status_code == 200
    assert admin_client.get("/django-admin/support/supportcase/").status_code == 200
    assert admin_client.get(f"/django-admin/support/supportcase/{case.pk}/change/").status_code == 200


def test_bot_asks_a_support_made_customer_to_confirm():
    from apps.telegram_bot.interfaces import support_confirm

    case = services.create_case(phone="90 777 88 99", summary="x")
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        assert support_confirm.ask(1001, case.customer, "uz", suggested_name="Jasur") is True
    keyboard = send.call_args[0][2]
    assert "Noma'lum" in send.call_args[0][1] and any(b["callback_data"] == "sup:use" for row in keyboard for b in row)
    with patch("apps.telegram_bot.interfaces.callback_router._send"):
        support_confirm.handle(case.customer, 1001, "use", "uz")
    case.customer.refresh_from_db()
    assert case.customer.full_name == "Jasur" and services.pending_confirmation(case.customer) is None
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        assert support_confirm.ask(1001, case.customer, "uz") is False  # nothing left to confirm


def test_a_soft_deleted_customer_is_restored_not_duplicated():
    case = services.create_case(phone="90 123 00 11", summary="x")
    from apps.identity.infrastructure.models import User

    User.all_objects.filter(pk=case.customer_id).update(is_deleted=True)
    again = services.create_case(phone="90 123 00 11", summary="y")
    assert again.customer_id == case.customer_id and User.objects.filter(pk=case.customer_id).exists()
