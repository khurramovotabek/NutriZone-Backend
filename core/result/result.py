"""
Result pattern.

Application Services that want to signal failure without raising for
*expected, cheaply-recoverable* business outcomes (as opposed to the
`DomainException` hierarchy in `common/exceptions/`, which remains the
correct mechanism for failures the interfaces layer should translate
straight to an HTTP error per REST API Blueprint §7) return a `Result`
instead. This is deliberately a small, closed vocabulary -- not a
general-purpose either/monad library -- to keep every module's use of
it uniform (MIC §1: "no module may define its own coding style").

When to use Result vs. raising DomainException (both are legitimate,
per MIC §4's Application Service rules):
  - Raise a DomainException when the caller (an API view, a Celery
    task) should treat the failure as exceptional and let the standard
    exception-handling machinery (common/exceptions/handlers.py) turn
    it into a response.
  - Return a Result when the *caller itself* needs to branch on the
    outcome as a normal part of its own control flow (e.g. a
    CheckoutOrchestrator step calling several sub-services and
    aggregating multiple possible validation failures before deciding
    what to do next) -- see `ValidationAggregator` below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Error:
    """A single, typed error -- the payload of a Failure."""

    code: str
    message: str
    field: str | None = None  # set when the error is attributable to one input field


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    """
    Base Result type. Prefer the `Result.success()` / `Result.failure()`
    constructors over instantiating this directly.
    """

    is_success: bool
    value: T | None = None
    errors: tuple[Error, ...] = field(default_factory=tuple)

    @property
    def is_failure(self) -> bool:
        return not self.is_success

    @staticmethod
    def success(value: T) -> "Result[T]":
        return Result(is_success=True, value=value, errors=())

    @staticmethod
    def failure(*errors: Error) -> "Result[T]":
        if not errors:
            raise ValueError("Result.failure() requires at least one Error.")
        return Result(is_success=False, value=None, errors=tuple(errors))

    @staticmethod
    def single_failure(code: str, message: str, field: str | None = None) -> "Result[T]":
        return Result.failure(Error(code=code, message=message, field=field))

    def unwrap(self) -> T:
        """
        Returns the value, or raises if this is a Failure.

        Intended for call sites (typically at an interfaces/api boundary
        translating a Result back into a raised DomainException) that
        have already checked `is_success` and are extracting the value,
        or that intentionally want a hard failure if a precondition was
        violated.
        """
        if self.is_failure:
            raise ResultUnwrapError(self.errors)
        assert self.value is not None or self.is_success  # narrows type for callers
        return self.value  # type: ignore[return-value]

    def map(self, func):
        """Transforms the success value, passing through a Failure unchanged."""
        if self.is_failure:
            return self
        return Result.success(func(self.value))


class ResultUnwrapError(RuntimeError):
    """Raised by `Result.unwrap()` on a Failure."""

    def __init__(self, errors: tuple[Error, ...]) -> None:
        self.errors = errors
        super().__init__(f"Attempted to unwrap a Failure Result: {errors}")


class ValidationAggregator:
    """
    Collects multiple Errors across several checks before producing one
    Result -- the concrete mechanism behind MIC §6's "Validation
    Aggregation" requirement, e.g. a checkout step that wants to report
    every failed cart line at once rather than stopping at the first.
    """

    def __init__(self) -> None:
        self._errors: list[Error] = []

    def add(self, code: str, message: str, field: str | None = None) -> None:
        self._errors.append(Error(code=code, message=message, field=field))

    def add_if(self, condition: bool, code: str, message: str, field: str | None = None) -> None:
        if condition:
            self.add(code, message, field)

    @property
    def has_errors(self) -> bool:
        return bool(self._errors)

    def to_result(self, value: T | None = None) -> Result[T]:
        if self._errors:
            return Result.failure(*self._errors)
        return Result.success(value)  # type: ignore[arg-type]
