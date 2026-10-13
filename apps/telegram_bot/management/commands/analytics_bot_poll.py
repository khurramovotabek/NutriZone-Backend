"""Local development without a public webhook: removes the webhook and long-polls getUpdates for NutriZoneAnalyticsBot."""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Long-polls NutriZoneAnalyticsBot updates (dev only -- deletes its webhook first)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process the pending updates once and exit.")

    def handle(self, *args, **options):
        from apps.telegram_bot.infrastructure import analytics_bot as bot

        bot.call("deleteWebhook", {"drop_pending_updates": False})
        offset = None
        self.stdout.write(self.style.SUCCESS(f"Polling @{bot.username()} … Ctrl+C to stop."))
        while True:
            try:
                updates = bot.call("getUpdates", {"offset": offset, "timeout": 0 if options["once"] else 25, "allowed_updates": ["message", "callback_query"]})
            except bot.BotApiError as exc:
                self.stderr.write(str(exc))
                time.sleep(3)
                continue
            for update in updates or []:
                offset = update["update_id"] + 1
                try:
                    bot.handle_update(update)
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"update {update.get('update_id')}: {exc!r}")
            if options["once"]:
                if offset is not None:
                    bot.call("getUpdates", {"offset": offset, "timeout": 0})  # acknowledge
                return
