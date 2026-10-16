"""
Sending a Dashboard Telegram post (models.TelegramPost) through the customer bot.

One post = one photo (uploaded, or the attached product's) + formatted text + URL buttons. The photo is uploaded
once; every following chat reuses Telegram's file_id. Text up to 1024 visible characters rides as the photo
caption; a longer text goes as a second message right under the photo (the buttons sit on the last message).
Private chats are paced under Telegram's ~30 messages/second limit; a customer who blocked the bot is just counted.
"""
from __future__ import annotations

import json
import logging
import time

import requests
from django.conf import settings
from django.utils import timezone

from apps.telegram_bot.infrastructure.telegram_html import CAPTION_LIMIT, visible_length

logger = logging.getLogger("nutrizone.telegram_bot.posts")

PACE_SECONDS = 0.04


class PostError(Exception):
    pass


def _token() -> str:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        raise PostError("TELEGRAM_BOT_TOKEN sozlanmagan")
    return token


def _api(method: str, *, data=None, files=None) -> dict:
    base = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
    try:
        r = requests.post(f"{base}/bot{_token()}/{method}", data=data, files=files, timeout=30)
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise PostError(f"{method}: {exc.__class__.__name__}") from exc
    if not body.get("ok"):
        raise PostError(str(body.get("description") or r.status_code))
    return body.get("result") or {}


# ----------------------------------------------------------------------------- content


def product_card(post) -> dict | None:
    if not post.product_id:
        return None
    from apps.products.infrastructure.selectors import _cards_with_price_and_rating

    product = type(post.product).objects.filter(pk=post.product_id).prefetch_related("translations", "media", "variants").first()
    if product is None:
        return None
    cards = _cards_with_price_and_rating([product], "uz")
    return cards[0] if cards else None


def keyboard(post, card: dict | None = None) -> list:
    """URL buttons, two per row; a product post gets «Sotib olish» first. Telegram accepts only http(s)/tg links."""
    rows, row = [], []
    items = []
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if card and base.startswith("https://"):
        items.append({"text": "🛒 Sotib olish", "url": f"{base}/products/{card['slug']}"})
    for b in post.buttons or []:
        text, url = (b.get("text") or "").strip(), (b.get("url") or "").strip()
        if text and url.startswith(("https://", "http://", "tg://")):
            items.append({"text": text[:64], "url": url})
    for it in items:
        row.append(it)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def photo_bytes(post, card: dict | None) -> tuple[bytes, str] | None:
    if post.image:
        post.image.open("rb")
        try:
            return post.image.read(), post.image.name.rsplit("/", 1)[-1]
        finally:
            post.image.close()
    if card and card.get("primary_image_path"):
        from apps.telegram_bot.infrastructure.shop_rich import photo

        png = photo(card["primary_image_path"], 1080)
        if png:
            return png, "product.png"
    return None


def recipients(post) -> list[str]:
    """Private chat ids (deduplicated) for the subscriber / customer audiences; the channel is sent separately."""
    from apps.identity.infrastructure.models import User

    ids: set[str] = set()
    if post.to_customers:
        ids |= {str(x) for x in User.objects.exclude(status="blocked").filter(telegram_user_id__isnull=False).values_list("telegram_user_id", flat=True)}
    if post.to_subscribers:
        from apps.notifications.infrastructure.models import NewsSubscription

        ids |= {str(x) for x in NewsSubscription.objects.filter(user__telegram_user_id__isnull=False).exclude(user__status="blocked").values_list("user__telegram_user_id", flat=True)}
    return sorted(ids)


# ----------------------------------------------------------------------------- sending


class _Sender:
    def __init__(self, post) -> None:
        self.post = post
        self.card = product_card(post)
        self.kb = keyboard(post, self.card)
        self.photo = photo_bytes(post, self.card)
        self.file_id: str | None = None
        self.caption_fits = visible_length(post.body) <= CAPTION_LIMIT

    def _markup(self) -> dict:
        return {"reply_markup": json.dumps({"inline_keyboard": self.kb}, ensure_ascii=False)} if self.kb else {}

    def send(self, chat_id: str) -> int:
        """Returns the message id of the first message (the one to pin)."""
        common = {"chat_id": chat_id, "parse_mode": "HTML"}
        if self.post.silent:
            common["disable_notification"] = "true"
        body = self.post.body or ""
        if self.photo:
            data = {**common}
            last = not body or self.caption_fits
            if body and self.caption_fits:
                data["caption"] = body
            if last:
                data.update(self._markup())
            files = None
            if self.file_id:
                data["photo"] = self.file_id
            else:
                files = {"photo": (self.photo[1], self.photo[0])}
            res = _api("sendPhoto", data=data, files=files)
            if not self.file_id:
                sizes = res.get("photo") or []
                self.file_id = sizes[-1]["file_id"] if sizes else None
            first_id = int(res.get("message_id") or 0)
            if last:
                return first_id
            _api("sendMessage", data={**common, "text": body, "link_preview_options": json.dumps({"is_disabled": True}), **self._markup()})
            return first_id
        res = _api("sendMessage", data={**common, "text": body or self.post.title, "link_preview_options": json.dumps({"is_disabled": True}), **self._markup()})
        return int(res.get("message_id") or 0)


def is_blocked(error: Exception) -> bool:
    text = str(error).lower()
    return any(x in text for x in ("blocked", "deactivated", "chat not found", "forbidden"))


def send_test(post, chat_id: str) -> None:
    """One copy to the given chat (the editor's own Telegram) -- nothing is recorded on the post."""
    _Sender(post).send(str(chat_id))


def send(post_id) -> dict:
    """Celery body: channel first (and pin), then private chats. Idempotent per post (only a queued post is sent)."""
    from apps.telegram_bot.infrastructure.models import TelegramPost, TelegramPostStatus

    claimed = TelegramPost.objects.filter(pk=post_id, status=TelegramPostStatus.QUEUED).update(status=TelegramPostStatus.SENDING)
    if not claimed:
        return {"skipped": True}
    post = TelegramPost.objects.select_related("product").get(pk=post_id)
    sent = failed = 0
    errors: list[str] = []
    try:
        sender = _Sender(post)
        chats = recipients(post)
        TelegramPost.objects.filter(pk=post.pk).update(recipients=len(chats) + (1 if post.to_channel and post.channel else 0))
        if post.to_channel and post.channel:
            try:
                mid = sender.send(post.channel.strip())
                sent += 1
                TelegramPost.objects.filter(pk=post.pk).update(channel_message_id=mid)
                if post.pin and mid:
                    try:
                        _api("pinChatMessage", data={"chat_id": post.channel.strip(), "message_id": mid, "disable_notification": "true"})
                    except PostError as exc:
                        errors.append(f"pin: {exc}")
            except PostError as exc:
                failed += 1
                errors.append(f"kanal: {exc}")
        for chat in chats:
            try:
                sender.send(chat)
                sent += 1
            except PostError as exc:
                failed += 1
                if not is_blocked(exc) and len(errors) < 5:
                    errors.append(f"{chat}: {exc}")
            time.sleep(PACE_SECONDS)
        status = TelegramPostStatus.SENT if sent else TelegramPostStatus.FAILED
    except Exception as exc:  # noqa: BLE001 - recorded on the post, visible in the dashboard
        logger.exception("telegram post %s failed", post_id)
        errors.append(str(exc)[:300])
        status = TelegramPostStatus.FAILED
    TelegramPost.objects.filter(pk=post.pk).update(status=status, sent_count=sent, failed_count=failed, last_error="\n".join(errors)[:2000], sent_at=timezone.now())
    return {"sent": sent, "failed": failed}


def queue(post) -> None:
    from django.db import transaction

    from apps.telegram_bot.infrastructure.models import TelegramPost, TelegramPostStatus
    from apps.telegram_bot.infrastructure.tasks import send_post

    TelegramPost.objects.filter(pk=post.pk).update(status=TelegramPostStatus.QUEUED, sent_count=0, failed_count=0, last_error="")
    transaction.on_commit(lambda: send_post.delay(str(post.pk)))
