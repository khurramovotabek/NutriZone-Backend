"""
What the free advisor knows: shop facts read live from the database (branches, contacts, payment methods, coins)
and short, safe usage guidance per product kind. Every text exists in uz / ru / en.
"""
from __future__ import annotations

T = {
    "greet": {
        "uz": "Assalomu alaykum! Men NutriZone maslahatchisiman 💪\n\nMaqsadingizga mos sport ozuqasini tanlashda yordam beraman. Masalan yozing:\n• **180 sm, 80 kg, 25 yosh, massa olmoqchiman**\n• **Kreatin qanday ichiladi?**\n• **Ozish uchun nima tavsiya qilasiz?**",
        "ru": "Здравствуйте! Я консультант NutriZone 💪\n\nПомогу подобрать спортивное питание под вашу цель. Например, напишите:\n• **180 см, 80 кг, 25 лет, хочу набрать массу**\n• **Как принимать креатин?**\n• **Что посоветуете для похудения?**",
        "en": "Hi! I'm the NutriZone advisor 💪\n\nI'll help you pick sports nutrition for your goal. For example, type:\n• **180 cm, 80 kg, 25 years, I want to build muscle**\n• **How do I take creatine?**\n• **What do you recommend for fat loss?**",
    },
    "thanks": {"uz": "Arzimaydi! Yana savolingiz bo'lsa, yozing 🙂", "ru": "Пожалуйста! Если будут вопросы — пишите 🙂", "en": "You're welcome! Ask me anything else 🙂"},
    "ask": {
        "uz": "Sizga aniq tavsiya berishim uchun yana bir nechta ma'lumot kerak: {fields}.\n\nBittada yozishingiz mumkin, masalan: **175 sm, 72 kg, 28 yosh, ozish, haftada 3 marta**.",
        "ru": "Чтобы дать точную рекомендацию, нужно ещё: {fields}.\n\nМожно одним сообщением, например: **175 см, 72 кг, 28 лет, похудение, 3 раза в неделю**.",
        "en": "To give you an accurate recommendation I still need: {fields}.\n\nOne message is fine, e.g.: **175 cm, 72 kg, 28 years, fat loss, 3 times a week**.",
    },
    "fields": {
        "uz": {"height": "bo'yingiz (sm)", "weight": "vazningiz (kg)", "age": "yoshingiz", "goal": "maqsadingiz (massa / ozish / chidamlilik / salomatlik)"},
        "ru": {"height": "рост (см)", "weight": "вес (кг)", "age": "возраст", "goal": "цель (масса / похудение / выносливость / здоровье)"},
        "en": {"height": "your height (cm)", "weight": "weight (kg)", "age": "age", "goal": "goal (muscle / fat loss / endurance / health)"},
    },
    "goal_name": {
        "uz": {"muscle": "mushak massasi", "weight_loss": "ozish", "endurance": "chidamlilik", "health": "salomatlik"},
        "ru": {"muscle": "набор массы", "weight_loss": "похудение", "endurance": "выносливость", "health": "здоровье"},
        "en": {"muscle": "muscle gain", "weight_loss": "fat loss", "endurance": "endurance", "health": "health"},
    },
    "kind_name": {
        "uz": {"protein": "Protein", "creatine": "Kreatin", "gainer": "Geyner", "bcaa": "BCAA / aminokislotalar", "carnitine": "L-karnitin", "vitamin": "Multivitamin", "omega": "Omega-3", "collagen": "Kollagen", "preworkout": "Pre-workout"},
        "ru": {"protein": "Протеин", "creatine": "Креатин", "gainer": "Гейнер", "bcaa": "BCAA / аминокислоты", "carnitine": "L-карнитин", "vitamin": "Мультивитамины", "omega": "Омега-3", "collagen": "Коллаген", "preworkout": "Предтренировочный"},
        "en": {"protein": "Protein", "creatine": "Creatine", "gainer": "Mass gainer", "bcaa": "BCAA / amino acids", "carnitine": "L-carnitine", "vitamin": "Multivitamin", "omega": "Omega-3", "collagen": "Collagen", "preworkout": "Pre-workout"},
    },
    "why": {
        "uz": {"protein": "kunlik oqsil me'yorini qulay to'ldiradi", "creatine": "kuch va massa uchun eng ko'p isbotlangan qo'shimcha", "gainer": "kaloriya yetishmasa vazn olishga yordam beradi",
               "bcaa": "uzoq mashg'ulotda mushakni himoya qiladi", "carnitine": "kaloriya defitsiti bilan birga yog' yoqishga yordamchi", "vitamin": "parhezda vitamin yetishmovchiligining oldini oladi",
               "omega": "yurak, bo'g'im va tiklanish uchun", "collagen": "bo'g'im, teri va paylar uchun", "preworkout": "mashg'ulot oldidan energiya"},
        "ru": {"protein": "удобно добрать суточную норму белка", "creatine": "самая доказанная добавка для силы и массы", "gainer": "помогает набрать вес при нехватке калорий",
               "bcaa": "защищает мышцы на долгих тренировках", "carnitine": "помощник в сжигании жира при дефиците калорий", "vitamin": "предотвращает дефицит витаминов на диете",
               "omega": "для сердца, суставов и восстановления", "collagen": "для суставов, кожи и связок", "preworkout": "энергия перед тренировкой"},
        "en": {"protein": "an easy way to reach your daily protein", "creatine": "the best-proven supplement for strength and size", "gainer": "helps you gain weight when calories fall short",
               "bcaa": "protects muscle during long sessions", "carnitine": "a helper for fat loss alongside a calorie deficit", "vitamin": "prevents vitamin gaps while dieting",
               "omega": "for heart, joints and recovery", "collagen": "for joints, skin and tendons", "preworkout": "energy before training"},
    },
    "usage": {
        "uz": {"protein": "Kuniga 1–2 porsiya (20–40 g oqsil): biri mashg'ulotdan keyin, qolgani ovqatlar orasida. 250–300 ml suv yoki sut bilan aralashtiring.",
               "creatine": "Har kuni 3–5 g, dam olish kunlari ham. Vaqti muhim emas — eng muhimi har kuni. Yetarli suv iching.",
               "gainer": "Kuniga 1–2 porsiya ovqatlar orasida yoki mashg'ulotdan keyin. Ovqat o'rnini bosmaydi.",
               "bcaa": "Mashg'ulot oldidan yoki davomida 5–10 g, suv bilan.",
               "carnitine": "Mashg'ulotdan 20–30 daqiqa oldin 1–2 g. Natija faqat kaloriya defitsiti va mashqlar bilan.",
               "vitamin": "Kuniga 1 marta ovqat bilan, qadoqdagi dozada.", "omega": "Kuniga 1–3 kapsula ovqat bilan.",
               "collagen": "Kuniga 5–10 g, ertalab yoki kechqurun.", "preworkout": "Mashg'ulotdan 20–30 daqiqa oldin 1 porsiya. Kechqurun ichmang (kofein)."},
        "ru": {"protein": "1–2 порции в день (20–40 г белка): одна после тренировки, остальные между приёмами пищи. Смешивайте с 250–300 мл воды или молока.",
               "creatine": "3–5 г каждый день, включая дни отдыха. Время не важно — важна регулярность. Пейте достаточно воды.",
               "gainer": "1–2 порции в день между едой или после тренировки. Не заменяет еду.",
               "bcaa": "5–10 г до или во время тренировки, с водой.",
               "carnitine": "1–2 г за 20–30 минут до тренировки. Работает только при дефиците калорий и нагрузке.",
               "vitamin": "1 раз в день с едой, по дозировке на упаковке.", "omega": "1–3 капсулы в день с едой.",
               "collagen": "5–10 г в день, утром или вечером.", "preworkout": "1 порция за 20–30 минут до тренировки. Не принимайте вечером (кофеин)."},
        "en": {"protein": "1–2 servings a day (20–40 g protein): one after training, the rest between meals. Mix with 250–300 ml of water or milk.",
               "creatine": "3–5 g every day, rest days included. Timing doesn't matter — consistency does. Drink enough water.",
               "gainer": "1–2 servings a day between meals or after training. Not a meal replacement.",
               "bcaa": "5–10 g before or during training, with water.",
               "carnitine": "1–2 g 20–30 minutes before training. Works only with a calorie deficit and exercise.",
               "vitamin": "Once a day with food, at the dose on the label.", "omega": "1–3 capsules a day with food.",
               "collagen": "5–10 g a day, morning or evening.", "preworkout": "1 serving 20–30 minutes before training. Avoid in the evening (caffeine)."},
    },
    "disclaimer": {
        "uz": "_Bu umumiy sport ovqatlanishi maslahati, tibbiy tavsiya emas. Kasalligingiz bo'lsa yoki dori qabul qilsangiz, shifokor bilan maslahatlashing._",
        "ru": "_Это общий совет по спортивному питанию, а не медицинская рекомендация. При заболеваниях или приёме лекарств проконсультируйтесь с врачом._",
        "en": "_General sports-nutrition guidance, not medical advice. If you have a condition or take medication, check with your doctor._",
    },
    "nothing": {
        "uz": "Afsuski, \"{q}\" bo'yicha mos mahsulot topmadim. Boshqacha yozib ko'ring (masalan: protein, kreatin, vitamin) yoki maqsadingizni ayting — men tanlab beraman.",
        "ru": "К сожалению, по запросу «{q}» ничего не нашлось. Попробуйте иначе (например: протеин, креатин, витамины) или назовите цель — я подберу.",
        "en": "Sorry, I couldn't find anything for \"{q}\". Try other words (e.g. protein, creatine, vitamins) or tell me your goal and I'll pick for you.",
    },
    "found": {"uz": "Mana mos mahsulotlar:", "ru": "Вот что подходит:", "en": "Here's what fits:"},
    "operator": {
        "uz": "Operator bilan bog'lanish: {contacts}\n\nYoki saytdagi **Chat** bo'limiga yozing — xodimlarimiz javob beradi.",
        "ru": "Связаться с оператором: {contacts}\n\nИли напишите в раздел **Чат** на сайте — сотрудники ответят.",
        "en": "Talk to a person: {contacts}\n\nOr write in the **Chat** section of the site — our team will reply.",
    },
}

FAQ = {
    "faq_delivery": {
        "uz": "🚚 **Yetkazib berish**\nBuyurtmani saytda yoki Telegram botda rasmiylashtirasiz, manzilni xaritada belgilaysiz. Yetkazish narxi va muddati manzilga qarab rasmiylashtirishda ko'rsatiladi.\n\n🏪 Shoshilinch bo'lsa — **do'kondan olib ketish**ni tanlang: buyurtma tayyor bo'lgach xabar keladi.",
        "ru": "🚚 **Доставка**\nОформите заказ на сайте или в Telegram-боте и отметьте адрес на карте. Стоимость и срок доставки показываются при оформлении в зависимости от адреса.\n\n🏪 Если срочно — выберите **самовывоз из магазина**: придёт уведомление, когда заказ готов.",
        "en": "🚚 **Delivery**\nPlace your order on the site or in the Telegram bot and pin your address on the map. The delivery price and time are shown at checkout for your address.\n\n🏪 In a hurry? Choose **in-store pickup** — you'll be notified when it's ready.",
    },
    "faq_original": {
        "uz": "✅ **100% original kafolati**\nMahsulotlarni faqat rasmiy distribyutorlardan olamiz va har bir partiya hujjatlarini saqlaymiz. Istalgan mahsulot sertifikatini chatda so'rashingiz mumkin. Qadoqdagi tekshiruv kodini ishlab chiqaruvchi saytida tekshirish ham mumkin.",
        "ru": "✅ **Гарантия 100% оригинала**\nМы закупаем товар только у официальных дистрибьюторов и храним документы на каждую партию. Сертификат на любой товар можно запросить в чате. Код проверки на упаковке можно проверить на сайте производителя.",
        "en": "✅ **100% original guarantee**\nWe buy only from official distributors and keep the documents for every batch. Ask for any product's certificate in the chat, and verify the code on the pack on the manufacturer's site.",
    },
    "faq_returns": {
        "uz": "↩️ **Qaytarish**\nBuyurtma sahifasida (Buyurtmalarim) qaytarish so'rovini yuborishingiz mumkin. Ochilmagan, qadoqi buzilmagan mahsulot qabul qilinadi; nuqsonli mahsulot almashtiriladi. Savol bo'lsa — chatga yozing.",
        "ru": "↩️ **Возврат**\nЗапрос на возврат можно отправить на странице заказа (Мои заказы). Принимаем невскрытый товар с целой упаковкой; бракованный — обменяем. Вопросы — в чат.",
        "en": "↩️ **Returns**\nRequest a return on the order page (My orders). Unopened products with intact packaging are accepted; defective items are exchanged. Questions — write in the chat.",
    },
    "faq_order": {
        "uz": "📦 Buyurtmangiz holatini **Buyurtmalarim** sahifasida yoki Telegram botdagi **Buyurtmalarim** tugmasi orqali ko'rasiz. Har bir o'zgarish haqida bildirishnoma keladi.",
        "ru": "📦 Статус заказа — на странице **Мои заказы** или по кнопке **Мои заказы** в Telegram-боте. О каждом изменении приходит уведомление.",
        "en": "📦 Check your order on the **My orders** page or with the **My orders** button in the Telegram bot. You're notified of every change.",
    },
}


def _place_in(text: str, branches: list) -> str:
    """The city / district the shopper named, if a branch is there ("Samarqandda do'kon bormi?" -> "Samarqand")."""
    from apps.assistant.infrastructure.tools import _norm_place

    said = _norm_place(text)
    places = {p for b in branches for p in (b.get("address") or "").split(", ") if p}
    for place in sorted(places, key=len, reverse=True):
        stem = _norm_place(place)[:6]
        if len(stem) >= 4 and stem in said:
            return place
    return ""


def stores_text(locale: str, text: str = "") -> str:
    from apps.assistant.infrastructure.tools import get_store_info

    branches = get_store_info({}, locale).get("branches", [])
    head = {"uz": "🏪 **Do'konlarimiz**", "ru": "🏪 **Наши магазины**", "en": "🏪 **Our stores**"}[locale]
    if not branches:
        return head + "\n" + {"uz": "Hozircha filial ma'lumoti yo'q.", "ru": "Пока нет данных о филиалах.", "en": "No branch details yet."}[locale]
    place = _place_in(text, branches)
    if place:
        branches = [b for b in branches if place in (b.get("address") or "")] or branches
        head = {"uz": f"🏪 **{place}dagi do'konlarimiz**", "ru": f"🏪 **Наши магазины: {place}**", "en": f"🏪 **Our stores in {place}**"}[locale]
    lines = []
    for b in branches[: 6 if place else 14]:
        bits = [", ".join(b.get("phones") or [])]
        if place or len(branches) <= 6:
            bits.append(b.get("landmark") or "")
            if b.get("map_url"):
                bits.append("📍 " + b["map_url"])
        extra = " · ".join(x for x in bits if x)
        lines.append(f"• **{b['name']}** — {b.get('address', '')}" + (f"\n  {extra}" if extra else ""))
    tail = {"uz": "\n\nShahar yoki tuman nomini yozing — o'sha yerdagi filial manzili va xaritasini yuboraman. Barchasi xaritada: **Do'konlar** sahifasi.",
            "ru": "\n\nНапишите город или район — пришлю адрес и карту ближайшего филиала. Все на карте: страница **Магазины**.",
            "en": "\n\nTell me your city or district and I'll send the nearest branch with a map link. All on the map: the **Stores** page."}[locale]
    return head + "\n" + "\n".join(lines) + ("" if place else tail)


def catalog_text(kind: str, locale: str) -> str:
    """Brands / flavours the shop actually carries (with product counts), straight from the catalogue."""
    from apps.assistant.infrastructure.tools import browse_catalog

    items = [i for i in browse_catalog({"kind": kind}, locale)["items"] if i["products"]]
    head = {
        "brands": {"uz": "🏷 **Bizdagi brendlar**", "ru": "🏷 **Бренды в наличии**", "en": "🏷 **Brands we carry**"},
        "flavours": {"uz": "🍫 **Mavjud ta'mlar**", "ru": "🍫 **Доступные вкусы**", "en": "🍫 **Flavours available**"},
    }[kind][locale]
    if not items:
        return head + "\n" + {"uz": "Hozircha ro'yxat bo'sh.", "ru": "Пока пусто.", "en": "Nothing yet."}[locale]
    body = "\n".join(f"• {i['name']} — {i['products']}" for i in items[:20])
    tail = {"uz": "\n\nQaysi biri qiziq? Nomini yozing — mahsulotlarni ko'rsataman.", "ru": "\n\nЧто интересно? Напишите название — покажу товары.",
            "en": "\n\nWhich one? Type its name and I'll show the products."}[locale]
    return head + "\n" + body + tail


def payment_text(locale: str) -> str:
    from apps.payment.infrastructure.models import PaymentProviderConfig

    names = {"payme": "Payme", "click": "Click", "uzum": "Uzum Bank", "uzcard": "Uzcard", "humo": "Humo", "cash": None}
    online = [names.get(p) or p for p in PaymentProviderConfig.objects.filter(is_enabled=True).order_by("sort_order").values_list("provider", flat=True) if p != "cash"]
    online = [x for x in online if x]
    cash = {"uz": "naqd pul (yetkazib berishda yoki do'konda)", "ru": "наличные (при доставке или в магазине)", "en": "cash (on delivery or in store)"}[locale]
    head = {"uz": "💳 **To'lov usullari**", "ru": "💳 **Способы оплаты**", "en": "💳 **Payment methods**"}[locale]
    items = ([", ".join(online)] if online else []) + [cash]
    coins = {"uz": "Shuningdek, to'plangan **NutriZone coin** bilan qisman to'lash mumkin.", "ru": "Также можно частично оплатить накопленными **NutriZone коинами**.", "en": "You can also pay part of the order with your **NutriZone coins**."}[locale]
    return head + "\n" + "\n".join(f"• {x}" for x in items) + "\n\n" + coins


def loyalty_text(locale: str) -> str:
    from apps.loyalty.infrastructure.models import LoyaltyTier

    tiers = list(LoyaltyTier.objects.filter(is_active=True).order_by("min_spend").values_list("name", "percent"))
    head = {"uz": "🪙 **NutriZone coin**", "ru": "🪙 **NutriZone коины**", "en": "🪙 **NutriZone coins**"}[locale]
    body = {"uz": "Har bir xariddan coin olasiz va keyingi buyurtmalarda ular bilan to'laysiz. Qancha ko'p xarid qilsangiz, daraja shuncha yuqori:",
            "ru": "За каждую покупку начисляются коины, которыми можно оплачивать следующие заказы. Чем больше покупок, тем выше уровень:",
            "en": "Every purchase earns coins you can spend on later orders. The more you buy, the higher your tier:"}[locale]
    levels = "\n".join(f"• {n} — {float(p):g}%" for n, p in tiers[:6])
    tail = {"uz": "\n\nBatafsil: **Bonuslar** sahifasi.", "ru": "\n\nПодробнее: страница **Бонусы**.", "en": "\n\nMore: the **Loyalty** page."}[locale]
    return f"{head}\n{body}\n{levels}{tail}" if levels else f"{head}\n{body}{tail}"


def contacts(locale: str) -> str:
    from apps.platform.infrastructure.models import SiteSettings

    s = SiteSettings.objects.filter(pk=1).first()
    parts = []
    if s and s.support_phone:
        parts.append(f"📞 {s.support_phone}")
    if s and s.telegram_username:
        parts.append(f"✈️ @{s.telegram_username.lstrip('@')}")
    if s and s.working_hours:
        parts.append(f"🕒 {s.working_hours}")
    return "  ·  ".join(parts) or {"uz": "saytdagi Aloqa sahifasi", "ru": "страница Контакты", "en": "the Contact page"}[locale]
