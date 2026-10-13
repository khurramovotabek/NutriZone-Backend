"""
Application-layer Port contract tests for POS.

**Unlike every module before Notifications/Loyalty/Analytics, this is
NOT a "0 Application Services" disclosure file** -- 6 real, certified
Application Services exist (Phase 3). Their behavior is tested in
`test_sale_services.py`; this file verifies only the `SaleRepository`
Port's own contract shape against its fake (and, by the same shape,
the real repository).
"""
from __future__ import annotations

import uuid

import pytest

from apps.pos.application.ports import SaleRepository
from apps.pos.tests.application.fakes import FakeSaleRepository
from apps.pos.tests.factories import make_sale

pytestmark = pytest.mark.unit


class TestFakeSaleRepositoryContract:
    def test_fake_satisfies_port_method_set(self):
        port_methods = {name for name in dir(SaleRepository) if not name.startswith("_")}
        fake_methods = {name for name in dir(FakeSaleRepository) if not name.startswith("_")}
        missing = port_methods - fake_methods
        assert not missing, f"FakeSaleRepository is missing Port methods: {missing}"

    def test_save_then_get_by_id_round_trips(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        assert repo.get_by_id(sale.id) is sale

    def test_get_by_id_missing_returns_none(self):
        repo = FakeSaleRepository()
        assert repo.get_by_id(uuid.uuid4()) is None
