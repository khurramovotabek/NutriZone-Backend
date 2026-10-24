"""Moliya: money accounts, expenses/income, P&L, cash flow, budget and debts -- on top of the sales, purchase and payroll data the system already keeps."""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"
    label = "finance"
    verbose_name = _("Moliya")

    def ready(self) -> None:
        from apps.finance.infrastructure import admin, models  # noqa: F401
