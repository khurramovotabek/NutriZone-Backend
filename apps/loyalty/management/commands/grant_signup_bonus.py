"""Gives the sign-up gift to customers who registered before the campaign started, oldest account first.

    python manage.py grant_signup_bonus --existing --dry-run   # who would get it
    python manage.py grant_signup_bonus --existing             # pay (stops when the slots run out)
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sign-up gift backfill for existing active customers (oldest first, until the limit is reached)."

    def add_arguments(self, parser):
        parser.add_argument("--existing", action="store_true", help="Required: confirms the backfill of existing accounts.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--no-notify", action="store_true", help="Credit silently (no inbox/Telegram message).")

    def handle(self, *args, existing=False, dry_run=False, no_notify=False, **opts):
        from apps.identity.infrastructure.models import User
        from apps.loyalty.infrastructure import signup_bonus
        from apps.loyalty.infrastructure.models import SignupBonusGrant

        if not existing:
            self.stderr.write("Pass --existing to confirm.")
            return
        st = signup_bonus.status()
        if not st.is_open:
            self.stdout.write(f"Campaign closed (enabled={st.enabled}, granted={st.granted}/{st.limit}).")
            return
        have = set(SignupBonusGrant.objects.values_list("user_id", flat=True))
        users = User.objects.filter(status="active").exclude(id__in=have).order_by("created_at").values_list("id", "phone_number")
        slots = st.remaining if st.remaining is not None else len(users)
        todo = list(users[:slots])
        self.stdout.write(f"{len(todo)} customer(s) {'would get' if dry_run else 'get'} {st.coins} coins (slots left: {st.remaining}).")
        if dry_run:
            return
        paid = 0
        for user_id, _phone in todo:
            row = signup_bonus.grant(user_id, source="backfill", notify_customer=not no_notify)
            paid += row is not None
        self.stdout.write(self.style.SUCCESS(f"Paid {paid}. Now granted: {signup_bonus.status().granted}."))
