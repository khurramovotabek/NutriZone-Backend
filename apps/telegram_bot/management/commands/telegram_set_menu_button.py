"""
Sets the customer bot's menu button (next to the message field) to open the storefront Mini App (FRONTEND_URL/tg),
Run on startup with the webhook registration; a no-op when FRONTEND_URL isn't HTTPS.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# setChatMenuButton has one label for everyone (no per-language variant); the Mini App itself follows the shopper's language.
MENU_LABEL = "🛍 Do'kon"


class Command(BaseCommand):
    help = "Points the customer bot's menu button at the storefront Mini App (FRONTEND_URL/tg)."

    def handle(self, *args, **options):
        import requests

        from apps.telegram_bot.interfaces.callback_router import mini_app_url

        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN is not configured.")
        url = mini_app_url()
        if not url:
            self.stdout.write("FRONTEND_URL is not an https:// URL -- Mini App menu button not set.")
            return
        base = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
        payload = {"menu_button": {"type": "web_app", "text": MENU_LABEL, "web_app": {"url": url}}}
        response = requests.post(f"{base}/bot{token}/setChatMenuButton", json=payload, timeout=10.0)
        body = response.json() if response.content else {}
        if not body.get("ok"):
            raise CommandError(f"setChatMenuButton failed: {body.get('description') or response.status_code}")
        self.stdout.write(self.style.SUCCESS(f"Mini App menu button set: {url}"))
        self._commands_and_profile(base, token)

    def _commands_and_profile(self, base: str, token: str) -> None:
        """The "/" command list and the bot's profile texts, in each shopper's own Telegram language (uz is the default)."""
        import requests

        for lang, (commands, description, short) in PROFILE.items():
            scope = {} if lang == "uz" else {"language_code": lang}
            calls = [
                ("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in commands], **scope}),
                ("setMyDescription", {"description": description, **scope}),
                ("setMyShortDescription", {"short_description": short, **scope}),
            ]
            for method, payload in calls:
                body = requests.post(f"{base}/bot{token}/{method}", json=payload, timeout=10.0).json()
                if not body.get("ok"):
                    self.stderr.write(f"{method} ({lang}): {body.get('description')}")
        self.stdout.write(self.style.SUCCESS("Bot commands and profile texts set (uz / ru / en)."))


PROFILE = {
    "uz": (
        [("start", "🏠 Boshlash"), ("dokon", "🛍 Do'konni ochish"), ("menu", "☰ Asosiy menyu"), ("savat", "🛒 Savatcha"), ("buyurtmalar", "📦 Buyurtmalarim"),
         ("topish", "🔎 Mahsulotni topib berish"), ("filiallar", "📍 Do'konlar va eng yaqini"), ("yordam", "ℹ️ Yordam"), ("privacy", "📄 Oferta va maxfiylik")],
        "NutriZone — sport ovqatlanishining rasmiy do'koni.\n\n🛍 Mahsulotlarni bot yoki Mini App orqali tanlang\n🔎 Saytda yo'q mahsulotni topib beramiz\n⚡ Kod va parolsiz buyurtma\n🪙 Har xariddan NutriZone Coins\n📦 Buyurtma holati shu chatda",
        "NutriZone — sport ovqatlanishi do'koni. Original mahsulotlar, tez yetkazib berish.",
    ),
    "ru": (
        [("start", "🏠 Начать"), ("shop", "🛍 Открыть магазин"), ("menu", "☰ Главное меню"), ("cart", "🛒 Корзина"), ("orders", "📦 Мои заказы"),
         ("find", "🔎 Найти товар для меня"), ("stores", "📍 Магазины и ближайший"), ("help", "ℹ️ Помощь"), ("privacy", "📄 Оферта и конфиденциальность")],
        "NutriZone — официальный магазин спортивного питания.\n\n🛍 Выбирайте товары в боте или в Mini App\n🔎 Найдём товар, которого нет на сайте\n⚡ Заказ без кодов и паролей\n🪙 NutriZone Coins за каждую покупку\n📦 Статус заказа в этом чате",
        "NutriZone — спортивное питание. Оригинальная продукция, быстрая доставка.",
    ),
    "en": (
        [("start", "🏠 Start"), ("shop", "🛍 Open the shop"), ("menu", "☰ Main menu"), ("cart", "🛒 Cart"), ("orders", "📦 My orders"),
         ("find", "🔎 Find a product for me"), ("stores", "📍 Stores and the nearest"), ("help", "ℹ️ Help"), ("privacy", "📄 Terms & privacy")],
        "NutriZone — the official sport nutrition store.\n\n🛍 Shop in the bot or the Mini App\n🔎 We source products we don't list yet\n⚡ Order without codes or passwords\n🪙 NutriZone Coins on every purchase\n📦 Order updates in this chat",
        "NutriZone — sport nutrition. Original products, fast delivery.",
    ),
}
