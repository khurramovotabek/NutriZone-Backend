"""Fon vazifalari: schedules in Uzbek, health from worker signals, the premium list."""
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User as AuthUser
from django.test import Client
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from apps.platform.infrastructure import task_health
from apps.platform.infrastructure.jobs_admin import health_of, human_schedule, period_seconds

pytestmark = pytest.mark.django_db


def _cron(minute, hour, dow="*", dom="*", tz="Asia/Tashkent"):
    c = CrontabSchedule.objects.create(minute=minute, hour=hour, day_of_week=dow, day_of_month=dom, month_of_year="*", timezone=tz)
    return PeriodicTask.objects.create(name=f"t-{uuid.uuid4().hex[:6]}", task="x.y", crontab=c)


def _every(n, unit):
    i = IntervalSchedule.objects.create(every=n, period=unit)
    return PeriodicTask.objects.create(name=f"i-{uuid.uuid4().hex[:6]}", task="x.y", interval=i)


def test_schedules_read_as_sentences():
    assert human_schedule(_cron("*", "*")) == "har daqiqa"
    assert human_schedule(_cron("*/5", "*")) == "har 5 daqiqada"
    assert human_schedule(_cron("0", "12")) == "har kuni 12:00"
    assert human_schedule(_cron("0", "9", dow="1")) == "har dushanba 09:00"
    assert human_schedule(_cron("5", "9", dom="1")) == "har oy 1-kuni 09:05"
    assert human_schedule(_cron("0", "4", tz="UTC")) == "har kuni 04:00 (UTC)"
    assert human_schedule(_every(30, "seconds")) == "har 30 soniyada"
    assert human_schedule(_every(1, "hours")) == "har soat"
    assert period_seconds(_cron("0", "9", dow="1")) == 7 * 86400


def test_health_states():
    now = timezone.now()
    t = _every(1, "minutes")
    assert health_of(t, {}) == "never"
    t.last_run_at = now - timedelta(seconds=30)
    assert health_of(t, {"ok_at": now.isoformat()}) == "ok"
    assert health_of(t, {"ok_at": (now - timedelta(minutes=5)).isoformat(), "fail_at": now.isoformat()}) == "failing"
    t.last_run_at = now - timedelta(hours=1)
    assert health_of(t, {"ok_at": (now - timedelta(hours=1)).isoformat()}) == "late"
    t.enabled = False
    assert health_of(t, {}) == "off"


def test_signals_record_per_periodic_task():
    name = f"Outbox relay: cart {uuid.uuid4().hex[:6]}"  # the cache is Redis: a fixed name would carry counts between runs
    req = SimpleNamespace(id="abc", periodic_task_name=name, headers=None)
    task = SimpleNamespace(name="apps.x.relay", request=req)
    task_health._prerun(task_id="abc", task=task)
    task_health._success(sender=task)
    task_health._failure(sender=task, task_id="abc", exception=RuntimeError("redis down"))
    got = task_health.read([name])[name]
    assert got["runs"] == 2 and got["ok_at"] and got["error"] == "RuntimeError: redis down" and got["streak"] == 1


def test_list_page():
    _every(1, "minutes")
    c = Client()
    c.force_login(AuthUser.objects.create_superuser(f"s{uuid.uuid4().hex[:6]}", password="x"))
    html = c.get("/django-admin/django_celery_beat/periodictask/").content.decode()
    assert "Fon vazifalari" in html and "har daqiqa" in html and "Hozir ishga tushirish" in html


def test_control_center_raises_and_closes_a_failing_job():
    from apps.platform.infrastructure import control_center as cc
    from apps.platform.infrastructure.models import ControlAlert

    t = _every(1, "minutes")
    t.last_run_at = timezone.now()
    t.save()
    for _ in range(3):
        task_health.record(t.name, False, error="ConnectionError: redis")
    found = cc.rule_jobs_failing(cc.settings_obj(), timezone.now(), {})
    assert len(found) == 1 and found[0]["severity"] == "critical" and "3 marta" in found[0]["title"]
    ControlAlert.objects.create(**{k: v for k, v in found[0].items() if k != "store_id"})
    task_health.record(t.name, True, 0.2)  # recovered
    assert cc.rule_jobs_failing(cc.settings_obj(), timezone.now(), {}) == []
    assert cc._resolve_gone(set(), timezone.now()) >= 1
    assert ControlAlert.objects.get(key=f"job_failing:{t.pk}").resolved_by_name == "Avtomatik"
