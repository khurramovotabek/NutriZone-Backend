"""
**The certified POS Infrastructure contains only 1 task:
`relay_outbox_events`** -- re-verified fresh in this phase's own Step
2. No "stale sale" cleanup/expiration/auto-void task exists, matching
the deliberate restraint disclosed in Phase 2's own `tasks.py` module
docstring; this file tests only what genuinely exists.
"""
from __future__ import annotations

import ast

import pytest

from apps.pos.infrastructure.tasks import relay_outbox_events

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_only_one_task_exists():
    tree = ast.parse(open("apps/pos/infrastructure/tasks.py").read())
    task_functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert task_functions == ["relay_outbox_events"], f"Expected exactly 1 task, found: {task_functions}"


def test_relay_outbox_events_runs_without_error():
    result = relay_outbox_events()
    assert isinstance(result, dict)
