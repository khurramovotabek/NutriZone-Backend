"""
The customer inbox: one place every other module calls to tell a customer something happened.

    notify(user_id, "order_shipped", ctx={"order": "ORD-..."}, link="/orders/ORD-...", dedupe_key="order:<id>:shipped")

- Text lives here, per kind, in uz/ru/en. The row stores all three (`i18n`) so the storefront shows the language
  the site is open in; `title`/`body` hold Uzbek (the default storefront language) for the admin and old clients.
- `dedupe_key` is unique in the database: the same business event (an order reaching "shipped", a coin credit)
  can never notify twice, whichever code path or retry fires it.
- Work runs on transaction commit (a rolled-back change never notifies) and never raises into the caller.
- Telegram: sent to the customer's private chat (`telegram_user_id`) by a Celery task, when `telegram=True` and
  the customer linked the bot. Loyalty kinds pass `telegram=False` because Loyalty already sends its own richer
  Telegram message.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger("nutrizone.app")

LANGS = ("uz", "ru", "en")


@dataclass(frozen=True)
class Kind:
    icon: str   # lucide icon name the storefront draws
    tone: str   # success / info / warning / danger / primary / violet
    priority: str
    uz: tuple[str, str]
    ru: tuple[str, str]
    en: tuple[str, str]


K = Kind
KINDS: dict[str, Kind] = {
    # ---- orders
    "order_confirmed": K("package-check", "success", "high",
        ("Buyurtma tasdiqlandi", "{order} raqamli buyurtmangiz tasdiqlandi va tayyorlanmoqda."),
        ("Заказ подтверждён", "Ваш заказ {order} подтверждён и готовится."),
        ("Order confirmed", "Your order {order} has been confirmed and is being prepared.")),
    "order_processing": K("package", "info", "normal",
        ("Buyurtma yig'ilmoqda", "{order} buyurtmangiz omborda yig'ilmoqda."),
        ("Заказ собирается", "Ваш заказ {order} собирается на складе."),
        ("Order is being packed", "Your order {order} is being packed.")),
    "payment_received": K("circle-check", "success", "high",
        ("To'lov qabul qilindi", "{order} buyurtmangiz uchun {amount} so'm {provider} orqali to'landi. Buyurtma tasdiqlandi."),
        ("Оплата получена", "Заказ {order}: {amount} сум оплачено через {provider}. Заказ подтверждён."),
        ("Payment received", "Order {order}: {amount} UZS paid via {provider}. Your order is confirmed.")),
    "payment_reminder": K("credit-card", "warning", "high",
        ("{order} buyurtmasi to'lovni kutmoqda", "{amount} so'mni {provider} orqali to'lang — to'lov qilinmasa buyurtma {hours} soatdan keyin bekor qilinadi."),
        ("Заказ {order} ждёт оплаты", "Оплатите {amount} сум через {provider} — без оплаты заказ будет отменён через {hours} ч."),
        ("Order {order} is waiting for payment", "Pay {amount} UZS via {provider} — unpaid orders are cancelled after {hours} h.")),
    "order_payment_expired": K("circle-x", "danger", "high",
        ("{order} buyurtmasi bekor qilindi", "Onlayn to'lov {hours} soat ichida amalga oshmadi. Mahsulotlar hali kerak bo'lsa, qaytadan buyurtma bering."),
        ("Заказ {order} отменён", "Онлайн-оплата не поступила в течение {hours} ч. Если товары ещё нужны — оформите заказ заново."),
        ("Order {order} was cancelled", "The online payment didn't arrive within {hours} h. If you still need the items, please order again.")),
    "payment_refunded": K("undo-2", "warning", "high",
        ("To'lov qaytarildi", "{order} buyurtmasi uchun {amount} so'm {provider} hisobingizga qaytarildi."),
        ("Оплата возвращена", "За заказ {order} {amount} сум возвращены на ваш счёт {provider}."),
        ("Payment refunded", "{amount} UZS for order {order} was refunded to your {provider} account.")),
    "order_shipped": K("truck", "primary", "high",
        ("Buyurtma yo'lda", "{order} buyurtmangiz kuryerga topshirildi va yo'lda."),
        ("Заказ в пути", "Ваш заказ {order} передан курьеру и уже в пути."),
        ("Order on its way", "Your order {order} has been handed to the courier.")),
    "order_ready_pickup": K("store", "primary", "high",
        ("Buyurtma olib ketishga tayyor", "{order} buyurtmangiz {store} do'konida tayyor: {address}. Kelganda buyurtma raqamini ayting."),
        ("Заказ готов к выдаче", "Ваш заказ {order} ждёт вас в магазине {store}: {address}. Назовите номер заказа на кассе."),
        ("Order ready for pickup", "Your order {order} is ready at {store}: {address}. Just give the order number at the counter.")),
    "order_picked_up": K("circle-check", "success", "high",
        ("Buyurtma olib ketildi", "{order} buyurtmangizni {store} do'konidan olib ketdingiz. Xaridingiz uchun rahmat!"),
        ("Заказ получен", "Вы забрали заказ {order} в магазине {store}. Спасибо за покупку!"),
        ("Order picked up", "You picked up order {order} at {store}. Thank you for shopping with us!")),
    "store_order_new": K("shopping-bag", "primary", "high",
        ("Yangi buyurtma: {order}", "{store} uchun {method} buyurtmasi — {units} dona, {amount} so'm. Qabul qilib, yig'ishni boshlang."),
        ("Новый заказ: {order}", "{store}: заказ ({method}) — {units} шт., {amount} сум. Примите его и начните сборку."),
        ("New order: {order}", "{store}: a {method} order — {units} items, {amount} UZS. Accept it and start packing.")),
    "order_delivered": K("circle-check", "success", "high",
        ("Buyurtma yetkazildi", "{order} buyurtmangiz yetkazib berildi. Xaridingiz uchun rahmat!"),
        ("Заказ доставлен", "Ваш заказ {order} доставлен. Спасибо за покупку!"),
        ("Order delivered", "Your order {order} has been delivered. Thank you for shopping with us!")),
    "order_cancelled": K("circle-x", "danger", "high",
        ("Buyurtma bekor qilindi", "{order} buyurtmangiz bekor qilindi. Savollar bo'lsa, biz bilan bog'laning."),
        ("Заказ отменён", "Ваш заказ {order} отменён. Если есть вопросы — свяжитесь с нами."),
        ("Order cancelled", "Your order {order} was cancelled. Contact us if you have any questions.")),
    "order_returned": K("undo-2", "warning", "normal",
        ("Buyurtma qaytarildi", "{order} buyurtmangiz bo'yicha qaytarish rasmiylashtirildi."),
        ("Заказ возвращён", "Возврат по заказу {order} оформлен."),
        ("Order returned", "The return for your order {order} has been processed.")),
    "order_failed": K("triangle-alert", "danger", "high",
        ("To'lov amalga oshmadi", "{order} buyurtmasi uchun to'lov o'tmadi. Qaytadan urinib ko'ring."),
        ("Оплата не прошла", "Оплата заказа {order} не прошла. Попробуйте ещё раз."),
        ("Payment failed", "Payment for order {order} did not go through. Please try again.")),
    # ---- returns & cancellations (apps/notifications/infrastructure/inbox_signals.py: _after_sales_status)
    # ---- store tills
    "pos_receipt": K("package-check", "success", "normal",
        ("Xaridingiz uchun rahmat!", "{store}: {number} chek — {amount} so'm. Elektron chekni ochish uchun tugmani bosing."),
        ("Спасибо за покупку!", "{store}: чек {number} — {amount} сум. Нажмите кнопку, чтобы открыть электронный чек."),
        ("Thanks for your purchase!", "{store}: receipt {number} — {amount} UZS. Tap the button to open the e-receipt.")),
    "news_subscribed": K("megaphone", "primary", "normal",
        ("Yangiliklarga obuna bo'ldingiz", "Endi aksiyalar, yangi mahsulotlar va foydali maqolalar haqida birinchilardan bo'lib bilasiz.{gift}"),
        ("Вы подписались на новости", "Теперь вы первыми узнаёте об акциях, новинках и полезных статьях.{gift}"),
        ("You're subscribed to news", "You'll be the first to hear about promotions, new products and useful articles.{gift}")),
    "subscription_gift": K("gift", "success", "high",
        ("Sovg'a: +{coins} coin", "Obuna sovg'asi — {number} xaridingiz uchun hisobingizga {coins} NutriZone Coins tushdi. Keyingi xaridda ishlating!"),
        ("Подарок: +{coins} коинов", "Подарок за подписку — за покупку {number} на счёт зачислено {coins} NutriZone Coins. Используйте при следующей покупке!"),
        ("Gift: +{coins} coins", "Your subscription gift — {coins} NutriZone Coins for purchase {number}. Use them on your next order!")),
    "salary_paid": K("coins", "success", "high",
        ("Oylik to'landi: {month}", "{month} uchun {total} so'm to'landi. Savdongiz {revenue} so'm, KPI {kpi} so'm. Rahmat!"),
        ("Зарплата выплачена: {month}", "За {month} выплачено {total} сум. Ваши продажи {revenue} сум, KPI {kpi} сум. Спасибо!"),
        ("Salary paid: {month}", "{total} UZS paid for {month}. Your sales {revenue} UZS, KPI {kpi} UZS. Thank you!")),
    "cashier_added": K("store", "success", "high",
        ("Siz kassirsiz: {store}", "Sizni «{store}» kassasiga kassir qilib qo'shishdi. Profil → Mening do'konim → POS terminal orqali savdo qilasiz."),
        ("Вы кассир: {store}", "Вас добавили кассиром в кассу «{store}». Продажи — Профиль → Мой магазин → POS-терминал."),
        ("You're a cashier: {store}", "You were added as a cashier at «{store}». Sell from Profile → My store → POS terminal.")),
    "shift_closed": K("coins", "info", "normal",
        ("Smena yopildi: {store}", "{sales} ta savdo, tushum {revenue} so'm. Naqd farqi: {difference} so'm."),
        ("Смена закрыта: {store}", "{sales} продаж, выручка {revenue} сум. Расхождение по наличным: {difference} сум."),
        ("Shift closed: {store}", "{sales} sales, revenue {revenue} UZS. Cash difference: {difference} UZS.")),
    # ---- cart
    "replenish_reminder": K("refresh-cw", "primary", "normal",
        ("{product} tugab qolmoqda", "Hisob-kitobimizcha, {product} {days_text}. Yangisini hozir buyurtma qilsangiz, tanaffussiz davom etasiz."),
        ("{product} скоро закончится", "По нашим расчётам, {product} {days_text}. Закажите сейчас — и продолжите без перерыва."),
        ("Your {product} is running low", "By our estimate, your {product} {days_text}. Reorder now to keep going without a break.")),
    "cart_reminder": K("shopping-cart", "primary", "normal",
        ("Savatingiz sizni kutyapti", "Savatingizda {products} turibdi. Buyurtmani bir necha bosishda yakunlashingiz mumkin."),
        ("Ваша корзина ждёт", "В вашей корзине {products}. Оформить заказ можно в пару кликов."),
        ("Your cart is waiting", "{products} are still in your cart. You can finish the order in a couple of taps.")),
    "return_requested": K("rotate-ccw", "info", "normal",
        ("Qaytarish so'rovi qabul qilindi", "{order} buyurtmasi bo'yicha {number} qaytarish so'rovingiz qabul qilindi. Do'kon tez orada ko'rib chiqadi."),
        ("Запрос на возврат принят", "Ваш запрос на возврат {number} по заказу {order} принят. Магазин скоро его рассмотрит."),
        ("Return request received", "Your return request {number} for order {order} has been received. The store will review it shortly.")),
    "return_approved": K("circle-check", "success", "high",
        ("Qaytarish tasdiqlandi", "{number} qaytarish so'rovingiz tasdiqlandi. Mahsulotni do'konga qaytarishingiz mumkin — kuryer yoki operator siz bilan bog'lanadi."),
        ("Возврат одобрен", "Ваш запрос на возврат {number} одобрен. Можно вернуть товар — курьер или оператор свяжется с вами."),
        ("Return approved", "Your return {number} has been approved. You can send the item back — a courier or operator will contact you.")),
    "return_rejected": K("circle-x", "danger", "high",
        ("Qaytarish rad etildi", "{number} qaytarish so'rovingiz rad etildi. Sabab: {reason}"),
        ("Возврат отклонён", "Ваш запрос на возврат {number} отклонён. Причина: {reason}"),
        ("Return rejected", "Your return request {number} was rejected. Reason: {reason}")),
    "return_received": K("package-check", "info", "normal",
        ("Mahsulot qabul qilindi", "{number} qaytarish bo'yicha mahsulot do'konga yetib keldi. Pul tez orada qaytariladi."),
        ("Товар получен", "Товар по возврату {number} получен магазином. Деньги скоро вернутся."),
        ("Item received", "The item for return {number} has reached the store. Your refund is on its way.")),
    "return_refunded": K("banknote", "success", "high",
        ("Pul qaytarildi", "{number} qaytarish bo'yicha {amount} so'm qaytarildi."),
        ("Деньги возвращены", "По возврату {number} возвращено {amount} сум."),
        ("Refund issued", "{amount} UZS has been refunded for return {number}.")),
    "cancellation_requested": K("clock", "info", "normal",
        ("Bekor qilish so'rovi yuborildi", "{order} buyurtmasini bekor qilish so'rovingiz do'konga yuborildi."),
        ("Запрос на отмену отправлен", "Ваш запрос на отмену заказа {order} отправлен в магазин."),
        ("Cancellation requested", "Your request to cancel order {order} has been sent to the store.")),
    "cancellation_approved": K("circle-check", "success", "normal",
        ("Bekor qilish tasdiqlandi", "{order} buyurtmasini bekor qilish so'rovingiz tasdiqlandi."),
        ("Отмена одобрена", "Ваш запрос на отмену заказа {order} одобрен."),
        ("Cancellation approved", "Your request to cancel order {order} has been approved.")),
    "cancellation_completed": K("circle-check", "success", "high",
        ("Mahsulotlar bekor qilindi", "{order} buyurtmangizdagi ayrim mahsulotlar bekor qilindi. Qolganlari yetkazib beriladi."),
        ("Часть товаров отменена", "Часть товаров в заказе {order} отменена. Остальное будет доставлено."),
        ("Items cancelled", "Some items in your order {order} were cancelled. The rest will be delivered.")),
    "cancellation_rejected": K("circle-x", "danger", "high",
        ("Bekor qilish rad etildi", "{order} buyurtmasini bekor qilish so'rovingiz rad etildi. Sabab: {reason}"),
        ("Отмена отклонена", "Ваш запрос на отмену заказа {order} отклонён. Причина: {reason}"),
        ("Cancellation rejected", "Your request to cancel order {order} was rejected. Reason: {reason}")),
    # ---- loyalty
    "coins_earned": K("coins", "warning", "normal",
        ("+{coins} coin hisobingizga tushdi", "{order} buyurtmasi uchun {percent}% cashback. Balans: {balance} coin."),
        ("+{coins} коинов зачислено", "Кэшбэк {percent}% за заказ {order}. Баланс: {balance} коинов."),
        ("+{coins} coins credited", "{percent}% cashback for order {order}. Balance: {balance} coins.")),
    "coins_earned_pos": K("coins", "warning", "normal",
        ("+{coins} coin hisobingizga tushdi", "Do'kondagi xaridingiz ({order}) uchun {percent}% cashback. Balans: {balance} coin."),
        ("+{coins} коинов зачислено", "Кэшбэк {percent}% за покупку в магазине ({order}). Баланс: {balance} коинов."),
        ("+{coins} coins credited", "{percent}% cashback for your in-store purchase ({order}). Balance: {balance} coins.")),
    "tier_up": K("trophy", "violet", "high",
        ("Tabriklaymiz! Siz {tier} darajasidasiz", "Endi har bir xariddan {percent}% coin qaytadi."),
        ("Поздравляем! Ваш уровень — {tier}", "Теперь с каждой покупки возвращается {percent}% коинами."),
        ("Congratulations! You reached {tier}", "You now get {percent}% back in coins on every purchase.")),
    "tier_changed": K("crown", "violet", "normal",
        ("Darajangiz yangilandi: {tier}", "Har bir xariddan {percent}% coin qaytadi."),
        ("Ваш уровень обновлён: {tier}", "С каждой покупки возвращается {percent}% коинами."),
        ("Your tier was updated: {tier}", "You get {percent}% back in coins on every purchase.")),
    "referral_bonus": K("gift", "success", "normal",
        ("+{coins} coin taklif bonusi", "Siz taklif qilgan do'stingiz birinchi xaridini qildi. Balans: {balance} coin."),
        ("+{coins} коинов за приглашение", "Приглашённый вами друг совершил первую покупку. Баланс: {balance} коинов."),
        ("+{coins} coins referral bonus", "The friend you invited made their first purchase. Balance: {balance} coins.")),
    "welcome_bonus": K("gift", "success", "normal",
        ("Xush kelibsiz bonusi: +{coins} coin", "Do'stingiz taklifi bilan qilgan birinchi xaridingiz uchun. Balans: {balance} coin."),
        ("Приветственный бонус: +{coins} коинов", "За первую покупку по приглашению друга. Баланс: {balance} коинов."),
        ("Welcome bonus: +{coins} coins", "For your first purchase via a friend's invite. Balance: {balance} coins.")),
    "coins_granted": K("coins", "success", "normal",
        ("+{coins} coin sovg'a", "{note}Balans: {balance} coin."),
        ("+{coins} коинов в подарок", "{note}Баланс: {balance} коинов."),
        ("+{coins} bonus coins", "{note}Balance: {balance} coins.")),
    "coins_deducted": K("coins", "neutral", "low",
        ("Balansingizdan {coins} coin yechildi", "{note}Balans: {balance} coin."),
        ("Списано {coins} коинов", "{note}Баланс: {balance} коинов."),
        ("{coins} coins deducted", "{note}Balance: {balance} coins.")),
    "coins_expiring": K("hourglass", "warning", "normal",
        ("{coins} coin {date} kuni kuyadi", "Ularni keyingi xaridingizda ishlating."),
        ("{coins} коинов сгорят {date}", "Используйте их в следующей покупке."),
        ("{coins} coins expire on {date}", "Use them on your next purchase.")),
    "tier_at_risk": K("shield-alert", "warning", "high",
        ("{tier} darajangizni saqlab qoling", "{date} gacha yana {amount} so'mlik xarid qiling — aks holda {percent}% keshbek {lower} darajasiga tushadi."),
        ("Сохраните уровень {tier}", "Совершите покупки ещё на {amount} сум до {date} — иначе кэшбэк {percent}% снизится до уровня {lower}."),
        ("Keep your {tier} level", "Shop for {amount} UZS more by {date} — otherwise your {percent}% cashback drops to {lower}.")),
    # ---- marketing
    "promo_code": K("ticket-percent", "primary", "normal",
        ("Yangi promokod: {code}", "{discount} chegirma{until}. Buyurtma berishda kodni kiriting."),
        ("Новый промокод: {code}", "Скидка {discount}{until}. Введите код при оформлении заказа."),
        ("New promo code: {code}", "{discount} off{until}. Enter the code at checkout.")),
    "campaign": K("sparkles", "violet", "normal",
        ("Aksiya: {name}", "{discount} chegirma{until}. Shoshiling!"),
        ("Акция: {name}", "Скидка {discount}{until}. Успейте!"),
        ("Sale: {name}", "{discount} off{until}. Don't miss it!")),
    "welcome": K("sparkles", "primary", "low",
        ("{brand}'ga xush kelibsiz!", "Har bir xariddan coin yig'ing va ularni keyingi buyurtmalarda ishlating."),
        ("Добро пожаловать в {brand}!", "Копите коины с каждой покупки и оплачивайте ими следующие заказы."),
        ("Welcome to {brand}!", "Earn coins on every purchase and spend them on your next orders.")),
    "announcement": K("megaphone", "primary", "normal", ("{title}", "{body}"), ("{title}", "{body}"), ("{title}", "{body}")),
    # ---- chat
    "chat_message": K("message-circle", "info", "normal",
        ("{sender}: yangi xabar", "{preview}"),
        ("{sender}: новое сообщение", "{preview}"),
        ("{sender}: new message", "{preview}")),
    "chat_rating": K("star", "success", "normal",
        ("Suhbatimizni baholang", "Qo'llab-quvvatlash xizmatimizdan qoniqdingizmi? 1–5 yulduz bilan baholang — bu bizga yaxshilanishga yordam beradi."),
        ("Оцените наш чат", "Довольны ли вы поддержкой? Поставьте оценку от 1 до 5 звёзд — это помогает нам стать лучше."),
        ("Rate our chat", "Happy with our support? Rate it 1–5 stars — it helps us get better.")),
}


class _Safe(dict):
    def __missing__(self, key):  # a missing placeholder renders empty instead of raising
        return ""


def render(kind: str, ctx: dict) -> dict:
    spec = KINDS[kind]
    from apps.platform.infrastructure.branding import brand_name

    data = _Safe({"brand": brand_name(), **{k: ("" if v is None else v) for k, v in ctx.items()}})
    out = {}
    for lang in LANGS:
        title, body = getattr(spec, lang)
        per_lang = _Safe(data)
        for key in ("title", "body", "note", "until", "discount", "method", "product", "days_text"):  # per-language overrides: ctx["i18n"]["ru"]["until"]
            v = ((ctx.get("i18n") or {}).get(lang) or {}).get(key)
            if v is not None:
                per_lang[key] = v
        out[lang] = {"title": title.format_map(per_lang)[:150], "body": body.format_map(per_lang)}
    return out


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def notify(user_id, kind: str, ctx: dict | None = None, *, link: str = "", dedupe_key: str | None = None,
           telegram: bool = True, priority: str | None = None) -> None:
    """Queues one inbox notification (and optionally a Telegram message) for after the current transaction commits."""
    if not user_id or kind not in KINDS:
        return
    ctx = dict(ctx or {})

    def _run() -> None:
        try:
            created = create_now(user_id, kind, ctx, link=link, dedupe_key=dedupe_key, priority=priority)
            if created and telegram:
                from apps.notifications.infrastructure.tasks import deliver_telegram_notification

                try:
                    deliver_telegram_notification.delay(str(created))
                except Exception:  # noqa: BLE001 - broker down: send inline, still best effort
                    send_telegram(created)
        except Exception:  # noqa: BLE001 - a notification must never break the business action that triggered it
            logger.exception("notify: %s for %s failed", kind, user_id)

    transaction.on_commit(_run)


def create_now(user_id, kind: str, ctx: dict, *, link: str = "", dedupe_key: str | None = None, priority: str | None = None) -> uuid.UUID | None:
    """Writes the inbox row immediately. Returns its id, or None when the dedupe key was already used."""
    from apps.notifications.infrastructure.models import NotificationModel

    spec = KINDS[kind]
    texts = render(kind, ctx)
    if dedupe_key and NotificationModel.objects.filter(dedupe_key=dedupe_key).exists():
        return None
    try:
        with transaction.atomic():
            row = NotificationModel.objects.create(
                recipient_id=user_id, notification_type=_type_for(kind), priority=priority or spec.priority,
                title=texts["uz"]["title"], body=texts["uz"]["body"] or " ", template_key=kind[:100],
                kind=kind, link=link[:255], i18n=texts, dedupe_key=dedupe_key,
            )
    except IntegrityError:
        return None  # lost a race on the same dedupe key -- already notified
    invalidate()
    return row.id


def _type_for(kind: str) -> str:
    return "promotional" if kind in ("promo_code", "campaign", "announcement") else "system" if kind == "welcome" else "transactional"


def invalidate() -> None:
    try:
        from apps.notifications.infrastructure.event_handlers import invalidate_notification_cache_group

        for group in ("notification_list", "notification_statistics"):
            invalidate_notification_cache_group(group)
    except Exception:  # noqa: BLE001 - cache down never blocks a notification
        pass


def telegram_text(row, lang: str) -> str:
    from django.utils.html import escape

    t = (row.i18n or {}).get(lang) or {"title": row.title, "body": row.body}
    body = t.get("html") or escape(t["body"])  # `html` is already Telegram-sanitized (dashboard RichText editor)
    return f"<b>{escape(t['title'])}</b>\n\n{body}".strip()


def telegram_keyboard(row, lang: str) -> list:
    from django.conf import settings

    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if not (row.link and base.startswith("https://")):  # Telegram only accepts https URL buttons
        return []
    label = {"uz": "🌐 Ochish", "ru": "🌐 Открыть", "en": "🌐 Open"}[lang]
    return [[{"text": label, "url": f"{base}{row.link}"}]]


def telegram_enabled_for(user_id, notification_type: str) -> bool:
    """The customer's own Telegram preference for this notification type (default: on)."""
    from apps.notifications.infrastructure.models import NotificationPreferenceModel

    disabled = NotificationPreferenceModel.objects.filter(user_id=user_id).values_list("disabled_combinations", flat=True).first() or []
    return ["telegram", notification_type] not in [list(pair) for pair in disabled]


def send_telegram(notification_id) -> bool:
    """Sends one stored notification to the recipient's Telegram private chat and records the delivery. Idempotent."""
    from apps.identity.infrastructure.models import User
    from apps.notifications.infrastructure import composition
    from apps.notifications.infrastructure.models import NotificationDeliveryModel, NotificationModel

    row = NotificationModel.objects.filter(id=notification_id).first()
    if row is None or row.deliveries.filter(channel="telegram").exists():
        return False
    user = User.objects.filter(id=row.recipient_id).only("telegram_user_id", "language").first()
    if user is None or not user.telegram_user_id:
        return False
    if not telegram_enabled_for(row.recipient_id, row.notification_type):
        return False  # the customer turned this category off in their settings; the inbox row still exists
    lang = user.language if user.language in LANGS else "uz"
    now = timezone.now()
    try:
        ref = composition.build_telegram_gateway().send_message_with_keyboard(str(user.telegram_user_id), telegram_text(row, lang), telegram_keyboard(row, lang))
    except Exception as exc:  # noqa: BLE001 - recorded as a failed delivery, visible in the admin
        NotificationDeliveryModel.objects.create(notification=row, channel="telegram", status="failed", attempted_at=now, failed_at=now, failure_reason=str(exc)[:500])
        return False
    NotificationDeliveryModel.objects.create(notification=row, channel="telegram", status="sent", attempted_at=now, delivered_at=now, provider_reference=str(ref or "")[:255])
    return True


# --------------------------------------------------------------------------- broadcasts


def audience_queryset(audience: str, target: str = ""):
    """The customers a broadcast reaches. Blocked accounts never receive it."""
    from datetime import timedelta

    from apps.identity.infrastructure.models import User

    qs = User.objects.exclude(status="blocked")
    if audience == "phone":
        digits = "".join(ch for ch in target if ch.isdigit())
        return qs.filter(phone_number__endswith=digits[-9:]) if len(digits) >= 9 else qs.none()
    if audience == "active":
        return qs.filter(status="active")
    if audience == "telegram":
        return qs.filter(telegram_user_id__isnull=False)
    if audience == "new":
        return qs.filter(created_at__gte=timezone.now() - timedelta(days=30))
    if audience == "buyers":
        from apps.ordering.infrastructure.models import OrderModel
        from apps.pos.infrastructure.models import SaleModel

        online = OrderModel.objects.filter(status__in=("delivered", "completed")).values("customer_id")
        pos = SaleModel.objects.filter(status="completed", customer_id__isnull=False).values("customer_id")
        return qs.filter(models_q_in(online, pos))
    if audience == "subscribers":
        from apps.notifications.infrastructure.models import NewsSubscription

        return qs.filter(id__in=NewsSubscription.objects.filter(is_active=True).values("user_id"))
    if audience == "segment":
        from apps.platform.infrastructure import segments

        return qs.filter(id__in=segments.members(target)) if target in segments.SEGMENTS else qs.none()
    if audience == "tier":
        from apps.loyalty.infrastructure import services as loyalty

        return qs.filter(id__in=_tier_members(target, loyalty)) if target else qs.none()
    return qs


def models_q_in(*subqueries):
    from django.db.models import Q

    q = Q()
    for sub in subqueries:
        q |= Q(id__in=sub)
    return q


def _tier_members(tier_slug: str, loyalty) -> list:
    from apps.loyalty.infrastructure.models import Wallet

    out = []
    for user_id in Wallet.objects.values_list("user_id", flat=True).iterator():
        try:
            tier = loyalty.summary(user_id).current_tier
        except Exception:  # noqa: BLE001
            continue
        if tier is not None and getattr(tier, "slug", "") == tier_slug:
            out.append(user_id)
    return out


def run_broadcast(broadcast_id) -> dict:
    """Fans a broadcast out: bulk in-app rows for the whole audience, then Telegram one by one (rate-limited)."""
    import time

    from apps.notifications.infrastructure.models import NotificationBroadcast, NotificationModel

    b = NotificationBroadcast.objects.filter(id=broadcast_id).first()
    if b is None or b.status in ("sending", "sent"):
        return {"skipped": True}
    NotificationBroadcast.objects.filter(id=b.id).update(status="sending")
    try:
        texts = b.i18n or render(b.kind, {"title": b.title, "body": b.body})
        spec = KINDS.get(b.kind, KINDS["announcement"])
        user_ids = list(audience_queryset(b.audience, b.target).values_list("id", flat=True))
        rows = [
            NotificationModel(
                recipient_id=uid, notification_type=_type_for(b.kind), priority=b.priority or spec.priority,
                title=texts["uz"]["title"][:150], body=texts["uz"]["body"] or " ", template_key=b.kind, kind=b.kind,
                link=b.link, i18n=texts, broadcast=b, dedupe_key=f"broadcast:{b.id}:{uid}",
            )
            for uid in user_ids
        ]
        if b.send_in_app or b.send_telegram:
            NotificationModel.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)
            invalidate()
        sent = failed = 0
        if b.send_telegram:
            from apps.notifications.infrastructure.models import NotificationPreferenceModel

            # Customers who turned this category off in their settings aren't messaged (nor counted as failures).
            opted_out = NotificationPreferenceModel.objects.filter(disabled_combinations__contains=[["telegram", _type_for(b.kind)]]).values("user_id")
            ids = (
                NotificationModel.objects.filter(broadcast=b, recipient_id__in=audience_queryset(b.audience, b.target).filter(telegram_user_id__isnull=False).values("id"))
                .exclude(recipient_id__in=opted_out)
                .values_list("id", flat=True)
            )
            for nid in ids.iterator():
                if send_telegram(nid):
                    sent += 1
                else:
                    failed += 1
                time.sleep(0.04)  # stay under Telegram's ~30 messages/second bot limit
            if not b.send_in_app:  # Telegram-only: the rows existed just to carry the delivery log -- hide them from the inbox
                NotificationModel.objects.filter(broadcast=b).update(status="cancelled")
        NotificationBroadcast.objects.filter(id=b.id).update(status="sent", recipients=len(user_ids), telegram_sent=sent, telegram_failed=failed, finished_at=timezone.now())
        return {"recipients": len(user_ids), "telegram_sent": sent, "telegram_failed": failed}
    except Exception:
        NotificationBroadcast.objects.filter(id=b.id).update(status="failed", finished_at=timezone.now())
        logger.exception("broadcast %s failed", broadcast_id)
        raise


def start_broadcast(broadcast) -> None:
    """Runs the broadcast on a Celery worker after commit (inline if the broker is down)."""

    def _go() -> None:
        from apps.notifications.infrastructure.tasks import run_notification_broadcast

        try:
            run_notification_broadcast.delay(str(broadcast.id))
        except Exception:  # noqa: BLE001
            run_broadcast(broadcast.id)

    transaction.on_commit(_go)
