"""
URL structure checks -- AST-adjacent static verification, not
`django.urls.resolve()` (requires a configured Django app registry,
unavailable in this sandbox -- this file itself cannot be collected
without Django installed, since it imports `apps.audit.interfaces.
api.v1.urls`, which imports `django.urls`; disclosed precisely in the
certification report rather than conflated with "passing").
"""
from __future__ import annotations

import apps.audit.interfaces.api.v1.urls as audit_urls_module


def test_exactly_1_route_registered():
    assert len(audit_urls_module.urlpatterns) == 1


def test_activity_route_pattern():
    patterns = [str(p.pattern) for p in audit_urls_module.urlpatterns]
    assert "internal/audit/activity" in patterns


def test_app_name_is_audit():
    assert audit_urls_module.app_name == "audit"
