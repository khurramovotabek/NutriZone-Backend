from __future__ import annotations

import ast

import pytest

import apps.pos.domain.exceptions as exceptions_module
import apps.pos.domain.services as services_module
from apps.pos.domain import exceptions as exc
from apps.pos.domain.validators import QuantityValidator
from common.exceptions import DomainException

pytestmark = pytest.mark.unit


def test_zero_domain_services_exist():
    """A direct, executable statement of this module's certified real state -- not just asserted in a docstring."""
    tree = ast.parse(open(services_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert class_names == [], f"Expected zero Domain Services, found: {class_names}"


class TestValidators:
    def test_quantity_validator(self):
        assert QuantityValidator(5).value == 5


@pytest.mark.parametrize("exception_cls", [exc.InvalidQuantity, exc.EmptySale, exc.InvalidSaleTransition, exc.SaleLineItemNotFound])
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_programmatically_verify_exactly_4_exceptions():
    tree = ast.parse(open(exceptions_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 4, f"Expected exactly 4 POS domain exceptions, found {len(class_names)}: {class_names}"
