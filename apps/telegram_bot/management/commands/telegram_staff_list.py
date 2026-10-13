from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "List Telegram staff members (authorized to confirm/cancel orders from the Orders Channel)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Include revoked (inactive) staff members too.")

    def handle(self, *args, **options):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        qs = TelegramStaffMember.objects.all().order_by("-created_at")
        if not options["all"]:
            qs = qs.filter(is_active=True)

        rows = list(qs)
        if not rows:
            self.stdout.write("No staff members found.")
            return

        for row in rows:
            status = "active" if row.is_active else "revoked"
            name = row.full_name or "(no name)"
            self.stdout.write(f"{row.telegram_user_id}\t{name}\t{status}\t{row.created_at:%Y-%m-%d}")
