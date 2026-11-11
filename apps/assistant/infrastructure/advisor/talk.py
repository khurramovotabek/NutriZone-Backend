"""
Conversation, not just answers: the free advisor's small-talk layer -- how are you, who are you, what can you do,
complaints, goodbyes, plain "ok / ha" acknowledgements, and a helpful reply when it didn't understand -- in uz / ru /
en, addressing a signed-in customer by first name. Runs before product logic only for short messages that are
clearly conversational, so a real question ("sen kimsan, kreatin nima?") still reaches the expert answers.
"""
from __future__ import annotations

import random
import re

from apps.assistant.infrastructure.advisor import nlu

# intent -> stems (word-prefix match on the normalized Latin + Cyrillic text, like nlu)
TALK: dict[str, tuple[str, ...]] = {
    "how_are_you": ("qalaysiz", "qalesan", "qalesiz", "qandaysiz", "qandaysan", "yaxshimisiz", "ishlar qalay", "как дела", "как вы", "как ты", "how are you", "how's it going", "how are u"),
    "who": ("sen kimsan", "siz kimsiz", "kimsan", "kimsiz", "bot misan", "botmisan", "robot", "odammisan", "odam misan", "ты кто", "кто ты", "вы кто", "кто вы", "ты бот", "who are you", "are you a bot", "are you human", "are you real"),
    "abilities": ("nima qila olasan", "nima qila olasiz", "nimalar qila", "qanday yordam", "nimaga yordam", "что умеешь", "что ты умеешь", "чем можешь помочь", "чем поможешь", "what can you do", "how can you help", "what do you do"),
    "complaint": ("yomon", "ishlamayapti", "ishlamaydi", "jahlim", "achchiq", "norozi", "aldad", "aldash", "kech qoldi", "kelmadi", "shikoyat", "плохо", "ужасно", "не работает", "обман", "жалоб", "недоволен", "не пришел", "не пришёл", "bad service", "terrible", "not working", "complain", "scam", "didn't arrive", "angry"),
    # feelings: answered with empathy first, then something useful
    "price": ("qimmat", "qimmatku", "qimmatroq", "pulim yo'q", "pulim yetmaydi", "arzonroq yo'q", "arzonrog'i", "дорого", "дороговато", "нет денег", "дешевле нет", "too expensive", "expensive", "can't afford", "cheaper"),
    "down": ("charchadim", "charchagan", "motivatsiya", "kayfiyatim yo'q", "kayfiyat yo'q", "natija yo'q", "natija bermayapti", "tashlab qo'ymoqchi", "zerikdim", "xafa",
             "устал", "нет мотивации", "нет результата", "не получается", "грустно", "хочу бросить", "tired", "no motivation", "no results", "give up", "demotivated", "sad"),
    "bye": ("xayr", "hayr", "ko'rishguncha", "salomat bo'ling", "пока", "до свидания", "всего доброго", "bye", "goodbye", "see you"),
    "ack": ("ok", "okay", "xo'p", "xop", "mayli", "tushunarli", "tushundim", "ha", "yo'q", "yoq", "ладно", "понятно", "хорошо", "ок", "да", "нет", "got it", "fine", "yes", "no", "sure", "cool"),
    "guides": ("maslahatlar markazi", "центр советов", "advice centre", "advice center", "maqolalar", "статьи", "articles"),
    "praise": ("zo'r", "zor", "ajoyib", "barakalla", "malades", "молодец", "супер", "отлично", "круто", "great", "awesome", "nice", "cool bot", "good job"),
}

R = {
    "how_are_you": {
        "uz": ["Rahmat{name_c}, yaxshi! Sizga yordam berishga tayyorman 💪 Bugun nima bilan shug'ullanamiz — massa, ozish, chidamlilik yoki vitaminlar?",
               "Zo'r, rahmat{name_c}! O'zingiz yaxshimisiz? Mashg'ulotlar qalay ketyapti — qanday maqsad sari harakat qilyapsiz?"],
        "ru": ["Спасибо{name_c}, всё отлично! Готов помочь 💪 Чем займёмся сегодня — масса, похудение, выносливость или витамины?",
               "Хорошо, спасибо{name_c}! А как ваши тренировки? Какую цель сейчас ставите?"],
        "en": ["Doing great, thanks{name_c}! Ready to help 💪 What are we working on today — muscle, fat loss, endurance or vitamins?",
               "All good, thanks{name_c}! How's your training going — what goal are you chasing right now?"],
    },
    "who": {
        "uz": ["Men NutriZone'ning AI maslahatchisiman — sport ovqatlanishi va vitaminlar bo'yicha yordamchi 🤖💪\n\n"
               "Maqsadingizga mos mahsulot tanlayman, dozalar va qachon ichishni tushuntiraman, narx va filiallardagi qoldiqni aytaman. "
               "Murakkab holatlarda yoki buyurtma muammosida sizni jonli operatorga ulayman."],
        "ru": ["Я AI-консультант NutriZone — помощник по спортивному питанию и витаминам 🤖💪\n\n"
               "Подберу продукты под вашу цель, объясню дозировки и когда принимать, подскажу цены и наличие в филиалах. "
               "В сложных случаях или по проблемам с заказом соединю с живым оператором."],
        "en": ["I'm NutriZone's AI advisor — your sports nutrition and vitamin helper 🤖💪\n\n"
               "I pick products for your goal, explain doses and timing, and tell you prices and stock at our branches. "
               "For tricky cases or order problems I'll put you through to a person."],
    },
    "abilities": {
        "uz": ["Mana nimalarda yordam bera olaman:\n• **Shaxsiy tanlov** — bo'y, vazn, yosh va maqsadingizga ko'ra to'plam va kunlik oqsil/kaloriya\n"
               "• **Qo'llash** — kreatin, protein, vitaminlar qanday va qachon ichiladi\n• **Farqlar** — izolyat yoki konsentrat, BCAA yoki EAA\n"
               "• **Narx va qoldiq** — qaysi filialda bor\n• **Yetkazish, to'lov, coinlar** va buyurtma savollari\n\nBoshlash uchun maqsadingizni yozing 🙂"],
        "ru": ["Вот с чем помогу:\n• **Персональный подбор** — набор и суточная норма белка/калорий по росту, весу, возрасту и цели\n"
               "• **Приём** — как и когда пить креатин, протеин, витамины\n• **Разница** — изолят или концентрат, BCAA или EAA\n"
               "• **Цены и наличие** — в каком филиале есть\n• **Доставка, оплата, коины** и вопросы по заказу\n\nНапишите свою цель — начнём 🙂"],
        "en": ["Here's what I can help with:\n• **Personal picks** — a stack and daily protein/calories from your height, weight, age and goal\n"
               "• **How to take it** — creatine, protein, vitamins: how and when\n• **Differences** — isolate vs concentrate, BCAA vs EAA\n"
               "• **Prices and stock** — which branch has it\n• **Delivery, payment, coins** and order questions\n\nTell me your goal to get started 🙂"],
    },
    "complaint": {
        "uz": ["Noqulaylik uchun uzr so'raymiz{name_c} 🙏 Bu holatni tezda hal qilishimiz kerak. Iltimos, nima bo'lganini qisqacha yozing (buyurtma raqami bo'lsa — u ham), "
               "yoki to'g'ridan-to'g'ri operator bilan bog'laning: {contacts}"],
        "ru": ["Приносим извинения{name_c} 🙏 Давайте быстро решим вопрос. Коротко опишите, что случилось (и номер заказа, если есть), "
               "или свяжитесь с оператором напрямую: {contacts}"],
        "en": ["We're sorry about that{name_c} 🙏 Let's sort it out quickly. Tell me briefly what happened (and the order number if you have one), "
               "or reach a person directly: {contacts}"],
    },
    "price": {
        "uz": ["Tushunaman{name_c}, sport ozuqasi arzon emas 🙏 Lekin tejashning yo'llari bor:\n"
               "• **Arzonroq analoglar** — tarkibi deyarli bir xil, narxi 30–50% past (masalan kreatin monohidrat har qanday brendda bir xil ishlaydi)\n"
               "• **Aksiyalar** — chegirmadagi mahsulotlar: {site}/products?sale=1\n"
               "• **NutriZone Coins** — har xariddan bonus, keyingi xaridda to'lovga ishlatiladi\n"
               "• **Kattaroq qadoq** — porsiya narxi ancha arzon chiqadi\n\nByudjetingizni yozing (masalan **«300 minggacha protein»**) — shunga mosini topaman 💪"],
        "ru": ["Понимаю{name_c}, спортпит недешёвый 🙏 Но сэкономить можно:\n"
               "• **Доступные аналоги** — почти тот же состав на 30–50% дешевле (креатин моногидрат работает одинаково у любого бренда)\n"
               "• **Акции** — товары со скидкой: {site}/ru/products?sale=1\n"
               "• **NutriZone Coins** — бонусы с каждой покупки, можно оплатить ими следующую\n"
               "• **Большая упаковка** — порция выходит заметно дешевле\n\nНапишите бюджет (например **«протеин до 300 тысяч»**) — подберу 💪"],
        "en": ["I get it{name_c} — supplements aren't cheap 🙏 A few ways to save:\n"
               "• **Budget alternatives** — nearly the same formula for 30–50% less (creatine monohydrate works the same from any brand)\n"
               "• **Deals** — products on sale: {site}/en/products?sale=1\n"
               "• **NutriZone Coins** — earned on every order, spend them on the next one\n"
               "• **Bigger tubs** — a much lower price per serving\n\nTell me your budget (e.g. **\"protein under 300k\"**) and I'll find a match 💪"],
    },
    "down": {
        "uz": ["Bu holat hammada bo'ladi{name_c} — siz yolg'iz emassiz 🤝 Natija sekin keladi, lekin keladi.\n"
               "• **Uyqu** 7–8 soat — tiklanishning 50%i shu\n• **Oqsil** har kg vaznga 1,6–2 g\n• **Kichik maqsad** — har hafta bitta yaxshilanish\n"
               "• **Dam olish haftasi** — 6–8 haftada bir yengilroq hafta charchoqni ketkazadi\n\n"
               "Maqsadingiz va bo'y/vazningizni yozing — rejangizni birga ko'rib chiqamiz 💪🔥"],
        "ru": ["Такое бывает у всех{name_c} — вы не один 🤝 Результат приходит медленно, но приходит.\n"
               "• **Сон** 7–8 часов — половина восстановления\n• **Белок** 1,6–2 г на кг веса\n• **Маленькие цели** — одно улучшение в неделю\n"
               "• **Разгрузочная неделя** раз в 6–8 недель снимает усталость\n\nНапишите цель, рост и вес — разберём ваш план вместе 💪🔥"],
        "en": ["Everyone hits this{name_c} — you're not alone 🤝 Progress is slow, but it comes.\n"
               "• **Sleep** 7–8 hours — half of recovery\n• **Protein** 1.6–2 g per kg of body weight\n• **Small goals** — one improvement a week\n"
               "• **Deload week** every 6–8 weeks clears the fatigue\n\nTell me your goal, height and weight — let's look at your plan together 💪🔥"],
    },
    "bye": {
        "uz": ["Xayr{name_c}! Mashg'ulotlaringizga omad 💪 Savol tug'ilsa, men shu yerdaman.", "Ko'rishguncha{name_c}! Sog'lom bo'ling, kerak bo'lsa yozing 🙂"],
        "ru": ["До встречи{name_c}! Удачных тренировок 💪 Если появятся вопросы — я здесь.", "Всего доброго{name_c}! Будьте здоровы, пишите, если что 🙂"],
        "en": ["Bye{name_c}! Good luck with your training 💪 I'm here whenever you need me.", "See you{name_c}! Stay healthy, and message me anytime 🙂"],
    },
    "ack": {
        "uz": ["Yaxshi 🙂 Yana nima bilan yordam beray? Masalan, maqsadingiz uchun mahsulot tanlash yoki qanday ichishni tushuntirish."],
        "ru": ["Хорошо 🙂 Чем ещё помочь? Например, подобрать продукт под цель или объяснить, как его принимать."],
        "en": ["Great 🙂 What else can I help with? I can pick a product for your goal or explain how to take it."],
    },
    "praise": {
        "uz": ["Rahmat{name_c}, xursandman! 😊 Yana savol bo'lsa, bemalol yozing."],
        "ru": ["Спасибо{name_c}, приятно! 😊 Если будут вопросы — пишите."],
        "en": ["Thank you{name_c}, glad to help! 😊 Ask me anything else."],
    },
    "guides": {
        "uz": ["📚 **Maslahatlar markazi** — kreatin, protein, vitaminlar, ozish va massa olish bo'yicha 60 dan ortiq aniq javob: {site}/guides\n\nYoki savolingizni shu yerga yozing — darhol javob beraman."],
        "ru": ["📚 **Центр советов** — более 60 точных ответов о креатине, протеине, витаминах, похудении и наборе массы: {site}/ru/guides\n\nИли задайте вопрос здесь — отвечу сразу."],
        "en": ["📚 **Advice centre** — 60+ clear answers on creatine, protein, vitamins, fat loss and muscle gain: {site}/en/guides\n\nOr just ask me here — I'll answer right away."],
    },
    "unclear": {
        "uz": ["Kechirasiz, savolingizni to'liq tushunmadim 🤔 Boshqacha yozib ko'ring yoki quyidagilardan birini tanlang. Masalan: **«80 kg, massa olmoqchiman»**, **«kreatin qanday ichiladi»**, **«D vitamini qancha kerak»**."],
        "ru": ["Извините, не совсем понял вопрос 🤔 Попробуйте сформулировать иначе или выберите вариант ниже. Например: **«80 кг, хочу набрать массу»**, **«как пить креатин»**, **«сколько витамина D нужно»**."],
        "en": ["Sorry, I didn't quite get that 🤔 Try rephrasing, or pick one of the options below. For example: **\"80 kg, I want to build muscle\"**, **\"how to take creatine\"**, **\"how much vitamin D\"**."],
    },
}

CHIPS = {
    "uz": ["Menga mahsulot tanlab bering", "Kreatin qanday ichiladi?", "Maslahatlar markazi", "Operator bilan bog'lanish"],
    "ru": ["Подберите мне продукт", "Как принимать креатин?", "Центр советов", "Связаться с оператором"],
    "en": ["Pick a product for me", "How to take creatine?", "Advice centre", "Talk to a person"],
}

PRICE_CHIPS = {
    "uz": ["Aksiyadagi mahsulotlar", "Arzon kreatin", "300 minggacha protein", "Coinlar qanday ishlaydi?"],
    "ru": ["Товары со скидкой", "Недорогой креатин", "Протеин до 300 тысяч", "Как работают коины?"],
    "en": ["Products on sale", "Cheap creatine", "Protein under 300k", "How do coins work?"],
}

MAX_WORDS = 7  # longer messages are questions, not small talk


def _matches(text: str, stems) -> bool:
    """Word-prefix match, but a stem of 3 letters or fewer must be the whole word ("zor" is praise, "Zorvex" is a brand)."""
    short = [s for s in stems if len(s) <= 3]
    return nlu._has(text, [s for s in stems if len(s) > 3]) or any(re.search(rf"(?<![\w']){re.escape(s)}(?![\w'])", text) for s in short)


def _exact_short(text: str, words) -> bool:
    """"ok", "ha", "да" -- only when that's (almost) the whole message, never a word inside a question."""
    t = re.sub(r"[!?.,)( ]+", " ", text).strip()
    return t in words or (len(t.split()) <= 2 and t.split()[0] in words if t else False)


def intent(text: str) -> str | None:
    t = nlu.normalize(text)
    if not t or len(t.split()) > MAX_WORDS:
        return None
    both = f"{t} {t.translate(nlu.LATIN_FROM_CYR)}"
    if nlu.concepts_in(both):  # "yomon emas, kreatin nima uchun kerak?" is a product question, not small talk
        return None
    for key in ("guides", "price", "down", "complaint", "who", "abilities", "how_are_you", "bye", "praise"):
        if _matches(both, TALK[key]):
            return key
    if _exact_short(t, set(TALK["ack"])):
        return "ack"
    return None


def reply(key: str, loc: str, name: str = "", contacts: str = "") -> tuple[str, list[str]]:
    from django.conf import settings

    loc = loc if loc in ("uz", "ru", "en") else "uz"
    name_c = f", {name}" if name else ""
    site = (getattr(settings, "FRONTEND_URL", "") or "https://nutrizone.uz").rstrip("/")
    text = random.choice(R[key][loc]).format(name_c=name_c, contacts=contacts, site=site)
    chips = [] if key in ("bye",) else PRICE_CHIPS[loc] if key == "price" else CHIPS[loc]
    return text, chips


def looks_like_a_sentence(text: str) -> bool:
    """A real sentence that matched nothing (so the catalogue search would answer "nothing found for <the whole sentence>")."""
    return len(nlu.normalize(text).split()) >= 4
