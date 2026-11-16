"""Gives the opening gift to customers who already have a confirmed (or later) order, earliest first order first.

    python manage.py grant_signup_bonus --existing --dry-run   # who would get it
    python manage.py grant_signup_bonus --existing             # pay (stops when the slots run out)
"""
from django.core.management.base import BaseCommand

# a real purchase: confirmed or further along (a cancelled-before-confirm or unpaid order doesn't count)
BOUGHT = ("confirmed", "processing", "shipped", "delivered", "completed", "returned")


class Command(BaseCommand):
    help = "Opening-gift backfill for customers who already ordered (earliest first order first, until the limit is reached)."

    def add_arguments(self, parser):
        parser.add_argument("--existing", action="store_true", help="Required: confirms the backfill of existing buyers.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--no-notify", action="store_true", help="Credit silently (no inbox/Telegram message).")

    def handle(self, *args, existing=False, dry_run=False, no_notify=False, **opts):
        from django.db.models import Min

        from apps.ordering.infrastructure.models import OrderModel
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
        buyers = (OrderModel.objects.filter(customer_id__isnull=False, status__in=BOUGHT).exclude(customer_id__in=have)
                  .values("customer_id").annotate(first=Min("placed_at")).order_by("first").values_list("customer_id", flat=True))
        slots = st.remaining if st.remaining is not None else len(buyers)
        todo = list(buyers[:slots])
        self.stdout.write(f"{len(todo)} customer(s) {'would get' if dry_run else 'get'} {st.coins} coins (slots left: {st.remaining}).")
        if dry_run:
            return
        paid = 0
        for user_id in todo:
            row = signup_bonus.grant(user_id, source="backfill", notify_customer=not no_notify)
            paid += row is not None
        self.stdout.write(self.style.SUCCESS(f"Paid {paid}. Now granted: {signup_bonus.status().granted}."))
