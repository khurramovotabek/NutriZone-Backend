from decimal import Decimal

from django.db import migrations


def backfill(apps, schema_editor):
    """Existing sales get their payment split (one method) and every already-refunded sale its return record."""
    Sale = apps.get_model("pos", "SaleModel")
    Line = apps.get_model("pos", "SaleLineItemModel")
    Refund = apps.get_model("pos", "SaleRefundModel")
    Tx = apps.get_model("loyalty", "WalletTransaction")
    for sale in Sale.objects.filter(status__in=["completed", "refunded"]):
        lines = list(Line.objects.filter(sale_id=sale.id))
        gross = sum((li.unit_price_amount * li.quantity for li in lines), Decimal("0"))
        paid = max(Decimal("0"), gross - sale.discount_amount - sale.coins_redeemed + sale.delivery_fee_amount)
        method = "uzcard" if sale.payment_method == "card" else sale.payment_method
        sale.payments = [{"method": method, "amount": f"{paid:.2f}"}] if paid > 0 else []
        fields = ["payments"]
        if sale.status == "refunded" and not Refund.objects.filter(sale_id=sale.id).exists():
            reversed_ = Tx.objects.filter(order_id=sale.id, kind="reversal").values_list("amount", flat=True).first() or 0
            refund = Refund.objects.create(
                sale_id=sale.id, number=f"{sale.receipt_number or str(sale.id)[:8].upper()}-R1", cashier_id=sale.cashier_id,
                cash_session_id=sale.refund_cash_session_id, reason="",
                lines=[{"line_id": str(li.id), "variant_id": str(li.product_variant_id) if li.product_variant_id else None, "product_id": str(li.product_id),
                        "quantity": li.quantity, "unit_price": f"{li.unit_price_amount:.2f}", "value": f"{li.unit_price_amount * li.quantity:.2f}"} for li in lines],
                value=paid + sale.coins_redeemed, amount=paid, coins=sale.coins_redeemed,
                split={method: f"{paid:.2f}"} if paid > 0 else {}, cashback_reversed=abs(reversed_),
            )
            if sale.refunded_at:
                Refund.objects.filter(pk=refund.pk).update(created_at=sale.refunded_at)
            Line.objects.filter(sale_id=sale.id).update(refunded_quantity=models_F("quantity"))
            sale.refunded_amount, sale.refunded_coins, sale.refunded_split = paid, sale.coins_redeemed, refund.split
            fields += ["refunded_amount", "refunded_coins", "refunded_split"]
        Sale.objects.filter(pk=sale.pk).update(**{f: getattr(sale, f) for f in fields})


def models_F(name):
    from django.db.models import F

    return F(name)


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0008_split_payments_partial_refunds"),
        ("loyalty", "0009_wallets_for_everyone"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
