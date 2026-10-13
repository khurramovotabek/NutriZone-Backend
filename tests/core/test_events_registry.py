from __future__ import annotations

import pytest

from core.events import EventContract, EventContractError, EventRegistry

pytestmark = pytest.mark.unit


def test_register_and_get_round_trip():
    registry = EventRegistry()
    contract = EventContract(event_type="ProductCreated", emitted_by="catalog", payload_schema=dict)
    registry.register(contract)
    assert registry.get("ProductCreated") is contract


def test_get_unregistered_event_raises():
    registry = EventRegistry()
    with pytest.raises(EventContractError):
        registry.get("NotRegistered")


def test_register_duplicate_event_type_raises():
    registry = EventRegistry()
    contract = EventContract(event_type="OrderPlaced", emitted_by="ordering", payload_schema=dict)
    registry.register(contract)
    with pytest.raises(EventContractError):
        registry.register(contract)


def test_all_event_types_returns_sorted_list():
    registry = EventRegistry()
    registry.register(EventContract(event_type="Zeta", emitted_by="a", payload_schema=dict))
    registry.register(EventContract(event_type="Alpha", emitted_by="b", payload_schema=dict))
    assert registry.all_event_types() == ["Alpha", "Zeta"]


def test_empty_registry_returns_empty_list():
    registry = EventRegistry()
    assert registry.all_event_types() == []
