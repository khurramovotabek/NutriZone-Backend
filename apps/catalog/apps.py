"""Django AppConfig for the `catalog` bounded context.

Maps 1:1 to Domain Architecture Specification 2.2 and to the
`catalog` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = _("Catalog")
