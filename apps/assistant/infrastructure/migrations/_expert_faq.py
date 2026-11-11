"""
Expert knowledge, part 5: everyday shopper questions the live advisor answered off-topic on 2026-11-11 -- storing an
opened tub, creatine with coffee, whether a gainer makes you fat, protein on rest days, whether protein alone makes
you fat, paying in instalments. Data for migration 0012.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("usage", 65, "Ochilgan qadoqni saqlash va yaroqlilik muddati",
     "protein ochilgandan keyin qancha saqlanadi\nochilgan proteinni qanday saqlash kerak\nyaroqlilik muddati o'tgan protein ichsa bo'ladimi\nсколько хранится открытый протеин\nкак хранить протеин\nhow long does protein last after opening",
     "saqlash, saqlanadi, ochilgan, ochilgandan, yaroqlilik, muddati, srok, хранить, хранится, срок, годности, открытый, storage, store, expiry, opened",
     "📦 **Saqlash qoidalari:**\n"
     "• Quruq, salqin joyda (25 °C dan past), quyosh tushmaydigan joyda; muzlatkich shart emas — namlik paydo bo'ladi.\n"
     "• Qopqoq yoki zip-qulfni har safar mahkam yoping, quruq qoshiq ishlating.\n"
     "• Ochilgandan keyin **3–6 oy** ichida ishlatish tavsiya etiladi; asosiy sana — qadoqdagi yaroqlilik muddati.\n"
     "• Kukun qotib qolsa, hidi yoki rangi o'zgarsa — ichmang.\n\n"
     "Saytimizdagi har bir mahsulot sahifasida yaroqlilik muddati ko'rsatiladi 🙂",
     "📦 **Как хранить:**\n"
     "• В сухом прохладном месте (до 25 °C), без солнца; холодильник не нужен — появится влага.\n"
     "• Каждый раз плотно закрывайте крышку или zip-замок, берите сухую ложку.\n"
     "• После вскрытия лучше использовать за **3–6 месяцев**; главное — срок годности на упаковке.\n"
     "• Если порошок слипся, изменились запах или цвет — не пейте.\n\n"
     "Срок годности указан на странице каждого товара у нас на сайте 🙂",
     "📦 **How to store it:**\n"
     "• Somewhere dry and cool (below 25 °C), out of the sun; no fridge — it brings moisture.\n"
     "• Close the lid or zip tightly every time and use a dry scoop.\n"
     "• Once opened, use it within **3–6 months**; the date on the pack is what counts.\n"
     "• If the powder clumps hard or the smell or colour changes — don't drink it.\n\n"
     "Every product page on our site shows the expiry date 🙂"),
    ("usage", 60, "Kreatinni kofe bilan ichish",
     "kofe bilan kreatin ichsa bo'ladimi\nkreatin va kofein birga\nкреатин с кофе\nможно ли креатин с кофеином\ncreatine with coffee",
     "kofe, kofein, qahva, кофе, кофеин, coffee, caffeine, kreatin, креатин, creatine",
     "☕ **Ha, bo'ladi.** Eski bitta tadqiqot kofein kreatin ta'sirini kamaytirishi mumkinligini aytgan, lekin keyingi tadqiqotlar odatdagi miqdorda (kuniga 1–3 chashka) sezilarli farq topmagan.\n"
     "• Kreatinni kuniga 3–5 g, istalgan vaqtda ichishda davom eting.\n"
     "• Oshqozon bezovta bo'lsa — kreatinni ovqat bilan, kofeni alohida iching.\n"
     "• Kofeinni (pre-workout bilan birga) kuniga ~400 mg dan oshirmang va uxlashdan 6 soat oldin to'xtating.",
     "☕ **Да, можно.** Одно старое исследование предполагало, что кофеин снижает эффект креатина, но более поздние работы при обычных дозах (1–3 чашки в день) заметной разницы не нашли.\n"
     "• Продолжайте пить креатин по 3–5 г в день, в любое время.\n"
     "• Если беспокоит желудок — креатин с едой, кофе отдельно.\n"
     "• Кофеин (вместе с предтреником) — не больше ~400 мг в день и не позже чем за 6 часов до сна.",
     "☕ **Yes, that's fine.** One old study suggested caffeine might blunt creatine, but later studies at normal intakes (1–3 cups a day) found no meaningful difference.\n"
     "• Keep taking 3–5 g of creatine a day, at any time.\n"
     "• If your stomach complains, take creatine with food and the coffee separately.\n"
     "• Keep caffeine (pre-workout included) under ~400 mg a day and stop 6 hours before sleep."),
    ("product", 60, "Gainer semirtiradimi",
     "gainer semirtiradimi\ngainerdan yog' bosadimi\nqorin chiqib qoladimi gainerdan\nгейнер толстит\nот гейнера будет жир\ndoes a mass gainer make you fat",
     "gainer, geyner, гейнер, semir, semirtiradimi, yog', qorin, толстит, жир, fat",
     "⚖️ Gainer — bu shunchaki **ko'p kaloriya** (uglevod + oqsil). U yog' ham, mushak ham bo'lishi mumkin — natija sizga bog'liq:\n"
     "• **Mashq qilsangiz** va kunlik ehtiyojdan +250…500 kkal ortiq yesangiz — vazn asosan mushak hisobiga oshadi.\n"
     "• **Mashq qilmasangiz** yoki to'liq porsiyani ovqatga qo'shimcha ichsangiz — yog' bosadi.\n"
     "• Yarim porsiyadan boshlang, haftasiga 0,25–0,5 kg qo'shilishni kuzating; tezroq oshsa — porsiyani kamaytiring.\n"
     "• Ishtahangiz yaxshi va ovqatdan kaloriya yetarli bo'lsa — gainer o'rniga oddiy protein yetadi.\n\n"
     "Bo'y, vazn va yoshingizni yozing — kunlik kaloriyangizni hisoblab beraman 💪",
     "⚖️ Гейнер — это просто **много калорий** (углеводы + белок). Они станут мышцами или жиром — зависит от вас:\n"
     "• **Тренируетесь** и едите на 250–500 ккал больше нормы — вес растёт в основном за счёт мышц.\n"
     "• **Не тренируетесь** или пьёте полную порцию сверх обычной еды — будет жир.\n"
     "• Начните с половины порции, следите за прибавкой 0,25–0,5 кг в неделю; растёт быстрее — уменьшите порцию.\n"
     "• Если аппетит хороший и калорий из еды хватает — вместо гейнера достаточно обычного протеина.\n\n"
     "Напишите рост, вес и возраст — посчитаю вашу суточную калорийность 💪",
     "⚖️ A gainer is simply **a lot of calories** (carbs + protein). Whether they become muscle or fat is up to you:\n"
     "• **If you train** and eat 250–500 kcal above your needs, the weight you gain is mostly muscle.\n"
     "• **If you don't train**, or drink a full serving on top of normal meals, you'll gain fat.\n"
     "• Start with half a serving and aim for 0.25–0.5 kg a week; gaining faster — cut the serving.\n"
     "• If your appetite is good and food covers your calories, plain protein is enough instead of a gainer.\n\n"
     "Tell me your height, weight and age and I'll work out your daily calories 💪"),
    ("usage", 55, "Mashg'ulotsiz kunlarda protein",
     "dam olish kuni protein ichish kerakmi\nmashg'ulot bo'lmagan kuni protein\nпротеин в дни отдыха\nнужен ли протеин без тренировки\nprotein on rest days",
     "dam olish, mashg'ulotsiz, rest, отдых, отдыха, без тренировки, protein, протеин",
     "😴 **Ha, ichish mumkin va foydali.** Mushak dam olish kunlari tiklanadi va o'sadi, shuning uchun muhimi — har kuni **kunlik oqsil me'yori** (1,6–2 g/kg).\n"
     "• Ovqatdan yetarli oqsil olsangiz — protein shart emas.\n"
     "• Yetmasa — 1 porsiya (20–30 g) ertalab yoki ovqatlar orasida.\n"
     "• Kreatin esa dam olish kunlari ham kuniga 3–5 g ichiladi.",
     "😴 **Да, можно и полезно.** Мышцы восстанавливаются и растут именно в дни отдыха, поэтому важна **суточная норма белка** каждый день (1,6–2 г/кг).\n"
     "• Если белка из еды хватает — протеин не обязателен.\n"
     "• Не хватает — 1 порция (20–30 г) утром или между приёмами пищи.\n"
     "• Креатин в дни отдыха тоже по 3–5 г.",
     "😴 **Yes — and it helps.** Muscles recover and grow on rest days, so what matters is your **daily protein target** every day (1.6–2 g/kg).\n"
     "• If food covers it, a shake isn't required.\n"
     "• If not — one serving (20–30 g) in the morning or between meals.\n"
     "• Creatine stays at 3–5 g on rest days too."),
    ("product", 55, "Proteindan semirib ketish mumkinmi",
     "proteindan semirib ketamanmi\nprotein semirtiradimi\nот протеина толстеют\nпротеин полнит\ndoes protein make you fat",
     "semir, semirtiradimi, semirib, protein, протеин, толстеют, полнит, fat, weight",
     "🥤 Protein o'zi semirtirmaydi — bir porsiya atigi **100–130 kkal**, bu bitta yogurtga teng. Vazn faqat umumiy kaloriya ko'p bo'lsa oshadi.\n"
     "• Ozish paytida protein aksincha yordam beradi: to'qlik beradi va mushakni saqlaydi.\n"
     "• Suv bilan aralashtiring (sut +100 kkal qo'shadi) va uni ovqat o'rniga yoki kechki shirinlik o'rniga iching.",
     "🥤 Протеин сам по себе не полнит — порция всего **100–130 ккал**, как один йогурт. Вес растёт только при избытке калорий в целом.\n"
     "• При похудении протеин, наоборот, помогает: даёт сытость и сохраняет мышцы.\n"
     "• Разводите водой (молоко добавит +100 ккал) и пейте вместо перекуса или вечернего сладкого.",
     "🥤 Protein doesn't make you fat by itself — a serving is just **100–130 kcal**, about one yoghurt. Weight goes up only when total calories are too high.\n"
     "• When cutting, protein actually helps: it keeps you full and protects muscle.\n"
     "• Mix it with water (milk adds ~100 kcal) and use it instead of a snack or an evening sweet."),
    ("policy", 70, "Bo'lib to'lash (nasiya)",
     "nasiya bormi\nbo'lib to'lash mumkinmi\nmuddatli to'lov\nрассрочка есть\nможно в рассрочку\ninstallments\npay later",
     "nasiya, bo'lib, muddatli, рассрочка, рассрочку, installment, installments, later",
     "💳 Bo'lib to'lash (nasiya) imkoniyati va shartlarini operatorimiz aniq aytib beradi — chatga yoki do'konga yozing.\n"
     "Hozir ishlayotgan to'lov usullari rasmiylashtirishning **To'lov** bosqichida ko'rinadi. Tejash uchun: **NutriZone Coins** bilan buyurtmaning bir qismini to'lash va **aksiyadagi** mahsulotlar 🔥",
     "💳 Про рассрочку и её условия точно подскажет оператор — напишите в чат или в магазин.\n"
     "Доступные способы оплаты видны на шаге **Оплата** при оформлении. Чтобы сэкономить: оплачивайте часть заказа **NutriZone Coins** и смотрите **товары со скидкой** 🔥",
     "💳 Our operator will tell you exactly whether instalments are available and on what terms — message the chat or the store.\n"
     "The payment methods that work right now are shown at the **Payment** step of checkout. To save: pay part of an order with **NutriZone Coins** and check the **deals** 🔥"),
]
