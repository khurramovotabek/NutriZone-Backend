"""
Telegram callback router -- Phase 15C, i18n added Phase 15G.

Callback data format: "namespace:action:id" (compact, per this
phase's own explicit convention). Every handler re-resolves the
authenticated customer via ResolveTelegramCustomer before acting --
callback data supplies only *what* to act on, never *who* is
authorized to act (that always comes from the verified
telegram_user_id on the update itself, never from the callback
payload).

i18n: reuses the real, existing User.language field -- every
customer-facing string is now looked up via t(key, lang, **kwargs)
instead of hardcoded Uzbek text.
"""
from __future__ import annotations

import html
import re
import logging
import uuid

from apps.telegram_bot.interfaces.i18n import t
from common.exceptions import ResourceNotFound

logger = logging.getLogger("nutrizone.app")


def _lang(user) -> str:
    return getattr(user, "language", None) or "uz"


def mini_app_url() -> str | None:
    """The storefront's Telegram Mini App entry (/tg) -- only over HTTPS, the one scheme Telegram opens in a Mini App."""
    from django.conf import settings as django_settings

    frontend = (getattr(django_settings, "FRONTEND_URL", None) or "").rstrip("/")
    return f"{frontend}/tg" if frontend.startswith("https://") else None


def _main_menu_keyboard(lang: str) -> list:
    """The shop in one tap on top (Mini App), then the bot's own sections two per row."""
    rows = []
    shop = mini_app_url()
    if shop:
        rows.append([{"text": t("menu_open_shop", lang), "web_app": {"url": shop}}])
    rows += [
        [{"text": t("menu_products", lang), "callback_data": "menu:products"}, {"text": t("menu_catalog", lang), "callback_data": "menu:catalog"}],
        [{"text": t("menu_brands", lang), "callback_data": "menu:brands"}, {"text": t("menu_cart", lang), "callback_data": "menu:cart"}],
        [{"text": t("menu_orders", lang), "callback_data": "menu:orders"}, {"text": t("menu_loyalty", lang), "callback_data": "menu:loyalty"}],
        [{"text": t("menu_find", lang), "callback_data": "menu:find"}, {"text": t("menu_stores", lang), "callback_data": "menu:stores"}],
        [{"text": t("menu_chat", lang), "callback_data": "menu:chat"}, {"text": t("menu_news", lang), "callback_data": "menu:news"}],
        [{"text": t("menu_autologin", lang), "callback_data": "menu:autologin"}],
        [{"text": t("menu_getcode", lang), "callback_data": "menu:getcode"}],
        [{"text": t("menu_social", lang), "callback_data": "menu:social"}, {"text": "\U0001F310 Til / Язык / Language", "callback_data": "menu:lang"}],
    ]
    return rows


def _send(chat_id: int, text: str, keyboard: list | None = None) -> None:
    from apps.notifications.infrastructure import composition as notifications_composition

    try:
        gateway = notifications_composition.build_telegram_gateway()
        if keyboard is not None:
            gateway.send_message_with_keyboard(str(chat_id), text, keyboard)
        else:
            gateway.send_message(str(chat_id), "", text)
    except Exception:  # noqa: BLE001
        logger.warning("Telegram bot: failed to send message to chat %s", chat_id)


def _send_venues(chat_id: int, venues: list) -> None:
    """The branches an advisor answer is about, as real map pins (open in the user's own map app with one tap)."""
    from apps.notifications.infrastructure import composition as notifications_composition

    if not venues:
        return
    try:
        gateway = notifications_composition.build_telegram_gateway()
        for v in venues[:3]:
            gateway.send_venue(str(chat_id), v["lat"], v["lng"], v["title"][:60], (v.get("address") or "")[:120])
    except Exception:  # noqa: BLE001 -- the text answer already has the map links
        logger.warning("Telegram bot: failed to send branch pins to chat %s", chat_id)


AI_CHIPS_TTL = 6 * 3600


def _chip_rows(chat_id: int, chips: list) -> list:
    """Quick replies under an advisor answer: their texts are kept in the cache (callback data is limited to 64 bytes)."""
    from django.core.cache import cache

    chips = [c for c in (chips or []) if c][:4]
    if not chips:
        return []
    cache.set(f"tg:aiq:{chat_id}", chips, AI_CHIPS_TTL)
    pairs = [chips[i:i + 2] for i in range(0, len(chips), 2)]
    return [[{"text": f"💬 {c[:30]}", "callback_data": f"aiq:{chips.index(c)}"} for c in pair] for pair in pairs]


def _chip_tapped(chat_id: int, telegram_user_id: int, index: str | None) -> None:
    from django.core.cache import cache

    chips = cache.get(f"tg:aiq:{chat_id}") or []
    try:
        text = chips[int(index or "")]
    except (ValueError, IndexError):
        return
    search_text(chat_id, telegram_user_id, text)


def _resolve_user(telegram_user_id: int):
    from apps.identity.infrastructure import models as identity_orm
    from apps.telegram_bot.application.services.linking import ResolveTelegramCustomer

    customer_id = ResolveTelegramCustomer().execute(telegram_user_id)
    if customer_id is None:
        return None
    return identity_orm.User.objects.filter(id=customer_id).first()


def send_main_menu(chat_id: int, lang: str = "uz", user=None) -> None:
    """The main menu, greeting the shopper by name and showing what's in their cart (shared with the Mini App)."""
    if user is None:
        user = _resolve_user(chat_id) if isinstance(chat_id, int) and chat_id > 0 else None
    head = []
    if user is not None:
        first = (user.full_name or "").split()[0] if (user.full_name or "").strip() else ""
        if first:
            head.append(t("menu_greeting", lang, name=html.escape(first)))
        try:
            from apps.telegram_bot.application.services.shopping import TelegramCartService

            cart = TelegramCartService().view_cart(user) if user.telegram_cart_id else None
            units = sum(i["quantity"] for i in cart["items"]) if cart else 0
            if units:
                head.append(t("menu_cart_line", lang, units=units, total=money_text(cart["total"], lang)))
        except Exception:  # noqa: BLE001 - the menu never fails because of the cart line
            logger.info("main menu: cart line unavailable for chat %s", chat_id)
    text = t("main_menu", lang)
    if head:
        text = text.replace("\n\n", "\n" + "\n".join(head) + "\n\n", 1)
    _send(chat_id, text, _main_menu_keyboard(lang))
    set_chat_menu_button(chat_id, lang)


COMMANDS = {"menu": "home", "menyu": "home", "savat": "cart", "cart": "cart", "buyurtmalar": "orders", "orders": "orders", "dokon": "shop", "shop": "shop",
            "topish": "find", "find": "find", "filiallar": "stores", "stores": "stores", "privacy": "privacy", "yordam": "help", "help": "help"}


def run_command(chat_id: int, telegram_user_id: int, command: str) -> bool:
    """/menu /savat /buyurtmalar /dokon (and their English twins) from the bot's command list. False = not ours."""
    action = COMMANDS.get(command)
    if action is None:
        return False
    user = _resolve_user(telegram_user_id)
    if action == "privacy":  # works before sign-up too: Telegram asks every bot to answer /privacy
        _show_legal(chat_id, _lang(user) if user else "uz")
        return True
    if user is None:
        _send(chat_id, t("please_register", "uz"), [])
        return True
    lang = _lang(user)
    if action in ("find", "stores", "help"):
        _handle_menu(user, chat_id, action, None, lang)
    elif action == "home":
        send_main_menu(chat_id, lang, user=user)
    elif action == "cart":
        _show_cart(user, chat_id, lang)
    elif action == "orders":
        _handle_menu(user, chat_id, "orders", None, lang)
    else:
        shop = mini_app_url()
        if shop:
            _send(chat_id, t("menu_open_shop", lang), [[{"text": t("menu_open_shop", lang), "web_app": {"url": shop}}]])
        else:
            send_main_menu(chat_id, lang, user=user)
    return True


def _send_rich(chat_id: int, build, keyboard: list | None = None) -> bool:
    """Sends a rich screen (shop_rich builders) through the customer bot. False = the caller sends its classic text."""
    from django.conf import settings as django_settings

    token = getattr(django_settings, "TELEGRAM_BOT_TOKEN", None)
    if not token or getattr(django_settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") != "live":
        return False
    try:
        from apps.telegram_bot.infrastructure import rich as R

        doc = build()
        if doc is None:
            return False
        R.send(token, chat_id, doc, keyboard)
        return True
    except Exception:  # noqa: BLE001 -- the classic screen is always there
        logger.warning("Telegram bot: rich screen failed for chat %s", chat_id, exc_info=True)
        return False


def _send_rich_receipt(chat_id: int, order_number: str, lang: str) -> bool:
    """The premium receipt (orders_rich.customer_receipt_doc) through the customer bot. False = send the classic text."""
    from django.conf import settings as django_settings

    token = getattr(django_settings, "TELEGRAM_BOT_TOKEN", None)
    if not token or getattr(django_settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") != "live":
        return False
    try:
        from apps.telegram_bot.infrastructure import orders_rich
        from apps.telegram_bot.infrastructure import rich as R

        doc = orders_rich.customer_receipt_doc(order_number, lang)
        if doc is None:
            return False
        R.send(token, chat_id, doc, [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return True
    except Exception:  # noqa: BLE001
        logger.warning("customer receipt: rich message failed for %s", order_number, exc_info=True)
        return False


def send_welcome(chat_id: int, user, lang: str) -> None:
    """Right after sign-up: a personal welcome with the shop (Mini App) one tap away -- it signs the shopper in by itself."""
    first = ((getattr(user, "full_name", "") or "").split() or [""])[0]
    shop = mini_app_url()
    keyboard = [[{"text": t("menu_open_shop", lang), "web_app": {"url": shop}}]] if shop else []  # [] keeps HTML parse mode
    _send(chat_id, t("welcome_registered", lang, name=html.escape(first or "")).replace(", !", "!"), keyboard)


def set_chat_menu_button(chat_id: int, lang: str) -> None:
    """This chat's menu button (next to the message field) opens the Mini App, labelled in the shopper's language."""
    url = mini_app_url()
    if not url:
        return
    from django.core.cache import cache

    if not cache.add(f"tg:menubtn:{chat_id}:{lang}:{url}", 1, 60 * 60 * 24):  # once a day per chat/language is plenty
        return
    try:
        import requests
        from django.conf import settings as django_settings

        token = getattr(django_settings, "TELEGRAM_BOT_TOKEN", None)
        if not token or getattr(django_settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") != "live":
            return
        base = getattr(django_settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
        requests.post(f"{base}/bot{token}/setChatMenuButton", json={"chat_id": chat_id, "menu_button": {"type": "web_app", "text": t("menu_button_label", lang), "web_app": {"url": url}}}, timeout=5)
    except Exception:  # noqa: BLE001 - cosmetic; the global menu button still opens the shop
        logger.info("menu button: could not set it for chat %s", chat_id)


def handle_callback(callback_query: dict) -> None:
    from_user = callback_query["from"]
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id", from_user["id"])
    data = callback_query.get("data", "")

    parts = data.split(":")
    if len(parts) < 2:
        _send(chat_id, t("unknown_action", "uz"))
        return

    namespace = parts[0]
    action = parts[1]
    arg = parts[2] if len(parts) > 2 else None

    # Manager actions have their own, separate authorization boundary
    # (staff allowlist, not customer identity) -- routed before the
    # customer-identity resolution below, which would incorrectly
    # reject a staff member who has no linked customer account.
    if namespace == "manager":
        _handle_manager_action(from_user["id"], chat_id, message.get("message_id"), action, arg)
        return

    if namespace == "authlogin":
        _handle_auth_login_action(from_user["id"], chat_id, action, arg)
        return

    if namespace == "onboarding":
        _handle_onboarding_action(from_user["id"], chat_id, action, arg)
        return

    user = _resolve_user(from_user["id"])
    if user is None:
        _send(chat_id, t("please_register", "uz"))
        return

    lang = _lang(user)

    try:
        if namespace == "menu":
            _handle_menu(user, chat_id, action, arg, lang)
        elif namespace == "catalog":
            _handle_catalog(user, chat_id, action, arg, lang)
        elif namespace == "cart":
            _handle_cart(user, chat_id, action, arg, lang)
        elif namespace == "checkout":
            _handle_checkout(user, chat_id, action, lang, arg)
        elif namespace == "pay":
            _handle_pay(user, chat_id, action, arg, lang)
        elif namespace == "pm":
            _handle_products_menu(user, chat_id, action, lang, message)
        elif namespace == "pc":
            _handle_product_card(user, chat_id, action, lang, message)
        elif namespace == "po":
            _handle_product_open(user, chat_id, action, arg, lang)
        elif namespace == "sup":
            from apps.telegram_bot.interfaces import support_confirm

            support_confirm.handle(user, chat_id, action, lang)
        elif namespace == "flt":
            _handle_filter(user, chat_id, action, arg, lang, message)
        elif namespace == "ord":
            _handle_order(user, chat_id, action, arg, lang)
        elif namespace == "news":
            from apps.telegram_bot.interfaces import news_menu

            news_menu.handle(user, chat_id, action, lang)
        elif namespace == "fp":
            from apps.telegram_bot.interfaces import find_product

            find_product.handle_callback(user, chat_id, action, lang)
        elif namespace == "st":
            from apps.telegram_bot.interfaces import stores_menu

            stores_menu.handle_callback(chat_id, action, arg, lang)
        elif namespace == "aiq":
            _chip_tapped(chat_id, from_user["id"], action)
        else:
            _send(chat_id, t("unknown_action", lang))
    except ResourceNotFound:
        _send(chat_id, t("not_found", lang))
    except Exception:  # noqa: BLE001
        logger.exception("Telegram callback failed: data=%s telegram_user_id=%s", data, from_user["id"])
        _send(chat_id, t("technical_error", lang))


def _is_authorized_staff(telegram_user_id: int) -> bool:
    from apps.telegram_bot.infrastructure.models import TelegramStaffMember

    return TelegramStaffMember.objects.filter(telegram_user_id=telegram_user_id, is_active=True).exists()


def _handle_manager_action(telegram_user_id: int, chat_id: int, message_id, action: str, order_id: str | None) -> None:
    import uuid as _uuid

    from apps.telegram_bot.infrastructure.models import TelegramOrderChannelMessage

    if not _is_authorized_staff(telegram_user_id):
        logger.warning("Telegram manager action rejected: telegram_user_id=%s is not an authorized staff member.", telegram_user_id)
        return

    if not order_id:
        return

    if action in ("ret_ok", "can_ok"):
        _handle_after_sales_action(telegram_user_id, action, order_id)
        return

    channel_message = TelegramOrderChannelMessage.objects.filter(order_id=_uuid.UUID(order_id)).first()

    if channel_message is not None and channel_message.resolved_at is not None:
        return

    from django.utils import timezone as django_timezone

    from apps.ordering.domain.exceptions import InvalidOrderLifecycleTransition
    from apps.ordering.infrastructure import composition as ordering_composition

    order_uuid = _uuid.UUID(order_id)

    try:
        if action == "confirm":
            order = ordering_composition.build_confirm_order(None).execute(order_uuid)
        elif action == "cancel":
            order = ordering_composition.build_cancel_order(None).execute(order_uuid, reason="Manager cancelled via Telegram Orders Channel")
        else:
            return
    except InvalidOrderLifecycleTransition:
        if channel_message is not None:
            TelegramOrderChannelMessage.objects.filter(order_id=order_uuid).update(resolved_at=django_timezone.now())
        return

    if channel_message is not None:
        TelegramOrderChannelMessage.objects.filter(order_id=order_uuid).update(resolved_at=django_timezone.now())
        try:
            from apps.notifications.infrastructure import composition as notifications_composition

            # The Orders Channel message was sent by the separate Orders
            # Bot (see orders_channel_subscriber.py) -- only the bot that
            # sent a message can edit it, so this must use the same
            # orders-bot-scoped gateway, not the customer-facing one.
            _resolve_order_post(notifications_composition.build_orders_telegram_gateway(), channel_message, order, action, telegram_user_id)
        except Exception:  # noqa: BLE001
            logger.warning("Telegram manager action: order state changed successfully but editing the channel message failed.", exc_info=True)


def _resolve_order_post(gateway, channel_message, order, action: str, telegram_user_id: int) -> None:
    """The post keeps every detail; the headline becomes "✅ TASDIQLANDI · 14:35 — <who>" and Confirm/Cancel go away.
    A post sent with a product photo has a caption, which only editMessageCaption can change."""
    from apps.telegram_bot.infrastructure import orders_post
    from apps.telegram_bot.infrastructure.models import TelegramStaffMember

    who = TelegramStaffMember.objects.filter(telegram_user_id=telegram_user_id).values_list("full_name", flat=True).first()
    card = orders_post.build(order, banner=orders_post.banner(action, who))
    keyboard = orders_post.resolved_keyboard(order, card, confirmed=action == "confirm")
    try:  # a rich post is edited as a rich post: same picture/tables, the new status on top
        from apps.telegram_bot.infrastructure import orders_bot, orders_rich
        from apps.telegram_bot.infrastructure import rich as R

        if orders_bot.token():
            doc, _meta = orders_rich.order_doc(order.id, banner=orders_post.banner(action, who))
            if doc is not None:
                R.edit(orders_bot.token(), channel_message.chat_id, channel_message.message_id, doc, keyboard)
                return
    except Exception:  # noqa: BLE001 - not a rich post (sent before the upgrade) -> classic edit below
        logger.info("manager action: rich edit not possible for %s, using the classic edit", order.id)
    try:
        gateway.edit_message_text(channel_message.chat_id, channel_message.message_id, card["text"], inline_keyboard=keyboard)
    except Exception:  # noqa: BLE001 - a photo post: same content as its caption
        gateway.edit_message_caption(channel_message.chat_id, channel_message.message_id, card["text"], inline_keyboard=keyboard)


def _handle_after_sales_action(telegram_user_id: int, action: str, object_id: str) -> None:
    """
    "Tasdiqlash" on an after-sales post (after_sales_channel_subscriber.py): approves a customer's return request, or
    approves + completes a cancellation request (order, stock and coins are updated by the services). Same staff
    allowlist as the order buttons (checked by the caller); the post is then edited to show who did what.
    """
    import uuid as _uuid

    from django.db import transaction
    from django.utils import timezone as django_timezone

    from apps.ordering.infrastructure import models as ordering_orm
    from apps.ordering.infrastructure.composition import build_ordering_service_context
    from apps.ordering.infrastructure.repositories import DjangoOrderCancellationRepository, DjangoOrderRepository, DjangoOrderReturnRepository
    from apps.telegram_bot.infrastructure.models import TelegramAfterSalesChannelMessage, TelegramStaffMember

    try:
        pk = _uuid.UUID(object_id)
    except ValueError:
        return
    key = f"{'return' if action == 'ret_ok' else 'cancellation'}:{pk}"
    message = TelegramAfterSalesChannelMessage.objects.filter(event_key=key).first()
    if message is not None and message.resolved_at is not None:
        return
    staff = TelegramStaffMember.objects.filter(telegram_user_id=telegram_user_id).values_list("full_name", flat=True).first() or "Menejer"
    ctx = build_ordering_service_context(actor_id=None, actor_label=f"{staff} (Telegram)")
    try:
        with transaction.atomic():
            if action == "ret_ok":
                from apps.ordering.application.services.returns import ApproveReturn

                ApproveReturn(DjangoOrderReturnRepository(), ctx).execute(pk)
                ret = ordering_orm.OrderReturnModel.objects.get(pk=pk)
                text = f"\u2705 <b>QAYTARISH TASDIQLANDI</b>\n\n\U0001F9FE {ret.return_number}\n\U0001F464 {staff}\n\nMahsulot qaytib kelgach, dashboardda \u201cQabul qilish\u201d bosing."
            else:
                from apps.ordering.application.services.cancellations import ApproveCancellation, CompleteCancellation

                repo = DjangoOrderCancellationRepository()
                ApproveCancellation(repo, ctx).execute(pk)
                CompleteCancellation(repo, ctx, DjangoOrderRepository()).execute(pk)
                can = ordering_orm.OrderCancellationModel.objects.get(pk=pk)
                number = ordering_orm.OrderModel.objects.filter(id=can.order_id).values_list("order_number", flat=True).first() or ""
                text = f"\u2705 <b>BEKOR QILISH TASDIQLANDI</b>\n\n\U0001F9FE {number}\n\U0001F464 {staff}\n\nBuyurtma va ombor qoldig'i yangilandi."
    except Exception:  # noqa: BLE001 -- already decided elsewhere (dashboard) or not possible any more: just close the buttons
        logger.info("After-sales Telegram action %s on %s not applied (already handled?)", action, pk)
        text = None
    if message is None:
        return
    TelegramAfterSalesChannelMessage.objects.filter(event_key=key).update(resolved_at=django_timezone.now())
    try:
        from apps.notifications.infrastructure import composition as notifications_composition

        gateway = notifications_composition.build_orders_telegram_gateway()
        text = text or "\u2139\uFE0F <b>Bu so'rov allaqachon hal qilingan</b> (dashboardda). Holatini dashboardda ko'ring."
        gateway.edit_message_text(message.chat_id, message.message_id, text, inline_keyboard=[])
    except Exception:  # noqa: BLE001
        logger.warning("After-sales Telegram action applied but editing the channel post failed.")


def _handle_auth_login_action(telegram_user_id: int, chat_id: int, action: str, session_id: str | None) -> None:
    """
    Phase 4: the Confirm/Cancel buttons from the automatic-login
    deep-link flow. Deliberately does NOT go through the router's own
    generic `_resolve_user` gate above -- this function performs its
    own, stricter checks, since a login confirmation is more
    security-sensitive than a normal menu action.

    Wrong-user protection: the session's own telegram_user_id (set by
    `_handle_telegram_auth_start` from the real /start update) must
    match this callback's own sender exactly -- a different Telegram
    user pressing a button on someone else's confirmation message
    must never be able to confirm that session.
    """
    import uuid as _uuid

    from django.db import transaction
    from django.utils import timezone as django_timezone

    from apps.identity.infrastructure import models as identity_orm
    from apps.telegram_bot.application.services.linking import ResolveTelegramCustomer
    from apps.telegram_bot.interfaces.i18n import t

    lang = "uz"
    customer_id = ResolveTelegramCustomer().execute(telegram_user_id)
    if customer_id is not None:
        user = identity_orm.User.objects.filter(id=customer_id).first()
        lang = getattr(user, "language", None) or "uz"

    if not session_id:
        return

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        return

    with transaction.atomic():
        session = identity_orm.TelegramAuthSession.objects.select_for_update().filter(id=session_uuid).first()
        if session is None:
            _send(chat_id, t("auth_login_invalid", lang))
            return

        if session.status != identity_orm.TelegramAuthSessionStatus.PENDING:
            _send(chat_id, t("auth_login_invalid", lang))
            return

        if session.expires_at <= django_timezone.now():
            session.status = identity_orm.TelegramAuthSessionStatus.EXPIRED
            session.save(update_fields=["status"])
            _send(chat_id, t("auth_login_expired", lang))
            return

        if session.telegram_user_id is not None and session.telegram_user_id != telegram_user_id:
            # Wrong-user protection (see _handle_telegram_auth_start's own
            # matching check): a Telegram user other than the one who
            # actually pressed /start on this session's deep link must
            # never be able to confirm or cancel it.
            _send(chat_id, t("auth_login_invalid", lang))
            return

        if customer_id is None:
            _send(chat_id, t("auth_login_not_linked", lang))
            return

        if action == "cancel":
            session.status = identity_orm.TelegramAuthSessionStatus.FAILED
            session.telegram_user_id = telegram_user_id
            session.save(update_fields=["status", "telegram_user_id"])
            _send(chat_id, t("auth_login_cancelled", lang))
            return

        if action != "confirm":
            return

        session.status = identity_orm.TelegramAuthSessionStatus.VERIFIED
        session.telegram_user_id = telegram_user_id
        session.user_id = customer_id
        session.verified_at = django_timezone.now()
        session.save(update_fields=["status", "telegram_user_id", "user_id", "verified_at"])

    _send(chat_id, t("auth_login_confirmed", lang))


def _handle_onboarding_action(telegram_user_id: int, chat_id: int, action: str, arg: str | None) -> None:
    """
    Real, business-required onboarding callbacks -- routed before the
    generic user-resolve gate above since a mid-onboarding Telegram
    user has no identity.User yet. Reuses this same module's own
    _send() and the existing, unmodified LinkTelegramCustomer/
    onboarding_state -- no second registration service, no second
    state store.
    """
    from apps.telegram_bot.interfaces import onboarding_state

    if action == "lang":
        language = arg if arg in ("uz", "ru", "en") else "uz"
        onboarding_state.set_awaiting_language(chat_id)  # reset TTL before the next transition below
        onboarding_state.set_awaiting_full_name(chat_id, language)
        _send(chat_id, t("full_name_prompt", language))
        return

    state = onboarding_state.get_state(chat_id)
    if state is None:
        _send(chat_id, t("onboarding_expired", "uz"))
        return
    language = state.get("language", "uz")

    if action == "confirm":
        full_name = state.get("full_name")
        phone_number = state.get("phone_number")
        if not full_name or not phone_number:
            _send(chat_id, t("onboarding_expired", language))
            return

        from apps.telegram_bot.application.services.linking import (
            LinkTelegramCustomer,
            TelegramIdentityAlreadyLinkedToAnotherUser,
        )

        onboarding_state.clear(chat_id)
        try:
            result = LinkTelegramCustomer().execute(telegram_user_id=telegram_user_id, phone_number_raw=phone_number, full_name=full_name, language=language)
        except TelegramIdentityAlreadyLinkedToAnotherUser:
            _send(chat_id, t("already_linked_elsewhere", language))
            return
        except Exception:  # noqa: BLE001
            logger.exception("Telegram bot: onboarding confirmation linking failed for telegram_user_id=%s", telegram_user_id)
            _send(chat_id, t("technical_error", language))
            return

        from apps.identity.infrastructure import models as identity_orm

        user = identity_orm.User.objects.filter(id=result.user_id).first()
        final_lang = getattr(user, "language", None) or language
        send_welcome(chat_id, user, final_lang)
        if user is not None:
            from apps.telegram_bot.interfaces import support_confirm

            support_confirm.ask(chat_id, user, final_lang, suggested_name=full_name)  # account made from a support call
            from apps.telegram_bot.interfaces import loyalty_menu

            loyalty_menu.apply_pending_referral(user, telegram_user_id, chat_id, final_lang)
            from apps.telegram_bot.interfaces import news_menu

            news_menu.apply_pending(user, telegram_user_id, chat_id, final_lang)
        send_main_menu(chat_id, final_lang)
        return

    if action == "edit":
        # Minimal, real edit path: this project's existing onboarding
        # architecture has no per-field edit UI -- returning to the
        # name step (keeping the already-picked language) is the
        # smallest correct behavior per this phase's own explicit
        # "at minimum, return to awaiting_full_name" instruction.
        onboarding_state.set_awaiting_full_name(chat_id, language)
        _send(chat_id, t("full_name_prompt", language))
        return

    if action == "cancel":
        onboarding_state.clear(chat_id)
        _send(chat_id, t("onboarding_cancelled", language))
        return


def _handle_checkout(user, chat_id: int, action: str, lang: str, arg: str | None = None) -> None:
    from apps.telegram_bot.application.services import checkout as checkout_service

    if action == "start":
        summary = checkout_service.get_checkout_summary(user)
        if summary["item_count"] == 0:
            _send(chat_id, t("cart_empty", lang), [[{"text": t("menu_catalog", lang), "callback_data": "menu:catalog"}]])
            return
        if summary["readiness"] != "ready":
            _send(chat_id, t("checkout_not_ready_prices", lang), [[{"text": t("menu_cart", lang), "callback_data": "menu:cart"}]])
            return

        from apps.geo.infrastructure import models as geo_orm

        has_real_address = geo_orm.Address.objects.filter(owner_type="user", owner_id=user.id).exists()
        if not has_real_address:
            _request_delivery_location(chat_id, lang)
            return

        _send_checkout_summary(chat_id, lang, summary)

    elif action in ("confirm", "pay"):
        # "confirm" = cash on delivery; "pay:<method>" = online (Payme / Click / Uzum / Uzcard / Humo) right after the order is created.
        from apps.telegram_bot.application.services.checkout import (
            CheckoutNotReady,
            NoDeliveryAddress,
            OrderAlreadyCreatedForThisCart,
        )

        try:
            result = checkout_service.confirm_cash_order(user)
        except NoDeliveryAddress:
            _request_delivery_location(chat_id, lang)
            return
        except OrderAlreadyCreatedForThisCart as exc:
            _send(chat_id, t("order_already_placed", lang, order_number=exc.order_number))
            return
        except CheckoutNotReady:
            _send(chat_id, t("checkout_not_ready_generic", lang), [[{"text": t("menu_cart", lang), "callback_data": "menu:cart"}]])
            return

        method = arg if action == "pay" else None
        if method and _online_method_active(method):
            from apps.payment.infrastructure import automation, service as payment_service
            from apps.payment.infrastructure.providers.registry import provider_label

            order = payment_service.find_order(result["order_number"])
            text = t("order_placed_online", lang, order_number=result["order_number"], total=result["total"], currency=result["currency"], provider=provider_label(method))
            try:
                automation.send_pay_message(user, order, method, text)
                return
            except Exception:  # noqa: BLE001 - fall back to the plain confirmation; the reminder will offer payment again
                logger.exception("Telegram checkout: pay message for %s failed", result["order_number"])
        if not _send_rich_receipt(chat_id, result["order_number"], lang):
            _send(chat_id, t("order_placed", lang, order_number=result["order_number"], total=result["total"], currency=result["currency"]))

    elif action == "cancel":
        from apps.telegram_bot.interfaces import checkout_state

        checkout_state.clear(chat_id)
        _send(chat_id, t("checkout_cancelled", lang), [[{"text": t("menu_cart", lang), "callback_data": "menu:cart"}]])


def _request_delivery_location(chat_id: int, lang: str) -> None:
    """Real integration, closing the previously disclosed gap: prompts the customer to share their real delivery location via Telegram's own native "Share Location" button, rather than proceeding with a fabricated address."""
    from apps.notifications.infrastructure import composition as notifications_composition
    from apps.telegram_bot.interfaces import checkout_state

    checkout_state.set_awaiting_location(chat_id)
    try:
        gateway = notifications_composition.build_telegram_gateway()
        gateway.send_location_request(str(chat_id), t("ask_delivery_location", lang), t("share_location_button", lang))
    except Exception:  # noqa: BLE001
        logger.warning("Telegram bot: failed to send location request to chat %s", chat_id)


def _online_methods() -> list[str]:
    """Online methods switched on in Dashboard → To'lovlar (Payme / Click / Uzum / Uzcard / Humo)."""
    try:
        from apps.payment.infrastructure.providers import registry

        return [s.key for s in registry.all_states() if s.spec.online and s.status == "active"]
    except Exception:  # noqa: BLE001 - payments unavailable: cash only
        return []


def _online_method_active(method: str) -> bool:
    return method in _online_methods()


def _send_checkout_summary(chat_id: int, lang: str, summary: dict) -> None:
    from apps.payment.infrastructure.providers.registry import provider_label

    methods = _online_methods()
    if not methods:
        text = t("checkout_title", lang, total=summary["total"], currency=summary["currency"])
        keyboard = [
            [{"text": t("checkout_confirm_button", lang), "callback_data": "checkout:confirm"}],
            [{"text": t("checkout_cancel_button", lang), "callback_data": "checkout:cancel"}],
        ]
    else:
        text = t("checkout_choose_payment", lang, total=summary["total"], currency=summary["currency"])
        keyboard = [[{"text": t("checkout_pay_online_button", lang, provider=provider_label(m)), "callback_data": f"checkout:pay:{m}"}] for m in methods]
        keyboard += [
            [{"text": t("checkout_pay_cash_button", lang), "callback_data": "checkout:confirm"}],
            [{"text": t("checkout_cancel_button", lang), "callback_data": "checkout:cancel"}],
        ]
    _send(chat_id, text, keyboard)


def _handle_pay(user, chat_id: int, action: str, order_number: str | None, lang: str) -> None:
    """pay:cash:<order> -- the customer will pay the courier instead of online (from the order / reminder message)."""
    if action != "cash" or not order_number:
        _send(chat_id, t("unknown_action", lang))
        return
    from apps.payment.infrastructure import automation

    outcome = automation.choose_cash(user.id, order_number)
    key = {"ok": "pay_cash_ok", "paid": "pay_cash_paid", "in_flight": "pay_cash_in_flight"}.get(outcome, "pay_cash_not_open")
    _send(chat_id, t(key, lang, order_number=order_number))


def _handle_menu(user, chat_id: int, action: str, arg: str | None, lang: str) -> None:
    if action == "catalog":
        _show_categories(chat_id, lang)
    elif action == "cart":
        _show_cart(user, chat_id, lang)
    elif action == "home":
        send_main_menu(chat_id, lang)
    elif action == "lang":
        _show_language_menu(chat_id)
    elif action == "setlang" and arg:
        _set_language(user, chat_id, arg)
    elif action == "products":
        _show_products_menu(chat_id, lang)
    elif action == "brands":
        _show_brands(chat_id, lang)
    elif action == "orders":
        _show_my_orders(user, chat_id, lang)
    elif action == "social":
        _show_social_links(chat_id, lang)
    elif action == "find":
        from apps.telegram_bot.interfaces import find_product

        find_product.prompt(chat_id, lang)
    elif action == "stores":
        from apps.telegram_bot.interfaces import stores_menu

        stores_menu.show(chat_id, lang)
    elif action == "legal":
        _show_legal(chat_id, lang)
    elif action == "help":
        _show_help(chat_id, lang)
    elif action == "chat":
        _start_chat_prompt(chat_id, lang, user)
    elif action == "endchat":
        _end_chat(chat_id, lang)
    elif action == "autologin":
        _send_autologin_link(user, chat_id, lang)
    elif action == "getcode":
        send_login_code(user, chat_id, lang)
    elif action == "news":
        from apps.telegram_bot.interfaces import news_menu

        news_menu.show(user, chat_id, lang)
    elif action in ("loyalty", "loyalty_ref", "loyalty_hist"):
        from apps.telegram_bot.interfaces import loyalty_menu

        {"loyalty": loyalty_menu.show_wallet, "loyalty_ref": loyalty_menu.show_referral, "loyalty_hist": loyalty_menu.show_history}[action](user, chat_id, lang)


def _show_products_menu(chat_id: int, lang: str) -> None:
    """
    Real, product-required upgrade: "📦 Mahsulotlar" used to dump the 8
    newest products as buttons directly. Now shows the entry-point
    sub-menu first (Best Sellers / New / All / On sale) -- each of its own
    buttons starts the real, paginated single-card browsing session (see
    _start_browse). "On sale" lists products whose price list carries an
    old price above today's price (catalog_browse's own on_sale filter),
    biggest saving first; as a rich message it is a deals board first.
    """
    keyboard = [
        [{"text": t("products_menu_best", lang), "callback_data": "pm:best"}],
        [{"text": t("products_menu_new", lang), "callback_data": "pm:new"}],
        [{"text": t("products_menu_all", lang), "callback_data": "pm:all"}],
        [{"text": t("products_menu_sale", lang), "callback_data": "pm:sale"}],
        [{"text": t("home_button", lang), "callback_data": "menu:home"}],
    ]
    from apps.telegram_bot.infrastructure import shop_rich

    if _send_rich(chat_id, lambda: shop_rich.showcase_doc(lang), keyboard):
        return
    _send(chat_id, t("products_menu_title", lang), keyboard)


def _show_brands(chat_id: int, lang: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    brands = [b for b in TelegramCatalogService().list_brands(locale=lang) if b.get("name")]  # a brand with no translation for the active locale yields an empty name -- never render it as a blank, useless button
    if not brands:
        _send(chat_id, t("no_brands", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    keyboard = [[{"text": b["name"], "callback_data": f"catalog:brand:{b['id']}"}] for b in brands]
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, t("brands_list_title", lang), keyboard)


def _show_my_orders(user, chat_id: int, lang: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramOrderService

    orders, total = TelegramOrderService().list_my_orders(customer_id=user.id, page=1, page_size=5)
    if not orders:
        _send(chat_id, t("no_orders", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    lines = [t("my_orders_title", lang), ""]
    keyboard = []
    for order in orders:
        lines.append(f"\U0001F4E6 #{order['order_number']} — {order['status']}")
        keyboard.append([{"text": f"{t('btn_order_detail', lang)} #{order['order_number']}", "callback_data": f"ord:detail:{order['order_number']}"}])
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    from apps.telegram_bot.infrastructure import shop_rich

    if _send_rich(chat_id, lambda: shop_rich.orders_doc(orders, lang), keyboard):
        return
    _send(chat_id, "\n".join(lines), keyboard)


def _handle_order(user, chat_id: int, action: str, order_number: str | None, lang: str) -> None:
    from apps.telegram_bot.application.services.shopping import OrderNotOwnedByCustomer, TelegramOrderService

    if action != "detail" or not order_number:
        return
    from apps.telegram_bot.infrastructure import shop_rich

    back = [[{"text": t("back_button", lang), "callback_data": "menu:orders"}, {"text": t("home_button", lang), "callback_data": "menu:home"}]]
    if _send_rich(chat_id, lambda: shop_rich.order_doc(order_number, user.id, lang), back):
        return

    try:
        detail = TelegramOrderService().get_order_detail(order_number, customer_id=user.id)
    except OrderNotOwnedByCustomer:
        # Deliberately the same message as "not found" -- confirming an
        # order NUMBER exists but belongs to someone else would itself
        # leak information to whoever guessed/enumerated it.
        _send(chat_id, t("order_not_found", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    except ResourceNotFound:
        _send(chat_id, t("order_not_found", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return

    lines = [t("order_detail_title", lang, number=detail["order_number"]), "", t("order_status_label", lang), detail["status"], ""]
    lines.append(t("order_products_label", lang))
    for line in detail["lines"]:
        lines.append(f"• {line['quantity']} × {_format_price(line['line_total_amount'], line['currency']) or line['currency']}")
    lines.append("")
    lines.append(t("order_total_label", lang))
    lines.append(_format_price(detail["total_amount"], detail["currency"]) or f"{detail['total_amount']} {detail['currency']}")
    if detail["address"]:
        addr = detail["address"]
        address_line = ", ".join(part for part in [addr.get("city"), addr.get("region"), addr.get("line1"), addr.get("line2")] if part)
        if address_line:
            lines.append("")
            lines.append(t("order_address_label", lang))
            lines.append(address_line)

    _send(chat_id, "\n".join(lines), [[{"text": t("back_button", lang), "callback_data": "menu:orders"}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])


def _show_social_links(chat_id: int, lang: str) -> None:
    from apps.platform.infrastructure.composition import build_get_site_settings

    settings_obj = build_get_site_settings()
    links = []
    if settings_obj.telegram_channel_url:
        links.append([{"text": "\U0001F4E2 Telegram", "url": settings_obj.telegram_channel_url}])
    if settings_obj.instagram_url:
        links.append([{"text": "\U0001F4F7 Instagram", "url": settings_obj.instagram_url}])

    links.append([{"text": t("legal_button", lang), "callback_data": "menu:legal"}])
    links.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, t("social_links_text", lang) if len(links) > 2 else t("no_social_links_yet", lang), links)


def _site_page(path: str) -> str | None:
    from django.conf import settings as django_settings

    base = (getattr(django_settings, "FRONTEND_URL", None) or "").rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else None


def _show_legal(chat_id: int, lang: str) -> None:
    """/privacy and the shop's legal pages -- the public offer and the privacy policy on the website."""
    keyboard = []
    for key, path in (("legal_terms", "/terms"), ("legal_privacy", "/privacy")):
        url = _site_page(path if lang == "uz" else f"/{lang}{path}")
        if url:
            keyboard.append([{"text": t(key, lang), "url": url}])
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, t("legal_text", lang), keyboard)


def _show_help(chat_id: int, lang: str) -> None:
    _send(chat_id, t("help_text", lang), [
        [{"text": t("menu_chat", lang), "callback_data": "menu:chat"}, {"text": t("menu_stores", lang), "callback_data": "menu:stores"}],
        [{"text": t("menu_find", lang), "callback_data": "menu:find"}, {"text": t("legal_button", lang), "callback_data": "menu:legal"}],
        [{"text": t("home_button", lang), "callback_data": "menu:home"}],
    ])


def _end_chat(chat_id: int, lang: str) -> None:
    """Exits "active chat" mode in the bot (subsequent typed messages go back to normal menu handling) -- does NOT close the underlying Conversation itself, since a real support operator may still be reviewing/replying to it."""
    from apps.telegram_bot.interfaces import chat_state

    chat_state.clear(chat_id)
    send_main_menu(chat_id, lang)


def _start_chat_prompt(chat_id: int, lang: str, user=None) -> None:
    """
    Real integration: opens (or resumes) a real apps.chat Conversation
    and switches this chat_id into "active chat" mode via
    interfaces.chat_state -- closing the previously disclosed gap
    where this only acknowledged the request without ever wiring the
    typed message into apps.chat's own Conversation/Message
    aggregates.
    """
    from apps.chat.domain.enums import ConversationStatus, ConversationType, ParticipantRole
    from apps.chat.infrastructure import composition as chat_composition
    from apps.telegram_bot.interfaces import chat_state

    if user is None:
        _send(chat_id, t("please_register", lang))
        return

    existing, _total = chat_composition.build_conversation_selector().list_for_user(user.id, status=ConversationStatus.OPEN.value, page=1, page_size=50)
    support_conversation = next((c for c in existing if c["conversation_type"] == ConversationType.CUSTOMER_SUPPORT.value), None)

    if support_conversation:
        conversation_id = uuid.UUID(support_conversation["id"])
    else:
        conversation = chat_composition.build_open_conversation(actor_id=user.id).execute(
            opened_by=user.id, conversation_type=ConversationType.CUSTOMER_SUPPORT, opener_role=ParticipantRole.CUSTOMER,
        )
        conversation_id = conversation.id

    chat_state.set_active_conversation(chat_id, conversation_id)
    _send(chat_id, t("chat_prompt", lang), [[{"text": t("end_chat_button", lang), "callback_data": "menu:endchat"}]])


def _send_autologin_link(user, chat_id: int, lang: str) -> None:
    from django.conf import settings as django_settings

    from apps.identity.application.services.telegram_auth import CreateBotInitiatedAuthSession

    if user is None:
        _send(chat_id, t("please_register", lang))
        return

    frontend_url = getattr(django_settings, "FRONTEND_URL", None)
    if not frontend_url:
        logger.warning("Telegram bot: menu:autologin requested but FRONTEND_URL is not configured.")
        _send(chat_id, t("technical_error", lang))
        return

    created = CreateBotInitiatedAuthSession().execute(customer_id=user.id, telegram_user_id=user.telegram_user_id)
    login_url = f"{frontend_url.rstrip('/')}/auto-login?session={created.session_id}"
    _send(chat_id, t("autologin_link_text", lang), [[{"text": t("open_website_button", lang), "url": login_url}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])


def send_login_code(user, chat_id: int, lang: str) -> None:
    """No longer file-private: also reused by TelegramOTPProvider's "resend" button (same "menu:getcode" callback_data). NEVER called from `/start` (views.py::_handle_start) under any payload -- a login code is only ever generated by an explicit "Sayt uchun kod olish"/"Yangi kod olish" press."""
    from apps.identity.domain.exceptions import (
        OTPDeliveryFailedError,
        OTPMaxAttemptsExceededError,
        OTPResendTooSoonError,
    )
    from apps.identity.infrastructure import composition as identity_composition

    if user is None:
        _send(chat_id, t("please_register", lang))
        return

    try:
        identity_composition.build_request_telegram_otp().execute(phone_number_raw=user.phone_number, ip_address=None)
    except OTPResendTooSoonError as exc:
        retry_after = exc.details.get("retry_after_seconds") if exc.details else None
        if retry_after is not None:
            _send(chat_id, t("otp_resend_too_soon_with_time", lang, seconds=retry_after), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        else:
            _send(chat_id, t("otp_resend_too_soon", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    except OTPMaxAttemptsExceededError:
        # Real bug fix: this exception (raised by OTPPolicy.assert_within_hourly_quota
        # once a phone number has requested OTP_MAX_REQUESTS_PER_HOUR codes within
        # the last hour) previously escaped this handler entirely -- it is a
        # different exception type from OTPResendTooSoonError/OTPDeliveryFailedError,
        # so it fell through to handle_callback()'s own generic `except Exception`,
        # which logged it and sent the customer the opaque, unhelpful
        # "technical_error" message even though nothing was actually broken --
        # this was simply the hourly cap doing its job with no clear explanation.
        _send(chat_id, t("otp_max_attempts", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    except OTPDeliveryFailedError:
        _send(chat_id, t("technical_error", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    # The actual 6-digit code is delivered by TelegramOTPProvider directly via its own send_message call -- this handler only triggers it, matching the exact same RequestOTP path the website's "6-digit code" flow already uses (no second, divergent code-generation implementation).


def _show_language_menu(chat_id: int) -> None:
    keyboard = [
        [{"text": "\U0001F1FA\U0001F1FF O'zbekcha", "callback_data": "menu:setlang:uz"}],
        [{"text": "\U0001F1F7\U0001F1FA Русский", "callback_data": "menu:setlang:ru"}],
        [{"text": "\U0001F1EC\U0001F1E7 English", "callback_data": "menu:setlang:en"}],
    ]
    _send(chat_id, "\U0001F310 Tilni tanlang / Выберите язык / Choose a language:", keyboard)


def _set_language(user, chat_id: int, lang_code: str) -> None:
    from apps.identity.domain.enums import LanguagePreference

    valid_codes = {p.value for p in LanguagePreference}
    if lang_code not in valid_codes:
        return
    user.language = lang_code
    user.save(update_fields=["language"])
    send_main_menu(chat_id, lang_code)


def _show_categories(chat_id: int, lang: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    categories = TelegramCatalogService().list_categories(locale=lang)
    if not categories:
        _send(chat_id, t("no_categories", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return

    keyboard = [[{"text": cat["name"], "callback_data": f"catalog:category:{cat['id']}"}] for cat in categories]
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, t("catalog_title", lang), keyboard)


def _handle_catalog(user, chat_id: int, action: str, arg: str | None, lang: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    catalog = TelegramCatalogService()

    # Real, product-required upgrade: selecting a Category/Brand used to
    # dump up to 5-8 products as individual buttons (one Telegram
    # message per screen, product names only, no image/price/rating).
    # Both now start the same premium "one product, one message,
    # paginated" browsing session the Products menu itself uses --
    # never a second, divergent product-list UI. See _start_browse.
    if action == "category" and arg:
        _start_browse(chat_id, lang, "category", back_to="menu:catalog", category_id=arg)
        return

    if action == "brand" and arg:
        _start_browse(chat_id, lang, "brand", back_to="menu:brands", brand_id=arg)
        return

    if action == "product" and arg:
        product = catalog.get_product(uuid.UUID(arg))
        if product is None:
            _send(chat_id, t("product_not_found", lang), [[{"text": t("back_button", lang), "callback_data": "menu:catalog"}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])
            return
        variants = product.get("variants") or []
        active_variants = [v for v in variants if v.get("status") == "active"]
        text = f"<b>{product['name']}</b>\n\n"
        text += t("available", lang) if active_variants else t("unavailable", lang)
        keyboard = []
        if active_variants:
            for v in active_variants[:5]:
                keyboard.append([{"text": f"\U0001F6D2 {v.get('sku', '')}", "callback_data": f"cart:add:{v['id']}"}])
        keyboard.append([{"text": t("back_button", lang), "callback_data": "menu:catalog"}])
        keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
        _send(chat_id, text, keyboard)


def _handle_cart(user, chat_id: int, action: str, arg: str | None, lang: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramCartService

    cart_service = TelegramCartService()

    if action == "add_done" or (action == "add" and arg):
        if action == "add":
            cart_service.add_item(user, uuid.UUID(arg), quantity=1)
        _send(chat_id, t("added_to_cart", lang), [
            [{"text": t("view_cart_button", lang), "callback_data": "menu:cart"}],
            [{"text": t("continue_shopping_button", lang), "callback_data": "menu:catalog"}],
            [{"text": t("home_button", lang), "callback_data": "menu:home"}],
        ])
    elif action in ("increase", "decrease") and arg:
        item_id = uuid.UUID(arg)
        current = cart_service.view_cart(user)
        item = next((i for i in current["items"] if i["id"] == arg), None)
        if item is None:
            raise ResourceNotFound("Item not found.")
        new_qty = item["quantity"] + 1 if action == "increase" else max(1, item["quantity"] - 1)
        cart_service.update_quantity(user, item_id, new_qty)
        _show_cart(user, chat_id, lang)
    elif action == "remove" and arg:
        cart_service.remove_item(user, uuid.UUID(arg))
        _show_cart(user, chat_id, lang)
    else:
        _show_cart(user, chat_id, lang)


def money_text(amount, lang: str) -> str:
    from decimal import Decimal

    return f"{int(round(Decimal(str(amount or 0)))):,}".replace(",", " ") + " " + t("currency_som", lang)


def _show_cart(user, chat_id: int, lang: str) -> None:
    """The cart (shared with the Mini App): every line with its product name and line total, quantity buttons per line."""
    from apps.stores.infrastructure.stock_service import variant_infos
    from apps.telegram_bot.application.services.shopping import TelegramCartService

    try:
        cart = TelegramCartService().view_cart(user)
    except ResourceNotFound:
        cart = {"items": [], "total": "0", "currency": "UZS"}

    if not cart["items"]:
        _send(chat_id, t("cart_empty", lang), [[{"text": t("menu_catalog", lang), "callback_data": "menu:catalog"}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return

    infos = variant_infos([uuid.UUID(i["product_variant_id"]) for i in cart["items"]], locale=lang)
    units = sum(i["quantity"] for i in cart["items"])
    rows, keyboard = [], []
    for n, item in enumerate(cart["items"], 1):
        info = infos.get(uuid.UUID(item["product_variant_id"]))
        name = html.escape(info.name if info else "—")
        size = f" · {html.escape(info.size)}" if info and info.size else ""
        if item["priced"]:
            line_total = money_text(float(item["unit_amount"]) * item["quantity"], lang)
            rows.append(f"{n}. <b>{name}</b>{size}\n    {item['quantity']} × {money_text(item['unit_amount'], lang)} = <b>{line_total}</b>")
        else:
            rows.append(f"{n}. <b>{name}</b>{size}\n    {item['quantity']} × {t('price_pending', lang)}")
        short = (info.name if info else "—")
        short = short if len(short) <= 18 else short[:17] + "…"
        keyboard.append([
            {"text": "\u2796", "callback_data": f"cart:decrease:{item['id']}"},
            {"text": f"{item['quantity']} · {short}", "callback_data": "menu:cart"},
            {"text": "\u2795", "callback_data": f"cart:increase:{item['id']}"},
            {"text": "\U0001F5D1", "callback_data": f"cart:remove:{item['id']}"},
        ])
    text = "\n".join([t("cart_header", lang, units=units), "", f"<blockquote>{chr(10).join(rows)}</blockquote>",
                      t("cart_grand_total", lang, total=money_text(cart["total"], lang)), t("cart_shared_note", lang)])
    keyboard.append([{"text": t("checkout_button", lang), "callback_data": "checkout:start"}])
    shop = mini_app_url()
    if shop:
        keyboard.append([{"text": t("cart_open_app", lang), "web_app": {"url": f"{shop}?next=/cart"}}])
    keyboard.append([{"text": t("continue_shopping_button", lang), "callback_data": "menu:catalog"}, {"text": t("home_button", lang), "callback_data": "menu:home"}])
    from apps.telegram_bot.infrastructure import shop_rich

    if _send_rich(chat_id, lambda: shop_rich.cart_doc(user, cart, lang), keyboard):
        return
    _send(chat_id, text, keyboard)


# ============================================================
# Product browsing -- premium mini-store upgrade
#
# One product, one Telegram message, at a time. Pagination/detail/
# filter transitions all EDIT that same message (photo + caption +
# keyboard) rather than sending a new one, so browsing 20+ products
# never floods the chat. All navigation context (which listing, which
# filters, which page) lives in `catalog_state` -- callback_data itself
# never carries more than a short, fixed action name, and every render
# re-fetches the current product fresh from the same real selectors
# the website uses, so price/stock can never go stale mid-session.
# ============================================================


def _send_photo(chat_id: int, photo_url: str, caption: str, keyboard: list) -> str | None:
    from apps.notifications.infrastructure import composition as notifications_composition

    try:
        gateway = notifications_composition.build_telegram_gateway()
        return gateway.send_photo(str(chat_id), photo_url, caption, inline_keyboard=keyboard)
    except Exception:  # noqa: BLE001
        logger.warning("Telegram bot: failed to send photo to chat %s", chat_id)
        return None


def _edit_photo(chat_id: int, message_id: str, photo_url: str, caption: str, keyboard: list) -> bool:
    """Returns True on success. On failure (e.g. Telegram rejects the specific edit), the caller falls back to sending a brand-new message rather than leaving the user looking at a stale card -- see _render_browse's own fallback."""
    from apps.notifications.infrastructure import composition as notifications_composition

    try:
        gateway = notifications_composition.build_telegram_gateway()
        gateway.edit_message_media(str(chat_id), message_id, photo_url, caption, inline_keyboard=keyboard)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("Telegram bot: failed to edit photo message %s in chat %s", message_id, chat_id)
        return False


def _format_price(amount: str | None, currency: str | None) -> str | None:
    if not amount or not currency:
        return None
    try:
        value = round(float(amount))
    except (TypeError, ValueError):
        return None
    grouped = f"{value:,}".replace(",", " ")
    return f"{grouped} {currency}"


def _weight_line(product: dict) -> str | None:
    """`get_pos_display_info()` (selectors.py) now returns `weight_value`/`weight_unit` (a variant's weight may genuinely be labelled in either grams or kilograms, per explicit product decision) rather than always-grams -- kg values are shown as-is; gram values >= 1000 are still converted for readability, matching this caption's own prior display convention exactly for the common case."""
    value = product.get("weight_value")
    if not value:
        return None
    unit = product.get("weight_unit") or "g"
    if unit == "kg":
        return f"⚖️ {value:g} kg"
    if value >= 1000:
        return f"⚖️ {value / 1000:g} kg"
    return f"⚖️ {value:g} g"


def _rating_line(product: dict, lang: str) -> str:
    if product.get("rating_average") is not None and product.get("rating_count"):
        return f"⭐ {product['rating_average']:.1f} · {t('reviews_count', lang, count=product['rating_count'])}"
    return t("no_reviews_yet", lang)


def _stock_line(product: dict, lang: str) -> str | None:
    quantity = product.get("available_quantity")
    if quantity is None:
        return None
    if quantity <= 0:
        return t("stock_unavailable", lang)
    return t("stock_available", lang, stock=quantity)


def _product_caption(product: dict, lang: str) -> str:
    lines = []
    if product.get("brand_name"):
        lines.append(f"\U0001F947 <b>{product['brand_name']}</b>")
    lines.append("")
    lines.append(product["name"])
    weight_line = _weight_line(product)
    if weight_line:
        lines.append(weight_line)
    lines.append("")
    lines.append(_rating_line(product, lang))
    lines.append("")
    price_line = _format_price(product.get("price"), product.get("currency"))
    lines.append(f"\U0001F4B0 {price_line}" if price_line else f"\U0001F4B0 {t('price_pending', lang)}")
    stock_line = _stock_line(product, lang)
    if stock_line:
        lines.append("")
        lines.append(stock_line)
    return "\n".join(lines)


def _product_detail_caption(product: dict, lang: str) -> str:
    lines = []
    if product.get("brand_name"):
        lines.append(f"\U0001F947 <b>{product['brand_name']}</b>")
    lines.append("")
    lines.append(f"<b>{product['name']}</b>")
    weight_line = _weight_line(product)
    if weight_line:
        lines.append(weight_line)
    lines.append("")
    if product.get("rating_average") is not None and product.get("rating_count"):
        lines.append(f"⭐ {product['rating_average']:.1f} / 5")
        lines.append(t("reviews_count", lang, count=product["rating_count"]))
    else:
        lines.append(t("no_reviews_yet", lang))
    lines.append("")
    price_line = _format_price(product.get("price"), product.get("currency"))
    lines.append(f"\U0001F4B0 {price_line}" if price_line else f"\U0001F4B0 {t('price_pending', lang)}")
    lines.append("")
    stock_line = _stock_line(product, lang)
    if stock_line:
        lines.append(stock_line)
        lines.append("")
    for spec in product.get("specifications") or []:
        lines.append(f"{spec['key']}: {spec['value']}")
    if product.get("specifications"):
        lines.append("")
    if product.get("description"):
        lines.append(product["description"])
    return "\n".join(line for line in lines if line is not None)


def _product_card_keyboard(product: dict, page: int, total: int, lang: str, is_wishlisted: bool) -> list:
    keyboard = []
    default_variant_id = product.get("default_variant_id")
    if default_variant_id:
        keyboard.append([{"text": t("btn_add_to_cart", lang), "callback_data": f"cart:add:{default_variant_id}"}])
    keyboard.append([
        {"text": t("btn_view_detail", lang), "callback_data": "pc:detail"},
        {"text": t("btn_wishlist_added", lang) if is_wishlisted else t("btn_wishlist_add", lang), "callback_data": "pc:wish"},
    ])
    if total > 1:
        keyboard.append([
            {"text": "◀️", "callback_data": "pc:prev"},
            {"text": f"{page} / {total}", "callback_data": "pc:noop"},
            {"text": "▶️", "callback_data": "pc:next"},
        ])
    keyboard.append([{"text": t("btn_filter", lang), "callback_data": "flt:menu"}])
    keyboard.append([{"text": t("back_button", lang), "callback_data": "pc:back"}])
    return keyboard


def _product_detail_keyboard(product: dict, lang: str, is_wishlisted: bool) -> list:
    from django.conf import settings as django_settings

    keyboard = []
    default_variant_id = product.get("default_variant_id")
    if default_variant_id:
        keyboard.append([{"text": t("btn_add_to_cart", lang), "callback_data": f"cart:add:{default_variant_id}"}])
        keyboard.append([{"text": t("btn_buy_now", lang), "callback_data": "pc:buynow"}])
    keyboard.append([{"text": t("btn_wishlist_added", lang) if is_wishlisted else t("btn_wishlist_add", lang), "callback_data": "pc:wish"}])
    frontend_url = getattr(django_settings, "FRONTEND_URL", None)
    if frontend_url and product.get("slug"):
        keyboard.append([{"text": t("btn_view_website", lang), "url": f"{frontend_url.rstrip('/')}/products/{product['slug']}"}])
    keyboard.append([{"text": t("back_button", lang), "callback_data": "pc:cardback"}])
    return keyboard


def _resolve_current_product(state: dict, lang: str) -> tuple[dict | None, int]:
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    return TelegramCatalogService().browse(
        state["source"], page=state.get("page", 1), locale=lang,
        brand_id=uuid.UUID(state["brand_id"]) if state.get("brand_id") else None,
        category_id=uuid.UUID(state["category_id"]) if state.get("category_id") else None,
        query=state.get("query"), rating_gte=state.get("rating_gte"), price_min=state.get("price_min"), price_max=state.get("price_max"),
        product_id=uuid.UUID(state["product_id"]) if state.get("product_id") else None,
    )


def _empty_browse_keyboard(lang: str, back_to: str) -> list:
    return [
        [{"text": t("btn_clear_filters", lang), "callback_data": "flt:clear"}],
        [{"text": t("back_button", lang), "callback_data": back_to}],
        [{"text": t("home_button", lang), "callback_data": "menu:home"}],
    ]


def _render_browse(user, chat_id: int, lang: str, state: dict, *, edit_message_id: str | None = None) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramWishlistService
    from apps.telegram_bot.interfaces import catalog_state

    product, total = _resolve_current_product(state, lang)

    if product is None:
        text = t("empty_products", lang)
        keyboard = _empty_browse_keyboard(lang, state.get("back_to", "menu:products"))
        if edit_message_id and state.get("has_photo"):
            from apps.notifications.infrastructure import composition as notifications_composition

            try:
                notifications_composition.build_telegram_gateway().edit_message_text(str(chat_id), edit_message_id, text, inline_keyboard=keyboard)
                return
            except Exception:  # noqa: BLE001
                pass
        _send(chat_id, text, keyboard)
        catalog_state.merge(chat_id, has_photo=False)
        return

    is_wishlisted = TelegramWishlistService().is_wishlisted(user.id, uuid.UUID(product["id"]))
    caption = _product_caption(product, lang)
    keyboard = _product_card_keyboard(product, state.get("page", 1), total, lang, is_wishlisted)
    image_url = product.get("primary_image_path")

    if image_url:
        if edit_message_id and state.get("has_photo") and _edit_photo(chat_id, edit_message_id, image_url, caption, keyboard):
            return
        message_id = _send_photo(chat_id, image_url, caption, keyboard)
        catalog_state.merge(chat_id, has_photo=bool(message_id))
        return

    # No real image for this product -- a plain text card, never a broken image reference.
    if edit_message_id and not state.get("has_photo"):
        from apps.notifications.infrastructure import composition as notifications_composition

        try:
            notifications_composition.build_telegram_gateway().edit_message_text(str(chat_id), edit_message_id, caption, inline_keyboard=keyboard)
            return
        except Exception:  # noqa: BLE001
            pass
    _send(chat_id, caption, keyboard)
    catalog_state.merge(chat_id, has_photo=False)


def _start_browse(chat_id: int, lang: str, source: str, *, back_to: str = "menu:products", brand_id: str | None = None, category_id: str | None = None, user=None) -> None:
    from apps.telegram_bot.interfaces import catalog_state

    catalog_state.set_browsing(chat_id, source, brand_id=brand_id, category_id=category_id, page=1, back_to=back_to)
    state = catalog_state.get_browsing(chat_id)
    _render_browse(user, chat_id, lang, state)


MAX_QUERY_LEN = 80


def show_product_link(user, chat_id: int, product_id: str) -> None:
    """A product opened from a link (`/start p_<id>` -- inline-mode results, shared cards): its detail card, with the usual buttons."""
    from apps.telegram_bot.application.services.shopping import TelegramWishlistService
    from apps.telegram_bot.interfaces import catalog_state

    lang = _lang(user)
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        send_main_menu(chat_id, lang)
        return
    catalog_state.set_browsing(chat_id, "product", page=1, back_to="menu:home", product_id=str(pid))
    from apps.telegram_bot.infrastructure import shop_rich

    if _send_rich(chat_id, lambda: shop_rich.product_doc(pid, lang), _rich_product_keyboard(lang)):
        return
    full = _get_full_product(str(pid), lang)
    if not full:
        _send(chat_id, t("product_gone", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    caption = _product_detail_caption(full, lang)
    keyboard = _product_detail_keyboard(full, lang, TelegramWishlistService().is_wishlisted(user.id, pid))
    image_url = full.get("primary_image_path")
    message_id = _send_photo(chat_id, image_url, caption, keyboard) if image_url else None
    if not message_id:
        _send(chat_id, caption, keyboard)
    catalog_state.merge(chat_id, has_photo=bool(message_id))


def _md_to_html(text: str) -> str:
    """The advisor's light markdown (**bold**, _italic_, ~~struck~~) as Telegram HTML; everything else escaped."""
    import re

    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"~~(.+?)~~", r"<s>\1</s>", out)
    return re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<i>\1</i>", out, flags=re.S)


def claude_reply(conversation_id, text: str) -> dict:
    """One Claude assistant turn collected from the stream (the website widget's brain, with all the shop's tools)."""
    from asgiref.sync import async_to_sync

    from apps.assistant.infrastructure import engine as ai

    async def collect():
        out = {"reply": "", "cards": []}
        async for event in ai.run_turn(conversation_id, text):
            if event["type"] == "text":
                out["reply"] += event["delta"]
            elif event["type"] == "products":
                out["cards"] += event["items"]
            elif event["type"] == "error":
                out["reply"] = event.get("message") or out["reply"]
        return out

    return async_to_sync(collect)()


def _advisor_understands(text: str, lang: str) -> bool:
    """A "search"-looking message the free advisor still answers better: price, branch stock, contacts, hours, promo,
    compare, safety (Brain v2) or a question the shop taught word for word."""
    from apps.assistant.infrastructure import knowledge
    from apps.assistant.infrastructure.advisor import brain

    try:
        if brain.respond({}, text, lang if lang in ("uz", "ru", "en") else "uz") is not None:
            return True
        hits = knowledge.search(text, limit=1)
        return bool(hits and hits[0].exact)
    except Exception:  # noqa: BLE001 -- when in doubt the plain catalogue search answers
        logger.exception("advisor pre-check failed")
        return False


def _advisor_reply(user, chat_id: int, telegram_user_id: int, text: str, lang: str) -> bool:
    """Free text that is a question, a goal or profile facts goes to the local advisor (same brain as the website
    widget, its memory kept per Telegram user for 24 h); plain product words stay a catalogue search."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.assistant.infrastructure.advisor import nlu
    from apps.assistant.infrastructure.advisor.engine import _turn_sync
    from apps.assistant.infrastructure.models import AssistantConversation

    from apps.assistant.infrastructure import engine as ai

    smart = ai.uses_claude()
    if not smart and nlu.parse(text).intent == "search" and not _advisor_understands(text, lang):
        return False
    try:
        key = f"tg:{telegram_user_id}"
        conv = AssistantConversation.objects.filter(client_key=key, updated_at__gte=timezone.now() - timedelta(hours=24)).order_by("-updated_at").first()
        if conv is None or conv.turns >= 30:
            conv = AssistantConversation.objects.create(client_key=key, customer_id=user.id, channel="telegram", locale=lang if lang in ("uz", "ru", "en") else "uz",
                                                        engine="claude" if smart else "local")
        result = claude_reply(conv.id, text[:800]) if smart else _turn_sync(conv.id, text[:800])
    except Exception:  # noqa: BLE001 -- the bot falls back to the plain search
        logger.exception("advisor reply failed")
        return False
    if not result.get("reply"):
        return False
    rows = []
    for c in result["cards"][:4]:
        price = f" — {int(float(c['price'])):,}".replace(",", " ") if c.get("price") else ""
        rows.append([{"text": f"🛒 {c['name'][:34]}{price}", "callback_data": f"po:open:{c['id']}"}])
    rows += _chip_rows(chat_id, result.get("chips"))
    rows.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, _md_to_html(result["reply"])[:4000], rows)
    _send_venues(chat_id, result.get("venues"))
    return True


def group_question(message: dict) -> bool:
    """
    The assistant in a Telegram group: answers when the bot is @mentioned or someone replies to one of its
    messages (with privacy mode on, those are the only group texts Telegram delivers anyway). Each member gets their
    own short memory per group; product suggestions open on the website (buttons can't open a private card in a group).
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from apps.assistant.infrastructure import engine as ai
    from apps.assistant.infrastructure.advisor.engine import _turn_sync
    from apps.assistant.infrastructure.models import AssistantConversation

    bot = (settings.TELEGRAM_BOT_USERNAME or "").lstrip("@")
    text = message.get("text") or ""
    reply_to = (message.get("reply_to_message") or {}).get("from") or {}
    mentioned = bool(bot) and f"@{bot.lower()}" in text.lower()
    if not (mentioned or (reply_to.get("is_bot") and (reply_to.get("username") or "").lower() == bot.lower())):
        return False
    question = re.sub(rf"@{re.escape(bot)}\b", "", text, flags=re.I).strip() if bot else text.strip()
    if len(question) < 2 or not ai.is_configured():
        return False
    sender = message.get("from") or {}
    chat_id = message["chat"]["id"]
    code = (sender.get("language_code") or "uz")[:2]
    lang = code if code in ("uz", "ru", "en") else "uz"
    try:
        key = f"tgg:{chat_id}:{sender.get('id')}"
        conv = AssistantConversation.objects.filter(client_key=key, updated_at__gte=timezone.now() - timedelta(hours=6)).order_by("-updated_at").first()
        if conv is None or conv.turns >= 20:
            conv = AssistantConversation.objects.create(client_key=key, channel="telegram", locale=lang, engine="claude" if ai.uses_claude() else "local")
        result = claude_reply(conv.id, question[:800]) if ai.uses_claude() else _turn_sync(conv.id, question[:800])
    except Exception:  # noqa: BLE001 -- silence beats a broken answer in a group
        logger.exception("group assistant failed")
        return False
    if not result.get("reply"):
        return False
    site = (settings.FRONTEND_URL or "https://nutrizone.uz").rstrip("/")
    rows = [[{"text": f"🛒 {c['name'][:40]}", "url": f"{site}/products/{c['slug']}"}] for c in result["cards"][:3] if c.get("slug")]
    if bot:
        rows.append([{"text": "💬 NutriZone bot", "url": f"https://t.me/{bot}"}])
    name = html.escape(sender.get("first_name") or "")
    _send(chat_id, (f"{name}, " if name else "") + _md_to_html(result["reply"])[:3900], rows)
    _send_venues(chat_id, result.get("venues"))
    return True


def search_text(chat_id: int, telegram_user_id: int, text: str) -> None:
    """
    A plain text message to the bot is a product search -- the website's smart search (typos, Latin/Cyrillic,
    synonyms like "протеин"/"oqsil", goals like "ozish"), shown as the usual one-product-per-message cards.
    Counted in the dashboard's search analytics like a catalog search.
    """
    from apps.telegram_bot.interfaces import catalog_state

    user = _resolve_user(telegram_user_id)
    if user is None:
        _send(chat_id, t("please_register", "uz"))
        return
    lang = _lang(user)
    from apps.telegram_bot.interfaces import support_confirm

    if support_confirm.take_typed_name(user, chat_id, text, lang):
        return
    if _advisor_reply(user, chat_id, telegram_user_id, text, lang):
        return  # a question / profile / goal -- answered by the free NutriZone advisor
    query = " ".join(text.split())[:MAX_QUERY_LEN]
    catalog_state.set_browsing(chat_id, "search", page=1, back_to="menu:home", query=query)
    state = catalog_state.get_browsing(chat_id)
    product, total = _resolve_current_product(state, lang)
    try:
        from apps.search.infrastructure.repositories import record

        record(query, total, lang)
    except Exception:  # noqa: BLE001 -- analytics never blocks the answer
        logger.exception("Could not record a bot search")
    if product is None:
        _send(chat_id, t("search_no_results", lang, query=html.escape(query)), [
            [{"text": t("products_menu_all", lang), "callback_data": "pm:all"}, {"text": t("products_menu_best", lang), "callback_data": "pm:best"}],
            [{"text": t("menu_chat", lang), "callback_data": "menu:chat"}],
            [{"text": t("home_button", lang), "callback_data": "menu:home"}],
        ])
        return
    _send(chat_id, t("search_found", lang, query=html.escape(query), count=total))
    _render_browse(user, chat_id, lang, state)


def _handle_products_menu(user, chat_id: int, action: str, lang: str, message: dict) -> None:
    if action == "sale":
        _show_sale(user, chat_id, lang)
        return
    if action == "salecards":
        _start_browse(chat_id, lang, "sale", back_to="menu:products", user=user)
        return
    if action not in ("best", "new", "all"):
        return
    _start_browse(chat_id, lang, action, back_to="menu:products", user=user)


def _show_sale(user, chat_id: int, lang: str) -> None:
    """💰 Aksiyalar: a deals board (rich) with one button per product, or the card-by-card browse when rich is off."""
    from apps.telegram_bot.infrastructure import shop_rich

    deals = shop_rich.sale_cards(lang)
    if not deals:
        _send(chat_id, t("no_sale_products", lang), [[{"text": t("products_menu_best", lang), "callback_data": "pm:best"}],
                                                     [{"text": t("back_button", lang), "callback_data": "menu:products"}, {"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    keyboard = [[{"text": shop_rich.tr(lang, "cards_view"), "callback_data": "pm:salecards"}],
                [{"text": t("back_button", lang), "callback_data": "menu:products"}, {"text": t("home_button", lang), "callback_data": "menu:home"}]]
    if _send_rich(chat_id, lambda: shop_rich.sale_doc(lang, deals), keyboard):
        return
    _start_browse(chat_id, lang, "sale", back_to="menu:products", user=user)


def _handle_product_card(user, chat_id: int, action: str, lang: str, message: dict) -> None:
    from apps.telegram_bot.interfaces import catalog_state

    if action == "noop":
        return

    message_id = str(message.get("message_id", ""))
    state = catalog_state.get_browsing(chat_id)
    if state is None:
        _send(chat_id, t("session_expired_reopen", lang), [[{"text": t("products_menu_all", lang), "callback_data": "pm:all"}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return

    if action in ("next", "prev"):
        _pc_paginate(user, chat_id, lang, message_id, state, action)
    elif action == "back":
        _pc_back(user, chat_id, lang, message_id, state, action)
    elif action == "wish":
        _pc_wish(user, chat_id, lang, message_id, state, action)
    elif action == "detail":
        _pc_detail(user, chat_id, lang, message_id, state, action)
    elif action == "cardback":
        _pc_cardback(user, chat_id, lang, message_id, state, action)
    elif action == "buynow":
        _pc_buynow(user, chat_id, lang, message_id, state, action)


def _pc_paginate(user, chat_id: int, lang: str, message_id: str, state: dict, action: str) -> None:
    from apps.telegram_bot.interfaces import catalog_state

    _, total = _resolve_current_product(state, lang)
    page = state.get("page", 1) + (1 if action == "next" else -1)
    page = max(1, min(page, max(total, 1)))
    state = catalog_state.set_page(chat_id, page)
    _render_browse(user, chat_id, lang, state, edit_message_id=message_id)


def _pc_back(user, chat_id: int, lang: str, message_id: str, state: dict, action: str) -> None:
    from apps.telegram_bot.interfaces import catalog_state

    catalog_state.clear(chat_id)
    _dispatch_back(user, chat_id, lang, state.get("back_to", "menu:products"))


def _pc_wish(user, chat_id: int, lang: str, message_id: str, state: dict, action: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramWishlistService

    product, _total = _resolve_current_product(state, lang)
    if product is None:
        _send(chat_id, t("product_gone", lang))
        return
    TelegramWishlistService().toggle(user.id, uuid.UUID(product["id"]))
    _render_browse(user, chat_id, lang, state, edit_message_id=message_id)


def _pc_cardback(user, chat_id: int, lang: str, message_id: str, state: dict, action: str) -> None:
    _render_browse(user, chat_id, lang, state, edit_message_id=message_id)


def _pc_detail(user, chat_id: int, lang: str, message_id: str, state: dict, action: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramWishlistService

    product, _total = _resolve_current_product(state, lang)
    if product is None:
        _send(chat_id, t("product_gone", lang))
        return
    from apps.telegram_bot.infrastructure import shop_rich

    # the full product page as a rich message under the card (the card stays for browsing on)
    if _send_rich(chat_id, lambda: shop_rich.product_doc(product["id"], lang), _rich_product_keyboard(lang)):
        return
    full = _get_full_product(product["id"], lang)
    is_wishlisted = TelegramWishlistService().is_wishlisted(user.id, uuid.UUID(product["id"]))
    caption = _product_detail_caption(full, lang)
    keyboard = _product_detail_keyboard(full, lang, is_wishlisted)
    image_url = full.get("primary_image_path")

    if image_url and state.get("has_photo"):
        if not _edit_photo(chat_id, message_id, image_url, caption, keyboard):
            _send_photo(chat_id, image_url, caption, keyboard)
        return
    if not image_url and not state.get("has_photo"):
        from apps.notifications.infrastructure import composition as notifications_composition

        try:
            notifications_composition.build_telegram_gateway().edit_message_text(str(chat_id), message_id, caption, inline_keyboard=keyboard)
        except Exception:  # noqa: BLE001
            _send(chat_id, caption, keyboard)
        return
    _send(chat_id, caption, keyboard)


def _pc_buynow(user, chat_id: int, lang: str, message_id: str, state: dict, action: str) -> None:
    from apps.telegram_bot.application.services.shopping import TelegramCartService

    product, _total = _resolve_current_product(state, lang)
    if product is None or not product.get("default_variant_id"):
        _send(chat_id, t("product_gone", lang))
        return
    try:
        TelegramCartService().add_item(user, uuid.UUID(product["default_variant_id"]), quantity=1)
    except ResourceNotFound:
        _send(chat_id, t("price_pending", lang))
        return
    _handle_checkout(user, chat_id, "start", lang)


def _rich_product_keyboard(lang: str) -> list:
    return [[{"text": t("menu_cart", lang), "callback_data": "menu:cart"}, {"text": t("menu_products", lang), "callback_data": "menu:products"}],
            [{"text": t("home_button", lang), "callback_data": "menu:home"}]]


def _handle_product_open(user, chat_id: int, action: str, arg: str | None, lang: str) -> None:
    """Buttons inside the rich screens: open a product page (showcase), add its default size to the cart, or buy it now."""
    from apps.telegram_bot.application.services.shopping import TelegramCartService
    from apps.telegram_bot.infrastructure import shop_rich

    if not arg:
        return
    try:
        target = uuid.UUID(arg)
    except ValueError:
        return
    if action == "open":
        if not _send_rich(chat_id, lambda: shop_rich.product_doc(target, lang), _rich_product_keyboard(lang)):
            show_product_link(user, chat_id, str(target))
    elif action in ("add", "buy"):
        try:
            TelegramCartService().add_item(user, target, quantity=1)
        except ResourceNotFound:
            _send(chat_id, t("price_pending", lang))
            return
        if action == "buy":
            _handle_checkout(user, chat_id, "start", lang)
        else:
            _handle_cart(user, chat_id, "add_done", None, lang)


def _get_full_product(product_id: str, lang: str) -> dict:
    """Detail view needs description/specifications/variants (see ProductDetailSelector.get_by_id's own docstring) plus the same brand/weight/stock enrichment the card already fetched -- re-fetched here rather than threaded through, since the detail screen is only ever reached by an explicit tap, never part of a hot pagination loop."""
    from apps.telegram_bot.application.services.shopping import TelegramCatalogService

    svc = TelegramCatalogService()
    product = svc.get_product(uuid.UUID(product_id), locale=lang)
    return svc.enrich(product) if product else {}


def _dispatch_back(user, chat_id: int, lang: str, back_to: str) -> None:
    if back_to == "menu:catalog":
        _show_categories(chat_id, lang)
    elif back_to == "menu:brands":
        _show_brands(chat_id, lang)
    else:
        _show_products_menu(chat_id, lang)


# --- Filters (brand / category only -- see _handle_filter's own docstring for what isn't supported and why) ---


# Price bands for the bot's price filter, in so'm: (from, to); `None` = open-ended.
PRICE_BANDS: tuple[tuple[int, int | None], ...] = ((0, 200_000), (200_000, 500_000), (500_000, 1_000_000), (1_000_000, None))


def _price_band_label(lo: int, hi: int | None, lang: str) -> str:
    def fmt(n: int) -> str:
        return f"{n:,}".replace(",", " ")

    currency = t("currency_som", lang)
    if hi is None:
        return f"\U0001F4B0 {fmt(lo)}+ {currency}"
    if lo == 0:
        return f"\U0001F4B0 ≤ {fmt(hi)} {currency}"
    return f"\U0001F4B0 {fmt(lo)} – {fmt(hi)} {currency}"


def _filter_menu_keyboard(lang: str) -> list:
    return [
        [{"text": t("filter_brand", lang), "callback_data": "flt:brandlist"}],
        [{"text": t("filter_category", lang), "callback_data": "flt:catlist"}],
        [{"text": t("filter_rating", lang), "callback_data": "flt:rating"}],
        [{"text": t("filter_price", lang), "callback_data": "flt:price"}],
        [{"text": t("btn_clear_filters", lang), "callback_data": "flt:clear"}],
        [{"text": t("back_button", lang), "callback_data": "pc:cardback"}],
    ]


def _handle_filter(user, chat_id: int, action: str, arg: str | None, lang: str, message: dict) -> None:
    """
    Real, product-required scope decision, evidenced directly against
    `apps.products.infrastructure.selectors.DjangoProductSearchBackend.
    search()`: only `brand_id`/`category_id` are ever actually applied
    to the query there -- `filters["price"]`/`filters["availability"]`
    are parsed by `parse_search_params` but silently dropped by the
    real search implementation, and no rating filter/sort exists
    anywhere in the product read model at all. Implementing Rating/
    Price filtering here would mean either faking a filter that does
    nothing (forbidden) or filtering client-side over an unpaginated
    fetch (silently wrong at any real catalog size, and explicitly
    forbidden by this phase's own "no fake filtering" rule). Brand and
    Category are real, both already correctly applied by
    `CatalogSelector.list()` -- fully implemented below.
    """
    from apps.telegram_bot.interfaces import catalog_state

    message_id = str(message.get("message_id", ""))
    state = catalog_state.get_browsing(chat_id)
    if state is None:
        _send(chat_id, t("session_expired_reopen", lang), [[{"text": t("products_menu_all", lang), "callback_data": "pm:all"}]])
        return

    if action == "menu":
        _edit_current_to(chat_id, message_id, state, t("filter_menu_title", lang), _filter_menu_keyboard(lang))
        return

    if action == "rating":
        keyboard = [[{"text": f"⭐ {n}+", "callback_data": f"flt:setrating:{n}"}] for n in (4, 3)]
        keyboard.append([{"text": t("btn_clear_filters", lang), "callback_data": "flt:setrating:0"}])
        keyboard.append([{"text": t("back_button", lang), "callback_data": "flt:menu"}])
        _edit_current_to(chat_id, message_id, state, t("filter_rating_title", lang), keyboard)
        return

    if action == "price":
        keyboard = [[{"text": _price_band_label(lo, hi, lang), "callback_data": f"flt:setprice:{lo}-{hi if hi is not None else ''}"}] for lo, hi in PRICE_BANDS]
        keyboard.append([{"text": t("btn_clear_filters", lang), "callback_data": "flt:setprice:"}])
        keyboard.append([{"text": t("back_button", lang), "callback_data": "flt:menu"}])
        _edit_current_to(chat_id, message_id, state, t("filter_price_title", lang), keyboard)
        return

    if action == "setrating":
        rating = int(arg) if arg and arg.isdigit() and int(arg) in (3, 4) else None
        _render_browse(user, chat_id, lang, catalog_state.merge(chat_id, rating_gte=rating, page=1) or state, edit_message_id=message_id)
        return

    if action == "setprice":
        lo, _, hi = (arg or "").partition("-")
        _render_browse(user, chat_id, lang, catalog_state.merge(chat_id, price_min=int(lo) if lo.isdigit() else None, price_max=int(hi) if hi.isdigit() else None, page=1) or state,
                       edit_message_id=message_id)
        return

    if action == "brandlist":
        from apps.telegram_bot.application.services.shopping import TelegramCatalogService

        brands = [b for b in TelegramCatalogService().list_brands(locale=lang) if b.get("name")]
        keyboard = [[{"text": b["name"], "callback_data": f"flt:setbrand:{b['id']}"}] for b in brands]
        keyboard.append([{"text": t("back_button", lang), "callback_data": "flt:menu"}])
        _edit_current_to(chat_id, message_id, state, t("filter_brand_select_title", lang), keyboard)
        return

    if action == "catlist":
        from apps.telegram_bot.application.services.shopping import TelegramCatalogService

        categories = TelegramCatalogService().list_categories(locale=lang)
        keyboard = [[{"text": c["name"], "callback_data": f"flt:setcat:{c['id']}"}] for c in categories]
        keyboard.append([{"text": t("back_button", lang), "callback_data": "flt:menu"}])
        _edit_current_to(chat_id, message_id, state, t("filter_category_select_title", lang), keyboard)
        return

    searching = state.get("source") == "search"  # a filter narrows a text search instead of replacing it
    kept = {k: state.get(k) for k in ("rating_gte", "price_min", "price_max") if state.get(k) is not None}  # price/rating survive a brand/category change
    if action == "setbrand" and arg:
        if searching:
            catalog_state.set_browsing(chat_id, "search", brand_id=arg, category_id=state.get("category_id"), page=1, back_to=state.get("back_to", "menu:home"), query=state.get("query"))
        else:
            catalog_state.set_browsing(chat_id, "brand", brand_id=arg, page=1, back_to=state.get("back_to", "menu:products"))
        if kept:
            catalog_state.merge(chat_id, **kept)
        _render_browse(user, chat_id, lang, catalog_state.get_browsing(chat_id), edit_message_id=message_id)
        return

    if action == "setcat" and arg:
        if searching:
            catalog_state.set_browsing(chat_id, "search", brand_id=state.get("brand_id"), category_id=arg, page=1, back_to=state.get("back_to", "menu:home"), query=state.get("query"))
        else:
            catalog_state.set_browsing(chat_id, "category", category_id=arg, page=1, back_to=state.get("back_to", "menu:products"))
        if kept:
            catalog_state.merge(chat_id, **kept)
        _render_browse(user, chat_id, lang, catalog_state.get_browsing(chat_id), edit_message_id=message_id)
        return

    if action == "clear":
        if searching:
            catalog_state.set_browsing(chat_id, "search", page=1, back_to=state.get("back_to", "menu:home"), query=state.get("query"))
        else:
            catalog_state.set_browsing(chat_id, "all", page=1, back_to=state.get("back_to", "menu:products"))
        _render_browse(user, chat_id, lang, catalog_state.get_browsing(chat_id), edit_message_id=message_id)
        return


def _edit_current_to(chat_id: int, message_id: str, state: dict, text: str, keyboard: list) -> None:
    """Edits the current browse message into a text-only screen (filter menu / brand-select / etc.) -- if it's currently a photo message, that photo is dropped in favor of a plain edited text message rather than trying to keep an unrelated product image behind a filter menu."""
    from apps.notifications.infrastructure import composition as notifications_composition
    from apps.telegram_bot.interfaces import catalog_state

    if state.get("has_photo"):
        _send(chat_id, text, keyboard)
        catalog_state.merge(chat_id, has_photo=False)
        return
    try:
        notifications_composition.build_telegram_gateway().edit_message_text(str(chat_id), message_id, text, inline_keyboard=keyboard)
    except Exception:  # noqa: BLE001
        _send(chat_id, text, keyboard)
