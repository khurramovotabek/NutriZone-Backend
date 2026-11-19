"""
Background-job health for the dashboard ("Fon vazifalari"): the outcome of each scheduled job's latest run.

Celery keeps results in Redis only for a while and django_celery_results is not the result backend, so the
dashboard never knew whether a job that beat *sent* actually *worked* (the outbox relays crashed silently for
weeks in October). Worker signals now record, per periodic task (beat's `periodic_task_name` header; the task
name for anything started by hand), the last success, the last failure with its error and how long the run took.

One small cache write per run (Redis, shared by workers and web); never raises into the task itself.
"""
from __future__ import annotations

import logging
import time

from django.utils import timezone

logger = logging.getLogger(__name__)

PREFIX = "nz:jobhealth:v1:"


def _ck(name: str) -> str:
    import hashlib

    return PREFIX + hashlib.sha1(name.encode()).hexdigest()  # names carry spaces / colons


_started: dict[str, float] = {}


def _key_of(task, request=None) -> str:
    req = request or getattr(task, "request", None)
    name = getattr(req, "periodic_task_name", None) or ((getattr(req, "headers", None) or {}).get("periodic_task_name") if req else None)
    return name or getattr(task, "name", "") or "unknown"


def read(keys) -> dict[str, dict]:
    from django.core.cache import cache

    by_key = {_ck(k): k for k in keys if k}
    try:
        found = cache.get_many(list(by_key))
    except Exception:  # noqa: BLE001 - health is advisory
        return {}
    return {by_key[k]: v for k, v in found.items()}


def record(key: str, ok: bool, runtime: float | None = None, error: str = "") -> None:
    from django.core.cache import cache

    try:
        now = timezone.now().isoformat()
        cur = cache.get(_ck(key)) or {}
        cur["runs"] = int(cur.get("runs", 0)) + 1
        if ok:
            cur.update({"ok_at": now, "runtime": round(runtime, 2) if runtime is not None else None, "streak": 0})
        else:
            cur.update({"fail_at": now, "error": (error or "")[:400], "fails": int(cur.get("fails", 0)) + 1, "streak": int(cur.get("streak", 0)) + 1})
        cache.set(_ck(key), cur, None)
    except Exception:  # noqa: BLE001 - never break the job over its bookkeeping
        logger.debug("job health: could not record %s", key, exc_info=True)


def _prerun(sender=None, task_id=None, task=None, **_kw):
    if task_id:
        _started[task_id] = time.monotonic()


def _success(sender=None, **_kw):
    tid = getattr(getattr(sender, "request", None), "id", None)
    start = _started.pop(tid, None) if tid else None
    record(_key_of(sender), True, time.monotonic() - start if start else None)


def _failure(sender=None, task_id=None, exception=None, **_kw):
    _started.pop(task_id, None)
    record(_key_of(sender), False, error=f"{type(exception).__name__}: {exception}" if exception else "xato")


def connect() -> None:
    from celery.signals import task_failure, task_prerun, task_success

    task_prerun.connect(_prerun, weak=False, dispatch_uid="nz-jobhealth-prerun")
    task_success.connect(_success, weak=False, dispatch_uid="nz-jobhealth-success")
    task_failure.connect(_failure, weak=False, dispatch_uid="nz-jobhealth-failure")
