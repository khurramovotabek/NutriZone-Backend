"""
Phase 08.10: NutriZone Admin POS / Devices / Telegram tests.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def non_staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_customer_{uuid.uuid4().hex[:8]}", is_staff=False)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


def _make_sale(quantity=2, unit_price=Decimal("25000")):
    from apps.pos.infrastructure import models as orm

    sale = orm.SaleModel.objects.create(branch_id=uuid.uuid4(), cashier_id=uuid.uuid4(), status="completed")
    orm.SaleLineItemModel.objects.create(sale=sale, product_id=uuid.uuid4(), quantity=quantity, unit_price_amount=unit_price, unit_price_currency="UZS")
    return sale


class TestPOSWorkspace:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/pos/salemodel/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/pos/salemodel/")
        assert response.status_code in (302, 403)

    def test_list_shows_real_sale(self, staff_client):
        sale = _make_sale()
        response = staff_client.get("/django-admin/pos/salemodel/")
        assert response.status_code == 200
        assert str(sale.id) in response.content.decode()

    def test_no_n_plus_1_on_sale_list(self, staff_client):
        """Regression test for the confirmed, fixed N+1 (line_item_count() called .count() despite an existing prefetch)."""
        for i in range(5):
            _make_sale()

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/pos/salemodel/")
        assert response.status_code == 200
        count_5 = len(ctx.captured_queries)

        for i in range(5, 10):
            _make_sale()

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/pos/salemodel/")
        assert response.status_code == 200
        count_10 = len(ctx.captured_queries)

        assert count_10 < count_5 + 3, f"Query count grew from {count_5} to {count_10} for 5 more sales -- possible N+1"


class TestPOSReceipt:
    """Phase 08.10: no Receipt model exists (confirmed by direct search) -- this reuses SaleModel's own real, already-persisted data with the exact same certified subtotal formula already used for Order (Phase 08.4)."""

    def test_anonymous_denied(self):
        sale_id = uuid.uuid4()
        response = Client().get(f"/django-admin/pos/receipt/{sale_id}/")
        assert response.status_code in (302, 403)

    def test_receipt_shows_real_total(self, staff_client):
        sale = _make_sale(quantity=3, unit_price=Decimal("10000"))
        response = staff_client.get(f"/django-admin/pos/receipt/{sale.id}/")
        assert response.status_code == 200
        assert "30000" in response.content.decode()  # 3 * 10000, proves real data, not a static shape

    def test_nonexistent_sale_returns_404(self, staff_client):
        response = staff_client.get(f"/django-admin/pos/receipt/{uuid.uuid4()}/")
        assert response.status_code == 404


class TestDevicesWorkspace:
    """Phase 08.10: closes a genuine gap -- Device had zero admin registration despite being a real model."""

    def test_anonymous_denied(self):
        response = Client().get("/django-admin/identity/device/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/identity/device/")
        assert response.status_code in (302, 403)

    def test_list_shows_real_device(self, staff_client):
        from apps.identity.infrastructure import models as orm

        orm.Device.objects.create(device_type="mobile", device_name="Visible Test Device")
        response = staff_client.get("/django-admin/identity/device/")
        assert response.status_code == 200
        assert "Visible Test Device" in response.content.decode()

    def test_push_token_never_appears_in_rendered_page(self, staff_client):
        """Critical secret-safety test -- push_token is a credential-like value, abusable if leaked."""
        from apps.identity.infrastructure import models as orm

        secret_token = f"SECRET-PUSH-{uuid.uuid4().hex}"
        device = orm.Device.objects.create(device_type="mobile", device_name="Secret Check", push_token=secret_token)

        response = staff_client.get(f"/django-admin/identity/device/{device.id}/change/")
        assert response.status_code == 200
        assert secret_token not in response.content.decode()

        response_list = staff_client.get("/django-admin/identity/device/")
        assert secret_token not in response_list.content.decode()


class TestTelegramStatus:
    """Phase 08.10: no database-backed 'Telegram Bot' model exists (confirmed by direct search) -- configuration presence only, no fabricated message/delivery statistics."""

    def test_anonymous_denied(self):
        response = Client().get("/django-admin/telegram/status/")
        assert response.status_code in (302, 403)

    def test_staff_can_view_status(self, staff_client):
        response = staff_client.get("/django-admin/telegram/status/")
        assert response.status_code == 200
        assert "Telegram botlar markazi" in response.content.decode()

    def test_shows_not_configured_when_token_absent(self, staff_client):
        """The test environment genuinely has no TELEGRAM_BOT_TOKEN set -- proves the status reflects real settings state, not a hardcoded claim."""
        response = staff_client.get("/django-admin/telegram/status/")
        assert "Sozlanmagan" in response.content.decode()

    def test_no_token_value_ever_rendered(self, staff_client):
        from django.test import override_settings

        with override_settings(TELEGRAM_BOT_TOKEN="123456:SUPER-SECRET-BOT-TOKEN-VALUE"):
            response = staff_client.get("/django-admin/telegram/status/")
        assert "123456:SUPER-SECRET-BOT-TOKEN-VALUE" not in response.content.decode()
        assert "Sozlangan" in response.content.decode()  # presence shown, value never rendered

    def test_no_fabricated_message_statistics(self, staff_client):
        """This phase's own explicit rule: do not fabricate message counts/delivery stats with no backing model."""
        response = staff_client.get("/django-admin/telegram/status/")
        content = response.content.decode()
        assert "messages sent" not in content.lower()
        assert "delivery rate" not in content.lower()


class TestCrossWorkspaceRegression:
    def test_dashboard_home_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "nz-dashboard" in response.content.decode()

    def test_control_center_audit_timeline_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/audit-timeline/")
        assert response.status_code == 200

    def test_reports_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/reports/")
        assert response.status_code == 200
