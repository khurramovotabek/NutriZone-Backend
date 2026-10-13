from __future__ import annotations

import inspect

import pytest

from apps.chat.infrastructure import composition

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestComposition:
    def test_composition_builds_a_real_repository(self):
        repo = composition.build_conversation_repository()
        assert repo is not None

    def test_all_19_factories_are_callable(self):
        """Verifies every build_* factory in composition.py actually executes without error. Fresh count is 19 (previous 18 + build_mark_conversation_read, read receipts)."""
        factories = [name for name, obj in vars(composition).items() if name.startswith("build_") and inspect.isfunction(obj)]
        assert len(factories) == 19
        for name in factories:
            factory = getattr(composition, name)
            factory()
