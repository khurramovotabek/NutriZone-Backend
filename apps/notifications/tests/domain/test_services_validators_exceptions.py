from __future__ import annotations

import ast

import pytest

import apps.notifications.domain.exceptions as exceptions_module
import apps.notifications.domain.services as services_module
from apps.notifications.domain import exceptions as exc
from apps.notifications.domain.validators import NotificationBodyValidator, NotificationTitleValidator
from common.exceptions import DomainException

pytestmark = pytest.mark.unit


def test_zero_domain_services_exist():
    """A direct, executable statement of this module's certified real state -- not just asserted in a docstring. Fails loudly if a Domain Service is ever added without this test being updated to match."""
    tree = ast.parse(open(services_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert class_names == [], f"Expected zero Domain Services, found: {class_names}"


class TestValidators:
    def test_notification_title_validator(self):
        assert NotificationTitleValidator("Shipped").value == "Shipped"

    def test_notification_body_validator(self):
        assert NotificationBodyValidator("On its way.").value == "On its way."


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.InvalidNotificationTransition, exc.NotificationAlreadyCancelled, exc.NotificationAlreadyDelivered,
        exc.DeliveryNotFound, exc.InvalidDeliveryTransition, exc.EmptyNotificationContent, exc.NotificationContentTooLong,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_programmatically_verify_exactly_7_exceptions():
    tree = ast.parse(open(exceptions_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 7, f"Expected exactly 7 Notifications domain exceptions, found {len(class_names)}: {class_names}"
