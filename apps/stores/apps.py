"""Django AppConfig for the `stores` bounded context.

A real product requirement: physical/partner stores ("do'kon"), each
with an owner (an ordinary storefront customer account, identity.User
-- never a Dashboard staff account), managed media (images/video),
dynamic weekly working hours, contact details, a map location, and a
many-to-many stock relationship with existing products/variants (a
store never creates products -- only sets how many of an existing
product it carries).

Dashboard staff manage every store (assign/reassign owners, edit any
field) via the standard Django admin permission system -- no
per-owner Django group is needed, since the owner customer never logs
into the Dashboard at all; they manage their store from the
storefront's own authenticated "My Store" account page instead.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StoresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.stores"
    label = "stores"
    verbose_name = _("Stores")

    def ready(self) -> None:
        from apps.stores.infrastructure import admin  # noqa: F401 -- registers admin.py, matching every other module's infrastructure/admin.py location
        from apps.stores.infrastructure import owner_invite

        owner_invite.install()
