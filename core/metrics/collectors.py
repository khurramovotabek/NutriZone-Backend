"""
Metrics infrastructure.

A thin, backend-agnostic facade over the standard four metric shapes
(Counter/Gauge/Histogram/Timer), with a `prometheus_client`-backed
implementation as the default -- "Prometheus-compatible abstraction"
per the mission. The facade exists so business modules depend on
`core.metrics`, never on `prometheus_client` directly: swapping the
backend (e.g. to StatsD) later touches only `core/metrics/backends.py`,
not every module that records a metric.
"""
from __future__ import annotations

import contextlib
import time
from typing import Iterator, Protocol


class MetricsBackend(Protocol):
    def inc_counter(self, name: str, value: float, labels: dict[str, str]) -> None: ...

    def set_gauge(self, name: str, value: float, labels: dict[str, str]) -> None: ...

    def observe_histogram(self, name: str, value: float, labels: dict[str, str]) -> None: ...


class NullMetricsBackend:
    """No-op backend -- the default until `configure_metrics()` is called, so metric calls never raise in tests/foundation phase."""

    def inc_counter(self, name: str, value: float, labels: dict[str, str]) -> None:
        pass

    def set_gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        pass

    def observe_histogram(self, name: str, value: float, labels: dict[str, str]) -> None:
        pass


class PrometheusMetricsBackend:
    """
    Backed by `prometheus_client`. Metric objects are created lazily and
    cached by name, since `prometheus_client` requires a metric to be
    registered exactly once per name/label-set combination.
    """

    def __init__(self) -> None:
        self._counters: dict[str, object] = {}
        self._gauges: dict[str, object] = {}
        self._histograms: dict[str, object] = {}

    def _get_or_create(self, cache: dict[str, object], name: str, labels: dict[str, str], factory):
        key = f"{name}:{','.join(sorted(labels))}"
        if key not in cache:
            from prometheus_client import Counter, Gauge, Histogram  # noqa: PLC0415, F401

            cache[key] = factory(name, list(labels.keys()))
        return cache[key]

    def inc_counter(self, name: str, value: float, labels: dict[str, str]) -> None:
        from prometheus_client import Counter  # noqa: PLC0415

        metric = self._get_or_create(self._counters, name, labels, lambda n, lbls: Counter(n, n, lbls))
        (metric.labels(**labels) if labels else metric).inc(value)

    def set_gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        from prometheus_client import Gauge  # noqa: PLC0415

        metric = self._get_or_create(self._gauges, name, labels, lambda n, lbls: Gauge(n, n, lbls))
        (metric.labels(**labels) if labels else metric).set(value)

    def observe_histogram(self, name: str, value: float, labels: dict[str, str]) -> None:
        from prometheus_client import Histogram  # noqa: PLC0415

        metric = self._get_or_create(self._histograms, name, labels, lambda n, lbls: Histogram(n, n, lbls))
        (metric.labels(**labels) if labels else metric).observe(value)


class MetricsCollector:
    """
    The facade every module imports. `core.metrics.default_collector` is
    the process-wide instance; `configure_metrics()` swaps its backend.
    """

    def __init__(self, backend: MetricsBackend | None = None) -> None:
        self.backend: MetricsBackend = backend or NullMetricsBackend()

    def configure(self, backend: MetricsBackend) -> None:
        self.backend = backend

    def counter(self, name: str, value: float = 1.0, **labels: str) -> None:
        self.backend.inc_counter(name, value, labels)

    def gauge(self, name: str, value: float, **labels: str) -> None:
        self.backend.set_gauge(name, value, labels)

    def histogram(self, name: str, value: float, **labels: str) -> None:
        self.backend.observe_histogram(name, value, labels)

    @contextlib.contextmanager
    def timer(self, name: str, **labels: str) -> Iterator[None]:
        """Records elapsed seconds into a histogram named `<name>_duration_seconds` on exit."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.histogram(f"{name}_duration_seconds", duration, **labels)


default_collector = MetricsCollector()


def configure_metrics(backend: MetricsBackend) -> None:
    default_collector.configure(backend)
