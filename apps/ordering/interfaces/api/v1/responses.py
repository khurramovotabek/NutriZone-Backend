"""
Ordering response envelope helpers.

A thin re-export of `common.responses` -- Ordering's response
envelope is NOT reinvented here; every prior module (Cart, Pricing)
calls `common.responses.success_response`/`paginated_response`
directly from views.py, and this module exists only because this
phase's brief explicitly names a dedicated `responses.py` file.
Keeping it a pure re-export (rather than wrapping with Ordering-
specific logic) avoids a second, divergent envelope implementation
existing anywhere in the platform.
"""
from __future__ import annotations

from common.responses import paginated_response, success_response

__all__ = ["success_response", "paginated_response"]
