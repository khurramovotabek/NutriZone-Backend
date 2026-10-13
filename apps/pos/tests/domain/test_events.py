from __future__ import annotations

import ast
import dataclasses
import uuid
from decimal import Decimal

import pytest

import apps.pos.domain.events as events_module
import apps.pos.domain.exceptions as exceptions_module
from apps.pos.domain.events import SaleCompleted, SaleLineItemAdded, SaleLineItemRemoved, SaleOpened, SaleVoided

pytestmark = pytest.mark.unit


def test_sale_opened_payload():
    sale_id, branch_id, cashier_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = SaleOpened(sale_id=sale_id, branch_id=branch_id, cashier_id=cashier_id).to_payload()
    assert payload["sale_id"] == str(sale_id)
    assert payload["branch_id"] == str(branch_id)


def test_sale_line_item_added_payload():
    sale_id, line_item_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = SaleLineItemAdded(sale_id=sale_id, line_item_id=line_item_id, product_id=product_id, quantity=3, unit_price=Decimal("5.00")).to_payload()
    assert payload["quantity"] == 3
    assert payload["unit_price"] == "5.00"


def test_sale_line_item_removed_payload():
    sale_id, line_item_id = uuid.uuid4(), uuid.uuid4()
    assert SaleLineItemRemoved(sale_id=sale_id, line_item_id=line_item_id).to_payload() == {"sale_id": str(sale_id), "line_item_id": str(line_item_id)}


def test_sale_completed_payload():
    sale_id = uuid.uuid4()
    payload = SaleCompleted(sale_id=sale_id, total_amount=Decimal("42.50"), currency="UZS").to_payload()
    assert payload["total_amount"] == "42.50"
    assert payload["currency"] == "UZS"


def test_sale_voided_payload():
    sale_id = uuid.uuid4()
    assert SaleVoided(sale_id=sale_id).to_payload() == {"sale_id": str(sale_id)}


def test_every_event_is_a_frozen_dataclass():
    event_classes = [obj for name, obj in vars(events_module).items() if isinstance(obj, type) and dataclasses.is_dataclass(obj)]
    for cls in event_classes:
        assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} is not frozen"


def test_events_are_immutable():
    event = SaleVoided(sale_id=uuid.uuid4())
    with pytest.raises(Exception):
        event.sale_id = uuid.uuid4()  # type: ignore[misc]


def test_programmatically_verify_exactly_8_events():
    """Count updated to 7 after the premium checkout redesign added SaleCustomerSet, then to 8 with SaleRefunded (Sale.refund() -- the whole-sale return of a completed sale)."""
    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 8, f"Expected exactly 8 POS domain events, found {len(class_names)}: {class_names}"


def test_zero_collisions_between_events_and_exceptions():
    event_names = set(n.name for n in ast.parse(open(events_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    exception_names = set(n.name for n in ast.parse(open(exceptions_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    collisions = event_names & exception_names
    assert not collisions, f"Naming collisions found between events and exceptions: {collisions}"
