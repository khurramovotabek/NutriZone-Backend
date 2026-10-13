"""
One idempotent setup step for NutriZoneAnalyticsBot (also run automatically on web start when the bot is configured):
  * the three report schedules in django_celery_beat (Asia/Tashkent) -- created or corrected, never duplicated;
  * the bot's command menu and description;
  * the webhook, when PUBLIC_BASE_URL is set (skip with --no-webhook, e.g. while using analytics_bot_poll locally).
"""
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

# name → (report kind, crontab: minute, hour, day_of_week, day_of_month)
SCHEDULES = {
    "Analytics bot: kunlik hisobot (23:59)": ("today", "59", "23", "*", "*"),
    "Analytics bot: haftalik hisobot (dushanba 09:00)": ("week", "0", "9", "1", "*"),
    "Analytics bot: oylik hisobot (1-kun 09:00)": ("month", "5", "9", "*", "1"),
}
TASK = "telegram_bot.analytics_report"


def ensure_schedules() -> list[str]:
    import json

    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    done = []
    for name, (kind, minute, hour, dow, dom) in SCHEDULES.items():
        cron, _ = CrontabSchedule.objects.get_or_create(minute=minute, hour=hour, day_of_week=dow, day_of_month=dom, month_of_year="*", timezone="Asia/Tashkent")
        PeriodicTask.objects.update_or_create(name=name, defaults={
            "task": TASK, "crontab": cron, "interval": None, "args": json.dumps([kind]), "kwargs": "{}", "enabled": True, "queue": "default",
            "description": "apps/telegram_bot/infrastructure/analytics_bot.py -- deduplicated per period and recipient",
        })
        done.append(name)
    # any other row pointing at the same task would send a second copy -- the named rows above are the only ones
    PeriodicTask.objects.filter(task=TASK).exclude(name__in=list(SCHEDULES)).delete()
    return done


class Command(BaseCommand):
    help = "Creates NutriZoneAnalyticsBot's report schedules, sets its command menu and (optionally) its webhook."

    def add_arguments(self, parser):
        parser.add_argument("--no-webhook", action="store_true", help="Don't register the webhook.")

    def handle(self, *args, **options):
        from django.conf import settings

        from apps.telegram_bot.infrastructure import analytics_bot

        for name in ensure_schedules():
            self.stdout.write(self.style.SUCCESS(f"Schedule ok: {name}"))
        if not analytics_bot.is_live():
            self.stdout.write(self.style.WARNING("TELEGRAM_ANALYTICS_BOT_TOKEN not set (or gateway not live) -- skipped the bot menu and webhook."))
            return
        analytics_bot.set_commands()
        self.stdout.write(self.style.SUCCESS("Bot commands and description set."))
        if not analytics_bot.recipients():
            self.stdout.write(self.style.WARNING("TELEGRAM_ANALYTICS_CHAT_IDS is empty -- nobody will receive reports yet."))
        if not options["no_webhook"] and getattr(settings, "PUBLIC_BASE_URL", None):
            call_command("telegram_set_webhook", bot="analytics")
