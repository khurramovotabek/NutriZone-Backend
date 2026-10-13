"""
`/api/internal/` namespace root.

Endpoints intended only for the Admin CRM and POS Workspace (manual
wallet adjustment, stock override, scheduler/audit ops screens --
REST API Blueprint §13.19-13.21) -- excluded from public API
documentation and any future third-party developer program.
"""
from __future__ import annotations

app_name = "internal"

urlpatterns: list = []
