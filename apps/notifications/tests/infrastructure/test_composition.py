from __future__ import annotations

import inspect

import pytest

from apps.notifications.infrastructure import composition

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestComposition:
    def test_composition_builds_a_real_repository(self):
        repo = composition.build_notification_repository()
        assert repo is not None

    def test_all_8_factories_are_callable(self):
        """Verifies every build_* factory in composition.py actually executes without error. Count re-verified fresh at 8 (was 7 before Phase 15F's build_orders_telegram_gateway, the separate Orders Bot's own gateway builder)."""
        factories = [name for name, obj in vars(composition).items() if name.startswith("build_") and inspect.isfunction(obj)]
        assert len(factories) == 8
        for name in factories:
            factory = getattr(composition, name)
            factory()

    def test_notification_service_factories_now_exist(self):
        """Phase 02G closed the module's own previously-disclosed 'zero Application Services' state -- this test replaces the old zero-services canary, now documenting the real, current state instead of asserting an absence that is no longer true."""
        factories = [name for name, obj in vars(composition).items() if name.startswith("build_") and inspect.isfunction(obj)]
        assert "build_create_notification" in factories
        assert "build_notification_service_context" in factories
