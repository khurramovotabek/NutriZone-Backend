"""
The conversation layer the rule engine was missing (2026-11-20), found by replaying all 351 real questions:

* follow-ups that only make sense with what was said before -- "Qanday ichiladi?", "Arzonroq variant" (a chip!),
  "Ta'siri qancha vaqtda seziladi?" -- are resolved against the product / kind just discussed, or asked back;
* "Olmaliqqa qanchaga keladi?" is delivery (it listed creatine prices), "Surxondaryoda filial bormi?" is stores
  (it listed random tubs), "nasiya yoki bo'lib to'lash bormi" is payment (the "yoki" made it a product comparison);
* a product named by its own name ("Ostovip monogidrat kreatin", "iso100 olmoqchiman", "Gold Standard bormi") is
  shown itself, not the best of its kind;
* "+99890… raqamga qo'ng'iroq qiling" is a callback request -- the staff channel gets it, it isn't lost in the log;
* a reply from the fuzzy catalogue search that has nothing to do with the words asked ("ob-havo qanday") is dropped.

`route()` returns a full reply tuple, a rewritten question (str) for the normal pipeline, or None.
"""
from __future__ import annotations

import re

from apps.assistant.infrastructure.advisor import kb, nlu

try:  # rapidfuzz is a backend requirement (smart search); the plain fallback only keeps tests without it working
    from rapidfuzz import fuzz as _fuzz
except ImportError:  # pragma: no cover
    _fuzz = None


def _l(loc: str, uz: str, ru: str, en: str) -> str:
    return {"uz": uz, "ru": ru, "en": en}.get(loc, uz)


def _both(text: str) -> str:
    t = nlu.normalize(text)
    return f"{t} {t.translate(nlu.LATIN_FROM_CYR)}"


def _money(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------------------------- callback request

PHONE = re.compile(r"(?<!\d)(?:\+?998[\s\-()]*)?\(?(\d{2})\)?[\s\-]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})(?!\d)")
CALL = ("qo'ng'iroq", "qongiroq", "qo'ngiroq", "telefon qil", "aloqaga chiq", "bog'lan", "boglan", "chiqing", "tel qil", "звон", "позвон", "перезвон",
        "свяж", "набер", "call me", "call back", "callback", "contact me", "ring me", "қўнғироқ")


def callback_phone(text: str) -> str | None:
    """"Можете позвонить на номер +998903154499" -- a normalized +998 number when the message asks to be called."""
    m = PHONE.search(text or "")
    if not m or not nlu._has(_both(text), CALL):
        return None
    return "+998" + "".join(m.groups())


def callback_reply(phone: str, loc: str) -> str:
    shown = f"{phone[:4]} {phone[4:6]} {phone[6:9]} {phone[9:11]} {phone[11:]}"
    return _l(loc,
              f"✅ Raqamingizni qabul qildim: **{shown}**\nOperatorimiz ish vaqtida tez orada qo'ng'iroq qiladi. Kutayotganda savolingiz bo'lsa — shu yerga yozavering.",
              f"✅ Номер принят: **{shown}**\nОператор перезвонит в рабочее время в ближайшее время. Пока ждёте — можете задать вопрос здесь.",
              f"✅ Got your number: **{shown}**\nOur operator will call you back shortly during working hours. Meanwhile, ask me anything here.")


# ---------------------------------------------------------------------------------------------- places / delivery

# regions and the larger towns (Latin and Russian stems) -- enough to know a place was named; branches come from the DB
PLACES = {
    "Toshkent": ("toshken", "tashkent", "ташкент"), "Samarqand": ("samarqand", "samarkand", "самарканд"), "Buxoro": ("buxoro", "bukhara", "бухар"),
    "Andijon": ("andijon", "andijan", "андижан"), "Farg'ona": ("farg'ona", "fargona", "fergana", "фергана", "фарғона"), "Namangan": ("namangan", "наманган"),
    "Qashqadaryo": ("qashqadaryo", "кашкадар", "қашқадарё"), "Qarshi": ("qarshi", "карши"), "Surxondaryo": ("surxondaryo", "surxondaryo", "сурхандар", "сурхондарё"),
    "Termiz": ("termiz", "termez", "термез"), "Xorazm": ("xorazm", "khorezm", "хорезм", "хоразм"), "Urganch": ("urganch", "urgench", "ургенч"),
    "Xiva": ("xiva", "khiva", "хива"), "Navoiy": ("navoiy", "navoi", "навои"), "Jizzax": ("jizzax", "jizzakh", "джизак", "жиззах"),
    "Sirdaryo": ("sirdaryo", "сырдар", "сирдарё"), "Guliston": ("guliston", "гулистан"), "Qoraqalpog'iston": ("qoraqalpog", "karakalpak", "каракалпак"),
    "Nukus": ("nukus", "нукус"), "Olmaliq": ("olmaliq", "almalyk", "алмалык"), "Angren": ("angren", "ангрен"), "Chirchiq": ("chirchiq", "chirchik", "чирчик"),
    "Bekobod": ("bekobod", "бекабад"), "Ohangaron": ("ohangaron", "ахангаран"), "Yangiyo'l": ("yangiyo'l", "yangiyul", "янгиюль"), "Zarafshon": ("zarafshon", "зарафшан"),
    "Shahrisabz": ("shahrisabz", "шахрисабз"), "Kattaqo'rg'on": ("kattaqo'rg'on", "kattakurgan", "каттакурган"), "Marg'ilon": ("marg'ilon", "margilan", "маргилан"),
    "Qo'qon": ("qo'qon", "qoqon", "kokand", "коканд"), "Denov": ("denov", "денау"), "Nurafshon": ("nurafshon", "нурафшан"), "Gulbahor": ("gulbahor",),
}
REGION_WORDS = ("viloyat", "tuman", "область", "регион", "район", "region")
ARRIVE = ("qanchaga keladi", "qanchaga kelad", "qancha keladi", "qanchaga boradi", "qancha boradi", "yetib kel", "keladimi", "necha kunda", "nechi kunda",
          "jo'nat", "jonat", "yubora olasiz", "yuborasiz", "yuborasizlar", "pochta", "доставит", "доставка в", "доставляете", "отправ", "сколько идет",
          "сколько идёт", "сколько дней", "ship to", "deliver to", "send to", "yetkaz", "dostav", "достав", "етказ")


def place_in(text: str) -> str:
    """The most specific place named: "Toshkent viloyati, Olmaliq shahri" -> Olmaliq (the last one said)."""
    found = ""
    for w in text.split():
        b = _both(w)
        found = next((name for name, stems in PLACES.items() if nlu._has(b, stems)), found)
    return found


def _branch_place(text: str) -> str:
    from apps.assistant.infrastructure.tools import get_store_info

    return kb._place_in(text, get_store_info({}, "uz").get("branches", []))


def delivery_reply(text: str, loc: str, place: str) -> str:
    head = ""
    if place:
        head = _l(loc, f"📍 **{place}** — yetkazib beramiz.", f"📍 **{place}** — доставляем.", f"📍 **{place}** — yes, we deliver there.") + "\n\n"
    body = kb.delivery_text(loc)
    branch = _branch_place(text) if place else ""
    if branch:
        body += "\n\n" + _l(loc, f"🏪 {branch}da filialimiz bor — o'zingiz olib ketsangiz bepul.", f"🏪 В городе {branch} есть наш магазин — самовывоз бесплатно.",
                            f"🏪 We have a store in {branch} — pickup is free.")
    return head + body


def stores_reply(text: str, loc: str) -> str:
    place = place_in(text)
    if place and place != "Toshkent" and not _branch_place(text):
        # "Surxondaryoda filial bormi" -- say so plainly, then how they still get it
        return (_l(loc, f"😔 **{place}**da hozircha filialimiz yo'q — lekin u yerga yetkazib beramiz:", f"😔 В регионе **{place}** пока нет нашего магазина — но мы туда доставляем:",
                   f"😔 We don't have a store in **{place}** yet — but we deliver there:") + "\n\n" + kb.delivery_text(loc))
    return kb.stores_text(loc, text)


# ---------------------------------------------------------------------------------------------- payment

INSTALLMENT = ("nasiya", "bo'lib to'la", "bolib tola", "bo'lib-bo'lib", "muddatli", "kredit", "рассрочк", "в кредит", "кредит", "installment", "instalment", "pay later")


def payment_reply(text: str, loc: str) -> str:
    from apps.assistant.infrastructure import knowledge

    if nlu._has(_both(text), INSTALLMENT):
        hits = knowledge.search("nasiya bo'lib to'lash muddatli to'lov", limit=1)
        if hits:
            knowledge.mark_used([hits[0].entry])
            return hits[0].entry.answer(loc)
    hits = knowledge.search(text, limit=2)
    for h in hits:  # what the shop taught about paying (cards, cash on delivery...) wins over the bare list of methods
        about = nlu.normalize(" ".join((h.entry.title, h.entry.keywords or "")))
        if h.score >= 5.5 and nlu._has(f"{about} {about.translate(nlu.LATIN_FROM_CYR)}", nlu.INTENTS["faq_payment"]):
            knowledge.mark_used([h.entry])
            return h.entry.answer(loc)
    return kb.payment_text(loc)


# ---------------------------------------------------------------------------------------------- products named by name

GENERIC = re.compile(
    r"^(?:menga|meni|mani|sizda|sizlarda|bormi|bor|yo'qmi|kerak\w*|olmoqchi\w*|olsam|olay|olib|sotasiz\w*|sotiladimi|bering|qiling|iltimos|haqida|"
    r"protein\w*|proteyn\w*|whey|vey|oqsil\w*|izolyat\w*|isolate|konsentrat\w*|kreatin\w*|creatine?|monogidrat|monohidrat|monohydrate|mono|mikroniz\w*|"
    r"micronized|kukun|powder|tabletka|kapsula\w*|capsules?|tablets?|gramm|gr|kg|ml|g|ta'm\w*|tam\w*|flavou?r|shokolad\w*|vanil\w*|"
    r"geyner\w*|gainer\w*|vitamin\w*|bcaa|eaa|amino\w*|yaxshi\w*|zo'r|original\w*|asl|"
    r"есть|хочу|нужен|нужна|нужно|мне|у|вас|купить|продаете|протеин\w*|креатин\w*|"
    r"do|you|have|i|want|need|buy|any|the|a|is|there|please|need|"
    r"ich\w*|qabul\w*|qachon|принима\w*|пить|take|taken|"
    r"uchun|bilan|ham|va|eng|bu|shu|qanday|qanaqa|nima|nimaga|qancha|necha|qaysi|bo'ladi\w*|bo'lsa|qilib|qilish|ekan|edi|mi|"
    r"для|и|с|это|какой|какая|какие|что|как|сколько|for|and|with|of|this|what|how|which)$")
WANT = ("bormi", "bor mi", "bor?", "olmoqchi", "olsam", "olay", "kerak", "sotasiz", "sotiladimi", "mavjudmi", "есть", "хочу", "нужен", "нужна", "куплю",
        "купить", "продаете", "have", "want", "need", "buy", "in stock")
NOT_A_LISTING = re.compile(r"\b(?:yoki|va|vs|или|or|qaysi|farq\w*|solishtir\w*|narx\w*|qancha|necha|tarkib\w*|qanday|nima|nimaga|цена|сколько|состав|как|что|"
                           r"price|how|what|which|cost)\b")


def _words(text: str) -> list[str]:
    q = re.sub(r"[?!.,;:()«»\"]", " ", nlu.normalize(text)).translate(nlu.LATIN_FROM_CYR)
    return [w for w in q.split() if len(w) >= 3 and not w.isdigit() and not GENERIC.match(w) and not nlu.concepts_in(w)]


def before_place(text: str) -> str:
    """"Anabolic iso whey Toshken viloyat Olmaliq shahriga qanchaga keladi" -> "Anabolic iso whey" (the product comes first)."""
    out = []
    for w in text.split():
        b = _both(w)
        if nlu._has(b, REGION_WORDS) or any(nlu._has(b, stems) for stems in PLACES.values()):
            break
        out.append(w)
    return " ".join(out)


def _matches(word: str, name: str) -> bool:
    """A word of the question names this product: equal / prefix of a word of the name, or the same word misspelt
    ("ostovip" ~ "ostrovit", "goldstandart" ~ "goldstandard")."""
    n = nlu.normalize(name).translate(nlu.LATIN_FROM_CYR)
    tokens = re.findall(r"[0-9a-z']+", n)
    if any(t.startswith(word) or (len(t) >= 4 and word.startswith(t)) for t in tokens):
        return True
    if len(word) < 5 or _fuzz is None:
        return False
    compact = re.sub(r"[^0-9a-z]", "", n)
    return any(_fuzz.ratio(word, t) >= 78 for t in tokens if len(t) >= 4) or (len(word) >= 7 and _fuzz.partial_ratio(word, compact) >= 88)


def named_products(text: str, loc: str, limit: int = 5) -> list[dict]:
    """The products a message names by their own name (brand words alone don't count -- that's a brand listing)."""
    from apps.assistant.infrastructure import tools

    words = _words(text)
    if not words or len(words) > 5:
        return []
    query = " ".join(re.sub(r"[?!.,]", " ", nlu.normalize(text)).split())[:120]
    found = tools.search_products({"query": query, "limit": 8, "in_stock_only": False}, loc)["products"]
    out = []
    for x in found:
        name, brand = x.get("name") or "", x.get("brand") or ""
        if not all(_matches(w, f"{brand} {name}") for w in words):
            continue
        if all(_matches(w, brand) for w in words):  # "olimp bormi" -- only the brand: Brain lists the brand
            continue
        out.append(x)
    out.sort(key=lambda x: not x.get("in_stock"))
    return out[:limit]


def relevant(text: str, found: list[dict]) -> bool:
    """The catalogue search's hits have something to do with the words asked (it always returns *something*)."""
    words = _words(text)
    if not words:
        return True
    return any(_matches(w, f"{x.get('brand') or ''} {x.get('name') or ''} {x.get('category') or ''}") for w in words for x in found)


def product_lines(items: list[dict], loc: str) -> str:
    cur = _l(loc, "so'm", "сум", "UZS")
    out = []
    for i, x in enumerate(items, 1):
        old = f" ~~{_money(x['old_price_uzs'])}~~" if x.get("old_price_uzs") else ""
        stock = "" if x.get("in_stock") else _l(loc, " · hozir yo'q", " · нет в наличии", " · out of stock")
        out.append(f"{i}. **{x['name']}** — {_money(x.get('price_uzs'))} {cur}{old}{stock}")
    return "\n".join(out)


def named_reply(items: list[dict], loc: str) -> str:
    if not any(x.get("in_stock") for x in items):
        head = _l(loc, "Bu mahsulot katalogimizda bor, lekin hozir omborda tugagan:", "Этот товар есть в каталоге, но сейчас закончился:",
                  "It's in our catalogue but out of stock right now:")
        tail = _l(loc, "Kelishi bilan xabar olish uchun mahsulot sahifasida «Narx tushsa xabar bering» yoki «Mahsulot topib bering»dan foydalaning — yoki o'xshash variant tanlab beraman.",
                  "Чтобы узнать о поступлении — «Найти товар» на сайте, или я подберу аналог.",
                  "Use «Find a product» on the site to hear when it's back — or I can suggest an equivalent.")
        return f"{head}\n{product_lines(items, loc)}\n\n{tail}"
    head = _l(loc, "✅ **Ha, bor:**", "✅ **Да, есть:**", "✅ **Yes, we have it:**")
    tail = _l(loc, "Tarkibi, porsiyasi yoki qanday ichilishini so'rashingiz mumkin.", "Можете спросить состав, порции или как принимать.",
              "Ask me about its ingredients, servings or how to take it.")
    return f"{head}\n{product_lines(items, loc)}\n\n{tail}"


# ---------------------------------------------------------------------------------------------- arginine (not citrulline)

ARGININE = ("arginin", "аргинин")


def arginine_reply(loc: str) -> tuple[str, list[str]]:
    from apps.assistant.infrastructure import tools

    found = tools.search_products({"query": "arginine", "limit": 6, "in_stock_only": False}, loc)["products"]
    found = [x for x in found if _matches("arginin", x.get("name") or "")][:4]
    found.sort(key=lambda x: not x.get("in_stock"))
    text = _l(loc,
              "**L-arginin** — aminokislota, organizmda azot oksidi (NO) hosil bo'lishiga xizmat qiladi: qon tomirlari kengayadi, mashg'ulotda «pamp» seziladi.\n"
              "• Odatiy doza: 3–6 g, mashg'ulotdan 30–60 daqiqa oldin.\n"
              "• 💡 Bilib qo'ying: **L-sitrullin** qondagi arginin darajasini argininning o'zidan ham yaxshiroq oshiradi (6–8 g) — pamp uchun ko'pincha u tanlanadi.\n"
              "• Past qon bosimi yoki qon bosimi dorilari bo'lsa — shifokor bilan maslahatlashing.",
              "**L-аргинин** — аминокислота, из которой организм делает оксид азота (NO): сосуды расширяются, на тренировке чувствуется «памп».\n"
              "• Обычная доза: 3–6 г за 30–60 минут до тренировки.\n"
              "• 💡 Важно: **L-цитруллин** (6–8 г) поднимает уровень аргинина в крови даже лучше самого аргинина — для пампа чаще берут его.\n"
              "• При низком давлении или лекарствах от давления — посоветуйтесь с врачом.",
              "**L-arginine** — an amino acid the body turns into nitric oxide (NO): vessels widen and you feel the \"pump\".\n"
              "• Usual dose: 3–6 g, 30–60 minutes before training.\n"
              "• 💡 Good to know: **L-citrulline** (6–8 g) raises blood arginine even better than arginine itself — it's the usual pick for the pump.\n"
              "• With low blood pressure or blood-pressure medication, check with your doctor first.")
    if found:
        text += "\n\n" + _l(loc, "Ombordagi arginin:", "Аргинин в наличии:", "Arginine we carry:") + "\n" + product_lines(found, loc)
    return text, [x["id"] for x in found]


# ---------------------------------------------------------------------------------------------- "when will I feel it?"

EFFECT = ("ta'siri", "tasiri", "ta'sir qil", "natija", "qachon bil", "qancha vaqtda", "qancha vaqt keyin", "necha kunda", "nechi kunda", "necha haftada",
          "seziladi", "sezaman", "когда эффект", "через сколько", "когда будет результат", "когда почувств", "результат", "how long until", "how long before",
          "when will i see", "when will i feel", "how soon", "results", "kick in")

EFFECT_TIME = {
    "creatine": ("Mushaklar kreatinga **3–4 haftada** to'yinadi (kuniga 3–5 g); 5–7 kunlik «yuklama» (kuniga ~20 g) bilan — **~1 haftada**. Shundan keyin kuch va takrorlar soni oshadi. Birinchi haftalarda tarozi +1–2 kg ko'rsatishi mumkin — bu mushak ichidagi suv, yog' emas.",
                 "Мышцы насыщаются креатином за **3–4 недели** (3–5 г в день); с «загрузкой» 5–7 дней по ~20 г — примерно **за неделю**. Дальше растут сила и количество повторений. В первые недели весы могут показать +1–2 кг — это вода в мышцах, не жир.",
                 "Muscles fill up with creatine in **3–4 weeks** at 3–5 g a day; with a 5–7-day loading phase (~20 g a day) in about **a week**. Then strength and reps go up. The scale may show +1–2 kg in the first weeks — water inside the muscle, not fat."),
    "protein": ("Protein o'zi «ta'sir» qiladigan dori emas — kunlik oqsil me'yorini to'ldiradi. Mashg'ulot bilan tiklanish **1–2 haftada** yaxshilanganini sezasiz, mushakdagi ko'rinadigan o'zgarish — odatda **6–8 haftada**.",
                "Протеин — не препарат с «эффектом», он закрывает дневную норму белка. С тренировками восстановление улучшается за **1–2 недели**, видимые изменения в мышцах — обычно через **6–8 недель**.",
                "Protein isn't a drug with an \"effect\" — it fills your daily protein target. With training, recovery improves within **1–2 weeks**; visible muscle change usually takes **6–8 weeks**."),
    "gainer": ("Kaloriya profitsiti bo'lsa tarozi **1–2 haftada** qo'zg'aladi. Ideal sur'at — haftasiga **+0,25–0,5 kg**; tezroq bo'lsa ko'pi yog' bo'ladi, porsiyani kamaytiring.",
               "При профиците калорий вес сдвигается за **1–2 недели**. Идеальный темп — **+0,25–0,5 кг в неделю**; быстрее — это в основном жир, уменьшите порцию.",
               "In a calorie surplus the scale moves within **1–2 weeks**. The ideal pace is **+0.25–0.5 kg a week**; faster is mostly fat — cut the serving."),
    "preworkout": ("Ichgandan **20–30 daqiqada** boshlanadi va **2–4 soat** davom etadi (kofein organizmda ~5 soat qoladi) — shuning uchun kechki mashg'ulotdan 6 soat oldin ichmang.",
                   "Начинает действовать через **20–30 минут** и держится **2–4 часа** (кофеин выводится ~5 часов) — вечером не пейте позже чем за 6 часов до сна.",
                   "Kicks in **20–30 minutes** after drinking and lasts **2–4 hours** (caffeine stays ~5 hours) — so don't take it within 6 hours of bedtime."),
    "carnitine": ("Tez ta'sir yo'q: L-karnitin faqat **kaloriya defitsiti va kardio** bilan yordam beradi. Natijani **4–8 haftadan** keyin bel o'lchami va tarozi bilan baholang.",
                  "Быстрого эффекта нет: L-карнитин помогает только при **дефиците калорий и кардио**. Оценивайте результат через **4–8 недель** по талии и весам.",
                  "There's no quick effect: L-carnitine helps only with a **calorie deficit and cardio**. Judge it after **4–8 weeks** by your waist and the scale."),
    "bcaa": ("Mashg'ulot **paytida** ishlaydi (charchoqni biroz kamaytiradi); keyingi kunlardagi mushak og'rig'i biroz yengillashishi mumkin. Kunlik oqsil yetarli bo'lsa, farq kichik.",
             "Работает **во время** тренировки (немного снижает усталость), крепатура в следующие дни может быть мягче. Если белка в день хватает — разница небольшая.",
             "Works **during** the session (slightly less fatigue); soreness over the next days may be milder. If your daily protein is enough, the difference is small."),
    "citrulline": ("Pamp — o'sha kuni, ichgandan **~60 daqiqada**. Chidamlilikdagi foyda muntazam ichganda **1–2 haftada** seziladi.",
                   "Памп — в тот же день, через **~60 минут**. Выносливость растёт при регулярном приёме за **1–2 недели**.",
                   "The pump comes the same day, **~60 minutes** after. Endurance benefits show with regular use in **1–2 weeks**."),
    "beta_alanine": ("Mushakda karnozin to'planishi kerak: har kuni ichganda **2–4 haftada**. Ichgandan 15–20 daqiqada teridagi chimirlash — zararsiz, kichikroq dozalarga bo'lsangiz kamayadi.",
                     "Карнозин должен накопиться в мышцах: при ежедневном приёме **2–4 недели**. Покалывание через 15–20 минут — безвредно, меньше при дробных дозах.",
                     "Carnosine has to build up in the muscle: **2–4 weeks** of daily use. The tingling 15–20 minutes after is harmless and fades with smaller split doses."),
    "omega": ("Qondagi omega-3 darajasi **8–12 haftada** ko'tariladi — bo'g'im, teri, yurak foydasi asta-sekin keladi. Har kuni ovqat bilan iching.",
              "Уровень омега-3 в крови растёт **8–12 недель** — польза для суставов, кожи и сердца приходит постепенно. Пейте каждый день с едой.",
              "Blood omega-3 levels rise over **8–12 weeks** — the joint, skin and heart benefits come gradually. Take it daily with food."),
    "vitamin_d": ("Qondagi D vitamini **8–12 haftada** barqaror ko'tariladi. Kamchilik bo'lgan bo'lsa, charchoq va kayfiyat **1–2 oyda** yaxshilanadi; 3 oydan keyin 25(OH)D tahlilini qayta topshiring.",
                  "Уровень витамина D стабильно растёт **8–12 недель**. При дефиците усталость и настроение улучшаются за **1–2 месяца**; через 3 месяца пересдайте 25(OH)D.",
                  "Blood vitamin D rises steadily over **8–12 weeks**. If you were low, tiredness and mood improve within **1–2 months**; re-test 25(OH)D after 3 months."),
    "magnesium": ("Uyqu va mushak tortishishi bo'yicha **1–2 haftada** sezasiz; kamchilikni to'liq tiklash **1–2 oy**.",
                  "По сну и судорогам эффект — за **1–2 недели**; полностью восполнить дефицит — **1–2 месяца**.",
                  "For sleep and cramps you'll notice it in **1–2 weeks**; fully correcting a deficiency takes **1–2 months**."),
    "zinc": ("Immunitet, teri va soch uchun **4–12 hafta** muntazam ichish kerak. 40 mg dan oshirmang.",
             "Для иммунитета, кожи и волос нужно **4–12 недель** регулярного приёма. Не больше 40 мг в день.",
             "Immunity, skin and hair need **4–12 weeks** of regular use. Don't exceed 40 mg a day."),
    "iron": ("Gemoglobin **2–4 haftada** ko'tarila boshlaydi, temir zaxirasi (ferritin) — **2–3 oyda**. Faqat tahlil bilan iching va 3 oydan keyin qayta tekshiring.",
             "Гемоглобин начинает расти через **2–4 недели**, запасы железа (ферритин) — за **2–3 месяца**. Принимайте только по анализам и пересдайте через 3 месяца.",
             "Haemoglobin starts rising in **2–4 weeks**, iron stores (ferritin) in **2–3 months**. Take it only on blood tests and re-check after 3 months."),
    "collagen": ("Teri va bo'g'imlar uchun **8–12 hafta** har kuni ~10 g (C vitamini bilan). Undan oldin natija kutmang.",
                 "Для кожи и суставов — **8–12 недель** ежедневно по ~10 г (с витамином C). Раньше результата не ждите.",
                 "For skin and joints: **8–12 weeks** of ~10 g a day (with vitamin C). Don't expect results sooner."),
    "glucosamine": ("Bo'g'im og'rig'i kamayishi **4–12 haftada**. 3 oyda foyda sezmasangiz — davom ettirish shart emas.",
                    "Боль в суставах уменьшается за **4–12 недель**. Если за 3 месяца пользы нет — продолжать не нужно.",
                    "Joint pain eases in **4–12 weeks**. If you feel nothing after 3 months, there's no need to continue."),
    "ashwagandha": ("Stress va uyqu bo'yicha **2–4 haftada** sezila boshlaydi, to'liq natija — **6–8 haftada**. Kursdan keyin 2–4 hafta tanaffus qiling.",
                    "По стрессу и сну — через **2–4 недели**, полный эффект — за **6–8 недель**. После курса сделайте перерыв 2–4 недели.",
                    "Stress and sleep effects start in **2–4 weeks**, full effect in **6–8 weeks**. Take a 2–4-week break after a course."),
    "melatonin": ("Yotishdan **30–60 daqiqa** oldin ichiladi — o'sha kechasi ishlaydi. Har kuni uzoq muddat emas: rejimni tiklash uchun 1–2 hafta.",
                  "Принимают за **30–60 минут** до сна — работает в ту же ночь. Не постоянно: 1–2 недели, чтобы наладить режим.",
                  "Take it **30–60 minutes** before bed — it works that night. Not for daily long-term use: 1–2 weeks to reset your rhythm."),
    "sleep": ("Melatonin — o'sha kechasi (yotishdan 30–60 daqiqa oldin); magniy — **1–2 haftada**; ashvagandha — **2–4 haftada**. Eng katta ta'sirni rejim beradi: bir vaqtda yotish, kechqurun kofeinsiz.",
              "Мелатонин — в ту же ночь (за 30–60 минут до сна); магний — за **1–2 недели**; ашваганда — за **2–4 недели**. Главное — режим: ложиться в одно время, без кофеина вечером.",
              "Melatonin works that night (30–60 minutes before bed); magnesium in **1–2 weeks**; ashwagandha in **2–4 weeks**. The routine matters most: same bedtime, no caffeine in the evening."),
    "vitamin": ("Kamchilik bo'lsa charchoq **2–4 haftada** kamayadi; kamchilik bo'lmasa «sezilarli» ta'sir bo'lmaydi — multivitamin sug'urta vazifasini o'taydi.",
                "При дефиците усталость уменьшается за **2–4 недели**; без дефицита «ощутимого» эффекта не будет — мультивитамины работают как страховка.",
                "If you're deficient, tiredness eases in **2–4 weeks**; if not, there's no noticeable effect — a multivitamin is insurance."),
    "probiotic": ("Hazm bo'yicha **2–4 haftada** baholang. Antibiotik paytida — undan 2 soat keyin iching.",
                  "Оценивайте по пищеварению через **2–4 недели**. Во время антибиотиков — через 2 часа после них.",
                  "Judge it by digestion after **2–4 weeks**. With antibiotics, take it 2 hours after them."),
    "test_booster": ("O'simlikli bustyorlar testosteronni o'lchab bo'ladigan darajada kam oshiradi; libido bo'yicha ta'sir bo'lsa — **4–8 haftada**. Mushak uchun ulardan katta natija kutmang: uyqu, ovqat va mashg'ulot muhimroq.",
                     "Растительные бустеры почти не повышают измеримый тестостерон; эффект на либидо, если есть, — через **4–8 недель**. Большого роста мышц от них не ждите: важнее сон, еда и тренировки.",
                     "Herbal boosters barely move measurable testosterone; any libido effect shows in **4–8 weeks**. Don't expect much muscle from them — sleep, food and training matter more."),
    "electrolytes": ("Darhol — uzoq va issiq mashg'ulotda suyuqlik yo'qotishni qoplaydi, tortishish va charchoqni kamaytiradi.",
                     "Сразу — на длительной и жаркой тренировке восполняют потерю жидкости, уменьшают судороги и усталость.",
                     "Immediately — on long, hot sessions they replace lost fluid and cut cramps and fatigue."),
    "caffeine": ("**15–45 daqiqada** boshlanadi, 3–5 soat davom etadi.", "Начинает действовать через **15–45 минут**, держится 3–5 часов.",
                 "Kicks in within **15–45 minutes** and lasts 3–5 hours."),
}
EFFECT_TIME["zma"] = EFFECT_TIME["magnesium"]


def effect_reply(kind: str, loc: str) -> str | None:
    row = EFFECT_TIME.get(kind)
    if not row:
        return None
    name = kb.T["kind_name"][loc].get(kind, kind)
    return f"⏳ **{name} — {_l(loc, 'qachon natija beradi', 'когда будет эффект', 'when it works')}**\n{row[('uz', 'ru', 'en').index(loc) if loc in ('uz', 'ru', 'en') else 0]}"


def which_product_reply(loc: str) -> tuple[str, list[str]]:
    return (_l(loc, "Qaysi mahsulot haqida so'rayapsiz? Nomini yoki turini yozing — masalan, **kreatin**, **protein**, **D3 vitamini**.",
               "О каком продукте вопрос? Напишите название или вид — например, **креатин**, **протеин**, **витамин D3**.",
               "Which product do you mean? Type its name or kind — e.g. **creatine**, **protein**, **vitamin D3**."),
            {"uz": ["Kreatin qanday ichiladi?", "Protein qanday ichiladi?", "Geyner qanday ichiladi?"],
             "ru": ["Как принимать креатин?", "Как принимать протеин?", "Как принимать гейнер?"],
             "en": ["How to take creatine?", "How to take protein?", "How to take a gainer?"]}.get(loc, []))


SYMPTOMS = ("soch", "tirnoq", "husnbuzar", "charchay", "charchoq", "holsiz", "shamoll", "tumov", "tez-tez kasal", "stress", "asabiy", "tortish",
            "semirmay", "semira olma", "qorin yog'", "qorinni", "dori ich", "dori bilan", "antibiotik", "волос", "ногт", "прыщ", "усталост", "устаю",
            "простуж", "болею", "стресс", "судорог", "живот", "лекарств", "hair", "nails", "acne", "tired", "fatigue", "cold", "cramp", "belly", "medication")


CHEAPER = ("arzonroq", "arzoni", "arzon variant", "qimmat ekan", "qimmatku", "дешевле", "подешевле", "дорого", "cheaper", "less expensive", "too expensive")


def kind_of_focus(meta: dict, loc: str) -> str | None:
    """The kind of the one product being discussed (its name says it: "... Kreatin Monohidrat ...")."""
    from apps.assistant.infrastructure import tools

    focus = meta.get("focus")
    if not focus:
        return None
    cards = tools.cards([tools._uuid(focus)], loc)
    if not cards:
        return None
    found = nlu.concepts_in(_both(cards[0].get("name") or ""))
    return found[0] if found else None
