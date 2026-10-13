"""
Real, live-verified regression test for Phase C1/C2: OrderAdmin's
financial summary table and status history badges. Every scenario
here was proven live via a real admin request before being
formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.ordering.infrastructure import models as o_models

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestOrderFinancialSummary:
    def test_financial_summary_computes_correct_total_from_real_lines(self, staff_client):
        order = o_models.OrderModel.objects.create(id=uuid.uuid4(), order_number=f"NZ-{uuid.uuid4().hex[:8]}", status="processing", currency="UZS")
        o_models.OrderLineItemModel.objects.create(
            id=uuid.uuid4(), order=order, product_variant_id=uuid.uuid4(), quantity=2,
            unit_price_amount=780000, discount_amount=50000, tax_amount=0, status="active",
        )

        response = staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "nz-financial-summary" in body
        assert "1 560 000" in body  # subtotal: 2 x 780000 (grouped thousands in the order workspace)
        assert "−50 000" in body  # discount
        assert "1 510 000" in body  # total: 1560000 - 50000


class TestOrderStatusHistoryBadges:
    def test_status_history_uses_real_semantic_badges(self, staff_client):
        order = o_models.OrderModel.objects.create(id=uuid.uuid4(), order_number=f"NZ-{uuid.uuid4().hex[:8]}", status="completed", currency="UZS")
        o_models.OrderStatusHistoryEntryModel.objects.create(id=uuid.uuid4(), order=order, from_status=None, to_status="draft", changed_at=timezone.now())
        o_models.OrderStatusHistoryEntryModel.objects.create(id=uuid.uuid4(), order=order, from_status="processing", to_status="completed", changed_at=timezone.now())

        response = staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "nz-badge-success" in body

    def test_null_from_status_does_not_crash(self, staff_client):
        order = o_models.OrderModel.objects.create(id=uuid.uuid4(), order_number=f"NZ-{uuid.uuid4().hex[:8]}", status="draft", currency="UZS")
        o_models.OrderStatusHistoryEntryModel.objects.create(id=uuid.uuid4(), order=order, from_status=None, to_status="draft", changed_at=timezone.now())

        response = staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code == 200
