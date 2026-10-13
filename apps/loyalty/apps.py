"""
Django AppConfig for the `loyalty` bounded context -- tiered cashback
("coins") and the customer wallet that holds them.

1 so'm of qualifying spend is worth exactly 1 coin at the customer's
tier percentage. The wallet is an append-only ledger
(`WalletTransaction`) with a cached balance on `Wallet`; every coin
movement is one ledger row, so a balance can always be re-derived and
audited. Coins will later be spendable on promo codes and as a checkout
discount -- the ledger already models debits (`spend`) for that.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LoyaltyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.loyalty"
    label = "loyalty"
    verbose_name = _("Loyalty & Wallet")

    def ready(self) -> None:
        from apps.loyalty.infrastructure import (
            admin,  # noqa: F401 -- registers admin.py
            signals,  # noqa: F401 -- connects the order-status listener
            tasks,  # noqa: F401 -- registers the reconcile task with Celery
        )
