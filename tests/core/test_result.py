from __future__ import annotations

import pytest

from core.result import Error, Result, ResultUnwrapError, ValidationAggregator

pytestmark = pytest.mark.unit


def test_success_result_shape():
    result = Result.success(42)
    assert result.is_success
    assert not result.is_failure
    assert result.value == 42
    assert result.errors == ()


def test_failure_result_shape():
    error = Error(code="BAD", message="bad thing")
    result: Result[int] = Result.failure(error)
    assert result.is_failure
    assert not result.is_success
    assert result.value is None
    assert result.errors == (error,)


def test_failure_requires_at_least_one_error():
    with pytest.raises(ValueError):
        Result.failure()


def test_single_failure_convenience_constructor():
    result: Result[int] = Result.single_failure("CODE", "message", field="name")
    assert result.is_failure
    assert result.errors[0].code == "CODE"
    assert result.errors[0].field == "name"


def test_unwrap_success_returns_value():
    assert Result.success("value").unwrap() == "value"


def test_unwrap_failure_raises():
    result: Result[int] = Result.single_failure("CODE", "msg")
    with pytest.raises(ResultUnwrapError):
        result.unwrap()


def test_map_transforms_success_value():
    result = Result.success(2).map(lambda x: x * 10)
    assert result.is_success
    assert result.value == 20


def test_map_passes_through_failure_unchanged():
    failure: Result[int] = Result.single_failure("CODE", "msg")
    mapped = failure.map(lambda x: x * 10)
    assert mapped.is_failure
    assert mapped.errors == failure.errors


def test_validation_aggregator_collects_multiple_errors():
    aggregator = ValidationAggregator()
    aggregator.add("A", "first")
    aggregator.add("B", "second")
    result = aggregator.to_result()
    assert result.is_failure
    assert len(result.errors) == 2
    assert {e.code for e in result.errors} == {"A", "B"}


def test_validation_aggregator_add_if_conditional():
    aggregator = ValidationAggregator()
    aggregator.add_if(False, "A", "should not appear")
    aggregator.add_if(True, "B", "should appear")
    result = aggregator.to_result()
    assert len(result.errors) == 1
    assert result.errors[0].code == "B"


def test_validation_aggregator_success_when_no_errors():
    aggregator = ValidationAggregator()
    result = aggregator.to_result(value="ok")
    assert result.is_success
    assert result.value == "ok"


def test_validation_aggregator_has_errors_property():
    aggregator = ValidationAggregator()
    assert not aggregator.has_errors
    aggregator.add("A", "msg")
    assert aggregator.has_errors
