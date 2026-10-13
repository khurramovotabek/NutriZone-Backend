"""
Platform's Domain Event Catalogue registration.

Imported once from `apps/platform/apps.py::PlatformConfig.ready()`,
matching every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.platform.domain.events import FeatureFlagChanged
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("FeatureFlagChanged", FeatureFlagChanged),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="platform", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
