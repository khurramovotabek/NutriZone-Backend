from __future__ import annotations

import uuid

from django.db import models


class TelegramCheckoutConfirmation(models.Model):
    """
    Phase 15D: real, DB-level idempotency for order confirmation via
    Telegram. `cart_id` has a real unique constraint -- a duplicate or
    concurrent confirmation attempt for the same cart hits this
    constraint (IntegrityError) before any second Order can ever be
    created, matching this project's own established "let a real
    PostgreSQL constraint decide the race" discipline (e.g.
    OrderConfirmedNotificationCursor, PaymentModel.provider_reference).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart_id = models.UUIDField(unique=True, db_index=True)
    customer_id = models.UUIDField(db_index=True)
    order_number = models.CharField(max_length=32, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "telegram_bot_checkout_confirmations"


class TelegramStaffMember(models.Model):
    """
    Phase 15E: the authorization boundary for manager-facing actions
    (confirm/cancel an order from the Orders Channel). Deliberately an
    explicit allowlist, not self-service -- a Telegram user cannot
    grant themselves staff access via any bot command; rows here are
    only ever created via Django admin or a management command by
    someone who already has that access, matching this project's own
    principle that authorization must never be self-granted.
    """

    telegram_user_id = models.BigIntegerField(primary_key=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "telegram_bot_staff_members"

    def __str__(self) -> str:  # pragma: no cover
        return f"TelegramStaffMember({self.telegram_user_id})"


class TelegramOrdersChannelCursor(models.Model):
    """Independent progress marker through Ordering's own outbox, filtered to OrderCreated -- mirrors the exact, proven pattern already established by OrderConfirmedNotificationCursor/TelegramDispatchCursor."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_processed_created_at = models.DateTimeField(null=True, blank=True)
    last_processed_id = models.UUIDField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_bot_orders_channel_cursor"


class TelegramOrderChannelMessage(models.Model):
    """
    Records which Telegram message announced which real Order, so a
    manager's confirm/cancel button-press can edit that exact message
    afterward (removing the buttons, preventing a second click) and so
    a duplicate outbox replay can detect "already posted" and skip
    re-announcing the same order.
    """

    order_id = models.UUIDField(primary_key=True)
    chat_id = models.CharField(max_length=64)
    message_id = models.CharField(max_length=64)
    resolved_at = models.DateTimeField(null=True, blank=True)  # set once a manager confirms/cancels -- a second action is then a safe no-op

    class Meta:
        db_table = "telegram_bot_order_channel_messages"


class TelegramPosSaleChannelMessage(models.Model):
    """
    One row per POS sale event announced to the Orders Channel -- "completed"
    (the new-order post) and "refunded" (the return notice). The unique
    (sale_id, kind) pair is the exactly-once guard for a cursor replay,
    mirroring TelegramOrderChannelMessage's own role for online orders.
    """

    KIND_COMPLETED = "completed"
    KIND_REFUNDED = "refunded"

    id = models.BigAutoField(primary_key=True)
    sale_id = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=16)
    chat_id = models.CharField(max_length=64)
    message_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "telegram_bot_pos_sale_channel_messages"
        constraints = [models.UniqueConstraint(fields=["sale_id", "kind"], name="uniq_pos_sale_channel_message_kind")]


class TelegramAfterSalesChannelMessage(models.Model):
    """
    One row per customer after-sales event announced to the Orders Channel (after_sales_channel_subscriber.py):
    a return request, a cancellation request, or an order the customer cancelled themselves. `event_key`
    ("return:<id>", "cancellation:<id>", "order_cancel:<order id>") is the exactly-once guard for a cursor replay;
    `resolved_at` makes a second press of the message's button a safe no-op.
    """

    event_key = models.CharField(max_length=80, primary_key=True)
    chat_id = models.CharField(max_length=64)
    message_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "telegram_after_sales_channel_messages"


class TelegramBotSubscriber(models.Model):
    """
    Someone who pressed /start in one of the staff bots (Orders bot / Analytics bot). A bot can only write to people
    who started it, so this is the delivery list. Who sees what is decided at send time from live data, never from
    this row: store owners (stores.Store.owner, matched by the identity user's telegram_user_id) get only their own
    branches; the explicit allowlists (TelegramStaffMember / TELEGRAM_ANALYTICS_CHAT_IDS) get everything.
    """

    BOT_ORDERS = "orders"
    BOT_ANALYTICS = "analytics"
    BOTS = [(BOT_ORDERS, "Orders bot"), (BOT_ANALYTICS, "Analytics bot")]

    id = models.BigAutoField(primary_key=True)
    bot = models.CharField(max_length=16, choices=BOTS)
    chat_id = models.BigIntegerField()
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    display_name = models.CharField(max_length=255, blank=True, default="")
    username = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)  # false once Telegram says the user blocked the bot
    store_filter = models.UUIDField(null=True, blank=True)  # analytics: the branch an all-access viewer last picked (null = all)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_bot_subscribers"
        constraints = [models.UniqueConstraint(fields=["bot", "chat_id"], name="uniq_bot_subscriber_chat")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.bot}:{self.chat_id}"


class TelegramStorePost(models.Model):
    """Exactly-once guard for posts fanned out to store owners (one row per thing × chat)."""

    id = models.BigAutoField(primary_key=True)
    bot = models.CharField(max_length=16)
    key = models.CharField(max_length=120)  # e.g. "sale:<uuid>", "order:<uuid>", "chat:<message uuid>"
    chat_id = models.BigIntegerField()
    message_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "telegram_bot_store_posts"
        constraints = [models.UniqueConstraint(fields=["bot", "key", "chat_id"], name="uniq_store_post")]


class TelegramPostStatus(models.TextChoices):
    DRAFT = "draft", "Qoralama"
    SCHEDULED = "scheduled", "Rejalashtirilgan"
    QUEUED = "queued", "Navbatda"
    SENDING = "sending", "Yuborilmoqda"
    SENT = "sent", "Yuborildi"
    FAILED = "failed", "Xato"


class TelegramPost(models.Model):
    """
    A rich post composed in Dashboard → Telegram → Postlar and sent by @<customer bot> to the shop's channel,
    news subscribers and/or every Telegram-linked customer: formatted text (RichText editor), a photo (uploaded
    or the attached product's), URL buttons. Sending runs on Celery (posts.send) and is recorded here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField("Ichki nom", max_length=120, help_text="Faqat dashboardda ko'rinadi (mijozga yuborilmaydi).")
    body = models.TextField("Post matni", blank=True, default="")
    image = models.ImageField("Rasm", upload_to="telegram/posts/%Y/%m/", blank=True, null=True)
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Mahsulot",
                                help_text="Tanlansa: rasm bo'lmasa mahsulot rasmi qo'yiladi va «Sotib olish» tugmasi qo'shiladi.")
    buttons = models.JSONField("Tugmalar", default=list, blank=True)  # [{"text": ..., "url": ...}]
    to_channel = models.BooleanField("Kanalga", default=False)
    channel = models.CharField("Kanal", max_length=100, blank=True, default="", help_text="@username yoki -100… ID. Bot kanalda admin bo'lishi kerak.")
    to_subscribers = models.BooleanField("Yangilik obunachilariga", default=False)
    to_customers = models.BooleanField("Barcha Telegram mijozlarga", default=False)
    to_orders_channel = models.BooleanField("Buyurtmalar kanaliga (Orders bot)", default=False)
    to_orders_staff = models.BooleanField("Orders bot xodimlariga", default=False, help_text="Orders botda /start bosgan filial egalari va xodimlar.")
    to_analytics_staff = models.BooleanField("Analytics bot obunachilariga", default=False, help_text="Analytics botda /start bosgan rahbarlar va filial egalari.")
    scheduled_at = models.DateTimeField("Yuborish vaqti", null=True, blank=True, db_index=True,
                                        help_text="Bo'sh — darhol yuboriladi. Vaqt tanlansa, post shu daqiqada o'zi yuboriladi (Toshkent vaqti).")
    silent = models.BooleanField("Ovozsiz yuborish", default=False)
    pin = models.BooleanField("Kanalda qadab qo'yish", default=False)
    source = models.CharField("Manba", max_length=16, default="manual", db_index=True)  # manual / new / sale / restock
    dedupe_key = models.CharField(max_length=120, null=True, blank=True, unique=True)  # auto posts: one per product event
    status = models.CharField("Holat", max_length=12, choices=TelegramPostStatus.choices, default=TelegramPostStatus.DRAFT, db_index=True)
    recipients = models.PositiveIntegerField("Qabul qiluvchilar", default=0)
    sent_count = models.PositiveIntegerField("Yetkazildi", default=0)
    failed_count = models.PositiveIntegerField("Xato", default=0)
    channel_message_id = models.BigIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField("Yuborilgan vaqt", null=True, blank=True)
    created_by = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_posts"
        ordering = ("-created_at",)
        verbose_name = "Telegram post"
        verbose_name_plural = "Telegram postlar"

    def __str__(self) -> str:
        return self.title


class ChannelAutoPostSettings(models.Model):
    """Dashboard → Telegram → Kanal avtopostlari (singleton, pk=1): which catalog events the bot posts to the shop channel."""

    enabled = models.BooleanField("Avtopostlar yoqilgan", default=False)
    channel = models.CharField("Kanal", max_length=100, blank=True, default="", help_text="Bo'sh bo'lsa — Sayt sozlamalaridagi Telegram kanal.")
    new_products = models.BooleanField("Yangi mahsulotlar", default=True)
    discounts = models.BooleanField("Chegirmalar", default=True)
    min_discount = models.PositiveSmallIntegerField("Minimal chegirma (%)", default=10)
    restock = models.BooleanField("Yana sotuvda (omborga qaytgan)", default=True)
    quiet_from = models.PositiveSmallIntegerField("Jim rejim boshlanishi (soat)", default=22)
    quiet_to = models.PositiveSmallIntegerField("Jim rejim tugashi (soat)", default=9)
    max_per_run = models.PositiveSmallIntegerField("Bir martada ko'pi bilan", default=2, help_text="Har 15 daqiqada shuncha postdan oshmaydi — kanal spam bo'lmasin.")
    enabled_at = models.DateTimeField(null=True, blank=True)  # backlog guard: only products published after this are "new"
    daily_enabled = models.BooleanField("Kunlik jadval yoqilgan", default=True,
                                        help_text="Har kuni jadvaldagi vaqtlarda kanalga bittadan mahsulot posti (daily_posts.py).")
    daily_template = models.TextField("Post shabloni", blank=True, default="")
    repeat_days = models.PositiveSmallIntegerField("Takrorlamaslik (kun)", default=14, help_text="Bir mahsulot kanalda shuncha kun ichida qayta chiqmaydi.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_channel_autopost_settings"
        verbose_name = "Kanal jadvali"
        verbose_name_plural = "Kanal jadvali"

    def __str__(self) -> str:
        return "Kanal jadvali"

    @classmethod
    def get(cls) -> "ChannelAutoPostSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ProductStockFlag(models.Model):
    """Last seen availability per product -- lets the auto poster notice "sold out → back in stock"."""

    product_id = models.UUIDField(primary_key=True)
    in_stock = models.BooleanField(default=False)
    changed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_product_stock_flags"


class OrdersChannelSettings(models.Model):
    """
    Dashboard → Telegram botlar markazi → "Buyurtmalar kanali" (singleton, pk=1): the chat the Orders bot posts online
    orders, kassa sales and after-sales requests to. Set without a deploy -- automatically when the bot is made an
    admin of a channel (or someone posts /ulash there), or from the dashboard. Blank → the TELEGRAM_ORDERS_CHAT_ID env
    fallback (apps/telegram_bot/infrastructure/orders_chat.py is the only reader).
    """

    chat_id = models.CharField("Chat ID", max_length=64, blank=True, default="")
    title = models.CharField("Nomi", max_length=255, blank=True, default="")
    chat_type = models.CharField(max_length=20, blank=True, default="")
    username = models.CharField(max_length=64, blank=True, default="")
    connected_at = models.DateTimeField(null=True, blank=True)
    connected_by = models.CharField(max_length=150, blank=True, default="")
    last_error = models.CharField(max_length=500, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_orders_channel_settings"
        verbose_name = "Buyurtmalar kanali"
        verbose_name_plural = "Buyurtmalar kanali"

    def __str__(self) -> str:  # pragma: no cover
        return self.title or self.chat_id or "Buyurtmalar kanali"


class TelegramBotChat(models.Model):
    """Groups/channels a staff bot was added to (from my_chat_member / channel_post updates) -- the dashboard's pick list."""

    id = models.BigAutoField(primary_key=True)
    bot = models.CharField(max_length=16, default="orders")
    chat_id = models.BigIntegerField()
    title = models.CharField(max_length=255, blank=True, default="")
    chat_type = models.CharField(max_length=20, blank=True, default="")
    username = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, blank=True, default="")  # creator / administrator / member / left / kicked
    can_post = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_bot_chats"
        ordering = ("-updated_at",)
        constraints = [models.UniqueConstraint(fields=["bot", "chat_id"], name="uniq_bot_chat")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.bot}:{self.title or self.chat_id}"


class ChannelPostSlot(models.Model):
    """One daily time in the shop channel's schedule (Dashboard → Telegram → Kanal jadvali): at `time` one product post."""

    KIND_TOP = "top"
    KIND_SALE = "sale"
    KIND_NEW = "new"
    KIND_PICK = "pick"
    KINDS = [(KIND_TOP, "Kun mahsuloti (eng ko'p sotilgan / yuqori baho)"), (KIND_SALE, "Chegirmadagi mahsulot"),
             (KIND_NEW, "Yangi kelgan mahsulot"), (KIND_PICK, "Tasodifiy tavsiya")]

    settings = models.ForeignKey(ChannelAutoPostSettings, on_delete=models.CASCADE, related_name="slots", default=1)
    time = models.TimeField("Vaqt")
    kind = models.CharField("Nima post qilinadi", max_length=8, choices=KINDS, default=KIND_TOP)
    heading = models.CharField("Sarlavha", max_length=120, blank=True, default="", help_text="Postning birinchi qatori, masalan «☀️ Kun mahsuloti».")
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        db_table = "telegram_channel_post_slots"
        ordering = ("time",)
        verbose_name = "Jadval vaqti"
        verbose_name_plural = "Jadval vaqtlari"

    def __str__(self) -> str:
        return f"{self.time:%H:%M} · {self.get_kind_display()}"
