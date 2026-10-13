from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser

pytestmark = pytest.mark.unit


class TestIsAuthenticatedIdentityUser:
    def test_allows_authenticated_identity_user(self):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
        assert IsAuthenticatedIdentityUser().has_permission(request, view=None) is True

    def test_denies_anonymous_user(self):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        assert IsAuthenticatedIdentityUser().has_permission(request, view=None) is False

    def test_denies_when_user_is_none(self):
        request = SimpleNamespace(user=None)
        assert IsAuthenticatedIdentityUser().has_permission(request, view=None) is False
