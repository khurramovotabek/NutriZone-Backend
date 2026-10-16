"""Receipts registry: every POS sale, online order and manual receipt, printable, with a fiscal (OFD) layer."""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ReceiptsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.receipts"
    label = "receipts"
    verbose_name = _("Cheklar")

    def ready(self) -> None:
        from apps.receipts.infrastructure import admin, models, signals  # noqa: F401
