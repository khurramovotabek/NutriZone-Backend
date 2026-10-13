"""
Who may see what in the staff bots (Orders bot, Analytics bot).

  * all-access    the explicit allowlists: TELEGRAM_ANALYTICS_CHAT_IDS (analytics), TelegramStaffMember / the Orders
                  channel chat (orders). Never self-service.
  * store owner   the identity user whose telegram_user_id is this chat, owner of one or more stores.Store rows --
                  sees ONLY those branches. Ownership is read live each time, so re-assigning a store in the
                  dashboard takes effect immediately.
  * nobody else   is told their chat id and nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class Scope:
    chat_id: int
    all_access: bool = False
    stores: list = field(default_factory=list)  # stores.Store rows (selling branches) this chat may see
    name: str = ""

    @property
    def allowed(self) -> bool:
        return self.all_access or bool(self.stores)

    @property
    def store_ids(self) -> set:
        return {s.id for s in self.stores}

    def can_see(self, store_id) -> bool:
        return self.all_access or (store_id is not None and str(store_id) in {str(x) for x in self.store_ids})


def _analytics_allowlist() -> set[str]:
    raw = getattr(settings, "TELEGRAM_ANALYTICS_CHAT_IDS", "") or ""
    return {c.strip() for c in str(raw).replace(";", ",").split(",") if c.strip()}


def owned_stores(telegram_user_id) -> tuple[list, str]:
    from apps.identity.infrastructure.models import User
    from apps.stores.infrastructure.models import Store

    user = User.objects.filter(telegram_user_id=telegram_user_id).first() if telegram_user_id else None
    if user is None:
        return [], ""
    stores = list(Store.objects.filter(owner_id=user.id, kind="store").exclude(status="inactive").order_by("name"))
    return stores, user.full_name or ""


def scope(bot: str, chat_id, telegram_user_id=None) -> Scope:
    from apps.stores.infrastructure.models import Store
    from apps.telegram_bot.infrastructure.models import TelegramStaffMember

    tg_user = telegram_user_id or chat_id
    stores, name = owned_stores(tg_user)
    if bot == "analytics":
        all_access = str(chat_id) in _analytics_allowlist()
    else:
        all_access = str(chat_id) == str(getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", "") or "") or TelegramStaffMember.objects.filter(telegram_user_id=tg_user, is_active=True).exists()
    if all_access:
        stores = list(Store.objects.filter(kind="store").exclude(status="inactive").order_by("name"))
    return Scope(chat_id=int(chat_id), all_access=all_access, stores=stores, name=name)


def register(bot: str, message: dict):
    """/start (or any message) in a staff bot -> the subscriber row, re-activated if they had blocked the bot."""
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    chat = message.get("chat") or {}
    who = message.get("from") or {}
    name = " ".join(x for x in (who.get("first_name"), who.get("last_name")) if x)
    sub, _created = TelegramBotSubscriber.objects.update_or_create(
        bot=bot, chat_id=chat.get("id"),
        defaults={"telegram_user_id": who.get("id"), "display_name": name[:255], "username": (who.get("username") or "")[:64], "is_active": True},
    )
    return sub


def subscribers(bot: str):
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    return TelegramBotSubscriber.objects.filter(bot=bot, is_active=True)


def owners_of(bot: str, store_id) -> list:
    """Active subscribers of `bot` who own `store_id` (the all-access audience is handled by the channel posts)."""
    from apps.identity.infrastructure.models import User
    from apps.stores.infrastructure.models import Store

    owner_id = Store.objects.filter(id=store_id).values_list("owner_id", flat=True).first()
    if not owner_id:
        return []
    tg = User.objects.filter(id=owner_id).values_list("telegram_user_id", flat=True).first()
    if not tg:
        return []
    return list(subscribers(bot).filter(telegram_user_id=tg))


def deactivate(bot: str, chat_id) -> None:
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    TelegramBotSubscriber.objects.filter(bot=bot, chat_id=chat_id).update(is_active=False)
