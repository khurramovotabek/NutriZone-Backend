"""
Event contract registry.

Enforces MIC §7's rule that a module may not emit or consume an event
type absent from the Domain Event Catalogue (Domain Architecture
Specification §6). Concrete event payload dataclasses are registered
here from `shared/event_contracts/` as each module is implemented; at
foundation stage the registry exists and is empty, ready for the first
business module's registration calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EventContractError(RuntimeError):
    """Raised when code emits/subscribes to an event not in the registry."""


@dataclass(frozen=True, slots=True)
class EventContract:
    event_type: str
    emitted_by: str  # bounded-context app label
    payload_schema: type[Any]  # a dataclass or msgspec/pydantic type describing the payload shape


class EventRegistry:
    """Process-wide registry, populated at Django app-ready time by each module."""

    def __init__(self) -> None:
        self._contracts: dict[str, EventContract] = {}

    def register(self, contract: EventContract) -> None:
        if contract.event_type in self._contracts:
            raise EventContractError(f"Event type '{contract.event_type}' is already registered.")
        self._contracts[contract.event_type] = contract

    def get(self, event_type: str) -> EventContract:
        try:
            return self._contracts[event_type]
        except KeyError as exc:
            raise EventContractError(
                f"Event type '{event_type}' is not registered in the Domain Event Catalogue. "
                "See Domain Architecture Specification §6 -- a new event type requires a "
                "catalogue amendment before it may be emitted or consumed (MIC §7)."
            ) from exc

    def all_event_types(self) -> list[str]:
        return sorted(self._contracts.keys())


registry = EventRegistry()
