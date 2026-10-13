"""
Inventory `/api/v1/inventory/...` URL routing.

Every collection endpoint (list+create) is ONE view class on ONE path
entry -- verified below by a duplicate-path check, matching every
prior module's approach.
"""
from __future__ import annotations

from django.urls import path

from apps.inventory.interfaces.api.v1 import views

app_name = "inventory"

urlpatterns = [
    # --- Lifecycle ---
    path("items", views.InventoryListCreateView.as_view(), name="items-list-create"),
    path("items/code/<str:code>", views.InventoryDetailView.as_view(), name="items-detail-by-code"),
    path("items/<str:inventory_id>/archive", views.ArchiveInventoryView.as_view(), name="items-archive"),
    path("items/<str:inventory_id>/restore", views.RestoreInventoryView.as_view(), name="items-restore"),
    # --- Stock operations (admin) ---
    path("admin/stock/receive", views.ReceiveStockView.as_view(), name="admin-stock-receive"),
    path("admin/stock/confirm-incoming", views.ConfirmIncomingStockView.as_view(), name="admin-stock-confirm-incoming"),
    path("admin/stock/reserve", views.ReserveStockView.as_view(), name="admin-stock-reserve"),
    path("admin/stock/release", views.ReleaseReservationView.as_view(), name="admin-stock-release"),
    path("admin/stock/transfer", views.TransferStockView.as_view(), name="admin-stock-transfer"),
    path("admin/stock/adjust", views.AdjustStockView.as_view(), name="admin-stock-adjust"),
    path("admin/stock/damage", views.DamageStockView.as_view(), name="admin-stock-damage"),
    path("admin/stock/expire", views.ExpireStockView.as_view(), name="admin-stock-expire"),
    # --- Batch / Serial (admin) ---
    path("admin/batches", views.BatchListCreateView.as_view(), name="admin-batches-list-create"),
    path("admin/batches/<str:batch_id>", views.BatchDetailView.as_view(), name="admin-batches-detail"),
    path("admin/batches/<str:batch_id>/serials", views.RegisterSerialView.as_view(), name="admin-batches-register-serial"),
    path("admin/batches/<str:batch_id>/serials/<str:serial_item_id>/deactivate", views.DeactivateSerialView.as_view(), name="admin-batches-deactivate-serial"),
    # --- Reservations (admin) ---
    path("admin/reservations", views.ReservationListView.as_view(), name="admin-reservations-list-create"),
    path("admin/reservations/<str:reservation_id>", views.ReservationDetailView.as_view(), name="admin-reservations-detail"),
    path("admin/reservations/<str:reservation_id>/cancel", views.CancelReservationView.as_view(), name="admin-reservations-cancel"),
    path("admin/reservations/<str:reservation_id>/expire", views.ExpireReservationView.as_view(), name="admin-reservations-expire"),
    # --- Cycle Count (admin) ---
    path("admin/cycle-counts", views.StartCycleCountView.as_view(), name="admin-cycle-counts-start"),
    path("admin/cycle-counts/<str:cycle_count_id>/complete", views.CompleteCycleCountView.as_view(), name="admin-cycle-counts-complete"),
    # --- Physical Inventory (admin) ---
    path("admin/physical-inventories", views.StartPhysicalInventoryView.as_view(), name="admin-physical-inventories-start"),
    path("admin/physical-inventories/<str:physical_inventory_id>/complete", views.CompletePhysicalInventoryView.as_view(), name="admin-physical-inventories-complete"),
    # --- Snapshots (admin) ---
    path("admin/snapshots", views.CreateSnapshotView.as_view(), name="admin-snapshots-create"),
    path("admin/snapshots/<str:snapshot_id>/restore", views.RestoreSnapshotView.as_view(), name="admin-snapshots-restore"),
    # --- Ledger (admin) ---
    path("admin/ledger/<str:warehouse_inventory_id>", views.LedgerView.as_view(), name="admin-ledger"),
    # --- Queries ---
    path("search", views.InventorySearchView.as_view(), name="search"),
    path("admin/warehouses/<str:warehouse_id>/summary", views.WarehouseSummaryView.as_view(), name="admin-warehouse-summary"),
    path("admin/low-stock", views.LowStockView.as_view(), name="admin-low-stock"),
    path("admin/expiring-batches", views.ExpiringBatchView.as_view(), name="admin-expiring-batches"),
    path("admin/items", views.AdminInventoryView.as_view(), name="admin-items-list"),
]
