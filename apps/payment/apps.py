from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payment"
    label = "payment"
    verbose_name = _("To'lovlar")

    def ready(self) -> None:
        from apps.payment.infrastructure import admin, history, models  # noqa: F401 -- history: PaymentEvent signals -- registers models.py, which Django's default discovery cannot reach at this project's infrastructure/models.py location (confirmed: even apps.geo's own models_module reports None)
        from shared.event_contracts import payment as payment_event_contracts  # noqa: F401
