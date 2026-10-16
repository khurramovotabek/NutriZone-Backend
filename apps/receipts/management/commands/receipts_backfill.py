"""Adds every completed POS sale and every delivered / completed online order that has no receipt yet (idempotent)."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backfill the receipts registry from completed POS sales and delivered online orders."

    def handle(self, *args, **options):
        from apps.ordering.infrastructure.models import OrderModel
        from apps.pos.infrastructure.models import SaleModel
        from apps.receipts.infrastructure import builders
        from apps.receipts.infrastructure.models import Receipt

        done_sales = set(Receipt.objects.exclude(sale_id=None).values_list("sale_id", flat=True))
        done_orders = set(Receipt.objects.exclude(order_id=None).values_list("order_id", flat=True))
        made = 0
        for sale in SaleModel.objects.filter(status__in=("completed", "refunded"), receipt_number__isnull=False).exclude(id__in=done_sales).order_by("completed_at"):
            made += bool(builders.from_sale(sale))
        for order in OrderModel.objects.filter(status__in=("delivered", "completed")).exclude(id__in=done_orders).order_by("placed_at"):
            made += bool(builders.from_order(order))
        self.stdout.write(self.style.SUCCESS(f"Receipts added: {made}"))
