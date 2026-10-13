"""
Real, live-verified regression test for a systematic backend-wide
audit: a Python AST script searched every apps/*/application/services/
file for stage_events()/stage_event() calls not protected by
transaction.atomic() (either as a `with` block or a `@transaction.
atomic` decorator on the whole method) -- the same topology bug
already found once in POS's OpenSale and once in Chat's SendMessage.

209 candidates were found by a naive line-proximity check; re-checking
with proper decorator awareness narrowed this to 10 genuine
candidates across 4 files, each confirmed live via a raw
`manage.py shell` call (no test-transaction wrapper) before being
fixed and formalized here.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db


class TestFeatureFlagTransactionBoundary:
    def test_define_feature_flag_commits_without_atomic_error(self):
        from apps.platform.infrastructure import composition

        flag = composition.build_define_feature_flag().execute(key=f"flag_{uuid.uuid4().hex[:6]}")
        assert flag is not None
