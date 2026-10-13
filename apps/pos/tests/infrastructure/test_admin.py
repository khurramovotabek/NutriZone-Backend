"""
**`SaleAdmin` does NOT override `has_add_permission`/
`has_change_permission`/`has_delete_permission`; `PosOutboxEventAdmin`
DOES** -- confirmed by direct inspection during this phase's own Step
2, matching the exact same distinction already established for every
prior module's own `test_admin.py`. Calling `SaleAdmin`'s inherited
methods with `request=None` would crash against Django's real,
un-overridden base implementation (which accesses `request.user`) --
exactly the mistake already caught and fixed twice in this build
(Chat, Analytics). Every check on `SaleAdmin` below is a safe,
structural check instead.
"""
from __future__ import annotations

import pytest
from django.contrib import admin

from apps.pos.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoAdmin:
    def test_the_remaining_admin_registration_present(self):
        """PosOutboxEvent removed from the Dashboard (see test_outbox_event_removed_from_dashboard) -- only the customer-facing SaleModel remains."""
        assert orm.SaleModel in admin.site._registry

    def test_sale_line_item_has_no_top_level_registration(self):
        """The certified owned-entity boundary -- SaleLineItem must never become independently queryable admin infrastructure."""
        assert orm.SaleLineItemModel not in admin.site._registry

    def test_sale_admin_does_not_override_permission_methods(self):
        """A structural check, not a behavioral call -- see this module's own docstring for why calling has_add_permission(None) on SaleAdmin would be unsafe."""
        admin_cls = admin.site._registry[orm.SaleModel].__class__
        assert "has_add_permission" not in admin_cls.__dict__
        assert "has_change_permission" not in admin_cls.__dict__
        assert "has_delete_permission" not in admin_cls.__dict__

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: PosOutboxEvent removed from the Dashboard entirely -- read-only, system-internal event-log data."""
        assert orm.PosOutboxEvent not in admin.site._registry

    def test_only_export_actions_registered_on_sale_admin(self):
        """Sales are immutable records: the only bulk actions export them (Excel / CSV), none change them."""
        admin_instance = admin.site._registry[orm.SaleModel]
        assert list(admin_instance.actions) == ["export_selected_xlsx", "export_selected_csv"]
