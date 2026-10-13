from __future__ import annotations

import time

import pytest

from core.observability import (
    correlation_scope,
    get_causation_id,
    get_correlation_id,
    new_correlation_id,
    timed,
    timed_function,
)

pytestmark = pytest.mark.unit


def test_no_correlation_outside_a_scope():
    assert get_correlation_id() is None
    assert get_causation_id() is None


def test_correlation_scope_sets_and_restores():
    with correlation_scope() as cid:
        assert get_correlation_id() == cid
    assert get_correlation_id() is None


def test_correlation_scope_generates_id_when_not_supplied():
    with correlation_scope() as cid:
        assert cid is not None
        assert len(cid) > 0


def test_correlation_scope_preserves_supplied_id():
    with correlation_scope(correlation_id="fixed-id") as cid:
        assert cid == "fixed-id"
        assert get_correlation_id() == "fixed-id"


def test_correlation_scope_sets_causation_id():
    with correlation_scope(correlation_id="c1", causation_id="cause-1"):
        assert get_causation_id() == "cause-1"


def test_nested_correlation_scopes_restore_outer_value():
    with correlation_scope(correlation_id="outer"):
        with correlation_scope(correlation_id="inner"):
            assert get_correlation_id() == "inner"
        assert get_correlation_id() == "outer"


def test_new_correlation_id_produces_unique_values():
    assert new_correlation_id() != new_correlation_id()


def test_timed_context_manager_reports_elapsed():
    with timed("test.operation") as elapsed:
        time.sleep(0.01)
    assert elapsed() >= 0.01


def test_timed_function_decorator_preserves_return_value():
    @timed_function("test.decorated")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_timed_function_decorator_preserves_function_metadata():
    @timed_function()
    def my_func():
        """docstring"""
        return 1

    assert my_func.__name__ == "my_func"
    assert my_func.__doc__ == "docstring"
