"""
Real, product-required capability: physical/partner "Do'kon" (Store)
entities. Each store has its own owner (a Dashboard staff account),
managed media, dynamic weekly working hours, contact details, a map
location, and a many-to-many stock relationship with existing
products/variants.

Deliberately simple, standalone models (same convention as
Banner/BlogPost -- no DDD aggregate, no lifecycle state machine) since
a store is low-business-rule, owner-edited content, not a domain with
complex invariants.

CRITICAL boundary: a store owner NEVER creates or edits a product --
StoreProductStock only ever references an EXISTING ProductVariant and
records how many units this specific store carries. Enforced at the
admin layer (StoreProductStockInline uses a fixed, non-creatable
ProductVariant queryset), not by inventing a second product model.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


# What a branch offers -- the storefront shows these as chips (labels translated in the storefront's messages).
STORE_AMENITIES = ("card_payment", "cash", "online_payment", "installments", "parking", "consultant", "tasting", "pickup", "delivery", "wifi", "accessible")


class StoreKind(models.TextChoices):
    STORE = "store", _("Filial (savdo nuqtasi)")
    WAREHOUSE = "warehouse", _("Sklad (asosiy ombor)")


class StoreStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    TEMPORARILY_CLOSED = "temporarily_closed", _("Temporarily closed")
    COMING_SOON = "coming_soon", _("Coming soon")


# Branch colours for charts and reports: every store keeps ONE colour for life, so a line
# on the dashboard means the same branch whatever the date range. Distinct, readable on
# light and dark backgrounds; a new store gets the first palette colour not yet taken.
STORE_PALETTE = [
    "#2D8CFF", "#22C55E", "#FF9800", "#E91E63", "#7E35C1", "#4338CA", "#FF8057", "#F45B5B", "#38BDF8", "#E879F9",
    "#818CF8", "#C9DC45", "#607D8B", "#14B8A6", "#F59E0B", "#A855F7", "#EF4444", "#10B981", "#0EA5E9", "#D946EF",
    "#84CC16", "#F97316", "#6366F1", "#EC4899", "#06B6D4", "#C9BEB3", "#C5E1A5", "#8B5CF6", "#FB7185", "#65A30D",
]


def next_store_color(exclude_pk=None) -> str:
    used = {c.upper() for c in Store.objects.exclude(pk=exclude_pk).values_list("color", flat=True) if c}
    free = [c for c in STORE_PALETTE if c.upper() not in used]
    if free:
        return free[0]
    # palette exhausted: spread further hues around the colour wheel (deterministic, never random)
    import colorsys

    n = len(used)
    r, g, b = colorsys.hls_to_rgb(((n * 0.618033988749895) % 1.0), 0.55, 0.65)
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


class Store(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # A warehouse (sklad) is a stock location like a branch, but it never sells: it receives
    # goods (Kirim) and transfers them to branches. Hidden from the storefront and sales charts.
    kind = models.CharField(max_length=12, choices=StoreKind.choices, default=StoreKind.STORE, db_index=True, verbose_name=_("Location type"))
    owner = models.ForeignKey(
        "identity.User", on_delete=models.PROTECT, related_name="owned_stores", null=True, blank=True,
        verbose_name=_("Owner"), help_text=_("The customer account that manages this store from their own Account -- never a Dashboard staff account. This customer never creates or edits products -- only stock counts for existing products, via their own storefront \"My Store\" page."),
    )
    name = models.CharField(max_length=200, verbose_name=_("Store name"))
    color = models.CharField(
        max_length=7, blank=True, default="", verbose_name=_("Brand colour"),
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a hex colour like #2D8CFF."))],
        help_text=_("This branch's colour in every chart and report. Picked automatically for a new store; you can change it."),
    )
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_("Slug"), help_text=_("URL-friendly identifier. Auto-generated from the name if left blank."))
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))
    tagline = models.CharField(max_length=140, blank=True, default="", verbose_name=_("Tagline"), help_text=_("One line under the name, e.g. «Chilonzordagi eng katta sport ozuqa do'koni»."))
    amenities = models.JSONField(default=list, blank=True, verbose_name=_("Amenities"), help_text=_("Codes from STORE_AMENITIES (card payment, parking, consultant, ...)."))
    status = models.CharField(max_length=24, choices=StoreStatus.choices, default=StoreStatus.ACTIVE, db_index=True, verbose_name=_("Status"))

    # --- Media: logo/cover are single, dedicated images (Banner's own
    # one-image-per-field convention); the full gallery of additional
    # images/video lives in StoreMedia below. ---
    logo_storage_path = models.CharField(max_length=500, blank=True, default="", verbose_name=_("Logo"))
    logo_thumbnail_paths = models.JSONField(default=dict, blank=True)
    cover_image_storage_path = models.CharField(max_length=500, blank=True, default="", verbose_name=_("Cover image"))
    cover_image_thumbnail_paths = models.JSONField(default=dict, blank=True)

    # --- Contact ---
    phone_numbers = models.JSONField(default=list, blank=True, verbose_name=_("Phone numbers"), help_text=_("List of phone numbers, e.g. [\"+998901234567\", \"+998907654321\"]."))
    email = models.EmailField(blank=True, default="", verbose_name=_("Email"))
    telegram_username = models.CharField(max_length=64, blank=True, default="", verbose_name=_("Telegram username"))
    instagram_username = models.CharField(max_length=64, blank=True, default="", verbose_name=_("Instagram username"))

    # --- Location (for map display and city/district filtering) ---
    address = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Address"))
    city = models.CharField(max_length=100, blank=True, default="", db_index=True, verbose_name=_("City"))
    district = models.CharField(max_length=100, blank=True, default="", db_index=True, verbose_name=_("District"))
    latitude = models.FloatField(null=True, blank=True, verbose_name=_("Latitude"))
    longitude = models.FloatField(null=True, blank=True, verbose_name=_("Longitude"))
    landmark = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Landmark"), help_text=_("How to find the entrance, e.g. «Chorsu metro, 2-chiqish, Makro yonida»."))
    # online orders picked up here (apps/stores/infrastructure/store_orders.py)
    pickup_enabled = models.BooleanField(default=True, verbose_name=_("Pickup orders"), help_text=_("Customers can choose this branch at checkout to pick their order up."))
    pickup_note = models.CharField(max_length=300, blank=True, default="", verbose_name=_("Pickup note"), help_text=_("Shown to the customer when the order is ready, e.g. «Kassada buyurtma raqamini ayting»."))

    # --- Working hours ---
    # Real, product-required shape: one entry per weekday, each with its
    # own open/close time and a closed flag -- lets an owner set e.g.
    # "Mon-Fri 10:00-20:00, Sat-Sun 10:00-18:00" and change any single
    # day at any time (dynamic), without a rigid single open/close pair
    # for the whole week.
    working_hours = models.JSONField(
        default=dict, blank=True, verbose_name=_("Working hours"),
        help_text=_('Per-weekday hours, e.g. {"mon": {"open": "10:00", "close": "20:00", "closed": false}, ...}. Edit via the Working Hours fields below.'),
    )
    # Real, product-required capability: date-specific overrides of the
    # weekly schedule above (holidays, one-off early closures, etc) --
    # e.g. [{"date": "2026-01-01", "closed": true}, {"date": "2026-03-21", "open": "12:00", "close": "16:00"}].
    # A matching entry for "today" always wins over working_hours.
    special_hours = models.JSONField(default=list, blank=True, verbose_name=_("Special hours"), help_text=_('Date-specific overrides, e.g. [{"date": "2026-01-01", "closed": true}]. Takes priority over the weekly schedule for that date.'))

    products = models.ManyToManyField("products.ProductVariant", through="StoreProductStock", related_name="stores", verbose_name=_("Products"))

    # The register (kassa) PIN: one shared PIN per kassa, asked when a shift is opened and when another cashier takes
    # over the terminal. Only a hash is kept; 5 wrong PINs lock the kassa for a few minutes (see pos_cashiers.py).
    pos_pin_hash = models.CharField(max_length=128, blank=True, default="", verbose_name=_("Kassa PIN"))
    pos_pin_changed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("PIN changed"))
    pos_pin_failed = models.PositiveSmallIntegerField(default=0)
    pos_pin_locked_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stores_stores"
        verbose_name = _("Store")
        verbose_name_plural = _("Stores")
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def save(self, *args, **kwargs):
        if not self.color:
            self.color = next_store_color(exclude_pk=self.pk)
        if not self.slug and self.name:
            from django.utils.text import slugify

            base_slug = slugify(self.name)[:200] or "store"
            slug = base_slug
            counter = 1
            while Store.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def is_open_now(self) -> bool:
        if self.status != StoreStatus.ACTIVE:
            return False

        from zoneinfo import ZoneInfo

        from django.utils import timezone as django_timezone

        # Real, confirmed bug: `localtime()` converts to this project's
        # own `TIME_ZONE` setting (UTC, per config/settings/base.py --
        # a deliberate choice for how *stored* timestamps are displayed
        # project-wide, not a statement about where the business
        # operates), so a store correctly configured 10:00-20:00 showed
        # "closed" at 12:38 real Tashkent time (07:38 UTC, before 10:00).
        # Every real store on this storefront is Uzbekistan-only, and
        # `working_hours`/`special_hours` are entered by the owner as
        # plain Tashkent wall-clock HH:MM with no timezone of their own
        # -- so "now", for this one business-hours check specifically,
        # must always be real Asia/Tashkent time, independent of
        # whatever TIME_ZONE the rest of the project is configured with.
        now = django_timezone.now().astimezone(ZoneInfo("Asia/Tashkent"))
        today_str = now.date().isoformat()

        for entry in self.special_hours or []:
            if entry.get("date") == today_str:
                if entry.get("closed"):
                    return False
                return self._time_in_range(now, entry.get("open"), entry.get("close"))

        weekday_code = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now.weekday()]
        day = (self.working_hours or {}).get(weekday_code, {})
        if not day or day.get("closed"):
            return False
        return self._time_in_range(now, day.get("open"), day.get("close"))

    def today_hours(self) -> dict:
        """Today's effective hours in Tashkent time -- a special day wins over the weekly schedule (same rule as is_open_now)."""
        from zoneinfo import ZoneInfo

        from django.utils import timezone as django_timezone

        now = django_timezone.now().astimezone(ZoneInfo("Asia/Tashkent"))
        today = now.date().isoformat()
        for entry in self.special_hours or []:
            if entry.get("date") == today:
                return {"open": entry.get("open") or "", "close": entry.get("close") or "", "closed": bool(entry.get("closed")), "special": True, "note": entry.get("note") or ""}
        day = (self.working_hours or {}).get(["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now.weekday()], {})
        # `unknown`: the owner hasn't entered this day's hours yet -- show "hours not set", not "closed"
        unknown = not day.get("closed") and not (day.get("open") and day.get("close"))
        return {"open": day.get("open") or "", "close": day.get("close") or "", "closed": bool(day.get("closed")) or not day.get("open"), "special": False, "note": "",
                "unknown": unknown}

    def upcoming_special_days(self, days: int = 45) -> list[dict]:
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        from django.utils import timezone as django_timezone

        today = django_timezone.now().astimezone(ZoneInfo("Asia/Tashkent")).date()
        last = (today + timedelta(days=days)).isoformat()
        return sorted((e for e in (self.special_hours or []) if today.isoformat() <= (e.get("date") or "") <= last), key=lambda e: e["date"])

    @staticmethod
    def _time_in_range(now, open_str: str | None, close_str: str | None) -> bool:
        if not open_str or not close_str:
            return False
        try:
            open_h, open_m = (int(x) for x in open_str.split(":"))
            close_h, close_m = (int(x) for x in close_str.split(":"))
        except (ValueError, AttributeError):
            return False
        current_minutes = now.hour * 60 + now.minute
        return (open_h * 60 + open_m) <= current_minutes < (close_h * 60 + close_m)


class StoreMedia(models.Model):
    """Multiple images and/or one or more videos per store -- same storage-path convention as products.infrastructure.models.ProductMedia (no separate Media Asset architecture)."""

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="media")
    storage_path = models.CharField(max_length=500)
    thumbnail_paths = models.JSONField(default=dict, blank=True)
    is_video = models.BooleanField(default=False, verbose_name=_("Is video"))
    duration_seconds = models.FloatField(null=True, blank=True)  # video-only
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stores_store_media"
        verbose_name = _("Store Media")
        verbose_name_plural = _("Store Media")
        ordering = ["sort_order", "created_at"]
        indexes = [models.Index(fields=["store", "sort_order"])]


class StoreProductStock(models.Model):
    """
    The many-to-many "through" model: how many units of an EXISTING
    ProductVariant a given Store carries. This is the ONLY thing a
    store owner ever edits about a product -- never the product's own
    name/price/description/media, which remain the catalog team's
    responsibility elsewhere in the Dashboard.
    """

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="stock_entries")
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.CASCADE, related_name="store_stock_entries", verbose_name=_("Product"))
    quantity = models.PositiveIntegerField(default=0, verbose_name=_("Quantity"))
    # Units set aside for a transfer that is ready to ship: still on the shelf, no longer sellable.
    reserved_quantity = models.PositiveIntegerField(default=0, verbose_name=_("Reserved for transfer"))
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def available(self) -> int:
        return max(0, self.quantity - self.reserved_quantity)

    class Meta:
        db_table = "stores_store_product_stock"
        verbose_name = _("Store Product Stock")
        verbose_name_plural = _("Store Product Stock")
        constraints = [models.UniqueConstraint(fields=["store", "product_variant"], name="uq_store_product_variant")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.store.name} — {self.product_variant.sku} ({self.quantity})"


class StoreRating(models.Model):
    """
    Real, product-required capability: a customer can rate a store
    1-5 stars. Deliberately a simple, single-value rating -- no
    review text, no media, no moderation lifecycle -- matching this
    module's own established "low-business-rule, owner-edited
    content" convention (see this file's own module docstring) rather
    than reusing apps.reviews's heavier moderated `Review` aggregate,
    which is hardcoded to `product_id` and has no store concept at
    all (confirmed directly: apps/reviews/domain/aggregates.py::Review
    has no target-type field, only ever a product).

    One row per (store, customer) -- rating again updates the
    existing row (see the view's use of update_or_create) rather than
    creating a duplicate, so a store's average always reflects each
    customer's latest opinion, never an accumulation of old ones.
    """

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="ratings", verbose_name=_("Store"))
    customer = models.ForeignKey("identity.User", on_delete=models.CASCADE, related_name="store_ratings", verbose_name=_("Customer"))
    rating = models.PositiveSmallIntegerField(verbose_name=_("Rating"), validators=[MinValueValidator(1), MaxValueValidator(5)])
    # Private feedback: the customer's written review goes to management only -- never shown on the storefront,
    # visible in the Dashboard to superadmins only (StoreRatingAdmin).
    comment = models.TextField(_("Izoh"), blank=True, default="", max_length=1000)
    commented_at = models.DateTimeField(_("Izoh vaqti"), null=True, blank=True)
    is_read = models.BooleanField(_("O'qilgan"), default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stores_store_ratings"
        verbose_name = _("Store Rating")
        verbose_name_plural = _("Store Ratings")
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["store", "customer"], name="uq_store_customer_rating")]
        indexes = [models.Index(fields=["store"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.customer_id} → {self.store.name}: {self.rating}★"


class CashSessionStatus(models.TextChoices):
    OPEN = "open", _("Open")
    CLOSED = "closed", _("Closed")


class CashSession(models.Model):
    """
    One cash-register shift at a store: opened in the morning with the float
    in the drawer, closed in the evening with the counted cash. Sales can only
    be rung up while a session is open (store POS), and every completed sale /
    refund is stamped with the session it happened in, so the Z-report is exact.

    Totals are frozen onto the row at close time (the "Z-report") so later edits
    to catalog prices or loyalty data never rewrite a closed shift's history.
    At most one OPEN session per store (partial unique index).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="cash_sessions", verbose_name=_("Store"))
    status = models.CharField(max_length=12, choices=CashSessionStatus.choices, default=CashSessionStatus.OPEN, db_index=True, verbose_name=_("Status"))
    # A customer-account cashier (store tills) or, for the Dashboard's online kassa, empty + the staff member's name.
    opened_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("Opened by"))
    opened_by_name = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Opened by"))
    opened_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Opened at"))
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Opening cash (float)"))
    opening_note = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Opening note"))
    closed_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("Closed by"))
    closed_by_name = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Closed by"))
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name=_("Closed at"))
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Counted cash"))
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Expected cash"))
    cash_difference = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Difference"))
    closing_note = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Closing note"))
    # Z-report snapshot (frozen at close)
    sales_count = models.PositiveIntegerField(default=0, verbose_name=_("Sales"))
    items_sold = models.PositiveIntegerField(default=0, verbose_name=_("Units sold"))
    gross_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Gross sales"))
    discounts_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Discounts"))
    cash_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Cash taken"))
    uzcard_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Uzcard"))
    humo_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Humo"))
    coins_redeemed = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Paid with coins"))
    refunds_count = models.PositiveIntegerField(default=0, verbose_name=_("Refunds"))
    refunds_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Refunded"))
    cash_refunded = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Cash refunded"))

    class Meta:
        db_table = "stores_cash_sessions"
        ordering = ["-opened_at"]
        verbose_name = _("Cash register session")
        verbose_name_plural = _("Cash register sessions")
        constraints = [models.UniqueConstraint(fields=["store"], condition=models.Q(status="open"), name="uq_store_one_open_cash_session")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.store.name} — {self.opened_at:%d.%m.%Y %H:%M}"



# ======================================================================== stock ledger, goods receipts, transfers


class StockMovementType(models.TextChoices):
    RECEIPT = "receipt", _("Kirim (qabul)")
    SALE = "sale", _("Sotuv")
    RETURN = "return", _("Qaytarish (vozvrat)")
    TRANSFER_OUT = "transfer_out", _("Transfer: chiqim")
    TRANSFER_IN = "transfer_in", _("Transfer: kirim")
    ADJUSTMENT = "adjustment", _("Tuzatish")
    DAMAGE = "damage", _("Shikastlangan")
    EXPIRED = "expired", _("Muddati o'tgan")
    RESERVATION = "reservation", _("Band qilish")
    RELEASE = "release", _("Bandlikdan chiqarish")
    WRITE_OFF = "write_off", _("Hisobdan chiqarish")


class StockMovement(models.Model):
    """
    The stock ledger: one immutable row per change of a location's stock (or its reservation).
    `quantity` is signed for on-hand changes; RESERVATION / RELEASE move `reserved` only and
    record the units in `quantity` with the on-hand balance unchanged. Every stock change in
    the system goes through stock_service.move(), which writes this row in the same transaction.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="stock_movements", verbose_name=_("Location"))
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.PROTECT, related_name="+", verbose_name=_("Product"))
    movement_type = models.CharField(max_length=16, choices=StockMovementType.choices, db_index=True, verbose_name=_("Type"))
    quantity = models.IntegerField(verbose_name=_("Quantity"))
    balance_after = models.IntegerField(verbose_name=_("Balance after"))
    reserved_after = models.IntegerField(default=0, verbose_name=_("Reserved after"))
    reference = models.CharField(max_length=40, db_index=True, blank=True, verbose_name=_("Reference"))
    document_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor = models.CharField(max_length=150, blank=True, verbose_name=_("User"))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Note"))
    batch_number = models.CharField(max_length=48, blank=True, verbose_name=_("Batch"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry"))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("When"))

    class Meta:
        db_table = "stores_stock_movements"
        ordering = ["-created_at"]
        verbose_name = _("Stock movement")
        verbose_name_plural = _("Stock ledger")
        indexes = [models.Index(fields=["store", "product_variant", "-created_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.get_movement_type_display()} {self.quantity:+d}"

    def save(self, *args, **kwargs):
        # The ledger is append-only: a written movement is never edited (the database trigger from migration 0020 enforces it too).
        if not self._state.adding:
            raise PermissionError("Stock ledger rows cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Stock ledger rows cannot be deleted.")

    @property
    def balance_before(self) -> int:
        return self.balance_after - (0 if self.movement_type in ("reservation", "release") else self.quantity)


MANUAL_MOVEMENT_TYPES = (StockMovementType.ADJUSTMENT, StockMovementType.DAMAGE, StockMovementType.EXPIRED, StockMovementType.WRITE_OFF)


class StockAdjustment(StockMovement):
    """Qo'lda +/− jurnali: the ledger rows people made by hand (admin edits, counts, write-offs, transfer shortages)."""

    class Meta:
        proxy = True
        verbose_name = _("Qo'lda o'zgarish")
        verbose_name_plural = _("Qo'lda +/− jurnali")


class StockReceipt(models.Model):
    """A goods receipt (Kirim): units arriving at a location from a supplier -- scanned or imported from Excel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=20, unique=True, verbose_name=_("Number"))
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="receipts", verbose_name=_("Location"))
    supplier = models.CharField(max_length=160, blank=True, verbose_name=_("Supplier"))
    supplier_ref = models.ForeignKey("stores.Supplier", on_delete=models.PROTECT, null=True, blank=True, related_name="receipts", verbose_name=_("Supplier"))
    due_date = models.DateField(null=True, blank=True, verbose_name=_("Payment due"))  # receipt date + the supplier's payment terms
    invoice_number = models.CharField(max_length=60, blank=True, verbose_name=_("Invoice No."))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Note"))
    created_by = models.CharField(max_length=150, blank=True, verbose_name=_("Created by"))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Date"))
    total_units = models.PositiveIntegerField(default=0, verbose_name=_("Units"))
    total_value = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name=_("Value"))

    class Meta:
        db_table = "stores_stock_receipts"
        ordering = ["-created_at"]
        verbose_name = _("Goods receipt")
        verbose_name_plural = _("Goods receipts (Kirim)")

    def __str__(self) -> str:  # pragma: no cover
        return self.number


class StockReceiptItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(StockReceipt, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.PROTECT, related_name="+", verbose_name=_("Product"))
    quantity = models.PositiveIntegerField(verbose_name=_("Quantity"))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Unit cost"))
    batch_number = models.CharField(max_length=48, blank=True, verbose_name=_("Batch"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry"))

    class Meta:
        db_table = "stores_stock_receipt_items"


class TransferStatus(models.TextChoices):
    DRAFT = "draft", _("Qoralama")
    READY = "ready", _("Jo'natishga tayyor")
    IN_TRANSIT = "in_transit", _("Yo'lda")
    RECEIVING = "receiving", _("Qabul qilinmoqda")
    PARTIALLY_RECEIVED = "partial", _("Qisman qabul qilindi")
    RECEIVED = "received", _("Qabul qilindi")
    COMPLETED = "completed", _("Yakunlandi")
    CANCELLED = "cancelled", _("Bekor qilindi")


class DiscrepancyReason(models.TextChoices):
    DAMAGED = "damaged", _("Shikastlangan mahsulot")
    MISSING = "missing", _("Mahsulot yetib kelmadi")
    WRONG_PRODUCT = "wrong_product", _("Noto'g'ri mahsulot")
    COUNTING_ERROR = "counting_error", _("Sanashda xato")
    PACKAGING = "packaging", _("Qadoq muammosi")
    SHIPMENT_ERROR = "shipment_error", _("Jo'natishdagi xato")
    OTHER = "other", _("Boshqa")
    UNRESOLVED = "unresolved", _("Keyin aniqlanadi (o'tkazib yuborish)")  # receipt closes now; the manager settles it on approval


class StockTransfer(models.Model):
    """
    An inter-location transfer document (sklad → filial, filial → filial) with a strict state machine:
    DRAFT → READY (stock reserved) → IN_TRANSIT (left the source) → RECEIVING → [PARTIALLY_RECEIVED →]
    RECEIVED → COMPLETED; DRAFT/READY → CANCELLED. Transitions are validated in transfer_service only.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=20, unique=True, verbose_name=_("Transfer No."))
    source = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="transfers_out", verbose_name=_("From"))
    destination = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="transfers_in", verbose_name=_("To"))
    status = models.CharField(max_length=12, choices=TransferStatus.choices, default=TransferStatus.DRAFT, db_index=True, verbose_name=_("Status"))
    notes = models.CharField(max_length=500, blank=True, verbose_name=_("Notes"))
    created_by = models.CharField(max_length=150, blank=True, verbose_name=_("Created by"))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Created"))
    updated_at = models.DateTimeField(auto_now=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.CharField(max_length=150, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent"))
    received_by = models.CharField(max_length=150, blank=True)
    received_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Received"))
    completed_by = models.CharField(max_length=150, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=150, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    # Final receipt recorded a shortage / excess that a manager still has to approve.
    discrepancy_open = models.BooleanField(default=False, verbose_name=_("Discrepancy awaiting approval"))

    class Meta:
        db_table = "stores_stock_transfers"
        ordering = ["-created_at"]
        verbose_name = _("Inventory transfer")
        verbose_name_plural = _("Inventory transfers")
        permissions = [
            ("send_stocktransfer", "Can dispatch inventory transfers"),
            ("receive_stocktransfer", "Can receive inventory transfers"),
            ("approve_discrepancy", "Can approve transfer discrepancies"),
            ("cancel_stocktransfer", "Can cancel inventory transfers"),
        ]
        constraints = [models.CheckConstraint(condition=~models.Q(source=models.F("destination")), name="ck_transfer_source_ne_destination")]

    def __str__(self) -> str:  # pragma: no cover
        return self.number


class StockTransferItem(models.Model):
    """One product on a transfer: planned → picked (scanned at the source) → dispatched → received (scanned at the destination)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.PROTECT, related_name="+", verbose_name=_("Product"))
    name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=64, blank=True)
    barcode = models.CharField(max_length=64, blank=True)
    expected_quantity = models.PositiveIntegerField(default=0, verbose_name=_("Planned"))
    picked_quantity = models.PositiveIntegerField(default=0, verbose_name=_("Picked (scanned)"))
    dispatched_quantity = models.PositiveIntegerField(default=0, verbose_name=_("Dispatched"))
    received_quantity = models.PositiveIntegerField(default=0, verbose_name=_("Received (counted)"))
    received_posted = models.PositiveIntegerField(default=0)  # units already added to the destination's stock
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Unit price"))
    batch_number = models.CharField(max_length=48, blank=True, verbose_name=_("Batch"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry"))
    discrepancy_reason = models.CharField(max_length=20, choices=DiscrepancyReason.choices, blank=True, verbose_name=_("Discrepancy reason"))
    discrepancy_note = models.CharField(max_length=255, blank=True, verbose_name=_("Discrepancy note"))
    resolution = models.CharField(max_length=20, blank=True)  # write_off / return_to_source / deduct_source / accept
    resolved_by = models.CharField(max_length=150, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    batch_allocations = models.JSONField(default=list, blank=True)  # [{batch, expiry, qty}] the batches the dispatched units left from

    class Meta:
        db_table = "stores_stock_transfer_items"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["transfer", "product_variant", "batch_number"], name="uq_transfer_item_variant_batch")]

    @property
    def difference(self) -> int:
        return self.received_quantity - self.dispatched_quantity


class StockTransferEvent(models.Model):
    """Append-only audit trail of a transfer: who did what, when, with the old / new values."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=32, verbose_name=_("Action"))
    message = models.CharField(max_length=300, verbose_name=_("Message"))
    actor = models.CharField(max_length=150, blank=True, verbose_name=_("User"))
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "stores_stock_transfer_events"
        ordering = ["created_at"]


# ---------------------------------------------------------------- stock count (Inventarizatsiya)


class StockCountStatus(models.TextChoices):
    COUNTING = "counting", _("Sanalmoqda")
    REVIEW = "review", _("Tekshiruvda")
    POSTED = "posted", _("Tasdiqlangan")
    CANCELLED = "cancelled", _("Bekor qilingan")


class StockCountScope(models.TextChoices):
    FULL = "full", _("To'liq (joydagi barcha mahsulot)")
    PARTIAL = "partial", _("Tanlangan mahsulotlar")


class CountReason(models.TextChoices):
    DAMAGED = "damaged", _("Shikastlangan")
    EXPIRED = "expired", _("Muddati o'tgan")
    LOST = "lost", _("Yo'qolgan / o'g'irlik")
    UNRECORDED_SALE = "unrecorded_sale", _("Kassadan o'tmagan sotuv")
    UNRECORDED_RECEIPT = "unrecorded_receipt", _("Kirim qilinmagan mahsulot")
    FOUND = "found", _("Topilgan ortiqcha")
    ENTRY_ERROR = "entry_error", _("Avvalgi hisobdagi xato")
    OTHER = "other", _("Boshqa")


class StockCount(models.Model):
    """
    A stock count (Inventarizatsiya): what the system says a location holds vs. what is physically on the shelf.

    Expected quantities are snapshotted when a line enters the count; on posting every difference
    (counted − expected) is applied to the *live* stock as one ledger row, so sales that happened while
    people were counting are not lost. See count_service.py for the workflow.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=20, unique=True, verbose_name=_("Number"))
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="stock_counts", verbose_name=_("Location"))
    status = models.CharField(max_length=12, choices=StockCountStatus.choices, default=StockCountStatus.COUNTING, db_index=True, verbose_name=_("Status"))
    scope = models.CharField(max_length=10, choices=StockCountScope.choices, default=StockCountScope.FULL, verbose_name=_("Scope"))
    blind = models.BooleanField(default=True, verbose_name=_("Blind count"), help_text=_("Counters don't see the system quantity while counting."))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Note"))
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Date"))
    submitted_by = models.CharField(max_length=150, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.CharField(max_length=150, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=150, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    # filled when posted (the report)
    lines_total = models.PositiveIntegerField(default=0)
    lines_matched = models.PositiveIntegerField(default=0)
    shortage_units = models.PositiveIntegerField(default=0)
    excess_units = models.PositiveIntegerField(default=0)
    shortage_value = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    excess_value = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    class Meta:
        db_table = "stores_stock_counts"
        ordering = ["-created_at"]
        verbose_name = _("Stock count")
        verbose_name_plural = _("Stock counts (Inventarizatsiya)")
        permissions = [("post_stockcount", "Can post stock counts (adjust stock)")]

    def __str__(self) -> str:  # pragma: no cover
        return self.number


class StockCountItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.PROTECT, related_name="+", verbose_name=_("Product"))
    name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=64, blank=True)
    barcode = models.CharField(max_length=64, blank=True)
    expected_quantity = models.IntegerField(default=0)  # system on-hand when the line entered the count
    counted_quantity = models.IntegerField(null=True, blank=True)  # null = not counted yet
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reason = models.CharField(max_length=24, choices=CountReason.choices, blank=True)
    note = models.CharField(max_length=255, blank=True)
    counted_by = models.CharField(max_length=150, blank=True)
    counted_at = models.DateTimeField(null=True, blank=True)
    added_during_count = models.BooleanField(default=False)  # scanned although not on the list
    adjusted_quantity = models.IntegerField(default=0)  # the ledger change actually posted

    class Meta:
        db_table = "stores_stock_count_items"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["count", "product_variant"], name="uniq_stock_count_variant")]

    @property
    def difference(self) -> int:
        return (self.counted_quantity or 0) - self.expected_quantity if self.counted_quantity is not None else 0


# ======================================================================== suppliers, reorder points, write-offs


class Supplier(models.Model):
    """A company goods are bought from. Goods receipts are what we owe it; SupplierPayment rows are what we paid."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, verbose_name=_("Name"))
    legal_name = models.CharField(max_length=200, blank=True, verbose_name=_("Legal name"))
    tin = models.CharField(max_length=20, blank=True, verbose_name=_("STIR (TIN)"))
    contact_person = models.CharField(max_length=120, blank=True, verbose_name=_("Contact person"))
    phone = models.CharField(max_length=40, blank=True, verbose_name=_("Phone"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    address = models.CharField(max_length=255, blank=True, verbose_name=_("Address"))
    bank_details = models.CharField(max_length=255, blank=True, verbose_name=_("Bank details"), help_text=_("Bank, account number, MFO."))
    payment_terms_days = models.PositiveSmallIntegerField(default=0, verbose_name=_("Payment terms (days)"), help_text=_("0 = paid on delivery. A receipt is overdue after this many days."))
    note = models.TextField(blank=True, verbose_name=_("Note"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stores_suppliers"
        ordering = ["name"]
        verbose_name = _("Supplier")
        verbose_name_plural = _("Yetkazib beruvchilar")
        constraints = [models.UniqueConstraint(Lower("name"), name="uniq_supplier_name_ci")]

    def __str__(self) -> str:
        return self.name


class PaymentMethod(models.TextChoices):
    BANK = "bank", _("Bank o'tkazmasi")
    CASH = "cash", _("Naqd")
    CARD = "card", _("Karta")
    OFFSET = "offset", _("O'zaro hisob / qaytarish")


class SupplierPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments", verbose_name=_("Supplier"))
    amount = models.DecimalField(max_digits=16, decimal_places=2, verbose_name=_("Amount"))
    paid_on = models.DateField(verbose_name=_("Paid on"))
    method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.BANK, verbose_name=_("Method"))
    reference = models.CharField(max_length=60, blank=True, verbose_name=_("Document No."))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Note"))
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stores_supplier_payments"
        ordering = ["-paid_on", "-created_at"]
        verbose_name = _("Supplier payment")
        verbose_name_plural = _("Supplier payments")


class ReorderRule(models.Model):
    """
    Reorder point of one product at one location: when available + incoming falls to `min_quantity`,
    the replenishment page suggests sending enough to reach `target_quantity`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="reorder_rules", verbose_name=_("Location"))
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.CASCADE, related_name="+", verbose_name=_("Product"))
    min_quantity = models.PositiveIntegerField(verbose_name=_("Minimum"))
    target_quantity = models.PositiveIntegerField(verbose_name=_("Fill up to"))
    updated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stores_reorder_rules"
        verbose_name = _("Reorder point")
        verbose_name_plural = _("Minimal qoldiq")
        constraints = [
            models.UniqueConstraint(fields=["store", "product_variant"], name="uniq_reorder_rule"),
            models.CheckConstraint(condition=models.Q(target_quantity__gte=models.F("min_quantity")), name="reorder_target_gte_min"),
        ]


class WriteOffStatus(models.TextChoices):
    PENDING = "pending", _("Tasdiq kutilmoqda")
    APPROVED = "approved", _("Tasdiqlangan")
    REJECTED = "rejected", _("Rad etilgan")
    CANCELLED = "cancelled", _("Bekor qilingan")


class WriteOffReason(models.TextChoices):
    DAMAGED = "damaged", _("Shikastlangan")
    EXPIRED = "expired", _("Muddati o'tgan")
    DEFECT = "defect", _("Sifatsiz / nuqsonli")
    LOST = "lost", _("Yo'qolgan / o'g'irlik")
    TESTER = "tester", _("Tester / namuna")
    INTERNAL = "internal", _("Ichki ehtiyoj")
    OTHER = "other", _("Boshqa")


class WriteOff(models.Model):
    """
    Hisobdan chiqarish -- removing damaged / expired / lost goods from a location's stock with a reason and approval.
    Submitting reserves the units (they stop being sellable); approval deducts them; rejection releases them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=20, unique=True, verbose_name=_("Number"))
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="write_offs", verbose_name=_("Location"))
    status = models.CharField(max_length=12, choices=WriteOffStatus.choices, default=WriteOffStatus.PENDING, db_index=True, verbose_name=_("Status"))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Note"))
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Date"))
    decided_by = models.CharField(max_length=150, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)
    total_units = models.PositiveIntegerField(default=0)
    total_value = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    class Meta:
        db_table = "stores_write_offs"
        ordering = ["-created_at"]
        verbose_name = _("Write-off")
        verbose_name_plural = _("Hisobdan chiqarish")
        permissions = [("approve_writeoff", "Can approve write-offs (deduct stock)")]

    def __str__(self) -> str:
        return self.number


class WriteOffItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    write_off = models.ForeignKey(WriteOff, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.PROTECT, related_name="+", verbose_name=_("Product"))
    name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=64, blank=True)
    barcode = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField(verbose_name=_("Quantity"))
    reason = models.CharField(max_length=12, choices=WriteOffReason.choices, verbose_name=_("Reason"))
    batch_number = models.CharField(max_length=48, blank=True, verbose_name=_("Batch"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry"))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "stores_write_off_items"
        ordering = ["name"]


# ======================================================================== batch-level stock


class StockBatch(models.Model):
    """
    What a location holds of one product, per batch (partiya) and expiry date. The batches of a product at a
    location always add up to StoreProductStock.quantity -- stock_service.move() keeps them in step (outgoing
    units leave the batch that expires first, FEFO). batch_number "" / expiry None = "no batch recorded".
    Rows are kept at 0 for the history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="stock_batches", verbose_name=_("Location"))
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.CASCADE, related_name="+", verbose_name=_("Product"))
    batch_number = models.CharField(max_length=48, blank=True, verbose_name=_("Batch"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry"))
    quantity = models.PositiveIntegerField(default=0, verbose_name=_("Quantity"))
    received_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stores_stock_batches"
        verbose_name = _("Stock batch")
        verbose_name_plural = _("Stock batches")
        constraints = [models.UniqueConstraint(fields=["store", "product_variant", "batch_number", "expiry_date"], name="uniq_stock_batch", nulls_distinct=False)]
        indexes = [models.Index(fields=["store", "product_variant"]), models.Index(fields=["expiry_date"])]


class StockMovementBatch(models.Model):
    """Which batches one ledger row took units from / put units into (signed, like StockMovement.quantity)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement = models.ForeignKey(StockMovement, on_delete=models.CASCADE, related_name="batches")
    batch = models.ForeignKey(StockBatch, on_delete=models.CASCADE, related_name="movements")
    quantity = models.IntegerField()

    class Meta:
        db_table = "stores_stock_movement_batches"


# ======================================================================== POS cashiers (PIN sign-in at the terminal)


class StoreCashier(models.Model):
    """
    A cashier: a customer account (identity.User) a superadmin links to ONE kassa (store). The person signs in to the
    storefront with their own account, sees the store under "My store" (register, sales, stock, shifts -- not the
    store's settings) and every sale they ring up carries their user id (SaleModel.cashier_id). Several cashiers can
    share a kassa; the kassa's PIN (Store.pos_pin_hash) opens the shift and hands the terminal from one cashier to another.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="cashier_links", verbose_name=_("Kassa"))
    user = models.OneToOneField("identity.User", on_delete=models.CASCADE, related_name="cashier_link", verbose_name=_("Cashier"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Active"))
    added_by = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Added by"))
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Last activity"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Added"))
    # Pay: a fixed monthly base + KPI = kpi_percent of the cashier's own net sales that month (see payroll.py).
    base_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("3000000"), verbose_name=_("Base salary"))
    kpi_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("3"), verbose_name=_("KPI, % of sales"))

    class Meta:
        db_table = "stores_cashiers"
        ordering = ["store__name", "user__full_name"]
        verbose_name = _("Cashier")
        verbose_name_plural = _("Kassirlar")

    def __str__(self) -> str:
        return f"{self.user} @ {self.store}"


class CashierPayout(models.Model):
    """
    One cashier's pay for one month, frozen when it is paid: the sales it was computed from, the base and KPI rate
    in force, an optional adjustment (bonus +, deduction −) with its reason, and the total handed over.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="cashier_payouts", verbose_name=_("Cashier"))
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="cashier_payouts", verbose_name=_("Kassa"))
    month = models.DateField(db_index=True, verbose_name=_("Month"))  # the 1st of the month
    sales_count = models.PositiveIntegerField(default=0, verbose_name=_("Sales"))
    revenue = models.DecimalField(max_digits=16, decimal_places=2, default=0, verbose_name=_("Net sales"))
    base_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Base salary"))
    kpi_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("KPI, % of sales"))
    kpi_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("KPI"))
    adjustment = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("Adjustment"))
    adjustment_note = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Reason"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_("To pay"))
    paid_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Paid at"))
    paid_by = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Paid by"))

    class Meta:
        db_table = "stores_cashier_payouts"
        ordering = ["-month", "user__full_name"]
        constraints = [models.UniqueConstraint(fields=["user", "month"], name="uniq_cashier_payout_month")]
        verbose_name = _("Cashier payout")
        verbose_name_plural = _("Cashier payouts")

    def __str__(self) -> str:
        return f"{self.user} {self.month:%Y-%m}"


class StoreOrderLog(models.Model):
    """Every hand-over of an online order to a branch and every hand-back -- the branch report counts both (a handed-back
    order no longer carries the branch, so this log is the only record of it). Written by store_orders.assign / act."""

    ASSIGNED, HANDED_BACK = "assigned", "handed_back"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="order_logs")
    order_number = models.CharField(max_length=30, db_index=True)
    event = models.CharField(max_length=12, choices=[(ASSIGNED, "Biriktirildi"), (HANDED_BACK, "Omborga qaytarildi")], db_index=True)
    method = models.CharField(max_length=10, default="delivery")
    reason = models.CharField(max_length=300, blank=True, default="")
    actor = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "stores_store_order_log"
        ordering = ["-created_at"]
