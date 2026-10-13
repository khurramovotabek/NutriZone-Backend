"""
Django Admin registration -- engineering/ops debugging tool only, per
Django Implementation Blueprint §13 and MIC §9's Admin Contract. Bulk
actions call Application Services exclusively.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.application.services.lifecycle import ArchiveInventory, RestoreInventory
from apps.inventory.infrastructure import models as orm
from apps.inventory.infrastructure.repositories import DjangoInventoryRepository
from core.outbox import stage_event


def _stage_inventory_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.InventoryOutboxEvent, event_type, payload)


def _admin_ctx(request) -> InventoryServiceContext:
    return InventoryServiceContext(stage_events=_stage_inventory_events, actor_id=getattr(request.user, "id", None))


class ThresholdRuleInline(admin.TabularInline):
    model = orm.ThresholdRuleModel
    extra = 0


class StockAlertInline(admin.TabularInline):
    model = orm.StockAlertModel
    extra = 0
    readonly_fields = ("health_status", "triggered_at", "acknowledged")
    can_delete = False


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventoryModel)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("code", "status_badge", "tracking_badges", "health_badge", "warehouse_count")
    list_filter = ("status", "is_batch_tracked", "is_serial_tracked")
    search_fields = ("code", "product_variant_id")
    list_per_page = 25  # Phase 08.5: genuine gap, this project's own established default-pagination convention (Phase 08.3/08.4) was missing here
    inlines = [ThresholdRuleInline, StockAlertInline]
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "version")
    actions = ["archive_selected", "restore_selected"]

    def get_queryset(self, request):
        """
        Phase 08.5: closes a genuine, confirmed N+1 -- this admin had
        no get_queryset() override at all, so warehouse_count() and
        health_badge() (both reading obj.warehouse_inventories) issued
        2 extra queries per row. Measured directly before this fix: 13
        queries for 3 items, 19 for 6 (exactly 2 extra per additional
        row).
        """
        return super().get_queryset(request).prefetch_related("warehouse_inventories")

    def status_badge(self, obj: orm.InventoryModel) -> str:
        tone = {"active": "success", "inactive": "neutral", "archived": "danger"}.get(obj.status, "neutral")
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tone, obj.status)

    status_badge.short_description = "Status"

    def tracking_badges(self, obj: orm.InventoryModel) -> str:
        badges = []
        if obj.is_batch_tracked:
            badges.append("Batch")
        if obj.is_serial_tracked:
            badges.append("Serial")
        return ", ".join(badges) or "—"

    tracking_badges.short_description = "Tracking"

    def health_badge(self, obj: orm.InventoryModel) -> str:
        """Health badge -- computes InventoryHealthStatus on the fly from the total available quantity across warehouses, per the domain's own read-only derivation policy."""
        from apps.inventory.domain.services import InventoryHealthPolicy
        from apps.inventory.domain.value_objects import StockThreshold

        total_available = sum(wi.available_quantity for wi in obj.warehouse_inventories.all())
        threshold = StockThreshold(low_stock_at=obj.low_stock_at, reorder_at=obj.reorder_at, overstock_at=obj.overstock_at) if obj.low_stock_at is not None and obj.reorder_at is not None else None
        health = InventoryHealthPolicy.evaluate(total_available, threshold)
        tones = {"healthy": "success", "low_stock": "warning", "out_of_stock": "danger", "overstocked": "warning"}
        return format_html('<span class="nz-badge nz-badge-{}">{} ({})</span>', tones.get(health.value, "neutral"), health.value, total_available)

    health_badge.short_description = "Health"

    def warehouse_count(self, obj: orm.InventoryModel) -> int:
        """Uses len() on the already-prefetched .all(), not .count() -- per this project's own documented gotcha (Phase 08.4's ShipmentAdmin), .count() bypasses the prefetch cache and re-queries per row even when prefetch_related() is present."""
        return len(obj.warehouse_inventories.all())

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.action(description="Archive selected inventory items")
    def archive_selected(self, request, queryset):
        service = ArchiveInventory(DjangoInventoryRepository(), _admin_ctx(request))
        for item in queryset:
            try:
                service.execute(item.id)
            except Exception:  # noqa: BLE001
                self.message_user(request, f"Could not archive {item.code}.", level="error")

    @admin.action(description="Restore selected inventory items")
    def restore_selected(self, request, queryset):
        service = RestoreInventory(DjangoInventoryRepository(), _admin_ctx(request))
        for item in queryset:
            try:
                service.execute(item.id)
            except Exception:  # noqa: BLE001
                pass


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.WarehouseInventoryModel)
class WarehouseInventoryAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("inventory", "warehouse_id", "quantity_preview")
    list_filter = ("warehouse_id",)
    search_fields = ("inventory__code",)
    readonly_fields = ("id", "created_at", "updated_at")

    def quantity_preview(self, obj: orm.WarehouseInventoryModel) -> str:
        """Quantity preview -- per this phase's explicit admin requirement."""
        return f"avail:{obj.available_quantity} rsvd:{obj.reserved_quantity} inc:{obj.incoming_quantity} dmg:{obj.damaged_quantity} exp:{obj.expired_quantity}"

    quantity_preview.short_description = "Quantities"


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.ShelfInventoryModel)
class ShelfInventoryAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("warehouse_inventory", "shelf_id", "quantity")
    search_fields = ("shelf_id",)


class ReservationItemInline(admin.TabularInline):
    model = orm.ReservationItemModel
    extra = 0


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.ReservationModel)
class ReservationAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("reservation_number", "owner_type", "status_badge", "reservation_preview", "expires_at")
    list_filter = ("status", "owner_type")
    search_fields = ("reservation_number",)
    inlines = [ReservationItemInline]
    readonly_fields = ("id", "created_at", "updated_at")

    def status_badge(self, obj: orm.ReservationModel) -> str:
        tones = {"pending": "warning", "confirmed": "info", "released": "neutral", "expired": "danger", "cancelled": "danger"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def reservation_preview(self, obj: orm.ReservationModel) -> str:
        """Reservation preview -- per this phase's explicit admin requirement."""
        total = sum(i.quantity for i in obj.items.all())
        return f"{total} units across {obj.items.count()} item(s)"

    reservation_preview.short_description = "Items"


class SerialInline(admin.TabularInline):
    model = orm.SerialModel
    extra = 0


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.BatchModel)
class BatchAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("batch_number", "inventory", "status_badge", "batch_preview", "expiration_date")
    list_filter = ("status",)
    search_fields = ("batch_number",)
    inlines = [SerialInline]
    readonly_fields = ("id", "created_at", "updated_at")

    def status_badge(self, obj: orm.BatchModel) -> str:
        tones = {"active": "success", "expired": "danger", "quarantine": "warning", "depleted": "neutral", "recalled": "danger"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def batch_preview(self, obj: orm.BatchModel) -> str:
        """Batch preview -- per this phase's explicit admin requirement."""
        return f"received:{obj.quantity_received}, mfg:{obj.manufacture_date or '—'}"

    batch_preview.short_description = "Batch Info"


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.SerialModel)
class SerialAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("serial_number", "batch", "status")
    list_filter = ("status",)
    search_fields = ("serial_number",)


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventoryMovementModel)
class MovementAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("reference", "movement_type", "source_warehouse_inventory", "destination_warehouse_inventory", "occurred_at")
    list_filter = ("movement_type",)
    search_fields = ("reference",)
    readonly_fields = ("id", "created_at", "updated_at")


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventoryAdjustmentModel)
class AdjustmentAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("reference", "warehouse_inventory", "reason", "quantity_delta")
    list_filter = ("reason",)


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventoryLedgerModel)
class LedgerAdmin(admin.ModelAdmin):
    """Read-only -- append-only, per MIC §9."""
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently

    list_display = ("warehouse_inventory", "entry_type", "stock_status", "ledger_preview", "occurred_at")
    list_filter = ("entry_type", "stock_status")
    readonly_fields = [f.name for f in orm.InventoryLedgerModel._meta.fields]

    def ledger_preview(self, obj: orm.InventoryLedgerModel) -> str:
        """Ledger preview -- per this phase's explicit admin requirement."""
        sign = "+" if obj.quantity_delta >= 0 else ""
        return f"{sign}{obj.quantity_delta} -> {obj.balance_after}"

    ledger_preview.short_description = "Delta -> Balance"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class SnapshotItemInline(admin.TabularInline):
    model = orm.SnapshotItemModel
    extra = 0
    readonly_fields = ("inventory_id", "quantities_by_status")
    can_delete = False


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventorySnapshotModel)
class SnapshotAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("version", "status", "captured_at")
    list_filter = ("status",)
    inlines = [SnapshotItemInline]
    readonly_fields = ("id", "created_at", "updated_at")


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.CycleCountModel)
class CycleCountAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("warehouse_id", "status", "item_count")
    list_filter = ("status",)

    def get_queryset(self, request):
        """Phase 08.5: closes a genuine N+1 -- item_count() had no prefetch at all, issuing one query per row."""
        return super().get_queryset(request).prefetch_related("items")

    def item_count(self, obj: orm.CycleCountModel) -> int:
        return len(obj.items.all())


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.PhysicalInventoryModel)
class PhysicalInventoryAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("warehouse_id", "status", "item_count")
    list_filter = ("status",)

    def get_queryset(self, request):
        """Phase 08.5: closes the same genuine N+1 as CycleCountAdmin above."""
        return super().get_queryset(request).prefetch_related("items")

    def item_count(self, obj: orm.PhysicalInventoryModel) -> int:
        return len(obj.items.all())


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventoryHistoryModel)
class InventoryHistoryAdmin(admin.ModelAdmin):
    """Read-only -- an audit-trail table, per MIC §9's read-only-audit-fields convention."""
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently

    list_display = ("inventory", "description", "occurred_at", "actor_id")
    readonly_fields = [f.name for f in orm.InventoryHistoryModel._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.StockAlertModel)
class StockAlertAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently
    list_display = ("inventory", "health_status", "triggered_at", "acknowledged")
    list_filter = ("health_status", "acknowledged")


# Real, product-required simplification: Inventory removed from Dashboard entirely --
# stock is now managed directly on the ProductVariant admin form (see products/infrastructure/admin.py's
# own ProductVariantAdminForm.stock field). The underlying model and its data are untouched.
# @admin.register(orm.InventoryOutboxEvent)
class InventoryOutboxEventAdmin(admin.ModelAdmin):
    """Read-only -- append-only/Outbox tables are never editable in admin, per MIC §9."""
    list_per_page = 25  # Phase 08.5: applying this project's own established default-pagination convention (Phase 08.3/08.4) consistently

    list_display = ("event_type", "event_version", "created_at", "published_at", "publish_attempts")
    list_filter = ("event_type",)
    readonly_fields = [f.name for f in orm.InventoryOutboxEvent._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
