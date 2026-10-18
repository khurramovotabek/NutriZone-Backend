"""
Jazzmin configuration (Phase 08.1 -- Premium Admin Dashboard Foundation).

**Scope, stated explicitly**: this configures the existing
`/django-admin/` route only -- the "engineering/ops debugging tool"
named in Django Implementation Blueprint §13 and this repository's own
README ("What's deliberately not here" -- no server-rendered admin
dashboard templates; the real Admin CRM and POS Workspace are separate
frontends consuming the REST API exclusively). This phase makes that
existing internal tool visually premium and usable in three
languages/two color modes; it does not create a second, business-facing
admin surface, and does not reverse that documented architecture.

Menu items are restricted to models actually registered with Django
Admin, verified by direct inspection (Phase 08.1's own reconnaissance)
-- no fabricated navigation entries. One deliberate exception:
`custom_links["pricing"]` below links the Pricing app's sidebar group
to the real, existing Pricing List page (a custom admin view, not a
ModelAdmin) -- Jazzmin's own supported mechanism for this, not a
second, parallel navigation system.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

JAZZMIN_SETTINGS = {
    "site_title": "NutriZone",
    "site_header": "NutriZone",
    "site_brand": "NutriZone",
    "welcome_sign": _("NutriZone -- Internal Operations"),
    "copyright": "NutriZone",
    # Default brand mark; an uploaded Site Settings logo replaces it at render time (templates/admin/nz_branding.html).
    "site_logo": "admin/img/nutrizone-logo.svg",
    "site_logo_classes": "nz-brand-logo-img",
    "site_icon": "admin/img/nutrizone-logo.svg",
    "show_ui_builder": False,  # Phase 08.1: the design system is fixed and versioned in nutrizone-admin.css, not end-user-tunable
    "changeform_format": "single",
    "language_chooser": False,  # Phase 08.1's own language switcher (custom partial, uses Django's set_language view) replaces Jazzmin's built-in chooser
    # Phase 4: Jazzmin's own default (navigation_expanded=True) forces
    # a flat "nav-header" sidebar mode (static, icon-less app labels --
    # confirmed via direct source read of jazzmin/templates/admin/
    # base.html's own {% if jazzmin_settings.navigation_expanded %}
    # branch), silently preventing the "icons" setting below from ever
    # rendering, since the app-level icon is only used in the
    # "has-treeview" (collapsible) branch. Set to False so the real
    # per-app icons (and collapsible grouping) actually appear.
    "navigation_expanded": False,
    # Phase 3: real app_label sidebar ordering -- groups the
    # actually-registered app_labels (confirmed via
    # admin.site._registry inspection) into logical adjacency:
    # Overview -> Sales -> Catalog -> Customers -> Communication ->
    # System. No fabricated navigation entries; every label here is a
    # real, registered Django app.
    "order_with_respect_to": [
        # Overview
        "platform",
        "Analitika",
        # Sales
        "ordering",
        "payment",
        "payment.PaymentProviderConfig",
        "payment.PaymentModel",
        "payment.PaymentCallbackLog",
        "payment.PaymentReconciliationIssue",
        "cart",
        "cart.CartModel",
        "cart.CartAuditEntryModel",
        "pricing",
        "pos",
        "receipts",
        # Catalog
        "products",
        # Inventory has no registered ModelAdmin of its own (stock is
        # managed on the ProductVariant admin form -- see inventory/
        # infrastructure/admin.py's own module docstring); its sidebar
        # group is added by inventory_view.install_sidebar_entry() and
        # holds the Stock Dashboard via custom_links["inventory"] below.
        "inventory",
        # Customers
        "identity",
        "loyalty",
        "reviews",
        # Communication
        "notifications",
        "chat",
        "support",
        "Telegram",
        "assistant",
        # System
        "geo",
        "stores",
        "auth",
        "django_celery_beat",
        "django_celery_results",
        "token_blacklist",
    ],
    "icons": {
        "platform": "fas fa-tachometer-alt",
        "Analitika": "fas fa-chart-line",
        "support": "fas fa-headset",
        "receipts": "fas fa-receipt",
        "receipts.Receipt": "fas fa-receipt",
        "support.SupportCase": "fas fa-phone-volume",
        "support.ProductRequest": "fas fa-magnifying-glass-plus",
        "Telegram": "fab fa-telegram",
        "assistant": "fas fa-robot",
        "assistant.assistantconversation": "fas fa-comments",
        "ordering": "fas fa-receipt",
        "payment": "fas fa-credit-card",
        "payment.PaymentProviderConfig": "fas fa-building-columns",
        "payment.PaymentModel": "fas fa-money-bill-transfer",
        "payment.PaymentCallbackLog": "fas fa-satellite-dish",
        "payment.PaymentReconciliationIssue": "fas fa-scale-balanced",
        "cart": "fas fa-shopping-cart",
        "cart.CartModel": "fas fa-cart-shopping",
        "cart.CartAuditEntryModel": "fas fa-clock-rotate-left",
        "pricing": "fas fa-tags",
        "pos": "fas fa-cash-register",
        "products": "fas fa-box-open",
        "inventory": "fas fa-warehouse",
        "identity": "fas fa-users",
        "reviews": "fas fa-star",
        "notifications": "fas fa-bell",
        "notifications.notificationmodel": "fas fa-bell",
        "notifications.notificationbroadcast": "fas fa-bullhorn",
        "chat": "fas fa-comments",
        "chat.conversationmodel": "fas fa-comments",
        "chat.messagemodel": "fas fa-message",
        "chat.chatquickreply": "fas fa-bolt",
        "chat.conversationrating": "fas fa-star",
        "chat.chatsettings": "fas fa-sliders",
        "geo": "fas fa-map-marker-alt",
        "geo.country": "fas fa-earth-asia",
        "geo.region": "fas fa-map",
        "geo.district": "fas fa-draw-polygon",
        "geo.city": "fas fa-city",
        "geo.address": "fas fa-house",
        "stores": "fas fa-store",
        "loyalty": "fas fa-coins",
        "loyalty.LoyaltyTier": "fas fa-crown",
        "loyalty.Wallet": "fas fa-wallet",
        "loyalty.WalletTransaction": "fas fa-receipt",
        "auth": "fas fa-user-shield",
        "django_celery_beat": "fas fa-clock",
        "django_celery_results": "fas fa-list-check",
        "token_blacklist": "fas fa-ban",
    },
    # Adds the existing Pricing List page (apps.products.infrastructure
    # .price_list_view, previously reachable only from the main
    # Dashboard's Quick Actions) into the Pricing app's own sidebar
    # group, alongside Coupons -- a real Jazzmin feature for linking a
    # non-ModelAdmin view into an app's navigation, not a second,
    # parallel nav system. No `permissions` restriction: the view
    # itself only requires `staff_member_required` (see
    # `price_list_view.py`), so the link's visibility matches that
    # exactly rather than silently hiding it from a staff user who
    # lacks some specific model permission.
    # The WMS models live in the stores app but are reached from the Ombor group (custom_links["inventory"]).
    "hide_models": ["chat.chatsettings", "stores.stocktransfer", "stores.stockreceipt", "stores.stockmovement", "stores.stockcount",
                    "stores.writeoff", "stores.supplier", "stores.supplierpayment", "stores.reorderrule", "stores.storecashier",
                    "search.searchterm", "telegram_bot.telegrampost", "telegram_bot.channelautopostsettings", "receipts.receiptsettings"],  # reached from the Catalog group (custom_links["products"])
    "usermenu_links": [{"name": _("Mening profilim"), "url": "admin:nz_profile", "icon": "fas fa-user-circle"}],
    "custom_links": {
        # Biznes analitikasi (apps/platform/infrastructure/analytics_view.py) -- the same numbers NutriZoneAnalyticsBot sends.
        "platform": [
            {"name": _("Nazorat markazi"), "url": "admin:nz_control", "icon": "fas fa-shield-halved", "permissions": ["ordering.view_ordermodel", "pos.view_salemodel"]},
        ],
        # Analitika -- every report in one section. Not an app: Jazzmin turns a custom_links key that is no installed app into its own sidebar group, named by the key.
        "Analitika": [
            {"name": _("Biznes analitikasi"), "url": "admin:nz_analytics", "icon": "fas fa-chart-pie", "permissions": ["ordering.view_ordermodel", "pos.view_salemodel"]},
            {"name": _("Hisobotlar"), "url": "admin:nz_reports", "icon": "fas fa-file-invoice-dollar", "permissions": ["ordering.view_ordermodel"]},
            {"name": _("Sotuv rejasi"), "url": "admin:nz_sales_plan", "icon": "fas fa-bullseye", "permissions": ["ordering.view_ordermodel", "pos.view_salemodel"]},
            {"name": _("Filial hisoboti"), "url": "admin:nz_branch_report", "icon": "fas fa-store", "permissions": ["ordering.view_ordermodel"]},
            {"name": _("Mijozlar segmentlari"), "url": "admin:nz_segments", "icon": "fas fa-people-group", "permissions": ["ordering.view_ordermodel", "pos.view_salemodel"]},
            {"name": _("Ombor hisobotlari"), "url": "admin:nz_wms_reports", "icon": "fas fa-warehouse", "permissions": ["stores.view_stockmovement"]},
            {"name": _("Qidiruv tahlili"), "url": "admin:search_searchterm_changelist", "icon": "fas fa-magnifying-glass-chart", "permissions": ["search.view_searchterm"]},
            {"name": _("Operatorlar hisoboti"), "url": "admin:nz_chat_report", "icon": "fas fa-headset", "permissions": ["chat.view_conversationrating"]},
        ],
        # Telegram -- bots, channel posts and broadcasts (same mechanism).
        "receipts": [
            {"name": _("Yangi chek"), "url": "admin:receipts_receipt_manual", "icon": "fas fa-plus", "permissions": ["receipts.view_receipt"]},
            {"name": _("Chek sozlamalari"), "url": "admin:receipts_receiptsettings_changelist", "icon": "fas fa-gear", "permissions": ["receipts.change_receiptsettings"]},
        ],
        "support": [
            {"name": _("Support paneli"), "url": "admin:support_supportcase_board", "icon": "fas fa-table-columns", "permissions": ["support.view_supportcase"]},
        ],
        "Telegram": [
            {"name": _("Botlar markazi"), "url": "admin:nz_telegram_status", "icon": "fas fa-robot"},
            {"name": _("Postlar"), "url": "admin:telegram_bot_telegrampost_changelist", "icon": "fas fa-paper-plane", "permissions": ["telegram_bot.view_telegrampost"]},
            {"name": _("Kanal avtopostlari"), "url": "admin:telegram_bot_channelautopostsettings_changelist", "icon": "fas fa-bullhorn", "permissions": ["telegram_bot.change_channelautopostsettings"]},
            {"name": _("Mijozlarga xabar"), "url": "admin:nz_notify_send", "icon": "fas fa-bullhorn", "permissions": ["notifications.add_notificationbroadcast"]},
        ],
        # Dispatcher board (apps/ordering/infrastructure/admin_board.py): live Kanban of online orders.
        "ordering": [
            {"name": _("Buyurtmalar paneli"), "url": "admin:ordering_ordermodel_board", "icon": "fas fa-table-columns", "permissions": ["ordering.view_ordermodel"]},
        ],
        # What shoppers search for -- above all what they search for and don't find (apps/search).
        "products": [
            {"name": _("Guruhlash"), "url": "admin:nz_product_grouping", "icon": "fas fa-layer-group", "permissions": ["products.change_product"]},
            {"name": _("Qidiruv tahlili"), "url": "admin:search_searchterm_changelist", "icon": "fas fa-magnifying-glass-chart", "permissions": ["search.view_searchterm"]},
        ],
        "pricing": [
            {
                "name": _("Pricing List"),
                "url": "admin:nz_price_list",
                "icon": "fas fa-list",
            },
        ],
        # The POS Terminal (apps/platform/infrastructure/pos_view.py) --
        # a custom view, so it needs a link of its own next to POS's
        # registered Sale model.
        "pos": [
            {
                "name": _("Onlayn kassa"),
                "url": "admin:nz_pos_terminal",
                "icon": "fas fa-cash-register",
            },
            {"name": _("Kassalar va kassirlar"), "url": "admin:stores_storecashier_changelist", "icon": "fas fa-id-badge", "permissions": ["stores.view_storecashier"]},
            {"name": _("Oylik va KPI"), "url": "admin:stores_storecashier_payroll", "icon": "fas fa-sack-dollar", "permissions": ["stores.view_storecashier"]},
        ],
        # The Stock Dashboard (apps/platform/infrastructure/inventory_view.py's
        # own inventory_dashboard_view -- branch/product stock, search,
        # inline quantity edits) as Inventory's own top-level sidebar group
        # rather than nested under Products & Catalog.
        # Ombor (WMS) -- apps/stores/infrastructure/warehouse_admin.py: warehouses & branches share one stock
        # (StoreProductStock); every change is in the stock ledger.
        "geo": [
            {"name": _("Manzillar xaritasi"), "url": "admin:nz_geo_map", "icon": "fas fa-map-location-dot", "permissions": ["geo.view_address"]},
        ],
        "chat": [
            {"name": _("Chat markazi"), "url": "admin:nz_chat_admin", "icon": "fas fa-headset", "permissions": ["chat.view_conversationmodel"]},
            {"name": _("Operatorlar hisoboti"), "url": "admin:nz_chat_report", "icon": "fas fa-chart-column", "permissions": ["chat.view_conversationrating"]},
            {"name": _("Chat sozlamalari"), "url": "admin:chat_chatsettings_changelist", "icon": "fas fa-sliders", "permissions": ["chat.change_chatsettings"]},
        ],
        "notifications": [
            {"name": _("Xabar yuborish"), "url": "admin:nz_notify_send", "icon": "fas fa-paper-plane", "permissions": ["notifications.add_notificationbroadcast"]},
        ],
        "inventory": [
            {"name": _("Qoldiqlar"), "url": "admin:nz_wms_stock", "icon": "fas fa-cubes", "permissions": ["stores.view_stockmovement"]},
            {"name": _("To'ldirish (minimal qoldiq)"), "url": "admin:stores_reorderrule_changelist", "icon": "fas fa-arrows-rotate", "permissions": ["stores.view_reorderrule"]},
            {"name": _("Transferlar"), "url": "admin:stores_stocktransfer_changelist", "icon": "fas fa-right-left", "permissions": ["stores.view_stocktransfer"]},
            {"name": _("Kirim (qabul)"), "url": "admin:stores_stockreceipt_changelist", "icon": "fas fa-dolly", "permissions": ["stores.view_stockreceipt"]},
            {"name": _("Yetkazib beruvchilar"), "url": "admin:stores_supplier_changelist", "icon": "fas fa-truck-field", "permissions": ["stores.view_supplier"]},
            {"name": _("Yaroqlilik muddati"), "url": "admin:nz_wms_expiry", "icon": "fas fa-calendar-xmark", "permissions": ["stores.view_stockmovement"]},
            {"name": _("Hisobdan chiqarish"), "url": "admin:stores_writeoff_changelist", "icon": "fas fa-trash-can-arrow-up", "permissions": ["stores.view_writeoff"]},
            {"name": _("Inventarizatsiya"), "url": "admin:stores_stockcount_changelist", "icon": "fas fa-clipboard-check", "permissions": ["stores.view_stockcount"]},
            {"name": _("Ombor tarixi"), "url": "admin:stores_stockmovement_changelist", "icon": "fas fa-clock-rotate-left", "permissions": ["stores.view_stockmovement"]},
            {"name": _("Ombor hisobotlari"), "url": "admin:nz_wms_reports", "icon": "fas fa-chart-column", "permissions": ["stores.view_stockmovement"]},
        ],
    },
}

JAZZMIN_UI_TWEAKS = {
    # Deliberately minimal -- NutriZone's own visual identity is
    # applied via static/admin/css/nutrizone-admin.css (CSS custom
    # properties), not via Jazzmin's own Bootswatch theme presets,
    # per this phase's own "Jazzmin should feel like the foundation,
    # not the final visual identity" instruction.
    "theme": "flatly",
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_compact_style": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_flat_style": False,
    "default_theme_mode": "light",  # Jazzmin 3.x's own dark-mode mechanism (Bootstrap 5 data-bs-theme) is fixed to light; NutriZone's own theme switcher (nutrizone-theme.js, data-nz-theme) is the single source of truth for dark mode, avoiding two competing mechanisms
}
