"""
Correlation middleware for HTTP requests and Celery tasks.

`CorrelationMiddleware` opens a correlation scope for every HTTP
request (reusing an incoming `X-Correlation-ID` header if present, so a
correlation started by an upstream caller/gateway is preserved end to
end, matching common/middleware/request_id.py's same pattern for
request_id). `celery_correlation_signal_handlers()` wires the
equivalent behavior for Celery tasks via task-prerun/postrun signals,
so a task triggered by an HTTP request (or by another task) continues
the same correlation chain -- this is the "Background task metrics" /
"Request metrics" propagation the mission requires.
"""
from __future__ import annotations

from typing import Callable

from django.http import HttpRequest, HttpResponse

from core.observability.correlation import correlation_scope

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(CORRELATION_ID_HEADER)
        with correlation_scope(correlation_id=incoming) as correlation_id:
            response = self.get_response(request)
            response[CORRELATION_ID_HEADER] = correlation_id
            return response


def register_celery_correlation_signals() -> None:
    """
    Call once at Celery app startup (config/celery.py) to propagate
    correlation_id through task headers automatically. A task that
    stages an event or calls `.delay()`/`.apply_async()` with
    `headers={"correlation_id": get_correlation_id()}` will have that
    id restored here on the worker side when the task actually runs.
    """
    from celery.signals import task_postrun, task_prerun

    from core.observability.correlation import _causation_id, _correlation_id  # noqa: PLC0415

    _tokens: dict[str, tuple] = {}

    @task_prerun.connect
    def _on_task_prerun(task_id: str, task, **kwargs):  # noqa: ANN001
        headers = getattr(task.request, "headers", None) or {}
        corr_token = _correlation_id.set(headers.get("correlation_id"))
        caus_token = _causation_id.set(headers.get("causation_id"))
        _tokens[task_id] = (corr_token, caus_token)

    @task_postrun.connect
    def _on_task_postrun(task_id: str, **kwargs):  # noqa: ANN001
        tokens = _tokens.pop(task_id, None)
        if tokens:
            corr_token, caus_token = tokens
            _correlation_id.reset(corr_token)
            _causation_id.reset(caus_token)
