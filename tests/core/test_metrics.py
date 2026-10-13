from __future__ import annotations

import pytest

from core.metrics import MetricsCollector, NullMetricsBackend

pytestmark = pytest.mark.unit


class _RecordingBackend:
    def __init__(self) -> None:
        self.counters: list[tuple[str, float, dict]] = []
        self.gauges: list[tuple[str, float, dict]] = []
        self.histograms: list[tuple[str, float, dict]] = []

    def inc_counter(self, name, value, labels):
        self.counters.append((name, value, labels))

    def set_gauge(self, name, value, labels):
        self.gauges.append((name, value, labels))

    def observe_histogram(self, name, value, labels):
        self.histograms.append((name, value, labels))


def test_null_backend_never_raises():
    collector = MetricsCollector(NullMetricsBackend())
    collector.counter("test_counter")
    collector.gauge("test_gauge", 1.0)
    collector.histogram("test_histogram", 0.5)


def test_counter_forwards_to_backend():
    backend = _RecordingBackend()
    collector = MetricsCollector(backend)
    collector.counter("orders_placed", labels_key="value")
    assert backend.counters[0][0] == "orders_placed"
    assert backend.counters[0][1] == 1.0


def test_counter_custom_value():
    backend = _RecordingBackend()
    collector = MetricsCollector(backend)
    collector.counter("bytes_processed", value=1024)
    assert backend.counters[0][1] == 1024


def test_gauge_forwards_to_backend():
    backend = _RecordingBackend()
    collector = MetricsCollector(backend)
    collector.gauge("queue_depth", 42)
    assert backend.gauges[0] == ("queue_depth", 42, {})


def test_histogram_forwards_to_backend():
    backend = _RecordingBackend()
    collector = MetricsCollector(backend)
    collector.histogram("request_size_bytes", 256)
    assert backend.histograms[0] == ("request_size_bytes", 256, {})


def test_timer_records_a_histogram_on_exit():
    backend = _RecordingBackend()
    collector = MetricsCollector(backend)
    with collector.timer("operation"):
        pass
    assert len(backend.histograms) == 1
    assert backend.histograms[0][0] == "operation_duration_seconds"


def test_labels_are_passed_through():
    backend = _RecordingBackend()
    collector = MetricsCollector(backend)
    collector.counter("orders_placed", store_id="store-1", channel="web")
    _, _, labels = backend.counters[0]
    assert labels == {"store_id": "store-1", "channel": "web"}


def test_configure_swaps_backend():
    collector = MetricsCollector()
    assert isinstance(collector.backend, NullMetricsBackend)
    new_backend = _RecordingBackend()
    collector.configure(new_backend)
    assert collector.backend is new_backend
