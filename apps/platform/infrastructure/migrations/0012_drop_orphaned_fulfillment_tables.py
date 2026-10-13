"""
Real, closed cleanup: the Fulfillment module (Shipment,
DeliveryAttempt, TrackingEvent, ReturnShipment) was removed entirely
from the project (INSTALLED_APPS, all Python source, and every real
code-level dependency other apps had on it -- all confirmed via a
full test-suite pass with zero failures before this migration was
written). Its tables and `django_migrations` bookkeeping rows were
left behind as orphans in the database, since Django cannot generate
a normal "unapply" migration for an app that no longer exists in
INSTALLED_APPS.

Same rationale and safety guarantees as this app's own
0011_drop_orphaned_store_wallet_loyalty_tables migration: every DROP
TABLE uses IF EXISTS, and CASCADE only accounts for foreign keys
between these tables themselves (e.g.
fulfillment_return_shipment_lines -> fulfillment_return_shipments) --
no other app's tables reference any of these 7 tables directly
(bare UUID "reference by ID" columns only, per this project's own
documented modular-monolith convention).
"""
from django.db import migrations

_ORPHANED_TABLES = [
    "fulfillment_delivery_attempts",
    "fulfillment_outbox_events",
    "fulfillment_return_shipment_lines",
    "fulfillment_return_shipments",
    "fulfillment_shipment_lines",
    "fulfillment_shipments",
    "fulfillment_tracking_events",
]


def drop_orphaned_tables(apps, schema_editor) -> None:
    with schema_editor.connection.cursor() as cursor:
        for table_name in _ORPHANED_TABLES:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
        cursor.execute("DELETE FROM django_migrations WHERE app = 'fulfillment';")


class Migration(migrations.Migration):
    dependencies = [
        ("platform", "0011_drop_orphaned_store_wallet_loyalty_tables"),
    ]

    operations = [
        migrations.RunPython(
            drop_orphaned_tables,
            reverse_code=migrations.RunPython.noop,
            # Deliberately irreversible in spirit -- see 0011's own,
            # identical comment for the full rationale.
        ),
    ]
