from __future__ import annotations

import pytest
from django.db import connection

from apps.pos.infrastructure.health import (
    check_composition_integrity,
    check_orphaned_sale_line_items,
    check_pos_cache,
    check_pos_outbox_backlog,
    check_sale_line_item_integrity,
    check_sale_repository,
)
from apps.pos.infrastructure.repositories import DjangoSaleRepository
from apps.pos.tests.factories import make_sale_with_line

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_sale_repository_healthy(self):
        ok, detail = check_sale_repository()
        assert ok is True

    def test_check_pos_outbox_backlog_reports_count(self):
        ok, detail = check_pos_outbox_backlog()
        assert ok is True
        assert "pending" in detail

    def test_check_orphaned_sale_line_items_healthy_by_default(self):
        ok, detail = check_orphaned_sale_line_items()
        assert ok is True

    def test_check_sale_line_item_integrity_healthy_by_default(self):
        ok, detail = check_sale_line_item_integrity()
        assert ok is True

    def test_check_sale_line_item_integrity_flags_seeded_negative_price(self):
        """Seeds a deliberately invalid row with a negative unit price (bypassing Money's own non-negative constructor invariant via raw SQL) and verifies the health check actually catches it."""
        sale = make_sale_with_line()
        DjangoSaleRepository().save(sale)
        line_item_id = next(iter(sale.line_items.keys()))
        with connection.cursor() as cursor:
            cursor.execute("UPDATE pos_sale_line_items SET unit_price_amount = -5.00 WHERE id = %s", [str(line_item_id)])
        ok, detail = check_sale_line_item_integrity()
        assert ok is False

    def test_check_composition_integrity_healthy(self):
        ok, detail = check_composition_integrity()
        assert ok is True

    def test_check_pos_cache_round_trips(self):
        ok, detail = check_pos_cache()
        assert ok is True
