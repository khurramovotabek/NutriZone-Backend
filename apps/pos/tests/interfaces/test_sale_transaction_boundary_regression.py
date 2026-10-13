"""
Real, live-verified bug uchun doimiy regressiya testi.

Muammo: apps/pos/application/services/sale.py'dagi barcha 5 ta metod
(OpenSale/AddLineItem/RemoveLineItem/CompleteSale/VoidSale)
`repository.save()` va `stage_events()`ni transaction.atomic() blokisiz
chaqirar edi. Modulning o'z sarlavhasi "repository.save() o'zi allaqachon
atomic, shuning uchun qo'shimcha atomic() shart emas" deb da'vo qilar
edi -- bu noto'g'ri: save()'ning ICHKI atomic blokidan chiqqandan
keyin stage_events() chaqiriladi, o'sha payt hech qanday ochiq atomic
blok yo'q, va stage_event()'ning o'zi (core.outbox) aktiv atomic blok
talab qiladi (MIC §7).

Mavjud test_sale_services.py FakeSaleRepository/collect_events (mock)
ishlatgani uchun bu real assertion'ni hech qachon sinamagan -- shuning
uchun to'liq backend regressiya (4818/4818) bu bugni hech qachon
ushlamagan edi. Bu test mock ishlatmaydi -- real composition
funksiyalari, real DjangoSaleRepository, real core.outbox.stage_event().
"""
from __future__ import annotations

import uuid

import pytest

from apps.pos.infrastructure import composition

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestSaleLifecycleRealTransactionBoundary:
    def test_open_sale_commits_without_atomic_error(self):
        branch_id, cashier_id = uuid.uuid4(), uuid.uuid4()
        sale = composition.build_open_sale(cashier_id).execute(branch_id=branch_id, cashier_id=cashier_id)
        assert sale.branch_id == branch_id

    def test_add_line_item_commits_without_atomic_error(self):
        from decimal import Decimal

        cashier_id = uuid.uuid4()
        sale = composition.build_open_sale(cashier_id).execute(branch_id=uuid.uuid4(), cashier_id=cashier_id)
        updated = composition.build_add_line_item(cashier_id).execute(
            sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("10000"), unit_price_currency="UZS",
        )
        assert len(updated.line_items) == 1

    def test_complete_sale_commits_without_atomic_error(self):
        from decimal import Decimal

        cashier_id = uuid.uuid4()
        sale = composition.build_open_sale(cashier_id).execute(branch_id=uuid.uuid4(), cashier_id=cashier_id)
        sale = composition.build_add_line_item(cashier_id).execute(
            sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("10000"), unit_price_currency="UZS",
        )
        completed = composition.build_complete_sale(cashier_id).execute(sale.id)
        assert completed.status.value == "completed"

    def test_remove_line_item_commits_without_atomic_error(self):
        from decimal import Decimal

        cashier_id = uuid.uuid4()
        sale = composition.build_open_sale(cashier_id).execute(branch_id=uuid.uuid4(), cashier_id=cashier_id)
        sale = composition.build_add_line_item(cashier_id).execute(
            sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("10000"), unit_price_currency="UZS",
        )
        line_item_id = next(iter(sale.line_items))
        updated = composition.build_remove_line_item(cashier_id).execute(sale_id=sale.id, line_item_id=line_item_id)
        assert len(updated.line_items) == 0

    def test_void_sale_commits_without_atomic_error(self):
        cashier_id = uuid.uuid4()
        sale = composition.build_open_sale(cashier_id).execute(branch_id=uuid.uuid4(), cashier_id=cashier_id)
        voided = composition.build_void_sale(cashier_id).execute(sale.id)
        assert voided.status.value == "voided"
