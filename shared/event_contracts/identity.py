"""
Identity's Domain Event Catalogue registration.

Imported once from `apps/identity/apps.py::IdentityConfig.ready()` --
importing this module IS the act of registering these five (plus one
security-only) event contracts against
`core.events.registry.registry`, per MIC §7's "payload shape must be
registered in shared/event_contracts/ before the emitting code is
written" rule.
"""
from __future__ import annotations

from apps.identity.domain.events import (
    SessionRevoked,
    SuspiciousLoginDetected,
    UserAuthenticated,
    UserBlocked,
    UserProfileUpdated,
    UserRegistered,
    UserRoleAssigned,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("UserRegistered", UserRegistered),
    ("UserAuthenticated", UserAuthenticated),
    ("UserBlocked", UserBlocked),
    ("UserProfileUpdated", UserProfileUpdated),
    ("UserRoleAssigned", UserRoleAssigned),
    ("SuspiciousLoginDetected", SuspiciousLoginDetected),
    ("SessionRevoked", SessionRevoked),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="identity", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
