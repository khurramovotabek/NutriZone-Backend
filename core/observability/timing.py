"""
Performance timing.

A small context manager / decorator pair that records elapsed time and
(optionally) forwards it to core/metrics' Timer/Histogram -- kept
separate from core/metrics itself so timing can be used purely for
structured-logging purposes (e.g. "log how long this took") without
requiring a metrics backend to be configured, and so core/metrics
doesn't need to know about logging.
"""
from __future__ import annotations

import contextlib
import functools
import logging
import time
from typing import Callable, Iterator, TypeVar

logger = logging.getLogger("nutrizone.app")

F = TypeVar("F", bound=Callable[..., object])


@contextlib.contextmanager
def timed(operation: str, *, log_level: int = logging.DEBUG) -> Iterator[Callable[[], float]]:
    """
    Usage:
        with timed("catalog.resolve_price") as elapsed:
            ...
        # elapsed() available after the block too, if needed for a metric
    """
    start = time.perf_counter()
    holder: dict[str, float] = {}

    def _elapsed() -> float:
        return holder.get("duration", time.perf_counter() - start)

    try:
        yield _elapsed
    finally:
        duration = time.perf_counter() - start
        holder["duration"] = duration
        logger.log(log_level, "operation=%s duration_ms=%.2f", operation, duration * 1000)


def timed_function(operation: str | None = None) -> Callable[[F], F]:
    """Decorator form of `timed()` for whole-function instrumentation."""

    def decorator(func: F) -> F:
        op_name = operation or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            with timed(op_name):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
