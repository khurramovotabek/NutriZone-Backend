"""Sends one NutriZoneAnalyticsBot report now (or prints it with --dry-run)."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a report: bugun | kecha | hafta | oy | moliya | filiallar | mahsulotlar | ombor | 7kun | 30kun | shuoy. --scheduled uses the de-duplicated path."

    def add_arguments(self, parser):
        parser.add_argument("report", nargs="?", default="bugun")
        parser.add_argument("--chat", action="append", help="Recipient chat id (default: TELEGRAM_ANALYTICS_CHAT_IDS).")
        parser.add_argument("--dry-run", action="store_true", help="Print the Telegram HTML instead of sending.")
        parser.add_argument("--scheduled", action="store_true", help="Run exactly what the beat task runs (today/week/month, once per period).")

    def handle(self, *args, **options):
        from apps.telegram_bot.infrastructure import analytics_bot as bot

        report = bot.ALIASES.get(options["report"], options["report"])
        if options["scheduled"]:
            kind = {"bugun": "today", "hafta": "week", "oy": "month"}.get(report, report)
            self.stdout.write(str(bot.send_scheduled(kind)))
            return
        if report not in bot.REPORTS:
            raise CommandError(f"Unknown report '{report}'.")
        if options["dry_run"]:
            for i, text in enumerate(bot.build_messages(report), 1):
                self.stdout.write(f"--- message {i} ({len(text)} chars) ---\n{text}\n")
            return
        self.stdout.write(str(bot.send_now(report, options["chat"])))
