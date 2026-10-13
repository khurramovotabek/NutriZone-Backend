"""
Query infrastructure -- CQRS-lite read-side plumbing.

This formalizes the `application/selectors.py` pattern already
established in Django Implementation Blueprint §3 into a typed,
dispatchable shape, for the cases where a module wants queries to be
routed through a bus (e.g. so a cross-cutting concern like metrics/
observability can wrap every query uniformly, per the metrics/
observability requirements in this same phase) rather than called as
plain Python method calls. Using the bus is OPTIONAL -- a module's
Selector methods may continue to be called directly from
`application/services/` or `interfaces/api/views.py` exactly as
Django Implementation Blueprint §3 describes; QueryBus exists for the
subset of read operations that benefit from dispatch-time
instrumentation, not as a mandatory indirection layer for every read.

No business Query/QueryHandler is registered here -- this module
supplies only the generic mechanism, ready for `apps/<context>/
application/selectors.py` to register its own typed Query classes
against once that module is implemented.
"""
from __future__ import annotations

import time
from typing import Callable, Generic, Protocol, TypeVar

TResult = TypeVar("TResult")


class Query(Protocol[TResult]):
    """
    Marker protocol every query object implements. A concrete Query is
    just an immutable dataclass describing "what data is wanted" -- it
    carries no behavior itself; behavior lives in the matching
    QueryHandler.
    """


class QueryHandler(Generic[TResult]):
    """Base class for a query handler. Subclasses implement `handle()`."""

    def handle(self, query: Query[TResult]) -> TResult:  # pragma: no cover - abstract
        raise NotImplementedError


class ReadModelProvider(Protocol[TResult]):
    """
    A narrower alternative to QueryHandler for the common case of "fetch
    a single read model by some key" -- e.g. the future
    AvailabilityBoard/EffectivePriceBoard read-model lookups (Database
    Blueprint §7/§8) will implement this rather than the more general
    QueryHandler shape.
    """

    def get(self, **kwargs: object) -> TResult: ...


class QueryBusError(RuntimeError):
    """Raised when dispatching a query with no registered handler."""


class QueryBus:
    """
    Process-wide dispatcher: `query_type -> handler`. Instrumentation
    (timing metrics, structured logging) wraps every dispatched call
    uniformly here, so no individual module needs to add its own
    logging/metrics boilerplate around every query -- see
    `core/observability` and `core/metrics` for what actually gets
    recorded.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, QueryHandler] = {}
        self._on_dispatch: list[Callable[[type, float], None]] = []

    def register(self, query_type: type, handler: QueryHandler) -> None:
        if query_type in self._handlers:
            raise QueryBusError(f"A handler is already registered for {query_type.__name__}.")
        self._handlers[query_type] = handler

    def add_dispatch_listener(self, listener: Callable[[type, float], None]) -> None:
        """Registers a callback invoked as (query_type, duration_seconds) after every dispatch -- the hook core/metrics wires a Histogram/Timer into."""
        self._on_dispatch.append(listener)

    def dispatch(self, query: Query[TResult]) -> TResult:
        query_type = type(query)
        handler = self._handlers.get(query_type)
        if handler is None:
            raise QueryBusError(f"No handler registered for {query_type.__name__}.")

        start = time.perf_counter()
        try:
            return handler.handle(query)
        finally:
            duration = time.perf_counter() - start
            for listener in self._on_dispatch:
                listener(query_type, duration)


# Process-wide default bus. Business modules may construct their own
# QueryBus instance for isolated testing, but share this one in
# production so cross-cutting listeners (metrics) see every dispatched
# query platform-wide.
default_query_bus = QueryBus()
