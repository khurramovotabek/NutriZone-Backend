"""
Real, closed cleanup: the Store, Wallet, and Loyalty modules were
removed entirely from the project (INSTALLED_APPS, all Python source,
and every real code-level dependency other apps had on them -- all
confirmed via a full test-suite pass with zero failures before this
migration was written). Their tables and `django_migrations` bookkeeping
rows were left behind as orphans in the database, since Django cannot
generate a normal "unapply" migration for an app that no longer exists
in INSTALLED_APPS.

Every DROP TABLE uses IF EXISTS -- this migration is safe to run
against a database that never had these tables in the first place
(e.g. a fresh environment), and safe to re-run if it is ever applied
twice. CASCADE is used only because these tables may still carry
now-orphaned foreign key constraints from each other (e.g.
store_warehouses -> store_stores) -- no other app's tables reference
any of these 37 tables directly (confirmed: nothing outside
Store/Wallet/Loyalty ever used a real Django ForeignKey to them, only
bare UUID "reference by ID" columns, per this project's own documented
modular-monolith convention).
"""
from django.db import migrations

_ORPHANED_TABLES = [
    # Loyalty
    "loyalty_memberships",
    "loyalty_order_reward_cursor",
    "loyalty_order_reward_records",
    "loyalty_outbox_events",
    "loyalty_return_reversal_cursor",
    "loyalty_return_reward_reversal_records",
    "loyalty_tier_change_entries",
    # Store (including its own Warehouse/Delivery/Branch concepts)
    "store_branches",
    "store_contacts",
    "store_coverage_cities",
    "store_coverage_districts",
    "store_coverage_polygons",
    "store_delivery_coverages",
    "store_employees",
    "store_holiday_calendars",
    "store_holidays",
    "store_media",
    "store_media_assets",
    "store_outbox_events",
    "store_pickup_points",
    "store_role_assignments",
    "store_schedules",
    "store_services",
    "store_settings",
    "store_shelves",
    "store_storage_bins",
    "store_storage_zones",
    "store_stores",
    "store_warehouses",
    "store_working_hours",
    # Wallet
    "wallet_cashbacks",
    "wallet_ledger_entries",
    "wallet_outbox_events",
    "wallet_reservations",
    "wallet_reward_accounts",
    "wallet_reward_transactions",
    "wallet_wallets",
]


def drop_orphaned_tables(apps, schema_editor) -> None:
    with schema_editor.connection.cursor() as cursor:
        for table_name in _ORPHANED_TABLES:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
        # Also clears the removed apps' own migration history rows --
        # otherwise `django_migrations` keeps claiming migrations are
        # "applied" for apps that no longer exist in INSTALLED_APPS.
        cursor.execute("DELETE FROM django_migrations WHERE app IN ('store', 'wallet', 'loyalty');")


class Migration(migrations.Migration):
    dependencies = [
        ("platform", "0010_remove_banner_image"),
    ]

    operations = [
        migrations.RunPython(
            drop_orphaned_tables,
            reverse_code=migrations.RunPython.noop,
            # Deliberately irreversible in spirit: the real table
            # schemas, constraints, and any data are gone the moment
            # the forward operation runs. A reverse that merely
            # recreated empty tables would be actively misleading --
            # it would look like a successful rollback while silently
            # losing everything that was in these tables before
            # deletion. Django's own no-op is used here only because
            # RunPython has no "forbid reverse" primitive; reversing
            # this migration is never a safe operation.
        ),
    ]
