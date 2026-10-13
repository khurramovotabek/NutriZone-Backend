"""
Phase 15F: Telegram staff enrollment command tests.

Every scenario here was first verified live via real `manage.py`
invocations before being formalized, matching the discipline
established throughout Phase 15B-15E.
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command


def _run(*args, **kwargs):
    out = StringIO()
    call_command("telegram_staff", *args, stdout=out, **kwargs)
    return out.getvalue()


def _run_list(*args, **kwargs):
    out = StringIO()
    call_command("telegram_staff_list", *args, stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
class TestEnrollment:
    def test_enroll_with_yes_flag_creates_active_staff_member(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        output = _run("900200100", name="Test Manager", yes=True)
        assert "Enrolled" in output

        member = TelegramStaffMember.objects.get(telegram_user_id=900200100)
        assert member.is_active is True
        assert member.full_name == "Test Manager"

    def test_enroll_without_confirmation_prompts_and_respects_decline(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        with patch("builtins.input", return_value="n"):
            output = _run("900200101", name="Declined")
        assert "Cancelled" in output
        assert not TelegramStaffMember.objects.filter(telegram_user_id=900200101).exists()

    def test_enroll_without_confirmation_respects_yes_answer(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        with patch("builtins.input", return_value="y"):
            _run("900200102", name="Confirmed")
        assert TelegramStaffMember.objects.get(telegram_user_id=900200102).is_active is True

    def test_enrolling_already_active_member_is_a_safe_noop(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        _run("900200103", name="Already Active", yes=True)
        output = _run("900200103", name="Already Active", yes=True)
        assert "already an active staff member" in output
        assert TelegramStaffMember.objects.filter(telegram_user_id=900200103).count() == 1

    def test_reenrolling_a_revoked_member_reactivates_without_duplicate_row(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        _run("900200104", name="Reactivate Me", yes=True)
        _run("900200104", revoke=True, yes=True)
        _run("900200104", name="Reactivate Me", yes=True)

        assert TelegramStaffMember.objects.filter(telegram_user_id=900200104).count() == 1
        assert TelegramStaffMember.objects.get(telegram_user_id=900200104).is_active is True


@pytest.mark.django_db
class TestRevocation:
    def test_revoke_deactivates_existing_member(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        _run("900200200", name="To Revoke", yes=True)
        output = _run("900200200", revoke=True, yes=True)
        assert "Revoked" in output
        assert TelegramStaffMember.objects.get(telegram_user_id=900200200).is_active is False

    def test_revoke_nonexistent_member_raises_command_error(self):
        with pytest.raises(CommandError):
            _run("900299999", revoke=True, yes=True)

    def test_revoke_already_revoked_member_is_a_safe_noop(self):
        _run("900200201", name="Double Revoke", yes=True)
        _run("900200201", revoke=True, yes=True)
        output = _run("900200201", revoke=True, yes=True)
        assert "already inactive" in output


@pytest.mark.django_db
class TestListing:
    def test_list_shows_only_active_by_default(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        TelegramStaffMember.objects.create(telegram_user_id=900200300, full_name="Active One", is_active=True)
        TelegramStaffMember.objects.create(telegram_user_id=900200301, full_name="Revoked One", is_active=False)

        output = _run_list()
        assert "900200300" in output
        assert "900200301" not in output

    def test_list_all_shows_revoked_too(self):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        TelegramStaffMember.objects.create(telegram_user_id=900200302, full_name="Active Two", is_active=True)
        TelegramStaffMember.objects.create(telegram_user_id=900200303, full_name="Revoked Two", is_active=False)

        output = _run_list(all=True)
        assert "900200302" in output
        assert "900200303" in output

    def test_list_empty_shows_clear_message(self):
        output = _run_list()
        assert "No staff members found." in output


@pytest.mark.django_db
class TestEnrollmentIntegration:
    def test_enrolled_staff_member_can_actually_confirm_orders(self, settings):
        """End-to-end proof this command genuinely closes Phase 15E's own disclosed gap: an operator-enrolled staff member can perform the real, security-critical manager action."""
        import json
        import uuid
        from decimal import Decimal

        from django.test import Client

        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret-only-not-real"

        from apps.products.infrastructure import models as products_orm
        from apps.pricing.infrastructure import models as pricing_orm
        from apps.identity.infrastructure import models as identity_orm
        from apps.ordering.infrastructure import models as ordering_orm

        category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein", slug=f"protein-{uuid.uuid4().hex[:8]}")
        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Enroll Integration", slug=f"enroll-int-{uuid.uuid4().hex[:8]}")
        variant = products_orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)
        price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
        pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=Decimal("45000.00"))

        telegram_id = 900200400
        staff_id = 900200401
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number="+998935550001", full_name="Enroll Integration Customer", status="active", telegram_user_id=telegram_id)

        client = Client()
        secret = "test-webhook-secret-only-not-real"

        def post(payload):
            return client.post("/api/v1/telegram/webhook", data=json.dumps(payload), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)

        def cb(tid, data):
            return post({"callback_query": {"id": "cbq", "from": {"id": tid}, "message": {"chat": {"id": tid}, "message_id": "1"}, "data": data}})

        _run(str(staff_id), name="Real Enrolled Manager", yes=True)

        post({"message": {"message_id": 1, "from": {"id": telegram_id}, "chat": {"id": telegram_id}, "contact": {"phone_number": "998935550001", "user_id": telegram_id}}})
        cb(telegram_id, f"cart:add:{variant.id}")
        cb(telegram_id, "checkout:start")
        post({"message": {"chat": {"id": telegram_id}, "from": {"id": telegram_id}, "location": {"latitude": 41.3111, "longitude": 69.2797}}})
        cb(telegram_id, "checkout:confirm")

        user = identity_orm.User.objects.get(telegram_user_id=telegram_id)
        order = ordering_orm.OrderModel.objects.get(customer_id=user.id)

        cb(staff_id, f"manager:confirm:{order.id}")
        order.refresh_from_db()
        assert order.status == "confirmed"
