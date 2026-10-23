"""
Telegram inbound webhook -- Phase 15B foundation.

Chosen over polling: this project's own production deployment
(confirmed in Phase 15/15B reconnaissance) already runs a real Nginx
reverse proxy with HTTPS-ready configuration and a real Django ASGI/
WSGI split -- a webhook fits this exact topology directly, with no
extra long-running polling process needed (which would also risk
"multiple competing consumers" if ever scaled to multiple replicas,
something this project's own docker-compose.prod.yml already does
for the web service).

Security: validates Telegram's own `X-Telegram-Bot-Api-Secret-Token`
header (set via the real `setWebhook` API call's own `secret_token`
parameter, not a custom scheme) against `TELEGRAM_WEBHOOK_SECRET`.
Returns 200 quickly in all cases (including internal errors) per
Telegram's own documented expectation, logging failures server-side
rather than letting Telegram's own retry/backoff behavior repeatedly
hit a failing endpoint.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("nutrizone.app")


def _reply_text(chat_id: int, text: str) -> None:
    try:
        from apps.notifications.infrastructure import composition as notifications_composition

        gateway = notifications_composition.build_telegram_gateway()
        gateway.send_message(str(chat_id), "", text)
    except Exception:  # noqa: BLE001
        logger.warning("Telegram bot: failed to send reply to chat %s", chat_id)


def _handle_start(message: dict) -> None:
    """
    CRITICAL: `/start` is never a login-code command. It only (1)
    determines whether the Telegram user is already registered (via
    the real, persisted `identity.User` row linked by `telegram_user_id`
    -- never a Telegram-side flag or in-memory state), (2) resumes/starts
    registration if the account is missing or incomplete, or (3) shows
    the main menu. Login-code generation is reachable ONLY through the
    "Sayt uchun kod olish"/"Yangi kod olish" buttons, both of which route
    to the single, existing `send_login_code()` (menu:getcode callback,
    see callback_router.py) -- never from here, under any payload.
    """
    from apps.telegram_bot.application.services.linking import ResolveTelegramCustomer
    from apps.telegram_bot.interfaces.callback_router import send_main_menu
    from apps.telegram_bot.interfaces.i18n import t

    chat = message["chat"]
    from_user = message["from"]

    text = message.get("text", "")
    parts = text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None

    # "login" is the website's own single "Continue with Telegram"
    # button's deep link (never client-supplied otherwise -- the
    # website hardcodes this exact payload). Any OTHER, unrecognized
    # payload still goes through the unchanged automatic-login-session
    # flow below (the bot menu's own "Saytga avtomatik kirish" button).
    # Loyalty invite deep link: https://t.me/<bot>?start=ref_<CODE>
    referral_code = payload[4:] if payload and payload.startswith("ref_") else None
    if referral_code:
        payload = None
    # News subscription deep link from the site: https://t.me/<bot>?start=news
    wants_news = payload == "news"
    if wants_news:
        payload = None
    # Plain entry points that only need to open the chat: inline mode's "open the shop" button (start=inline)
    # and the Mini App's "register in the bot" link (start=webapp) -- never an auto-login token.
    if payload in ("inline", "webapp"):
        payload = None
    # Product deep link (inline-mode results, shared cards): https://t.me/<bot>?start=p_<product id>
    product_link = payload[2:] if payload and payload.startswith("p_") else None
    if product_link:
        payload = None

    if payload and payload != "login":
        _handle_telegram_auth_start(payload, from_user, chat)
        return

    existing_customer_id = ResolveTelegramCustomer().execute(from_user["id"])

    if referral_code:
        from apps.telegram_bot.interfaces import loyalty_menu

        if existing_customer_id is None:
            loyalty_menu.park_referral(from_user["id"], referral_code)  # applied once onboarding creates the account
        else:
            from apps.identity.infrastructure import models as identity_orm

            ref_user = identity_orm.User.objects.filter(id=existing_customer_id).first()
            if ref_user is not None:
                loyalty_menu.apply_referral(ref_user, referral_code, chat["id"], getattr(ref_user, "language", None) or "uz")

    if existing_customer_id is not None:
        from apps.identity.infrastructure import models as identity_orm

        user = identity_orm.User.objects.filter(id=existing_customer_id).first()
        lang = getattr(user, "language", None) or "uz"

        # Registration-completeness gate: a linked telegram_user_id
        # alone is not "fully registered" -- resume onboarding at the
        # missing step instead of showing the menu for a half-registered
        # account. In practice LinkTelegramCustomer (both the typed-name
        # onboarding path and its contact-share fallback) never creates
        # a row missing either field, so this is a defensive guard
        # against pre-existing/externally-edited data, not a path
        # reachable through the bot's own flows today.
        if user is None or not (user.full_name or "").strip() or not (user.phone_number or "").strip():
            from apps.telegram_bot.interfaces import onboarding_state

            logger.info("Telegram /start: telegram_user_id=%s registered=false action=resume_registration", from_user["id"])
            onboarding_state.set_awaiting_full_name(chat["id"], lang)
            _reply_text(chat["id"], t("full_name_prompt", lang))
            return

        # NOTE: the "login" deep-link payload previously bypassed this
        # and called send_login_code() directly -- that was the actual
        # bug (a registered customer sometimes got an unrequested
        # 6-digit code from /start). It is intentionally given no
        # special handling now: the website's link only needs to open
        # the right chat, which Telegram itself already does.
        if wants_news:
            from apps.telegram_bot.interfaces import news_menu

            news_menu.subscribe_from_link(user, chat["id"], lang)
            return
        if product_link:
            from apps.telegram_bot.interfaces.callback_router import show_product_link

            show_product_link(user, chat["id"], product_link)
            return
        logger.info("Telegram /start: telegram_user_id=%s registered=true action=show_menu", from_user["id"])
        send_main_menu(chat["id"], lang)
        return

    if wants_news:
        from apps.telegram_bot.interfaces import news_menu

        news_menu.park(from_user["id"])  # subscribed once onboarding creates the account
    logger.info("Telegram /start: telegram_user_id=%s registered=false action=start_registration", from_user["id"])
    _send_language_selection(chat["id"])
    from apps.telegram_bot.interfaces import onboarding_state

    onboarding_state.set_awaiting_language(chat["id"])


def _send_language_selection(chat_id: int) -> None:
    """Real, business-required onboarding entry point: shown before anything else for an unlinked Telegram user -- name/phone are only ever asked in the language the user themselves picks here."""
    from apps.telegram_bot.interfaces.callback_router import _send

    keyboard = [
        [{"text": "\U0001F1FA\U0001F1FF O'zbekcha", "callback_data": "onboarding:lang:uz"}],
        [{"text": "\U0001F1F7\U0001F1FA Русский", "callback_data": "onboarding:lang:ru"}],
        [{"text": "\U0001F1EC\U0001F1E7 English", "callback_data": "onboarding:lang:en"}],
    ]
    _send(chat_id, "\U0001F310 Tilni tanlang / Выберите язык / Choose a language:", keyboard)


def _handle_telegram_auth_start(payload: str, from_user: dict, chat: dict) -> None:
    """
    Phase 4: /start <payload> -- the automatic website login deep
    link. The Telegram sender identity comes ONLY from `from_user`
    (Telegram's own authenticated webhook field, never the payload
    itself, per this phase's own explicit security requirement).
    Never registers a new account or logs in an unlinked Telegram
    account automatically -- only presents a confirmation prompt for
    an already-linked customer, matching this phase's own explicit
    "automatic login only works for already-linked accounts" rule.
    """
    from apps.identity.infrastructure import models as identity_orm
    from apps.identity.infrastructure.security import hash_refresh_token
    from apps.telegram_bot.application.services.linking import ResolveTelegramCustomer
    from apps.telegram_bot.interfaces.i18n import t
    from django.utils import timezone as django_timezone

    token_hash = hash_refresh_token(payload)
    session = identity_orm.TelegramAuthSession.objects.filter(token_hash=token_hash).first()

    lang = "uz"
    customer_id = ResolveTelegramCustomer().execute(from_user["id"])
    if customer_id is not None:
        user = identity_orm.User.objects.filter(id=customer_id).first()
        lang = getattr(user, "language", None) or "uz"

    if session is None or session.status == identity_orm.TelegramAuthSessionStatus.CONSUMED:
        _reply_text(chat["id"], t("auth_login_invalid", lang))
        return

    if session.expires_at <= django_timezone.now():
        if session.status != identity_orm.TelegramAuthSessionStatus.EXPIRED:
            session.status = identity_orm.TelegramAuthSessionStatus.EXPIRED
            session.save(update_fields=["status"])
        _reply_text(chat["id"], t("auth_login_expired", lang))
        return

    if session.status != identity_orm.TelegramAuthSessionStatus.PENDING:
        _reply_text(chat["id"], t("auth_login_invalid", lang))
        return

    if customer_id is None:
        _reply_text(chat["id"], t("auth_login_not_linked", lang))
        return

    if session.telegram_user_id is not None and session.telegram_user_id != from_user["id"]:
        # Wrong-user protection: this session's confirmation prompt was
        # already bound to a different Telegram user's /start. A second,
        # different sender re-issuing /start with the same deep-link
        # token must never rebind the session to themselves.
        _reply_text(chat["id"], t("auth_login_invalid", lang))
        return

    if session.telegram_user_id is None:
        session.telegram_user_id = from_user["id"]
        session.save(update_fields=["telegram_user_id"])

    from apps.telegram_bot.interfaces.callback_router import _send

    keyboard = [
        [{"text": t("auth_login_confirm_button", lang), "callback_data": f"authlogin:confirm:{session.id}"}],
        [{"text": t("auth_login_cancel_button", lang), "callback_data": f"authlogin:cancel:{session.id}"}],
    ]
    _send(chat["id"], t("auth_login_confirm_prompt", lang), keyboard)


def _handle_full_name_reply(message: dict) -> None:
    """
    Onboarding step 2: the user has typed their full name in response
    to the language-selection step. Stores it (with the language they
    already picked) in the short-lived onboarding state (never in the
    database yet -- no customer account exists until confirmation is
    also given via the onboarding:confirm callback), then asks for
    their phone number via a native `request_contact` button.
    """
    from apps.telegram_bot.interfaces import onboarding_state
    from apps.telegram_bot.interfaces.i18n import t

    chat = message["chat"]
    full_name = message.get("text", "").strip()
    state = onboarding_state.get_state(chat["id"]) or {}
    language = state.get("language", "uz")

    if len(full_name) < 2:
        _reply_text(chat["id"], t("full_name_too_short", language))
        return

    onboarding_state.set_awaiting_phone(chat["id"], language, full_name)

    from apps.notifications.infrastructure import composition as notifications_composition

    try:
        gateway = notifications_composition.build_telegram_gateway()
        gateway.send_contact_request(str(chat["id"]), t("ask_phone_after_name", language, full_name=full_name), t("share_contact_button", language))
    except Exception:  # noqa: BLE001
        logger.warning("Telegram bot: failed to send contact request to chat %s", chat["id"])


def _handle_chat_message(message: dict, conversation_id) -> None:
    """
    Real integration: a plain-text message sent while this chat_id is
    in "active chat" mode (per interfaces.chat_state) is written into
    the real apps.chat Conversation via the same SendMessage
    Application Service the REST API itself uses -- not a
    Telegram-only shadow copy of the conversation.
    """
    from apps.chat.domain.enums import MessageType
    from apps.chat.infrastructure import composition as chat_composition
    from apps.identity.infrastructure import models as identity_orm
    from apps.telegram_bot.interfaces import chat_state
    from apps.telegram_bot.interfaces.i18n import t

    chat = message["chat"]
    from_user = message.get("from", {})
    text = message.get("text", "").strip()
    if not text:
        return

    user = identity_orm.User.objects.filter(telegram_user_id=from_user.get("id")).first()
    if user is None:
        chat_state.clear(chat["id"])
        _reply_text(chat["id"], t("please_register", _tg_lang(from_user)))
        return
    lang = getattr(user, "language", None) or _tg_lang(from_user)

    try:
        chat_composition.build_send_message(actor_id=user.id).execute(
            conversation_id=conversation_id, sender_id=user.id, message_type=MessageType.TEXT, content=text,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Telegram bot: failed to send chat message for conversation_id=%s", conversation_id)
        _reply_text(chat["id"], t("technical_error", lang))
        return

    chat_state.refresh(chat["id"], conversation_id)
    _reply_text(chat["id"], t("chat_message_sent", lang))


def _tg_lang(from_user: dict) -> str:
    """The shopper's Telegram app language (ru / en) before we know their NutriZone language; Uzbek otherwise."""
    code = (from_user or {}).get("language_code") or ""
    return code[:2] if code[:2] in ("ru", "en") else "uz"


def _handle_chat_photo(message: dict, conversation_id) -> None:
    """A photo sent while the support chat is open becomes an image message in the same Conversation."""
    from apps.chat.domain.enums import AttachmentType, MessageType
    from apps.chat.domain.value_objects import AttachmentMetadata
    from apps.chat.infrastructure import composition as chat_composition
    from apps.identity.infrastructure import models as identity_orm
    from apps.products.infrastructure.composition import build_media_pipeline
    from apps.telegram_bot.infrastructure import tg_files
    from apps.telegram_bot.interfaces import chat_state
    from apps.telegram_bot.interfaces.i18n import t
    from core.media import MediaType, MediaUploadRequest

    chat = message["chat"]
    from_user = message.get("from", {})
    user = identity_orm.User.objects.filter(telegram_user_id=from_user.get("id")).first()
    if user is None:
        chat_state.clear(chat["id"])
        _reply_text(chat["id"], t("please_register", _tg_lang(from_user)))
        return
    lang = getattr(user, "language", None) or _tg_lang(from_user)
    photo = tg_files.best_photo(message)
    try:
        f = tg_files.download(photo["file_id"])
        result = build_media_pipeline().process(MediaUploadRequest(filename=f.filename, content=f.content, mime_type=f.mime_type, media_type=MediaType.IMAGE))
        if result.is_failure:
            raise tg_files.TelegramFileError(result.errors[0].message)
        processed = result.value
        base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
        attachment = AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url=f"{base}{settings.MEDIA_URL}{processed.storage_path}",
                                        filename=f.filename, size_bytes=len(f.content))
        caption = (message.get("caption") or "").strip() or None
        chat_composition.build_send_message(actor_id=user.id).execute(
            conversation_id=conversation_id, sender_id=user.id, message_type=MessageType.ATTACHMENT, content=caption, attachment=attachment,
        )
    except Exception:  # noqa: BLE001 - the customer is told; the chat stays open
        logger.exception("Telegram bot: chat photo failed for conversation_id=%s", conversation_id)
        _reply_text(chat["id"], t("chat_photo_failed", lang))
        return
    chat_state.refresh(chat["id"], conversation_id)
    _reply_text(chat["id"], t("chat_message_sent", lang))


def _handle_location(message: dict) -> None:
    """
    Real integration, closing the previously disclosed gap: a
    Telegram native "Share Location" reply is only meaningful while
    the customer is mid-checkout (per interfaces.checkout_state) --
    an unrelated location share is silently ignored, never
    misinterpreted as a delivery address.
    """
    from apps.identity.infrastructure import models as identity_orm
    from apps.telegram_bot.application.services import checkout as checkout_service
    from apps.telegram_bot.interfaces import checkout_state
    from apps.telegram_bot.interfaces.callback_router import _send_checkout_summary

    chat = message["chat"]
    from_user = message.get("from", {})
    location = message.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")

    if latitude is None or longitude is None:
        return
    if not checkout_state.is_awaiting_location(chat["id"]):
        if chat.get("type") == "private":  # any other shared location: the nearest stores
            from apps.telegram_bot.interfaces import stores_menu

            known = identity_orm.User.objects.filter(telegram_user_id=from_user.get("id")).first()
            stores_menu.nearest(chat["id"], latitude, longitude, getattr(known, "language", None) or _tg_lang(from_user))
        return

    user = identity_orm.User.objects.filter(telegram_user_id=from_user.get("id")).first()
    if user is None:
        checkout_state.clear(chat["id"])
        return

    checkout_service.get_or_create_default_address(user, latitude, longitude)
    checkout_state.clear(chat["id"])

    lang = getattr(user, "language", None) or "uz"
    summary = checkout_service.get_checkout_summary(user)
    _send_checkout_summary(chat["id"], lang, summary)


def _handle_contact(message: dict) -> None:
    from apps.telegram_bot.application.services.linking import LinkTelegramCustomer, TelegramIdentityAlreadyLinkedToAnotherUser
    from apps.telegram_bot.interfaces.i18n import t

    contact = message["contact"]
    from_user = message["from"]
    chat = message["chat"]

    if contact.get("user_id") != from_user["id"]:
        _reply_text(chat["id"], t("contact_ownership_violation", "uz"))
        return

    phone_number = contact["phone_number"]
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"

    from apps.telegram_bot.interfaces import onboarding_state

    state = onboarding_state.get_state(chat["id"])

    if state and state.get("step") == "awaiting_phone" and state.get("full_name"):
        # Real, business-required behavior: the account is NOT created
        # yet -- the user must explicitly confirm name/phone/language
        # first (see onboarding:confirm in callback_router.py).
        language = state.get("language", "uz")
        full_name = state["full_name"]
        onboarding_state.set_awaiting_confirmation(chat["id"], language, full_name, phone_number)
        _send_onboarding_confirmation(chat["id"], language, full_name, phone_number)
        return

    # Fallback for a contact shared without going through the typed-name
    # onboarding step (e.g. a returning flow) -- never blocks linking.
    full_name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")]))
    onboarding_state.clear(chat["id"])

    try:
        tg_lang = (from_user.get("language_code") or "")[:2]
        result = LinkTelegramCustomer().execute(telegram_user_id=from_user["id"], phone_number_raw=phone_number, full_name=full_name or "Mijoz",
                                                language=tg_lang if tg_lang in ("uz", "ru", "en") else "uz")
    except TelegramIdentityAlreadyLinkedToAnotherUser:
        _reply_text(chat["id"], t("already_linked_elsewhere", "uz"))
        return
    except Exception:  # noqa: BLE001
        logger.exception("Telegram bot: contact linking failed for telegram_user_id=%s", from_user["id"])
        _reply_text(chat["id"], t("technical_error", "uz"))
        return

    from apps.identity.infrastructure import models as identity_orm

    user = identity_orm.User.objects.filter(id=result.user_id).first()
    lang = getattr(user, "language", None) or "uz"

    if result.already_linked_to_this_telegram_account:
        from apps.telegram_bot.interfaces.callback_router import send_main_menu

        send_main_menu(chat["id"], lang)
    elif result.is_new_customer:
        from apps.telegram_bot.interfaces.callback_router import send_main_menu, send_welcome

        send_welcome(chat["id"], user, lang)

        send_main_menu(chat["id"], lang)
    else:
        _reply_text(chat["id"], t("account_found", lang))
        from apps.telegram_bot.interfaces import support_confirm
        from apps.telegram_bot.interfaces.callback_router import send_main_menu

        support_confirm.ask(chat["id"], user, lang, suggested_name=full_name)  # account made from a support call
        send_main_menu(chat["id"], lang)


def _send_onboarding_confirmation(chat_id: int, language: str, full_name: str, phone_number: str) -> None:
    """Real, business-required step: shows the collected name/phone/language back to the user and requires an explicit confirm before any account is created -- matching this project's own "never silently link/create" discipline elsewhere (e.g. contact-ownership checks)."""
    from apps.telegram_bot.interfaces.callback_router import _send
    from apps.telegram_bot.interfaces.i18n import t

    text = t("onboarding_confirmation_summary", language, full_name=full_name, phone_number=phone_number, language_name=t(f"language_name_{language}", language))
    keyboard = [
        [{"text": t("onboarding_confirm_button", language), "callback_data": "onboarding:confirm"}],
        [{"text": t("onboarding_edit_button", language), "callback_data": "onboarding:edit"}],
        [{"text": t("onboarding_cancel_button", language), "callback_data": "onboarding:cancel"}],
    ]
    _send(chat_id, text, keyboard)


def _is_photo(message: dict) -> bool:
    from apps.telegram_bot.infrastructure.tg_files import best_photo

    return best_photo(message) is not None


def _handle_photo(message: dict) -> None:
    """A photo in the private chat: into the open support chat, else a "find this product" request (or the offer to make one)."""
    from apps.identity.infrastructure import models as identity_orm
    from apps.telegram_bot.interfaces import chat_state, find_product
    from apps.telegram_bot.interfaces.i18n import t

    chat_id = message["chat"]["id"]
    from_user = message.get("from", {})
    conversation_id = chat_state.get_active_conversation(chat_id)
    if conversation_id is not None:
        _handle_chat_photo(message, conversation_id)
        return
    user = identity_orm.User.objects.filter(telegram_user_id=from_user.get("id")).first()
    if user is None:
        _reply_text(chat_id, t("please_register", _tg_lang(from_user)))
        return
    find_product.handle_message(user, message, getattr(user, "language", None) or _tg_lang(from_user))


def _find_product_text(message: dict) -> bool:
    """Typed text while the bot waits for a product request (name / link). True = handled."""
    from apps.identity.infrastructure import models as identity_orm
    from apps.telegram_bot.interfaces import find_product

    chat_id = message["chat"]["id"]
    if message["text"].startswith("/") or not find_product.is_awaiting(chat_id):
        return False
    user = identity_orm.User.objects.filter(telegram_user_id=message.get("from", {}).get("id")).first()
    if user is None:
        return False
    return find_product.handle_message(user, message, getattr(user, "language", None) or "uz")


def _bot_command(message: dict) -> bool:
    """/menu, /savat, /buyurtmalar, /dokon … (see callback_router.COMMANDS). False lets other handling continue."""
    from apps.telegram_bot.interfaces.callback_router import run_command

    command = message["text"][1:].split()[0].split("@")[0].lower() if len(message["text"]) > 1 else ""
    return run_command(message["chat"]["id"], message["from"]["id"], command)


@csrf_exempt
def telegram_webhook_view(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    configured_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", None)
    if not configured_secret:
        logger.error("Telegram webhook received but TELEGRAM_WEBHOOK_SECRET is not configured -- rejecting.")
        return HttpResponse(status=403)

    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if provided_secret != configured_secret:
        logger.warning("Telegram webhook: secret token mismatch.")
        return HttpResponse(status=403)

    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Telegram webhook: malformed update body.")
        return HttpResponse(status=200)

    try:
        message = update.get("message")
        callback_query = update.get("callback_query")
        inline_query = update.get("inline_query")

        if inline_query is not None:
            from apps.telegram_bot.interfaces import inline_search

            inline_search.answer(inline_query)
        elif callback_query is not None:
            from apps.telegram_bot.interfaces.callback_router import handle_callback

            handle_callback(callback_query)
            _answer_callback_query(callback_query.get("id"))
        elif message is not None:
            if "contact" in message:
                _handle_contact(message)
            elif "location" in message:
                _handle_location(message)
            elif message.get("text", "").startswith("/start"):
                _handle_start(message)
            elif message.get("chat", {}).get("type") == "private" and not message.get("text") and _is_photo(message):
                _handle_photo(message)
            elif message.get("text", "").startswith("/") and message.get("chat", {}).get("type") == "private" and _bot_command(message):
                pass
            elif message.get("text"):
                from apps.telegram_bot.interfaces import chat_state, onboarding_state

                state = onboarding_state.get_state(message["chat"]["id"])
                step = state.get("step") if state else None
                if step == "awaiting_full_name":
                    _handle_full_name_reply(message)
                elif step == "awaiting_language":
                    # Must be answered via the language-selection buttons, not typed text.
                    _send_language_selection(message["chat"]["id"])
                elif step == "awaiting_confirmation":
                    # Must be answered via the confirm/edit/cancel buttons, not typed text.
                    _send_onboarding_confirmation(message["chat"]["id"], state.get("language", "uz"), state.get("full_name", ""), state.get("phone_number", ""))
                else:
                    active_conversation_id = chat_state.get_active_conversation(message["chat"]["id"])
                    if active_conversation_id is not None:
                        _handle_chat_message(message, active_conversation_id)
                    elif message.get("chat", {}).get("type") == "private" and _find_product_text(message):
                        pass
                    elif message.get("chat", {}).get("type") == "private" and not message["text"].startswith("/"):
                        # Anything else typed in a private chat is a product search (never in groups/channels).
                        from apps.telegram_bot.interfaces.callback_router import search_text

                        search_text(message["chat"]["id"], message["from"]["id"], message["text"])
                    elif message.get("chat", {}).get("type") in ("group", "supergroup"):
                        # In groups the assistant answers questions addressed to the bot (mention or reply)
                        from apps.telegram_bot.interfaces.callback_router import group_question

                        group_question(message)
    except Exception:  # noqa: BLE001
        logger.exception("Telegram webhook: unexpected failure processing update.")

    return HttpResponse(status=200)


@csrf_exempt
def telegram_orders_webhook_view(request):
    """
    Phase 15F: the separate Orders Bot's own webhook -- a genuinely
    different bot (own @username/token, see TELEGRAM_ORDERS_BOT_TOKEN)
    from the customer-facing bot above, authenticated with its own
    secret (TELEGRAM_ORDERS_WEBHOOK_SECRET), matching
    telegram_webhook_view's own validation shape exactly.

    This bot only ever sends messages with the Confirm/Cancel inline
    keyboard (see orders_channel_subscriber.py) -- so the only update
    type it is ever expected to receive back is a `callback_query` with
    `manager:confirm:<id>`/`manager:cancel:<id>` data, which reuses the
    exact same, already-tested `handle_callback` dispatcher the
    customer bot's webhook uses (its own `manager` namespace branch is
    already routed independently of customer identity). Any other
    update type (e.g. the bot being added to/removed from a group) is
    harmless and simply ignored, same discipline as the customer
    webhook's own unrecognized-update handling.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    configured_secret = getattr(settings, "TELEGRAM_ORDERS_WEBHOOK_SECRET", None)
    if not configured_secret:
        logger.error("Telegram Orders Bot webhook received but TELEGRAM_ORDERS_WEBHOOK_SECRET is not configured -- rejecting.")
        return HttpResponse(status=403)

    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if provided_secret != configured_secret:
        logger.warning("Telegram Orders Bot webhook: secret token mismatch.")
        return HttpResponse(status=403)

    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Telegram Orders Bot webhook: malformed update body.")
        return HttpResponse(status=200)

    try:
        from apps.telegram_bot.infrastructure import orders_bot

        if orders_bot.handle_update(update):  # /start, menu buttons (ob:*), the lists for owners and staff
            return HttpResponse(status=200)
        callback_query = update.get("callback_query")
        if callback_query is not None:
            from apps.telegram_bot.interfaces.callback_router import handle_callback

            handle_callback(callback_query)
            _answer_callback_query(callback_query.get("id"), bot_token=getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None))
    except Exception:  # noqa: BLE001
        logger.exception("Telegram Orders Bot webhook: unexpected failure processing update.")

    return HttpResponse(status=200)


@csrf_exempt
def telegram_analytics_webhook_view(request):
    """NutriZoneAnalyticsBot's webhook (own token and secret) -- commands and menu buttons, see analytics_bot.handle_update."""
    if request.method != "POST":
        return HttpResponse(status=405)
    configured_secret = getattr(settings, "TELEGRAM_ANALYTICS_WEBHOOK_SECRET", None)
    if not configured_secret:
        logger.error("Telegram Analytics Bot webhook received but TELEGRAM_ANALYTICS_WEBHOOK_SECRET is not configured -- rejecting.")
        return HttpResponse(status=403)
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != configured_secret:
        logger.warning("Telegram Analytics Bot webhook: secret token mismatch.")
        return HttpResponse(status=403)
    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=200)
    try:
        from apps.telegram_bot.infrastructure.analytics_bot import handle_update

        handle_update(update)
    except Exception:  # noqa: BLE001 - Telegram must always get a 200, or it redelivers the update
        logger.exception("Telegram Analytics Bot webhook: unexpected failure processing update.")
    return HttpResponse(status=200)


def _answer_callback_query(callback_query_id: str | None, bot_token: str | None = None) -> None:
    """Acknowledges the callback so Telegram doesn't show a permanent loading spinner on the button -- best-effort, per this module's own failure discipline."""
    if not callback_query_id:
        return
    try:
        import requests
        from django.conf import settings

        resolved_bot_token = bot_token if bot_token is not None else getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        base_url = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org")
        if resolved_bot_token:
            requests.post(f"{base_url}/bot{resolved_bot_token}/answerCallbackQuery", json={"callback_query_id": callback_query_id}, timeout=5)
    except Exception:  # noqa: BLE001
        pass
