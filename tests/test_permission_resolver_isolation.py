"""
Phase 09.8: proves HasPermissionCode.resolver isolation.

This test class exists specifically to catch a regression of the
exact bug found and fixed this phase: a test file mutating
HasPermissionCode.resolver without restoring it, silently making an
unrelated test elsewhere pass (or fail) for the wrong reason.
"""
from __future__ import annotations

import pytest

from common.permissions import HasPermissionCode

pytestmark = pytest.mark.django_db


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class TestPermissionResolverIsolation:
    def test_a_sets_a_custom_resolver_and_it_does_not_leak(self, monkeypatch):
        """After this test completes, HasPermissionCode.resolver must return to whatever it was before -- proven by test_b below asserting the pre-mutation value, not by this test alone."""
        monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
        assert isinstance(HasPermissionCode.resolver, _AllowAllResolver)
        # monkeypatch reverts this automatically when the test ends -- no manual restore needed or performed here.

    def test_b_sees_the_resolver_from_before_test_a_ran(self):
        """
        Deliberately does NOT set up any resolver itself. If test_a's
        mutation had leaked (the exact bug this phase fixed in 5 real
        files), this test would observe _AllowAllResolver() here
        instead of the real, unmodified resolver -- which would
        silently make security tests permissive for the wrong reason.
        """
        assert not isinstance(HasPermissionCode.resolver, _AllowAllResolver)
