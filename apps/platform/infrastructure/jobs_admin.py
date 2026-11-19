"""
Dashboard → Tizim → Fon vazifalari (django_celery_beat PeriodicTask) on the premium kit.

Each scheduled job in plain Uzbek ("har kuni 12:00", "har 30 soniyada") with its health: the latest run's result
from task_health (worker signals), "kechikmoqda" when beat has not sent it for 3 of its periods (beat down or the
job disabled by mistake), the last error. Tabs filter by health; actions: run now, enable, disable (beat's own).
The add / change form stays django_celery_beat's own (its schedule pickers).
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import format_html

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure import task_health

DOW = {"0": "yakshanba", "1": "dushanba", "2": "seshanba", "3": "chorshanba", "4": "payshanba", "5": "juma", "6": "shanba", "7": "yakshanba"}
UNITS = {"seconds": ("soniya", 1), "minutes": ("daqiqa", 60), "hours": ("soat", 3600), "days": ("kun", 86400), "microseconds": ("mks", 0.000001)}
STATUS = {  # key -> (label, colour, icon)
    "ok": ("Ishlayapti", "#16a34a", "fa-circle-check"),
    "failing": ("Xato", "#e11d48", "fa-circle-exclamation"),
    "late": ("Kechikmoqda", "#d97706", "fa-hourglass-half"),
    "never": ("Hali ishlamagan", "#64748b", "fa-circle-pause"),
    "off": ("O'chirilgan", "#94a3b8", "fa-power-off"),
}


def _two(v: str) -> str:
    return v.zfill(2) if v.isdigit() else v


def human_schedule(task) -> str:  # noqa: C901 - one branch per schedule shape
    """Beat's schedule as a sentence: interval, crontab (common shapes), clocked or solar."""
    if task.interval_id:
        i = task.interval
        label, _s = UNITS.get(i.period, (i.period, 1))
        return f"har {label}" if i.every == 1 else f"har {i.every} {label}da"
    if task.crontab_id:
        c = task.crontab
        m, h, dom, mon, dow = c.minute, c.hour, c.day_of_month, c.month_of_year, c.day_of_week
        tz = "" if str(c.timezone) in ("Asia/Tashkent", "") else f" ({c.timezone})"
        if m == "*" and h == "*":
            return "har daqiqa" + tz
        if m.startswith("*/") and h == "*":
            return f"har {m[2:]} daqiqada" + tz
        if h == "*" and m.isdigit():
            return f"har soatda, {m}-daqiqada" + tz
        if h.startswith("*/") and m.isdigit():
            return f"har {h[2:]} soatda" + tz
        if m.isdigit() and h.replace(",", "").isdigit():
            at = ", ".join(f"{_two(x)}:{_two(m)}" for x in h.split(","))
            if dom == "*" and mon == "*" and dow == "*":
                return f"har kuni {at}" + tz
            if dom == "*" and mon == "*" and dow in DOW:
                return f"har {DOW[dow]} {at}" + tz
            if dow == "*" and mon == "*" and dom.isdigit():
                return f"har oy {dom}-kuni {at}" + tz
        return f"{m} {h} {dom} {mon} {dow}" + tz
    if task.clocked_id:
        return "bir marta: " + ui.local(task.clocked.clocked_time)
    if task.solar_id:
        return f"quyosh: {task.solar.event}"
    return "—"


def period_seconds(task) -> float | None:
    """How often beat should send the job -- for "kechikmoqda" (late)."""
    if task.interval_id:
        return task.interval.every * UNITS.get(task.interval.period, ("", 1))[1]
    if task.crontab_id:
        c = task.crontab
        if c.minute == "*":
            return 60
        if c.minute.startswith("*/"):
            return 60 * int(c.minute[2:] or 1)
        if c.hour == "*":
            return 3600
        if c.hour.startswith("*/"):
            return 3600 * int(c.hour[2:] or 1)
        if c.day_of_month != "*":
            return 31 * 86400
        if c.day_of_week != "*":
            return 7 * 86400
        return 86400
    return None


def health_of(task, h: dict | None) -> str:
    if not task.enabled:
        return "off"
    h = h or {}
    ok_at, fail_at = parse_datetime(h["ok_at"]) if h.get("ok_at") else None, parse_datetime(h["fail_at"]) if h.get("fail_at") else None
    if fail_at and (not ok_at or fail_at > ok_at):
        return "failing"
    if task.last_run_at is None and not ok_at:
        return "never"
    every = period_seconds(task)
    last = max([d for d in (task.last_run_at, ok_at) if d] or [None]) if (task.last_run_at or ok_at) else None
    if every and last and timezone.now() - last > timedelta(seconds=every * 3 + 120):
        return "late"
    return "ok"


def module_of(name: str) -> str:
    return name.split(":", 1)[0].strip() if ":" in name else "Tizim"


def install() -> None:  # noqa: C901 - the admin class is defined inside (django_celery_beat imports lazily)
    from django_celery_beat.admin import PeriodicTaskAdmin as BeatAdmin
    from django_celery_beat.models import PeriodicTask

    class JobsAdmin(ui.PremiumListMixin, BeatAdmin):
        list_display = ("name", "last_run_at")
        list_filter = ()
        search_fields = ("name", "task")
        ordering = ("name",)
        list_per_page = 100
        nz_icon, nz_tone, nz_title = "fa-gears", "#0891b2", "Fon vazifalari"
        nz_subtitle = ("Sayt orqasida avtomatik ishlaydigan ishlar: Telegram postlar, hisobotlar, eslatmalar, to'lovlarni tekshirish. "
                       "Qizil — oxirgi ishga tushish xato bilan tugagan; sariq — jadval bo'yicha kelmay qolgan.")
        nz_columns = (("Vazifa", ""), ("Jadval", ""), ("Oxirgi ishga tushish", ""), ("Natija", ""), ("Holat", "r"))
        nz_grid = "minmax(280px,2.6fr) minmax(150px,1.2fr) 150px minmax(200px,1.8fr) 130px"
        nz_search = "Vazifa nomi yoki task…"
        nz_empty = ("Vazifa topilmadi", "")
        nz_sorts = (("Nomi", ""), ("Yaqinda ishlagan", "-2"))

        def _health_map(self, tasks):
            data = task_health.read([t.name for t in tasks] + [t.task for t in tasks])
            return {t.pk: data.get(t.name) or data.get(t.task) or {} for t in tasks}

        def _all(self):
            tasks = list(PeriodicTask.objects.select_related("interval", "crontab", "clocked", "solar"))
            h = self._health_map(tasks)
            return tasks, h, {t.pk: health_of(t, h[t.pk]) for t in tasks}

        def get_queryset(self, request):
            qs = super().get_queryset(request).select_related("interval", "crontab", "clocked", "solar")
            want = request.GET.get("nz")
            if want in STATUS:
                _tasks, _h, states = self._all()
                qs = qs.filter(pk__in=[pk for pk, s in states.items() if s == want])
            return qs

        def get_changelist(self, request, **kwargs):
            from django.contrib.admin.views.main import ChangeList

            class _CL(ChangeList):
                def get_filters_params(self, params=None):  # `nz` is the health tab, applied in get_queryset
                    out = super().get_filters_params(params)
                    out.pop("nz", None)
                    return out

            return _CL

        def nz_prepare(self, request, objs):
            self._h = self._health_map(objs)

        def nz_stats(self, request):
            tasks, _h, states = self._all()
            count = {k: sum(1 for s in states.values() if s == k) for k in STATUS}
            beat = max((t.last_run_at for t in tasks if t.last_run_at), default=None)
            beat_late = beat is None or timezone.now() - beat > timedelta(minutes=5)
            base = reverse("admin:django_celery_beat_periodictask_changelist")
            return [ui.stat_card("Faol vazifalar", len(tasks) - count["off"], "#0891b2", "fa-gears", f"{len(tasks)} tadan · {count['off']} o'chirilgan", href=base),
                    ui.stat_card("Xato bilan tugagan", count["failing"], "#e11d48" if count["failing"] else "#16a34a", "fa-circle-exclamation",
                                 "oxirgi ishga tushish" if count["failing"] else "hammasi toza", href=f"{base}?nz=failing"),
                    ui.stat_card("Kechikmoqda", count["late"], "#d97706" if count["late"] else "#16a34a", "fa-hourglass-half", "jadval bo'yicha kelmadi", href=f"{base}?nz=late"),
                    ui.stat_card("Rejalashtiruvchi (beat)", ui.ago(beat) if beat else "—", "#e11d48" if beat_late else "#16a34a", "fa-heart-pulse",
                                 "to'xtagan bo'lishi mumkin!" if beat_late else "oxirgi signal — ishlayapti")]

        def nz_tabs(self, request):
            _t, _h, states = self._all()
            opts = [("", "Barchasi", len(states))] + [(k, v[0], sum(1 for s in states.values() if s == k)) for k, v in STATUS.items()]
            return ui.tabs_for(request, "nz", [o for o in opts if o[0] == "" or o[2]], {k: v[1] for k, v in STATUS.items()})

        def nz_row(self, t):
            h = self._h.get(t.pk, {})
            state = health_of(t, h)
            label, color, icon = STATUS[state]
            short = t.task.rsplit(".", 1)[-1]
            name = format_html('<span class="nzi-user"><span class="nzi-av" style="--c:{}"><i class="fas fa-gear"></i></span><span><b>{}</b><small>{} · <code>{}</code></small></span></span>',
                               color, t.name, module_of(t.name), short)
            last = format_html("<b>{}</b><br><small class=\"nzi-muted\">{}</small>", ui.ago(t.last_run_at), ui.local(t.last_run_at)) if t.last_run_at else ui.muted("hali yo'q")
            if state == "failing":
                result = format_html('<span class="nzi-pill" style="--t:#e11d48">{} marta ketma-ket</span><br><small style="color:#e11d48" title="{}">{}</small>',
                                     h.get("streak", 1), h.get("error", ""), (h.get("error") or "")[:90])
            elif h.get("ok_at"):
                rt = h.get("runtime")
                result = format_html('<small>muvaffaqiyatli · {}{}</small>', ui.ago(parse_datetime(h["ok_at"])), f" · {rt} s" if rt is not None else "")
            else:
                result = ui.muted("natija hali yozilmagan")
            return [name, format_html("<span>{}</span>", human_schedule(t)), last, result,
                    format_html('<span class="nzi-pill" style="--t:{}"><i class="fas {}" aria-hidden="true"></i> {}</span>', color, icon, label)]

        # beat's own actions, in the staff's language
        @admin.action(description="Hozir ishga tushirish")
        def run_tasks(self, request, queryset):
            return super().run_tasks(request, queryset)

        @admin.action(description="Yoqish")
        def enable_tasks(self, request, queryset):
            return super().enable_tasks(request, queryset)

        @admin.action(description="O'chirish (to'xtatish)")
        def disable_tasks(self, request, queryset):
            return super().disable_tasks(request, queryset)

        actions = ("run_tasks", "enable_tasks", "disable_tasks")

    if admin.site.is_registered(PeriodicTask):
        admin.site.unregister(PeriodicTask)
    admin.site.register(PeriodicTask, JobsAdmin)
