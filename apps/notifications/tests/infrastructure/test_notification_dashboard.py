"""
Dashboard → Bildirishnomalar: the history list (which crashed with a 500 before -- format_html without arguments
on Django 6), the broadcast history and card, and the composer pre-filled from an earlier broadcast.
"""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from apps.identity.infrastructure.models import User
from apps.notifications.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def _customer():
    return User.objects.create(phone_number=f"+99897{uuid.uuid4().int % 10_000_000:07d}", full_name="Sardor Aliyev", status="active")


def _broadcast(**kw):
    defaults = {"title": "Yangi filial ochildi", "body": "Chilonzorda kutamiz", "i18n": {"uz": {"title": "Yangi filial ochildi", "body": "Chilonzorda kutamiz"},
                                                                                       "ru": {"title": "Открыли филиал", "body": "Ждём в Чиланзаре"}},
                "link": "/stores", "audience": "all", "recipients": 1, "status": "sent", "send_telegram": True, "created_by": "Admin", "finished_at": timezone.now()}
    return orm.NotificationBroadcast.objects.create(**{**defaults, **kw})


def _notification(user, broadcast=None, telegram_status="sent", **kw):
    n = orm.NotificationModel.objects.create(recipient_id=user.id, notification_type="in_app", title="Buyurtma yo'lda", body="ORD-1 yo'lda", kind="order_shipped",
                                             broadcast=broadcast, **kw)
    orm.NotificationDeliveryModel.objects.create(notification=n, channel="telegram", status=telegram_status, attempted_at=timezone.now(),
                                                 failure_reason="blocked" if telegram_status == "failed" else None)
    return n


class TestHistory:
    def test_list_renders_with_telegram_deliveries(self, admin_client):
        u = _customer()
        _notification(u, telegram_status="sent")
        _notification(u, telegram_status="failed")
        html = admin_client.get("/django-admin/notifications/notificationmodel/").content.decode()
        assert "Sardor Aliyev" in html and "Buyurtma yo&#x27;lda" in html and "Yuborildi" in html and "Xato" in html

    @pytest.mark.parametrize("query", ["?kind=orders", "?state=unread", "?tg=failed", "?prio=high"])
    def test_filters(self, admin_client, query):
        _notification(_customer())
        assert admin_client.get(f"/django-admin/notifications/notificationmodel/{query}").status_code == 200

    def test_notification_card(self, admin_client):
        n = _notification(_customer())
        assert admin_client.get(f"/django-admin/notifications/notificationmodel/{n.pk}/change/").status_code == 200


class TestBroadcasts:
    def test_list_and_card(self, admin_client):
        b = _broadcast()
        _notification(_customer(), broadcast=b, status="read", read_at=timezone.now())
        assert "Yangi filial ochildi" in admin_client.get("/django-admin/notifications/notificationbroadcast/").content.decode()
        html = admin_client.get(f"/django-admin/notifications/notificationbroadcast/{b.pk}/change/").content.decode()
        assert "Открыли филиал" in html and "Sardor Aliyev" in html and f"?from={b.pk}" in html

    def test_composer_copies_an_earlier_broadcast(self, admin_client):
        b = _broadcast(audience="telegram")
        html = admin_client.get(f"/django-admin/notifications/send/?from={b.pk}").content.decode()
        assert 'value="Yangi filial ochildi"' in html and "Ждём в Чиланзаре" in html and 'value="telegram" checked' in html

    def test_composer_ignores_a_bad_source(self, admin_client):
        assert admin_client.get("/django-admin/notifications/send/?from=nope").status_code == 200


def test_no_argument_less_format_html_anywhere():
    """Django 6 raises TypeError for format_html() without arguments -- it took down two dashboard pages. Use mark_safe for static markup."""
    import ast
    import pathlib

    from django.conf import settings

    offenders = []
    for f in pathlib.Path(settings.BASE_DIR, "apps").rglob("*.py"):
        if "/tests/" in str(f) or "/migrations/" in str(f):
            continue
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "format_html" and len(node.args) == 1 and not node.keywords:
                offenders.append(f"{f}:{node.lineno}")
    assert offenders == []
