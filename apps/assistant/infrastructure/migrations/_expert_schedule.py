"""
Expert knowledge, part 8 (2026-11-18): when and how to take things through the day -- an empty stomach, a daily
timetable for mass and for fat loss, what not to combine, creatine / protein / vitamins for women, beginners' first
month. Plus extra ways people actually ask existing questions (QUESTIONS_ADD), found by probing the live advisor.
Data for migration 0015.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("usage", 70, "Och qoringa nima ichsa bo'ladi",
     "ertalab och qoringa nima ichsa bo'ladi\noch qoringa ichish mumkinmi\nnahorga nima ichiladi\nчто пить натощак\nможно ли натощак\nwhat to take on an empty stomach",
     "och qoringa, nahorga, ertalab, натощак, утром, empty stomach, morning",
     "🌅 **Och qoringa (nahorga):**\n"
     "• ✅ Mumkin: **kreatin**, **L-karnitin** (kardiodan oldin), **kollagen**, **probiotik**, **B12**, **temir** (C vitamini bilan, choy/kofesiz), **elektrolitlar**.\n"
     "• ⚠️ Ovqat bilan iching: **omega-3, D3, K2, A, E** (yog'da eriydi — ovqatsiz yomon so'riladi), **multivitamin**, **rux** (och qoringa ko'ngil aynitadi), **magniy**.\n"
     "• ❌ Och qoringa tavsiya qilinmaydi: **pre-workout / kofein** sezgir oshqozonda, **yog' yoqiruvchi** — oldin biror narsa yeng.\n"
     "• Protein nahorga ham bo'ladi — tez nonushta sifatida, lekin ovqat o'rnini to'liq bosmaydi.\n\n"
     "Ertalabki ideal tartib: 1 stakan suv → kreatin 5 g → 20–30 daqiqadan keyin oqsilli nonushta + omega-3 va D3.",
     "🌅 **Натощак:**\n"
     "• ✅ Можно: **креатин**, **L-карнитин** (перед кардио), **коллаген**, **пробиотики**, **B12**, **железо** (с витамином C, без чая/кофе), **электролиты**.\n"
     "• ⚠️ С едой: **омега-3, D3, K2, A, E** (жирорастворимые — без еды усваиваются хуже), **мультивитамины**, **цинк** (натощак тошнит), **магний**.\n"
     "• ❌ Натощак не советуем: **предтрен / кофеин** при чувствительном желудке, **жиросжигатели** — сначала перекусите.\n"
     "• Протеин натощак можно — как быстрый завтрак, но полноценную еду не заменяет.\n\n"
     "Идеальное утро: стакан воды → креатин 5 г → через 20–30 минут белковый завтрак + омега-3 и D3.",
     "🌅 **On an empty stomach:**\n"
     "• ✅ Fine: **creatine**, **L-carnitine** (before cardio), **collagen**, **probiotics**, **B12**, **iron** (with vitamin C, no tea/coffee), **electrolytes**.\n"
     "• ⚠️ With food: **omega-3, D3, K2, A, E** (fat-soluble — poorly absorbed without food), **multivitamins**, **zinc** (nausea on an empty stomach), **magnesium**.\n"
     "• ❌ Not on an empty stomach: **pre-workout / caffeine** if your stomach is sensitive, **fat burners** — eat something first.\n"
     "• Protein in the morning is fine as a quick breakfast, but it doesn't replace a meal.\n\n"
     "Ideal morning: a glass of water → creatine 5 g → 20–30 min later a protein breakfast + omega-3 and D3."),

    ("usage", 72, "Kunlik qabul jadvali: massa uchun",
     "massa uchun kun davomida qachon nima ichaman\nmassa uchun ichish tartibi\nprotein kreatin geyner qachon ichiladi hammasi\nграфик приёма добавок на массу\nкак принимать добавки на массе по времени\nsupplement schedule for bulking",
     "jadval, tartib, kun davomida, massa, график, схема, массу, schedule, bulking, timetable",
     "🗓 **Massa uchun namunaviy kun (mashg'ulot kechqurun):**\n"
     "• **Nonushta:** kreatin 5 g + omega-3 + D3 (ovqat bilan).\n"
     "• **Nonushta va tushlik orasi:** geyner 1 porsiya (vazn sekin oshsa) yoki protein.\n"
     "• **Mashg'ulotdan 30–60 daqiqa oldin:** oddiy ovqat (guruch/non + go'sht) yoki banan + protein.\n"
     "• **Mashg'ulotdan keyin:** protein 1 porsiya (25–30 g) — oddiy ovqat 1–2 soatda bo'lsa, shart emas.\n"
     "• **Uxlashdan oldin:** kazein yoki tvorog + magniy.\n\n"
     "Asosiy qoida: kunlik **kaloriya ortiqchasi** (+300–500 kkal) va **1,6–2,2 g/kg oqsil**. Haftasiga +0,25–0,5 kg — to'g'ri tezlik. Dam olish kuni ham kreatin va protein ichiladi.",
     "🗓 **Пример дня на массе (тренировка вечером):**\n"
     "• **Завтрак:** креатин 5 г + омега-3 + D3 (с едой).\n"
     "• **Между завтраком и обедом:** гейнер 1 порция (если вес растёт медленно) или протеин.\n"
     "• **За 30–60 минут до тренировки:** обычная еда (рис/хлеб + мясо) или банан + протеин.\n"
     "• **После тренировки:** протеин 1 порция (25–30 г) — если нормальная еда через 1–2 часа, не обязательно.\n"
     "• **Перед сном:** казеин или творог + магний.\n\n"
     "Главное: **профицит калорий** (+300–500 ккал) и **1,6–2,2 г белка на кг**. +0,25–0,5 кг в неделю — правильный темп. В дни отдыха креатин и протеин тоже пьются.",
     "🗓 **A sample bulking day (evening workout):**\n"
     "• **Breakfast:** creatine 5 g + omega-3 + D3 (with food).\n"
     "• **Mid-morning:** 1 serving of gainer (if weight rises slowly) or protein.\n"
     "• **30–60 min before training:** a normal meal (rice/bread + meat) or a banana + protein.\n"
     "• **After training:** 1 serving of protein (25–30 g) — optional if a real meal follows within 1–2 h.\n"
     "• **Before bed:** casein or cottage cheese + magnesium.\n\n"
     "The rule: a **calorie surplus** (+300–500 kcal) and **1.6–2.2 g protein per kg**. +0.25–0.5 kg a week is the right pace. Keep creatine and protein on rest days too."),

    ("usage", 72, "Kunlik qabul jadvali: ozish uchun",
     "ozish uchun kun davomida qachon nima ichaman\nozish uchun ichish tartibi\nl karnitin protein qachon ichiladi ozishda\nграфик приёма добавок для похудения\nкак принимать добавки на сушке\nsupplement schedule for fat loss",
     "jadval, tartib, kun davomida, ozish, quritish, график, схема, похудение, сушка, schedule, cutting, fat loss",
     "🗓 **Ozish uchun namunaviy kun:**\n"
     "• **Ertalab:** suv + kreatin 5 g (ozishda ham mushak va kuchni saqlaydi), nonushta bilan omega-3, D3, multivitamin.\n"
     "• **Kardio/mashg'ulotdan 30 daqiqa oldin:** L-karnitin (1–2 g) — xohlasangiz kofein yoki pre-workout (kechki 16:00 dan keyin emas).\n"
     "• **Mashg'ulotdan keyin yoki ovqat o'rniga perekus:** **izolyat** 1 porsiya — oqsil ko'p, kaloriya kam (~110 kkal), to'q tutadi.\n"
     "• **Kechqurun:** magniy; ochlik kuchli bo'lsa kazein.\n\n"
     "Eng muhimi — **kaloriya defitsiti** (−300–500 kkal), **1,8–2,4 g/kg oqsil**, kuniga 8–10 ming qadam. Haftasiga vaznning 0,5–1% kamayishi — mushakni saqlagan holda ozish. Qo'shimchalar yordamchi, sehrli emas.",
     "🗓 **Пример дня для похудения:**\n"
     "• **Утро:** вода + креатин 5 г (на сушке тоже сохраняет мышцы и силу), с завтраком омега-3, D3, мультивитамины.\n"
     "• **За 30 минут до кардио/тренировки:** L-карнитин (1–2 г), по желанию кофеин или предтрен (не после 16:00).\n"
     "• **После тренировки или вместо перекуса:** **изолят** 1 порция — много белка, мало калорий (~110 ккал), долго сытно.\n"
     "• **Вечер:** магний; при сильном голоде казеин.\n\n"
     "Главное — **дефицит калорий** (−300–500 ккал), **1,8–2,4 г белка на кг**, 8–10 тысяч шагов. Минус 0,5–1% веса в неделю — похудение без потери мышц. Добавки помогают, но не творят чудес.",
     "🗓 **A sample fat-loss day:**\n"
     "• **Morning:** water + creatine 5 g (keeps muscle and strength while cutting), omega-3, D3 and a multivitamin with breakfast.\n"
     "• **30 min before cardio/training:** L-carnitine (1–2 g), optionally caffeine or a pre-workout (not after 4 pm).\n"
     "• **After training or as a snack:** 1 serving of **isolate** — lots of protein, few calories (~110 kcal), keeps you full.\n"
     "• **Evening:** magnesium; casein if hunger is strong.\n\n"
     "What matters most: a **calorie deficit** (−300–500 kcal), **1.8–2.4 g protein per kg**, 8–10k steps a day. Losing 0.5–1% of body weight a week keeps the muscle. Supplements help; they are not magic."),

    ("usage", 68, "Qaysi qo'shimchalarni birga ichib bo'lmaydi",
     "qaysi qo'shimchalarni birga ichib bo'lmaydi\nnimani nima bilan ichmaslik kerak\nbirga ichsa zararmi\nчто нельзя принимать вместе\nс чем не сочетается\nwhich supplements not to take together",
     "birga, bilan, aralashtirish, mos kelmaydi, вместе, сочетать, совместимость, together, combine, interaction",
     "🚫 **Birga ichmang (2 soat ajrating):**\n"
     "• **Temir ↔ kalsiy / rux / magniy / choy / kofe / sut** — bir-birining so'rilishini kamaytiradi.\n"
     "• **Rux ↔ kalsiy, temir** (yuqori dozada); uzoq vaqt 40 mg+ rux misni kamaytiradi.\n"
     "• **Bir nechta kofeinli mahsulot** (pre-workout + energetik + kofe + yog' yoqiruvchi) — yurak urishi, bosim, uyqusizlik.\n"
     "• **Ikki multivitamin** yoki multivitamin + alohida A/D katta doza — ortiqcha doza xavfi.\n\n"
     "✅ **Bemalol birga bo'ladi:** protein + kreatin (bitta shakerda), kreatin + kofe, omega-3 + D3 + K2 (ovqat bilan), magniy + B6, C vitamini + temir (so'rilishni oshiradi), protein + geyner.\n\n"
     "Dori ichayotgan bo'lsangiz (qon suyultiruvchi, bosim, qalqonsimon bez, antidepressant) — qo'shimchani shifokor bilan kelishing.",
     "🚫 **Не пейте вместе (разнесите на 2 часа):**\n"
     "• **Железо ↔ кальций / цинк / магний / чай / кофе / молоко** — мешают усвоению друг друга.\n"
     "• **Цинк ↔ кальций, железо** (в больших дозах); долго 40 мг+ цинка снижают медь.\n"
     "• **Несколько продуктов с кофеином** (предтрен + энергетик + кофе + жиросжигатель) — пульс, давление, бессонница.\n"
     "• **Два мультивитамина** или мульти + отдельно большие дозы A/D — риск передозировки.\n\n"
     "✅ **Спокойно сочетаются:** протеин + креатин (в одном шейкере), креатин + кофе, омега-3 + D3 + K2 (с едой), магний + B6, витамин C + железо (улучшает усвоение), протеин + гейнер.\n\n"
     "Если принимаете лекарства (разжижающие кровь, от давления, щитовидки, антидепрессанты) — согласуйте добавки с врачом.",
     "🚫 **Don't take together (keep 2 hours apart):**\n"
     "• **Iron ↔ calcium / zinc / magnesium / tea / coffee / milk** — they block each other's absorption.\n"
     "• **Zinc ↔ calcium, iron** (high doses); 40 mg+ zinc long-term lowers copper.\n"
     "• **Several caffeine products** (pre-workout + energy drink + coffee + fat burner) — heart rate, blood pressure, insomnia.\n"
     "• **Two multivitamins**, or a multi plus big separate A/D doses — overdose risk.\n\n"
     "✅ **Fine together:** protein + creatine (one shaker), creatine + coffee, omega-3 + D3 + K2 (with food), magnesium + B6, vitamin C + iron (better absorption), protein + gainer.\n\n"
     "On medication (blood thinners, blood pressure, thyroid, antidepressants)? Check supplements with your doctor."),

    ("usage", 66, "Birinchi oy: yangi boshlovchi qanday ichadi",
     "endi zalga qatnay boshladim qanday ichaman\nbirinchi marta protein ichaman qanday boshlay\nyangi boshlovchi uchun ichish tartibi\nтолько начал ходить в зал как принимать\nпервый раз протеин как начать\nbeginner how to start taking supplements",
     "boshlovchi, yangi, birinchi marta, endi boshladim, новичок, начинающий, впервые, beginner, first time, start",
     "🌱 **Birinchi oy — oddiy va xavfsiz:**\n"
     "1. **1–2-hafta:** faqat **protein**, kuniga 1 porsiya (mashg'ulotdan keyin yoki nonushtada). Qorin qanday qabul qilishini kuzating; shishsa — izolyatga o'ting.\n"
     "2. **3-hafta:** **kreatin** qo'shing — kuniga 3–5 g, har kuni, yuklamasiz. Suvni ko'paytiring (2,5–3 l).\n"
     "3. **Ozg'in bo'lsangiz** va vazn oshmasa — protein o'rniga yoki qo'shimcha **geyner** 1 porsiya.\n"
     "4. **Pre-workout**ni birinchi oyda shart emas; ichsangiz yarim porsiyadan boshlang.\n\n"
     "Natija 70% ovqat, uyqu (7–9 soat) va muntazam mashg'ulotdan. Bo'y, vazn va maqsadingizni yozsangiz, aniq dozani hisoblab beraman.",
     "🌱 **Первый месяц — просто и безопасно:**\n"
     "1. **1–2 неделя:** только **протеин**, 1 порция в день (после тренировки или на завтрак). Следите за желудком; если вздувает — переходите на изолят.\n"
     "2. **3 неделя:** добавьте **креатин** — 3–5 г каждый день, без загрузки. Пейте больше воды (2,5–3 л).\n"
     "3. **Если вы худой** и вес не растёт — вместо протеина или дополнительно **гейнер** 1 порция.\n"
     "4. **Предтрен** в первый месяц не нужен; если хотите — начните с половины порции.\n\n"
     "Результат на 70% — это еда, сон (7–9 часов) и регулярные тренировки. Напишите рост, вес и цель — рассчитаю точную дозу.",
     "🌱 **First month — simple and safe:**\n"
     "1. **Weeks 1–2:** just **protein**, 1 serving a day (after training or at breakfast). Watch how your stomach takes it; if bloated, switch to an isolate.\n"
     "2. **Week 3:** add **creatine** — 3–5 g every day, no loading. Drink more water (2.5–3 l).\n"
     "3. **If you're skinny** and weight doesn't move — a **gainer** serving instead of or on top of protein.\n"
     "4. **Pre-workout** isn't needed in month one; if you want it, start with half a serving.\n\n"
     "70% of the result is food, sleep (7–9 h) and consistent training. Tell me your height, weight and goal and I'll work out the exact dose."),
]

# existing entry title -> extra lines for `questions` (how real customers phrased it; the old wording kept)
QUESTIONS_ADD = {
    "Kazein — kechki protein": "uyquga yotishdan oldin protein ichsa bo'ladimi\nkechasi protein ichsa bo'ladimi\nuxlashdan oldin nima ichish kerak\nможно ли пить протеин перед сном\nprotein before sleep",
    "Omega-3": "omega 3 qachon ichish kerak\nomega 3 ovqatdan oldin yoki keyin\nbaliq yog'i qachon ichiladi\nомега 3 когда пить до еды или после\nwhen to take omega 3",
    "Yetkazib berish": "necha kunda keladi\ntoshkentga necha kunda keladi\nviloyatga necha kunda yetkaziladi\nqachon olib kelasiz\nза сколько дней доставка\nhow many days delivery",
    "Laktoza ko'tarmaslik va protein": "sut ko'tara olmayman qaysi protein\nsutni ko'tarolmayman protein ichsam bo'ladimi\nmolochniy ichsam qornim og'riydi",
    "Protein (whey) qanday ichiladi": "protin qanday ichiladi\nproteinni kuniga necha marta ichaman\nprotein kuniga necha mahal\nсколько раз в день пить протеин",
    "Kreatin qanday ichiladi": "kreatin mashg'ulotdan oldin yoki keyin\nkreatin qachon ichiladi\nкреатин до или после тренировки\ncreatine before or after workout",
    "Mashg'ulotdan oldin va keyin ovqatlanish": "mashg'ulotdan keyin nima ichish kerak\nmashg'ulotdan oldin nima yeyish kerak\nчто пить после тренировки",
}
