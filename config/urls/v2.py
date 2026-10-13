"""
`/api/v2/` namespace root.

Empty scaffold, present from project creation onward per REST API
Blueprint §2 -- "ready for the first breaking-change cycle." A module
gets a `v2` entry here only when a genuinely breaking change (per that
document's breaking-vs-non-breaking definition) requires it.
"""
from __future__ import annotations

app_name = "v2"

urlpatterns: list = []
