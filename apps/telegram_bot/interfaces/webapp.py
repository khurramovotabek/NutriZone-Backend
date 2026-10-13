"""
Telegram Mini App sign-in: the storefront opened inside Telegram (bot menu button / "Do'konni ochish") sends the
WebApp `initData`; it is verified exactly as Telegram specifies (HMAC-SHA256 with the key derived from the bot
token), and the linked customer gets the same bot-initiated auth session the "Saytga avtomatik kirish" link uses --
so the shopper is signed in without a code. https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from common.responses import success_response
from common.responses.envelope import error_response
from core.ratelimit import ScopedRateLimitThrottle

MAX_AGE_SECONDS = 3600  # an initData older than this is not accepted for sign-in (Telegram re-issues it on every open)


def verified_user(init_data: str, bot_token: str, now: float | None = None) -> dict | None:
    """The Telegram `user` object from a genuine, fresh initData; None for anything forged, tampered or stale."""
    if not init_data or not bot_token:
        return None
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    if not received_hash:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        auth_date = int(fields.get("auth_date", "0"))
        user = json.loads(fields.get("user") or "null")
    except (TypeError, ValueError):
        return None
    if not isinstance(user, dict) or not user.get("id") or (now or time.time()) - auth_date > MAX_AGE_SECONDS:
        return None
    return user


class WebAppSignInThrottle(ScopedRateLimitThrottle):
    scope = "telegram_webapp_signin"
    limit = 30
    window_seconds = 600


class TelegramWebAppSessionView(APIView):
    """`POST /telegram/webapp/session {"init_data"}` -> `{"session_id"}` to complete through the usual auto-login flow."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [WebAppSignInThrottle]

    @extend_schema(tags=["Telegram"], summary="Sign in from the Telegram Mini App")
    def post(self, request):
        from apps.identity.application.services.telegram_auth import CreateBotInitiatedAuthSession
        from apps.telegram_bot.application.services.linking import ResolveTelegramCustomer

        user = verified_user(str(request.data.get("init_data") or ""), getattr(settings, "TELEGRAM_BOT_TOKEN", None) or "")
        if user is None:
            return error_response("INVALID_INIT_DATA", "Telegram data could not be verified.", "authentication", 401)
        customer_id = ResolveTelegramCustomer().execute(int(user["id"]))
        if customer_id is None:
            return error_response("NOT_REGISTERED", "Open the bot and register first.", "business", 404)
        created = CreateBotInitiatedAuthSession().execute(customer_id=customer_id, telegram_user_id=int(user["id"]))
        return success_response(data={"session_id": str(created.session_id), "cart": shared_cart(customer_id)})


def shared_cart(customer_id) -> dict | None:
    """
    The shopper's bot cart (code + token), so the Mini App and the bot chat show ONE cart: what was added with the
    bot's buttons is in the Mini App and the other way round. Only ever returned to the verified owner (initData above).
    """
    import logging

    from apps.identity.infrastructure.models import User
    from apps.telegram_bot.application.services.shopping import TelegramCartService

    try:
        user = User.objects.get(id=customer_id)
        cart, _user = TelegramCartService()._get_or_create_cart(user)
        return {"code": cart.code.value, "token": str(cart.token)}
    except Exception:  # noqa: BLE001 - sign-in must never fail because of the cart; the Mini App then keeps its own cart
        logging.getLogger("nutrizone.telegram_bot").exception("webapp: shared cart unavailable for %s", customer_id)
        return None
