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
        "uz": "Sizga aniq tavsiya berishim uchun yana bir nechta ma'lumot kerak: {fields}.\n\nBittada yozishingiz mumkin, masalan: **{example}**.",
        "ru": "Чтобы дать точную рекомендацию, нужно ещё: {fields}.\n\nМожно одним сообщением, например: **{example}**.",
        "en": "To give you an accurate recommendation I still need: {fields}.\n\nOne message is fine, e.g.: **{example}**.",
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
    "who": {
        "uz": {"protein": "ovqatdan oqsil yetishmaydigan har bir mashq qiluvchiga — massa olishda ham, ozishda ham", "creatine": "kuch, portlovchi harakat va mushak massasini oshirmoqchi bo'lganlarga",
               "gainer": "ozg'in, tez metabolizmli va ovqatdan yetarli kaloriya ololmaydiganlarga", "bcaa": "och qoringa, uzoq yoki kardio mashg'ulot qiladiganlarga; oqsil yetarli bo'lsa foydasi kichik",
               "carnitine": "kaloriya defitsitida ozayotgan va muntazam kardio qiladiganlarga", "vitamin": "parhezda bo'lganlar va og'ir mashq qiluvchilarga",
               "omega": "baliqni kam yeydigan, bo'g'im va yurak salomatligini o'ylaydiganlarga", "collagen": "bo'g'im va paylariga yuk tushadiganlarga", "preworkout": "mashg'ulotda energiya va diqqat yetishmaydigan sog'lom kattalarga"},
        "ru": {"protein": "всем тренирующимся, кому не хватает белка из еды — и на массе, и на похудении", "creatine": "тем, кто хочет больше силы, взрывной мощи и мышечной массы",
               "gainer": "худощавым, с быстрым обменом, кому не хватает калорий из еды", "bcaa": "тем, кто тренируется натощак, долго или кардио; при достатке белка польза мала",
               "carnitine": "тем, кто худеет в дефиците калорий и регулярно делает кардио", "vitamin": "тем, кто на диете или много тренируется",
               "omega": "тем, кто редко ест рыбу и заботится о суставах и сердце", "collagen": "тем, у кого большая нагрузка на суставы и связки", "preworkout": "здоровым взрослым, которым не хватает энергии и фокуса на тренировке"},
        "en": {"protein": "anyone training who falls short on protein from food -- for both gaining and cutting", "creatine": "anyone after more strength, power and muscle",
               "gainer": "lean, fast-metabolism people who can't eat enough calories", "bcaa": "people training fasted, long or cardio; small benefit if protein is already enough",
               "carnitine": "people cutting in a calorie deficit who do regular cardio", "vitamin": "people dieting or training hard",
               "omega": "people who rarely eat fish and care about joints and heart", "collagen": "people with heavy load on joints and tendons", "preworkout": "healthy adults short on energy and focus in training"},
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


# More product kinds the advisor understands (nlu.CONCEPT_WORDS / nlu.SPECIFIC): name, what it does, who needs it, how to
# take it -- adult doses from ISSN / NIH ODS / EFSA guidance, kept to label-level amounts. Merged into T below.
KINDS = {
    "vitamin_d": {
        "uz": ("D3 vitamini", "suyak, mushak va immunitet uchun; qishda va quyoshda kam bo'lganlarda ko'pincha yetishmaydi",
               "quyoshda kam yuradiganlarga, qishda, qorong'i teri yoki ortiqcha vaznli odamlarga, 50 yoshdan oshganlarga",
               "Odatda kuniga 1000–2000 IU (25–50 mkg), yog'li ovqat bilan. Shifokorsiz kuniga 4000 IU dan oshirmang; aniq doza uchun qondagi 25(OH)D tahlilini topshiring."),
        "ru": ("Витамин D3", "для костей, мышц и иммунитета; зимой и при нехватке солнца его часто не хватает",
               "тем, кто мало бывает на солнце, зимой, при лишнем весе, после 50 лет",
               "Обычно 1000–2000 МЕ (25–50 мкг) в день с жирной едой. Без врача не больше 4000 МЕ в день; точную дозу подскажет анализ 25(OH)D."),
        "en": ("Vitamin D3", "for bones, muscles and immunity; often low in winter and with little sun",
               "people who get little sun, in winter, with higher body weight, over 50",
               "Usually 1000–2000 IU (25–50 mcg) a day with a meal containing fat. Don't exceed 4000 IU a day without a doctor; a 25(OH)D blood test gives the right dose."),
    },
    "vitamin_c": {
        "uz": ("C vitamini", "antioksidant, immunitet va kollagen hosil bo'lishi uchun, temir so'rilishini oshiradi",
               "meva-sabzavotni kam yeydiganlarga, chekuvchilarga, og'ir mashg'ulot va shamollash mavsumida",
               "Kuniga 200–500 mg yetarli, ovqat bilan. 2000 mg dan oshirmang — oshqozon buzilishi va buyrak toshi xavfi."),
        "ru": ("Витамин C", "антиоксидант, для иммунитета и синтеза коллагена, улучшает усвоение железа",
               "тем, кто мало ест овощей и фруктов, курящим, при тяжёлых тренировках и в сезон простуд",
               "Достаточно 200–500 мг в день с едой. Не больше 2000 мг — расстройство желудка и риск камней в почках."),
        "en": ("Vitamin C", "an antioxidant for immunity and collagen, and it boosts iron absorption",
               "people who eat little fruit and veg, smokers, heavy training and cold season",
               "200–500 mg a day with food is plenty. Stay under 2000 mg — stomach upset and kidney-stone risk."),
    },
    "vitamin_b12": {
        "uz": ("B12 vitamini", "qon hosil bo'lishi, asab tizimi va energiya almashinuvi uchun",
               "vegan va vegetarianlarga, 50 yoshdan oshganlarga, metformin yoki oshqozon kislotasini kamaytiruvchi dori ichadiganlarga",
               "Kuniga 250–500 mkg yoki qadoqdagi dozada, ertalab. Ortiqchasi siydik bilan chiqadi, xavfsiz."),
        "ru": ("Витамин B12", "для кроветворения, нервной системы и энергетического обмена",
               "веганам и вегетарианцам, после 50 лет, принимающим метформин или средства от изжоги",
               "250–500 мкг в день или по упаковке, утром. Избыток выводится, это безопасно."),
        "en": ("Vitamin B12", "for blood formation, the nervous system and energy metabolism",
               "vegans and vegetarians, people over 50, anyone on metformin or acid-reducing medication",
               "250–500 mcg a day or the label dose, in the morning. Excess is excreted; it's safe."),
    },
    "magnesium": {
        "uz": ("Magniy", "mushak qisqarishi, uyqu, asab va 300 dan ortiq ferment uchun; terlaganda yo'qotiladi",
               "ko'p terlaydigan sportchilarga, mushak tortishishi, yomon uyqu yoki stressda",
               "Kuniga 200–350 mg, kechqurun ovqat bilan. Glitsinat yoki sitrat shakli yaxshi so'riladi; oksid ich ketishiga sabab bo'lishi mumkin. Buyrak kasalligida shifokorga so'rang."),
        "ru": ("Магний", "для сокращения мышц, сна, нервной системы и сотен ферментов; теряется с потом",
               "спортсменам, которые много потеют, при судорогах, плохом сне и стрессе",
               "200–350 мг в день вечером с едой. Глицинат и цитрат усваиваются лучше, оксид может слабить. При болезнях почек — только с врачом."),
        "en": ("Magnesium", "for muscle contraction, sleep, nerves and hundreds of enzymes; lost in sweat",
               "athletes who sweat a lot, people with cramps, poor sleep or stress",
               "200–350 mg a day in the evening with food. Glycinate and citrate absorb best; oxide can loosen the stool. With kidney disease, ask a doctor."),
    },
    "zinc": {
        "uz": ("Rux (zinc)", "immunitet, teri, gormonlar va tiklanish uchun; terlaganda yo'qotiladi",
               "go'shtni kam yeydiganlarga, ko'p terlaydigan sportchilarga, shamollash boshlanganda",
               "Kuniga 10–25 mg ovqat bilan (och qoringa ko'ngil aynitishi mumkin). Uzoq vaqt kuniga 40 mg dan ko'p ichmang — mis yetishmovchiligiga olib keladi."),
        "ru": ("Цинк", "для иммунитета, кожи, гормонов и восстановления; теряется с потом",
               "тем, кто мало ест мяса, спортсменам с сильным потоотделением, в начале простуды",
               "10–25 мг в день с едой (натощак может тошнить). Долго больше 40 мг в день нельзя — вызывает дефицит меди."),
        "en": ("Zinc", "for immunity, skin, hormones and recovery; lost in sweat",
               "people who eat little meat, heavy sweaters, at the start of a cold",
               "10–25 mg a day with food (it can cause nausea on an empty stomach). Not above 40 mg a day long term — it causes copper deficiency."),
    },
    "iron": {
        "uz": ("Temir", "qonda kislorod tashish uchun; yetishmasa holsizlik, bosh aylanishi, chidamlilik pasayadi",
               "faqat tahlilda yetishmovchilik (ferritin, gemoglobin) tasdiqlanganlarga — ko'pincha hayz ko'radigan ayollar, vegetarianlar, chidamlilik sportchilari",
               "Shifokor aytgan dozada, C vitamini bilan; choy, qahva, sut va kalsiydan 2 soat ajratib. Tahlilsiz ichmang — ortiqcha temir zararli; bolalardan uzoqda saqlang."),
        "ru": ("Железо", "переносит кислород в крови; при нехватке — слабость, головокружение, падает выносливость",
               "только при дефиците по анализам (ферритин, гемоглобин) — чаще у женщин, вегетарианцев, спортсменов на выносливость",
               "В дозе от врача, с витамином C; отдельно от чая, кофе, молока и кальция на 2 часа. Без анализов не пейте — избыток железа вреден; храните от детей."),
        "en": ("Iron", "carries oxygen in the blood; too little means fatigue, dizziness and lower endurance",
               "only people with a deficiency confirmed by tests (ferritin, haemoglobin) — often menstruating women, vegetarians, endurance athletes",
               "At the dose your doctor gives, with vitamin C, 2 hours apart from tea, coffee, milk and calcium. Don't take it without a test — excess iron is harmful; keep away from children."),
    },
    "calcium": {
        "uz": ("Kalsiy", "suyak, tish va mushak qisqarishi uchun",
               "sut mahsulotlarini kam iste'mol qiladiganlarga, menopauzadagi ayollarga, veganlarga",
               "Avval ovqatdan (kuniga jami 1000–1200 mg). Qo'shimcha bo'lsa bir martada 500 mg dan ko'p emas, D vitamini bilan; temir va ruxdan alohida ichiladi."),
        "ru": ("Кальций", "для костей, зубов и сокращения мышц",
               "тем, кто мало ест молочного, женщинам в менопаузе, веганам",
               "Сначала из еды (всего 1000–1200 мг в день). Добавкой — не больше 500 мг за раз, с витамином D; отдельно от железа и цинка."),
        "en": ("Calcium", "for bones, teeth and muscle contraction",
               "people who eat little dairy, women in menopause, vegans",
               "Food first (1000–1200 mg a day in total). As a supplement no more than 500 mg at a time, with vitamin D, apart from iron and zinc."),
    },
    "electrolytes": {
        "uz": ("Elektrolitlar", "natriy, kaliy va magniyni tiklaydi — suvsizlanish va mushak tortishishining oldini oladi",
               "1 soatdan uzoq yoki issiqda mashq qiladiganlarga, ko'p terlaydiganlarga, yugurish va futbol o'yinchilariga",
               "Mashg'ulot davomida va keyin, suvga aralashtirib, soatiga 500–750 ml. Qisqa mashg'ulotga oddiy suv yetarli."),
        "ru": ("Электролиты", "восполняют натрий, калий и магний — против обезвоживания и судорог",
               "тем, кто тренируется дольше часа или в жару, много потеет, бегунам и футболистам",
               "Во время и после тренировки, разведя в воде, 500–750 мл в час. Для короткой тренировки хватит воды."),
        "en": ("Electrolytes", "replace sodium, potassium and magnesium — prevent dehydration and cramps",
               "anyone training over an hour or in the heat, heavy sweaters, runners and football players",
               "During and after training, mixed in water, 500–750 ml an hour. For short sessions plain water is enough."),
    },
    "glutamine": {
        "uz": ("Glutamin", "ichak va immunitet uchun aminokislota; mushak o'sishiga ta'siri sog'lom odamda kam isbotlangan",
               "juda og'ir va ko'p mashq qiladiganlarga, ichak noqulayligida; oddiy mashq qiluvchiga majburiy emas",
               "Kuniga 5 g, mashg'ulotdan keyin yoki uxlashdan oldin suv bilan."),
        "ru": ("Глютамин", "аминокислота для кишечника и иммунитета; на рост мышц у здоровых людей влияет слабо",
               "тем, кто тренируется очень много и тяжело, при проблемах с кишечником; обычному любителю не обязателен",
               "5 г в день после тренировки или перед сном, с водой."),
        "en": ("Glutamine", "an amino acid for the gut and immunity; little proven effect on muscle growth in healthy people",
               "people training very hard and often, or with gut issues; not essential for most",
               "5 g a day after training or before bed, with water."),
    },
    "beta_alanine": {
        "uz": ("Beta-alanin", "1–4 daqiqalik og'ir yuklamada charchoqni kechiktiradi (mushakda karnozinni oshiradi)",
               "krossfit, kurash, sprint, yuqori takrorli mashg'ulot qiladiganlarga",
               "Kuniga 3,2–6,4 g, 2–4 qismga bo'lib, kamida 4 hafta. Teridagi chimchilash (paresteziya) zararsiz."),
        "ru": ("Бета-аланин", "отодвигает усталость в нагрузке 1–4 минуты (повышает карнозин в мышцах)",
               "кроссфит, борьба, спринт, многоповторные тренировки",
               "3,2–6,4 г в день, разделив на 2–4 приёма, не меньше 4 недель. Покалывание кожи (парестезия) безвредно."),
        "en": ("Beta-alanine", "delays fatigue in 1–4 minute efforts (raises muscle carnosine)",
               "CrossFit, combat sports, sprints, high-rep training",
               "3.2–6.4 g a day in 2–4 split doses for at least 4 weeks. The skin tingling (paresthesia) is harmless."),
    },
    "citrulline": {
        "uz": ("L-sitrullin", "qon aylanishi (pamp) va takrorlar sonini biroz oshiradi; argininga qaraganda yaxshiroq ishlaydi",
               "kuch va pamp mashg'ulotlari qiladiganlarga, kofeinsiz pre-workout istaganlarga",
               "Mashg'ulotdan 40–60 daqiqa oldin 6–8 g sitrullin malat (yoki 3–6 g L-sitrullin)."),
        "ru": ("L-цитруллин", "улучшает кровоток (памп) и немного повышает число повторов; работает лучше аргинина",
               "силовые тренировки на памп, тем, кто хочет предтрен без кофеина",
               "6–8 г цитруллин малата (или 3–6 г L-цитруллина) за 40–60 минут до тренировки."),
        "en": ("L-citrulline", "improves blood flow (pump) and slightly raises reps; works better than arginine",
               "strength and pump training, anyone wanting a stimulant-free pre-workout",
               "6–8 g citrulline malate (or 3–6 g L-citrulline) 40–60 minutes before training."),
    },
    "caffeine": {
        "uz": ("Kofein", "kuch, chidamlilik va diqqatni oshiradi — eng isbotlangan sport stimulyatori",
               "sog'lom kattalarga; yurak, bosim muammosi, homiladorlik yoki uyqusizlikda tavsiya etilmaydi",
               "Mashg'ulotdan 30–60 daqiqa oldin 3 mg/kg (70 kg uchun ~200 mg). Kuniga jami 400 mg dan oshmasin, kechki 16:00 dan keyin ichmang."),
        "ru": ("Кофеин", "повышает силу, выносливость и концентрацию — самый доказанный спортивный стимулятор",
               "здоровым взрослым; не при проблемах с сердцем и давлением, беременности или бессоннице",
               "3 мг/кг за 30–60 минут до тренировки (~200 мг при 70 кг). Не больше 400 мг в день в сумме, не позже 16:00."),
        "en": ("Caffeine", "boosts strength, endurance and focus — the best-proven sports stimulant",
               "healthy adults; not with heart or blood-pressure problems, pregnancy or insomnia",
               "3 mg/kg 30–60 minutes before training (~200 mg at 70 kg). No more than 400 mg a day in total, none after about 4 pm."),
    },
    "test_booster": {
        "uz": ("Testosteron busterlar", "o'simlik ekstraktlari (tribulus, D-aspartat kislota...) — sog'lom erkakda testosteronni sezilarli oshirishi isbotlanmagan",
               "aslida ko'pchilikka kerak emas; yetishmovchilik shubhasi bo'lsa — tahlil va urolog/endokrinolog",
               "Kutilgan natija bo'lmasa pul sarflamang: uyqu, D vitamini, rux, yetarli kaloriya va kuch mashqlari testosteronga ko'proq ta'sir qiladi."),
        "ru": ("Тестобустеры", "растительные экстракты (трибулус, D-аспарагиновая кислота...) — заметного роста тестостерона у здоровых мужчин не доказано",
               "большинству не нужны; при подозрении на дефицит — анализы и уролог/эндокринолог",
               "Не тратьте деньги на ожидания: сон, витамин D, цинк, достаточные калории и силовые влияют на тестостерон сильнее."),
        "en": ("Testosterone boosters", "herbal extracts (tribulus, D-aspartic acid...) — no meaningful testosterone rise proven in healthy men",
               "most people don't need them; if you suspect low testosterone, get tested and see a doctor",
               "Save your money: sleep, vitamin D, zinc, enough calories and strength training matter more for testosterone."),
    },
    "ashwagandha": {
        "uz": ("Ashvagandha", "stress va kortizolni kamaytirish, uyqu va tiklanishni yaxshilashda o'rtacha dalillarga ega adaptogen",
               "stress, yomon uyqu va og'ir mashg'ulot davridagi sog'lom kattalarga",
               "Kuniga 300–600 mg standartlangan ekstrakt, 8 haftagacha. Homiladorlik, qalqonsimon bez yoki autoimmun kasallikda va tinchlantiruvchi dorilar bilan ichmang."),
        "ru": ("Ашваганда", "адаптоген с умеренными доказательствами для снижения стресса и кортизола, улучшения сна и восстановления",
               "здоровым взрослым при стрессе, плохом сне и тяжёлых тренировках",
               "300–600 мг стандартизированного экстракта в день, до 8 недель. Не при беременности, болезнях щитовидной железы, аутоиммунных и вместе с седативными."),
        "en": ("Ashwagandha", "an adaptogen with moderate evidence for lower stress and cortisol, better sleep and recovery",
               "healthy adults under stress, sleeping poorly or training hard",
               "300–600 mg standardised extract a day for up to 8 weeks. Not in pregnancy, thyroid or autoimmune disease, or with sedatives."),
    },
    "zma": {
        "uz": ("ZMA (rux + magniy + B6)", "rux va magniy yetishmovchiligini to'ldiradi, uyqu sifatini yaxshilashi mumkin",
               "ko'p terlaydigan va ovqatdan rux-magniy kam oladigan sportchilarga; yetarli bo'lsa testosteronni oshirmaydi",
               "Uxlashdan 30–60 daqiqa oldin och qoringa, sut mahsulotlarisiz (kalsiy so'rilishni kamaytiradi), qadoqdagi dozada."),
        "ru": ("ZMA (цинк + магний + B6)", "восполняет дефицит цинка и магния, может улучшить сон",
               "спортсменам, которые много потеют и недополучают цинк и магний; при их достатке тестостерон не повышает",
               "За 30–60 минут до сна натощак, без молочного (кальций мешает усвоению), по дозировке на упаковке."),
        "en": ("ZMA (zinc + magnesium + B6)", "covers zinc and magnesium gaps and may improve sleep",
               "athletes who sweat a lot and get little zinc and magnesium from food; it won't raise testosterone if you already have enough",
               "30–60 minutes before bed on an empty stomach, without dairy (calcium blocks absorption), at the label dose."),
    },
    "melatonin": {
        "uz": ("Melatonin", "uyquga ketishni tezlashtiradi, vaqt mintaqasi o'zgarganda yordam beradi",
               "uyquga qiynalib ketadigan, smenada ishlaydigan yoki uzoq parvozdan keyingi kattalarga",
               "Uxlashdan 30–60 daqiqa oldin 0,5–3 mg, qisqa muddat. Ichgandan keyin mashina haydamang; homiladorlik va bolalarga faqat shifokor bilan."),
        "ru": ("Мелатонин", "помогает быстрее уснуть и перестроиться при смене часовых поясов",
               "взрослым с трудным засыпанием, при сменной работе, после перелётов",
               "0,5–3 мг за 30–60 минут до сна, короткими курсами. После приёма не садитесь за руль; беременным и детям — только с врачом."),
        "en": ("Melatonin", "helps you fall asleep faster and adjust to time zones",
               "adults who struggle to fall asleep, shift workers, after long flights",
               "0.5–3 mg 30–60 minutes before bed, short term. Don't drive after taking it; pregnancy and children only with a doctor."),
    },
    "probiotic": {
        "uz": ("Probiotik", "ichak mikroflorasini qo'llab-quvvatlaydi; samarasi shtammga bog'liq",
               "antibiotik kursi davomida va keyin, ich qotishi yoki dam bo'lishda",
               "Kuniga 1 marta, qadoqdagi dozada; antibiotikdan 2 soat ajratib. Kefir, qatiq va tolali ovqat ham foydali."),
        "ru": ("Пробиотик", "поддерживает микрофлору кишечника; эффект зависит от штамма",
               "во время и после курса антибиотиков, при запорах или вздутии",
               "1 раз в день по дозировке на упаковке, через 2 часа после антибиотика. Кефир, катык и клетчатка тоже помогают."),
        "en": ("Probiotic", "supports gut flora; the effect depends on the strain",
               "during and after antibiotics, with constipation or bloating",
               "Once a day at the label dose, 2 hours apart from antibiotics. Kefir, yoghurt and fibre help too."),
    },
    "glucosamine": {
        "uz": ("Glyukozamin / xondroitin", "bo'g'im tog'ayini qo'llab-quvvatlash uchun; samarasi aralash, ba'zilarda og'riqni kamaytiradi",
               "bo'g'imlariga katta yuk tushadigan sportchilar va 40 yoshdan oshganlarga",
               "Kuniga 1500 mg glyukozamin sulfat (+ 800–1200 mg xondroitin), ovqat bilan, kamida 8–12 hafta. Dengiz mahsulotlariga allergiya yoki qon suyultiruvchi dori bo'lsa — shifokorga so'rang."),
        "ru": ("Глюкозамин / хондроитин", "для поддержки хрящей суставов; эффект неоднозначный, у части людей уменьшает боль",
               "спортсменам с большой нагрузкой на суставы и людям после 40",
               "1500 мг глюкозамина сульфата (+ 800–1200 мг хондроитина) в день с едой, не меньше 8–12 недель. При аллергии на морепродукты или приёме антикоагулянтов — посоветуйтесь с врачом."),
        "en": ("Glucosamine / chondroitin", "to support joint cartilage; evidence is mixed, some people get less pain",
               "athletes with heavy joint load and people over 40",
               "1500 mg glucosamine sulfate (+ 800–1200 mg chondroitin) a day with food for at least 8–12 weeks. With a shellfish allergy or blood thinners, ask a doctor."),
    },
}
for _kind, _texts in KINDS.items():
    for _loc, (_name, _why, _who, _usage) in _texts.items():
        T["kind_name"][_loc][_kind] = _name
        T["why"][_loc][_kind] = _why
        T["who"][_loc][_kind] = _who
        T["usage"][_loc][_kind] = _usage
