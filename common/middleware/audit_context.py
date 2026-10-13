"""
Request-scoped "current actor" context.

Populates created_by/updated_by on BaseModel-derived saves without every
application service having to pass the acting user down manually
(Django Implementation Blueprint §5). Uses contextvars rather than
`threading.local` so it behaves correctly under Django Channels'
async/ASGI request handling too.
"""
from __future__ import annotations

import contextvars
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

_current_actor_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "current_actor_id", default=None
)
_current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_request_id", default=None
)


def get_current_actor_id() -> uuid.UUID | None:
    return _current_actor_id.get()


def set_current_actor_id(actor_id: uuid.UUID | None) -> None:
    _current_actor_id.set(actor_id)


def get_current_request_id() -> str | None:
    return _current_request_id.get()


def set_current_request_id(request_id: str | None) -> None:
    _current_request_id.set(request_id)


class AuditContextMiddleware:
    """
    Sets the current-actor context var for the duration of a request.

    Must be placed after authentication middleware in MIDDLEWARE so
    `request.user` is already resolved (see config/settings/base.py).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        actor_id = getattr(user, "id", None) if user is not None and getattr(user, "is_authenticated", False) else None
        token = _current_actor_id.set(actor_id)
        try:
            return self.get_response(request)
        finally:
            _current_actor_id.reset(token)
