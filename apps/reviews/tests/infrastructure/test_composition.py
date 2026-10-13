from __future__ import annotations

import inspect

import pytest

from apps.reviews.infrastructure import composition

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestComposition:
    def test_composition_builds_a_real_repository(self):
        repo = composition.build_review_repository()
        assert repo is not None

    def test_all_15_factories_are_callable(self):
        """Verifies every build_* factory in composition.py actually executes without error -- not just that it's syntactically defined. Count is 15 (1 repository + 3 selectors + 2 gateways + 9 Application Service factories, added once Reviews' Application Service layer was built and wired)."""
        factories = [name for name, obj in vars(composition).items() if name.startswith("build_") and inspect.isfunction(obj)]
        assert len(factories) == 15
        for name in factories:
            factory = getattr(composition, name)
            factory()  # every factory accepts zero required args
