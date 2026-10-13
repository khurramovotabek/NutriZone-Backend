"""
Domain Clock abstraction.

Every place in the codebase that needs the current time calls `Clock`,
never `django.utils.timezone.now()` or `datetime.now()` directly.
This is what makes `Clock.freeze()` a reliable, single-point-of-control
mechanism for deterministic tests (MIC §8's Unit/Business Rule Tests
frequently need a fixed "now"), and what would let a future
requirement -- e.g. simulating a different server timezone for a
franchise store -- be satisfied by changing this one module rather than
auditing every call site in the codebase.

Enforcement note: `common/models/base.py`'s `TimestampedMixin` currently
uses `django.utils.timezone.now` directly as a field default, which is
intentional -- Django model field defaults are evaluated at class
definition/migration time in a way that doesn't compose cleanly with a
freezable abstraction, and Django's ORM layer is explicitly infrastructure,
not domain, code (Django Implementation Blueprint §3). `Clock` is for
`domain/`, `application/`, and `infrastructure/` *business logic* that
reasons about "now" -- not for ORM field defaults, which remain a
documented, narrow exception.
"""
from __future__ import annotations

import contextlib
import threading
from datetime import date, datetime, timezone as dt_timezone
from typing import Iterator

_UTC = dt_timezone.utc


class _ClockState(threading.local):
    frozen_at: datetime | None = None


_state = _ClockState()


class Clock:
    """
    Static-style facade -- there is exactly one Clock for the whole
    process, matching the "no direct usage of timezone.now() outside
    Clock" requirement. Thread-local freeze state so parallel test runs
    (pytest-xdist, per Django Implementation Blueprint §11) never leak
    a frozen time between workers.
    """

    @staticmethod
    def now() -> datetime:
        """Current time, timezone-aware, in UTC. The canonical 'now'."""
        if _state.frozen_at is not None:
            return _state.frozen_at
        return datetime.now(tz=_UTC)

    @staticmethod
    def utc_now() -> datetime:
        """Alias for `now()` -- explicit UTC naming for call sites where
        clarity matters (e.g. comparing against a stored UTC timestamp)."""
        return Clock.now()

    @staticmethod
    def today() -> date:
        """Current date, in UTC. Business modules needing store-local
        'today' (e.g. operating-hours checks) convert explicitly using
        the store's timezone -- Clock itself stays timezone-neutral at
        the UTC boundary, per platform convention (Django Implementation
        Blueprint §6: settings.TIME_ZONE = UTC)."""
        return Clock.now().date()

    @staticmethod
    @contextlib.contextmanager
    def freeze(at: datetime) -> Iterator[None]:
        """
        Freezes Clock.now()/today() to a fixed instant for the duration
        of the `with` block. `at` must be timezone-aware.

        Usage:
            with Clock.freeze(datetime(2026, 1, 1, tzinfo=timezone.utc)):
                assert Clock.today() == date(2026, 1, 1)
        """
        if at.tzinfo is None:
            raise ValueError("Clock.freeze() requires a timezone-aware datetime.")
        previous = _state.frozen_at
        _state.frozen_at = at
        try:
            yield
        finally:
            _state.frozen_at = previous

    @staticmethod
    def is_frozen() -> bool:
        return _state.frozen_at is not None
