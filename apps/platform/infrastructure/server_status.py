"""
Dashboard → Platforma → Server holati: one live picture of the machine and the services behind the shop.

Every probe is short (≤ 2 s), independent and never raises -- a dead Redis must still let the page tell you that
Redis is dead. `snapshot()` returns plain dicts; the view renders them and re-fetches the page every 30 s.

Status words: "ok" (yashil), "warn" (sariq), "down" (qizil), "off" (kulrang, not configured).
"""
from __future__ import annotations

import os
import shutil
import socket
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

QUEUES = ("transactional", "default", "scheduled", "bulk", "maintenance")


def _timed(fn):
    start = time.perf_counter()
    try:
        value = fn()
        return value, round((time.perf_counter() - start) * 1000, 1), None
    except Exception as exc:  # noqa: BLE001 - a probe reports, never raises
        return None, round((time.perf_counter() - start) * 1000, 1), f"{type(exc).__name__}: {str(exc)[:160]}"


def _human_bytes(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _human_duration(seconds: float) -> str:
    seconds = int(seconds or 0)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} kun {h} soat"
    if h:
        return f"{h} soat {m} daq"
    return f"{m} daqiqa"


def _level(value: float, warn: float, bad: float) -> str:
    return "down" if value >= bad else "warn" if value >= warn else "ok"


# ---------------------------------------------------------------- probes


def database() -> dict:
    from django.db import connection

    def probe():
        with connection.cursor() as c:
            c.execute("SELECT 1")
            c.execute("SELECT pg_database_size(current_database()), (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()), "
                      "current_setting('max_connections')::int, split_part(version(), ' ', 2)")
            size, conns, max_conns, version = c.fetchone()
        return size, conns, max_conns, version

    value, ms, err = _timed(probe)
    if err:
        return {"key": "db", "title": "Ma'lumotlar bazasi", "icon": "fa-database", "status": "down", "latency": ms, "error": err, "facts": []}
    size, conns, max_conns, version = value
    share = conns * 100 / max_conns if max_conns else 0
    status = "warn" if ms > 250 or share > 70 else "ok"
    return {"key": "db", "title": "Ma'lumotlar bazasi", "icon": "fa-database", "status": status, "latency": ms, "error": None,
            "facts": [("PostgreSQL", version), ("Hajmi", _human_bytes(size)), ("Ulanishlar", f"{conns} / {max_conns}")],
            "meter": {"label": "Ulanishlar", "pct": round(share)}}


def _redis(url: str | None = None):
    import redis as redis_lib

    return redis_lib.Redis.from_url(url or settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)


def redis() -> dict:
    def probe():
        r = _redis()
        r.ping()
        return r.info()

    info, ms, err = _timed(probe)
    if err:
        return {"key": "redis", "title": "Redis (kesh va navbat)", "icon": "fa-bolt", "status": "down", "latency": ms, "error": err, "facts": []}
    used, peak = info.get("used_memory", 0), info.get("maxmemory", 0) or 0
    facts = [("Versiya", info.get("redis_version", "")), ("Xotira", _human_bytes(used) + (f" / {_human_bytes(peak)}" if peak else "")),
             ("Mijozlar", info.get("connected_clients", 0)), ("Ishlayapti", _human_duration(info.get("uptime_in_seconds", 0)))]
    meter = {"label": "Xotira", "pct": round(used * 100 / peak)} if peak else None
    status = "warn" if ms > 100 or (meter and meter["pct"] > 85) else "ok"
    return {"key": "redis", "title": "Redis (kesh va navbat)", "icon": "fa-bolt", "status": status, "latency": ms, "error": None, "facts": facts, "meter": meter}


def workers() -> dict:
    def probe():
        from config.celery import app

        return app.control.inspect(timeout=1.5).ping() or {}

    replies, ms, err = _timed(probe)
    names = sorted(replies or {})
    if err or not names:
        return {"key": "celery", "title": "Fon ishchilari (Celery)", "icon": "fa-gears", "status": "down", "latency": ms,
                "error": err or "Hech bir ishchi javob bermadi — buyurtma xabarlari, Telegram va hisobotlar to'xtab qoladi.", "facts": []}
    return {"key": "celery", "title": "Fon ishchilari (Celery)", "icon": "fa-gears", "status": "ok", "latency": ms, "error": None,
            "facts": [("Ishchilar", len(names))] + [(n.split("@")[0], n.split("@")[-1][:12]) for n in names[:4]]}


def beat_and_jobs() -> dict:
    from django_celery_beat.models import PeriodicTask

    from apps.platform.infrastructure import task_health
    from apps.platform.infrastructure.jobs_admin import health_of

    def probe():
        tasks = list(PeriodicTask.objects.select_related("interval", "crontab", "clocked", "solar"))
        data = task_health.read([t.name for t in tasks] + [t.task for t in tasks])
        states = [health_of(t, data.get(t.name) or data.get(t.task) or {}) for t in tasks]
        beat = max((t.last_run_at for t in tasks if t.last_run_at), default=None)
        failing = [t.name for t, s in zip(tasks, states, strict=True) if s == "failing"]
        return len(tasks), sum(1 for s in states if s == "off"), failing, sum(1 for s in states if s == "late"), beat

    value, ms, err = _timed(probe)
    if err:
        return {"key": "beat", "title": "Rejalashtiruvchi (beat)", "icon": "fa-heart-pulse", "status": "down", "latency": ms, "error": err, "facts": []}
    total, off, failing, late, beat = value
    beat_age = (timezone.now() - beat).total_seconds() if beat else None
    status = "down" if beat_age is None or beat_age > 600 else "warn" if failing or late else "ok"
    from apps.platform.infrastructure.premium_admin import ago

    return {"key": "beat", "title": "Rejalashtiruvchi (beat)", "icon": "fa-heart-pulse", "status": status, "latency": None,
            "error": None if beat_age is not None and beat_age <= 600 else "Beat signal bermayapti — avtomatik vazifalar ishga tushmaydi.",
            "facts": [("Oxirgi signal", ago(beat) if beat else "—"), ("Faol vazifalar", total - off), ("Xato bilan", len(failing)), ("Kechikkan", late)],
            "list": failing[:5]}


def queues() -> dict:
    def probe():
        r = _redis(getattr(settings, "CELERY_BROKER_URL", "") or None)
        return {q: r.llen(q) for q in QUEUES}

    sizes, ms, err = _timed(probe)
    if err:
        return {"key": "queues", "title": "Navbatlar", "icon": "fa-layer-group", "status": "down", "latency": ms, "error": err, "facts": []}
    total = sum(sizes.values())
    return {"key": "queues", "title": "Navbatlar", "icon": "fa-layer-group", "status": _level(total, 200, 2000), "latency": None, "error": None,
            "facts": [(q, n) for q, n in sizes.items() if n or q == "default"], "big": total, "big_label": "kutayotgan vazifa"}


def outbox() -> dict:
    """Unpublished domain events (cache / search / notification side effects waiting for the relays)."""
    from django.apps import apps

    from core.outbox.models import AbstractOutboxEvent

    def probe():
        since = timezone.now() - timedelta(minutes=10)
        stuck, waiting = 0, 0
        for model in apps.get_models():
            if issubclass(model, AbstractOutboxEvent):
                qs = model.objects.filter(published_at__isnull=True)
                waiting += qs.count()
                stuck += qs.filter(created_at__lt=since).count()
        return waiting, stuck

    value, ms, err = _timed(probe)
    if err:
        return {"key": "outbox", "title": "Ichki hodisalar (outbox)", "icon": "fa-arrows-spin", "status": "warn", "latency": ms, "error": err, "facts": []}
    waiting, stuck = value
    return {"key": "outbox", "title": "Ichki hodisalar (outbox)", "icon": "fa-arrows-spin", "status": "warn" if stuck > 50 else "ok", "latency": None, "error": None,
            "facts": [("Navbatda", waiting), ("10 daqiqadan eski", stuck)], "big": waiting, "big_label": "yuborilmagan hodisa"}


def http_service(key: str, title: str, icon: str, url: str) -> dict:
    if not url:
        return {"key": key, "title": title, "icon": icon, "status": "off", "latency": None, "error": "Sozlanmagan", "facts": []}
    import urllib.request

    def probe():
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "NutriZone-Status/1.0", "X-Forwarded-Proto": "https"})
        with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310 - fixed, settings-provided URLs
            return resp.status

    code, ms, err = _timed(probe)
    if err:
        return {"key": key, "title": title, "icon": icon, "status": "down", "latency": ms, "error": err, "facts": [("Manzil", url)]}
    return {"key": key, "title": title, "icon": icon, "status": "warn" if ms > 1500 else "ok", "latency": ms, "error": None, "facts": [("HTTP", code), ("Manzil", url)]}


def host() -> dict:
    """Load, memory, disk, uptime of the machine (the container shares the host kernel's numbers)."""
    cpus = os.cpu_count() or 1
    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        load1 = load5 = load15 = 0.0
    mem_total = mem_avail = 0
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            info = {line.split(":")[0]: int(line.split()[1]) * 1024 for line in f if ":" in line}
        mem_total, mem_avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
    except OSError:
        pass
    uptime = 0.0
    try:
        with open("/proc/uptime", encoding="ascii") as f:
            uptime = float(f.read().split()[0])
    except OSError:
        pass
    disk = shutil.disk_usage("/")
    mem_pct = round((mem_total - mem_avail) * 100 / mem_total) if mem_total else 0
    disk_pct = round(disk.used * 100 / disk.total) if disk.total else 0
    cpu_pct = round(min(load1 / cpus, 1.5) * 100)
    gauges = [
        {"label": "Protsessor", "pct": min(cpu_pct, 100), "value": f"{load1:.2f}", "sub": f"{cpus} yadro · 5 daq {load5:.2f} · 15 daq {load15:.2f}", "status": _level(cpu_pct, 70, 95)},
        {"label": "Xotira (RAM)", "pct": mem_pct, "value": f"{mem_pct}%", "sub": f"{_human_bytes(mem_total - mem_avail)} / {_human_bytes(mem_total)}", "status": _level(mem_pct, 80, 93)},
        {"label": "Disk", "pct": disk_pct, "value": f"{disk_pct}%", "sub": f"{_human_bytes(disk.free)} bo'sh · {_human_bytes(disk.total)} dan", "status": _level(disk_pct, 80, 92)},
    ]
    return {"hostname": socket.gethostname(), "uptime": _human_duration(uptime), "gauges": gauges,
            "status": max((g["status"] for g in gauges), key=("ok", "warn", "down").index)}


def snapshot() -> dict:
    services = [
        database(), redis(), workers(), beat_and_jobs(), queues(), outbox(),
        http_service("stt", "Ovozli qidiruv (STT)", "fa-microphone", (getattr(settings, "STT_SERVICE_URL", "") or "").rstrip("/") + "/health" if getattr(settings, "STT_SERVICE_URL", "") else ""),
    ]
    order = ("ok", "off", "warn", "down")
    worst = max((s["status"] for s in services if s["status"] != "off"), key=order.index, default="ok")
    machine = host()
    overall = max((worst, machine["status"]), key=order.index)
    return {
        "overall": overall,
        "overall_text": {"ok": "Hammasi joyida", "warn": "E'tibor talab qiladi", "down": "Muammo bor"}.get(overall, ""),
        "services": services,
        "host": machine,
        "release": os.environ.get("APP_RELEASE", "") or "",
        "environment": "Production" if not settings.DEBUG else "Development",
        "python": ".".join(map(str, __import__("sys").version_info[:3])),
        "django": __import__("django").get_version(),
        "checked_at": timezone.localtime(),
        "counts": {s: sum(1 for x in services if x["status"] == s) for s in ("ok", "warn", "down", "off")},
    }
