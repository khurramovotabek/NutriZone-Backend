"""Django AppConfig for the `coupons` bounded context.

Maps 1:1 to Domain Architecture Specification 2.10 and to the
`coupons` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CouponsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.coupons"
    label = "coupons"
    verbose_name = _("Coupons")
