from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.query import QueryBus, QueryBusError, QueryHandler

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class _GetWidgetById:
    widget_id: str


class _GetWidgetByIdHandler(QueryHandler):
    def handle(self, query: _GetWidgetById) -> dict:
        return {"id": query.widget_id, "name": "Widget"}


def test_dispatch_routes_to_registered_handler():
    bus = QueryBus()
    bus.register(_GetWidgetById, _GetWidgetByIdHandler())
    result = bus.dispatch(_GetWidgetById(widget_id="w1"))
    assert result == {"id": "w1", "name": "Widget"}


def test_dispatch_without_registered_handler_raises():
    bus = QueryBus()
    with pytest.raises(QueryBusError):
        bus.dispatch(_GetWidgetById(widget_id="w1"))


def test_registering_the_same_query_type_twice_raises():
    bus = QueryBus()
    bus.register(_GetWidgetById, _GetWidgetByIdHandler())
    with pytest.raises(QueryBusError):
        bus.register(_GetWidgetById, _GetWidgetByIdHandler())


def test_dispatch_listener_receives_query_type_and_duration():
    bus = QueryBus()
    bus.register(_GetWidgetById, _GetWidgetByIdHandler())

    observed = []
    bus.add_dispatch_listener(lambda query_type, duration: observed.append((query_type, duration)))

    bus.dispatch(_GetWidgetById(widget_id="w2"))

    assert len(observed) == 1
    query_type, duration = observed[0]
    assert query_type is _GetWidgetById
    assert duration >= 0


def test_dispatch_listener_fires_even_when_handler_result_is_falsy():
    class _FalsyHandler(QueryHandler):
        def handle(self, query):
            return None

    bus = QueryBus()
    bus.register(_GetWidgetById, _FalsyHandler())
    observed = []
    bus.add_dispatch_listener(lambda qt, d: observed.append(qt))
    bus.dispatch(_GetWidgetById(widget_id="w3"))
    assert observed == [_GetWidgetById]


def test_multiple_query_types_are_independently_routed():
    @dataclass(frozen=True)
    class _OtherQuery:
        pass

    class _OtherHandler(QueryHandler):
        def handle(self, query):
            return "other"

    bus = QueryBus()
    bus.register(_GetWidgetById, _GetWidgetByIdHandler())
    bus.register(_OtherQuery, _OtherHandler())

    assert bus.dispatch(_GetWidgetById(widget_id="w4"))["id"] == "w4"
    assert bus.dispatch(_OtherQuery()) == "other"
