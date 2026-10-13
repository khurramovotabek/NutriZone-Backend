"""
Phase 15F: staff enrollment tooling.

Confirmed real gap from Phase 15E's own final report: TelegramStaffMember
existed with no way to populate it except direct database/shell access.
This command is that missing, real enrollment path -- deliberately a
CLI command run by an operator who already has server access, not a
Telegram bot command or a self-service web form, matching this
project's own established principle (stated directly in
TelegramStaffMember's own docstring) that staff authorization must
never be self-granted.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Enroll or revoke a Telegram staff member (authorized to confirm/cancel orders from the Orders Channel)."

    def add_arguments(self, parser):
        parser.add_argument("telegram_user_id", type=int, help="The Telegram user's numeric ID (not their @username, which can change).")
        parser.add_argument("--name", type=str, default="", help="Full name, for readability in listings and logs.")
        parser.add_argument("--revoke", action="store_true", help="Revoke (deactivate) this staff member instead of enrolling them.")
        parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt (for non-interactive/scripted use).")

    def handle(self, *args, **options):
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        telegram_user_id = options["telegram_user_id"]
        name = options["name"]
        revoke = options["revoke"]
        skip_confirm = options["yes"]

        existing = TelegramStaffMember.objects.filter(telegram_user_id=telegram_user_id).first()

        if revoke:
            if existing is None:
                raise CommandError(f"No staff member found with telegram_user_id={telegram_user_id}.")
            if not existing.is_active:
                self.stdout.write(self.style.WARNING(f"telegram_user_id={telegram_user_id} ({existing.full_name}) is already inactive."))
                return
            if not skip_confirm and not self._confirm(f"Revoke staff access for telegram_user_id={telegram_user_id} ({existing.full_name})?"):
                self.stdout.write("Cancelled.")
                return
            existing.is_active = False
            existing.save(update_fields=["is_active"])
            self.stdout.write(self.style.SUCCESS(f"Revoked staff access for telegram_user_id={telegram_user_id}."))
            return

        if existing is not None and existing.is_active:
            self.stdout.write(self.style.WARNING(f"telegram_user_id={telegram_user_id} ({existing.full_name}) is already an active staff member."))
            return

        prompt = f"Grant order confirm/cancel access to telegram_user_id={telegram_user_id}"
        prompt += f" ({name})?" if name else "?"
        if not skip_confirm and not self._confirm(prompt):
            self.stdout.write("Cancelled.")
            return

        if existing is not None:
            existing.is_active = True
            if name:
                existing.full_name = name
            existing.save(update_fields=["is_active", "full_name"])
        else:
            TelegramStaffMember.objects.create(telegram_user_id=telegram_user_id, full_name=name, is_active=True)

        self.stdout.write(self.style.SUCCESS(f"Enrolled telegram_user_id={telegram_user_id} as an authorized staff member."))

    def _confirm(self, prompt: str) -> bool:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        return answer in ("y", "yes")
