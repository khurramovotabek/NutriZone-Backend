"""
Expert knowledge, part 7: practical everyday questions -- what to buy first for mass or for fat loss, how long a tub
lasts and what it costs a month, protein recipes, lumps and foam, L-carnitine forms, choosing a flavour. Data for
migration 0014.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("product", 75, "Massa olish uchun to'plam: nimadan boshlash",
     "massa olish uchun nima olay\nmassa uchun to'plam\nmassaga nima kerak birinchi\nчто купить для набора массы\nнабор для массы с чего начать\nbulking stack what to buy first",
     "massa, to'plam, stak, boshlash, birinchi, набор, массы, стек, с чего начать, bulking, stack, mass, first",
     "💪 **Massa uchun to'plam — muhimlik tartibida:**\n\n"
     "1️⃣ **Protein** (kuniga 1–2 porsiya) — kunlik oqsilni yopadi (1,8–2,2 g/kg). Eng birinchi.\n"
     "2️⃣ **Kreatin monogidrat** (3–5 g har kuni) — kuch va hajmni eng arzon, isbotlangan usulda oshiradi.\n"
     "3️⃣ **Geyner** — faqat juda ozg'in bo'lsangiz va ovqat bilan kaloriya yeta olmasangiz.\n"
     "4️⃣ **Omega-3 va multivitamin** — tiklanish va umumiy salomatlik uchun qo'shimcha.\n\n"
     "💰 Byudjet kam bo'lsa: avval protein + kreatin (oyiga taxminan 1 banka protein va ½ banka kreatin). Pre-workout, BCAA — ixtiyoriy.\n\n"
     "🍽 Asosiysi baribir ovqat: kaloriya profitsiti +300–500 kkal, haftasiga +0,25–0,5 kg. Bo'y, vazn, yoshingizni yozsangiz — aynan sizga to'plam va dozani hisoblab beraman.",
     "💪 **Набор для массы — по важности:**\n\n"
     "1️⃣ **Протеин** (1–2 порции в день) — закрывает суточный белок (1,8–2,2 г/кг). В первую очередь.\n"
     "2️⃣ **Креатин моногидрат** (3–5 г ежедневно) — самый дешёвый и доказанный способ добавить силу и объём.\n"
     "3️⃣ **Гейнер** — только если вы очень худой и не добираете калории едой.\n"
     "4️⃣ **Омега-3 и мультивитамины** — дополнительно, для восстановления и здоровья.\n\n"
     "💰 Мало бюджета: сначала протеин + креатин (примерно 1 банка протеина и ½ банки креатина в месяц). Предтрен, BCAA — по желанию.\n\n"
     "🍽 Главное всё равно еда: профицит +300–500 ккал, +0,25–0,5 кг в неделю. Напишите рост, вес и возраст — рассчитаю набор и дозы под вас.",
     "💪 **A mass-gain stack — in order of importance:**\n\n"
     "1️⃣ **Protein** (1–2 scoops a day) — covers daily protein (1.8–2.2 g/kg). First.\n"
     "2️⃣ **Creatine monohydrate** (3–5 g daily) — the cheapest, proven way to add strength and size.\n"
     "3️⃣ **Gainer** — only if you're very skinny and can't eat enough calories.\n"
     "4️⃣ **Omega-3 and a multivitamin** — extras for recovery and health.\n\n"
     "💰 Tight budget: protein + creatine first (about 1 tub of protein and ½ tub of creatine a month). Pre-workout and BCAA are optional.\n\n"
     "🍽 Food still matters most: +300–500 kcal surplus, +0.25–0.5 kg a week. Tell me your height, weight and age and I'll work out your stack and doses."),
    ("product", 75, "Ozish (quritish) uchun to'plam",
     "ozish uchun nima olay\nquritish uchun to'plam\nyog' yoqish uchun nima ichay\nчто купить для похудения\nнабор для сушки\ncutting stack what to buy",
     "ozish, quritish, sushka, yog', to'plam, похудение, сушка, жир, набор, cutting, fat loss, stack",
     "🔥 **Ozish uchun to'plam — halol tartibda:**\n\n"
     "1️⃣ **Protein (izolyat yaxshi)** — kaloriya kamayganda mushakni saqlaydi va to'qlik beradi. Kuniga 2,0–2,4 g/kg oqsil.\n"
     "2️⃣ **Kreatin** — quritishda ham kuchni saqlaydi (tarozida +1 kg suv — yog' emas).\n"
     "3️⃣ **Multivitamin, Omega-3** — parhezda yetishmaydiganini to'ldiradi.\n"
     "4️⃣ **L-karnitin yoki termogenik** — ixtiyoriy, kichik yordamchi; o'zi yog' yoqmaydi. Termogeniklarda kofein bor — yurak/bosim muammosida mumkin emas.\n\n"
     "📉 Natijaning 90 % i — **kaloriya defitsiti** (−300…−500 kkal), kuniga 8–10 ming qadam, kuch mashg'uloti va uyqu. Haftasiga −0,5–1 % vazn — sog'lom tezlik.",
     "🔥 **Набор для похудения — честно, по порядку:**\n\n"
     "1️⃣ **Протеин (лучше изолят)** — сохраняет мышцы на дефиците и даёт сытость. 2,0–2,4 г/кг белка в день.\n"
     "2️⃣ **Креатин** — сохраняет силу и на сушке (+1 кг на весах — вода, не жир).\n"
     "3️⃣ **Мультивитамины, Омега-3** — восполняют то, чего не хватает на диете.\n"
     "4️⃣ **L-карнитин или термогеник** — по желанию, небольшой помощник; сам жир не сжигает. В термогениках кофеин — при проблемах с сердцем/давлением нельзя.\n\n"
     "📉 90 % результата — **дефицит калорий** (−300…−500 ккал), 8–10 тысяч шагов, силовые и сон. −0,5–1 % веса в неделю — здоровый темп.",
     "🔥 **A fat-loss stack — honestly, in order:**\n\n"
     "1️⃣ **Protein (isolate is best)** — keeps muscle in a deficit and keeps you full. 2.0–2.4 g/kg protein a day.\n"
     "2️⃣ **Creatine** — keeps strength while cutting (+1 kg on the scale is water, not fat).\n"
     "3️⃣ **Multivitamin, Omega-3** — fill what a diet lacks.\n"
     "4️⃣ **L-carnitine or a thermogenic** — optional, a small helper; it doesn't burn fat by itself. Thermogenics contain caffeine — not with heart or blood-pressure issues.\n\n"
     "📉 90 % of the result is a **calorie deficit** (−300…−500 kcal), 8–10k steps, strength training and sleep. −0.5–1 % of body weight a week is a healthy pace."),
    ("product", 70, "Bir banka qancha vaqtga yetadi va oyiga qancha turadi",
     "protein qancha vaqtga yetadi\nbir banka necha kunga yetadi\noyiga qancha pul ketadi\nна сколько хватит банки протеина\nсколько стоит в месяц\nhow long does a tub last",
     "yetadi, necha kun, oyiga, oylik, xarajat, хватит, сколько дней, в месяц, расход, last, how long, per month, monthly cost",
     "📆 **Bir banka qancha yetadi (taxminan):**\n\n"
     "• Protein 908 g (2 lb), 1 porsiya/kun → ~30 kun; 2 porsiya → ~15 kun.\n"
     "• Protein 2,27 kg (5 lb), 1 porsiya/kun → ~70–75 kun; 2 porsiya → ~35–37 kun.\n"
     "• Kreatin 300 g, 5 g/kun → 60 kun; 3 g/kun → 100 kun.\n"
     "• Geyner 3 kg, 1 porsiya (100–150 g)/kun → 20–30 kun.\n"
     "• BCAA 400 g, 10 g/kun → 40 kun. Multivitamin 60–120 tabletka → 1–4 oy.\n\n"
     "🧮 **Oylik xarajat** = banka narxi ÷ necha kunga yetishi × 30. Katta banka deyarli doim oyiga arzonroq tushadi.\n"
     "Mahsulot nomini yozsangiz, uning porsiyalari bo'yicha aniq hisoblab beraman.",
     "📆 **На сколько хватает банки (примерно):**\n\n"
     "• Протеин 908 г (2 lb), 1 порция/день → ~30 дней; 2 порции → ~15 дней.\n"
     "• Протеин 2,27 кг (5 lb), 1 порция/день → ~70–75 дней; 2 порции → ~35–37 дней.\n"
     "• Креатин 300 г, 5 г/день → 60 дней; 3 г/день → 100 дней.\n"
     "• Гейнер 3 кг, 1 порция (100–150 г)/день → 20–30 дней.\n"
     "• BCAA 400 г, 10 г/день → 40 дней. Мультивитамины 60–120 таблеток → 1–4 месяца.\n\n"
     "🧮 **Расход в месяц** = цена банки ÷ на сколько дней хватает × 30. Большая банка почти всегда выгоднее в месяц.\n"
     "Напишите название товара — посчитаю точно по его порциям.",
     "📆 **How long a tub lasts (roughly):**\n\n"
     "• Protein 908 g (2 lb), 1 scoop/day → ~30 days; 2 scoops → ~15 days.\n"
     "• Protein 2.27 kg (5 lb), 1 scoop/day → ~70–75 days; 2 scoops → ~35–37 days.\n"
     "• Creatine 300 g, 5 g/day → 60 days; 3 g/day → 100 days.\n"
     "• Gainer 3 kg, 1 serving (100–150 g)/day → 20–30 days.\n"
     "• BCAA 400 g, 10 g/day → 40 days. Multivitamin 60–120 tablets → 1–4 months.\n\n"
     "🧮 **Monthly cost** = tub price ÷ days it lasts × 30. A big tub is almost always cheaper per month.\n"
     "Name the product and I'll work it out from its own servings."),
    ("usage", 60, "Protein bilan retseptlar",
     "protein bilan nima tayyorlasa bo'ladi\nprotein retsept\nuyda geyner qanday qilinadi\nрецепты с протеином\nпротеиновые блины\nhomemade gainer recipe\nprotein recipes",
     "retsept, tayyorlash, quymoq, bo'tqa, suli, smuzi, uyda geyner, рецепт, блины, овсянка, смузи, домашний гейнер, recipe, pancakes, oatmeal, smoothie",
     "👨‍🍳 **Protein bilan oson retseptlar:**\n\n"
     "• **Proteinli suli bo'tqa:** 60 g suli + 200 ml suv/sut, pishgach biroz soviting va 1 qoshiq protein aralashtiring (qaynoqqa solsangiz kesaklanadi). ~35 g oqsil.\n"
     "• **Quymoq (pancake):** 1 banan + 2 tuxum + 1 qoshiq protein + 30 g suli uni — yopishmaydigan tovada 2 daqiqadan. ~40 g oqsil.\n"
     "• **Uy geyneri:** 300 ml sut + 1 qoshiq protein + 1 banan + 50 g suli + 1 osh qoshiq yong'oq pastasi — blenderda. ~800 kkal, ~50 g oqsil.\n"
     "• **Smuzi (ozish uchun):** 250 ml suv + 1 qoshiq izolyat + bir hovuch muzlatilgan rezavor + muz. ~150 kkal.\n"
     "• **Proteinli qatiq/tvorog:** 200 g tvorog yoki grek qatig'i + ½ qoshiq protein — kechki ovqat o'rniga.\n\n"
     "💡 Proteinni 60 °C dan issiq suyuqlikka to'g'ridan-to'g'ri solmang: avval ozgina sovuq suvda aralashtiring.",
     "👨‍🍳 **Простые рецепты с протеином:**\n\n"
     "• **Протеиновая овсянка:** 60 г овсянки + 200 мл воды/молока, после варки немного остудить и добавить мерную ложку протеина (в кипяток — комки). ~35 г белка.\n"
     "• **Блины (pancake):** 1 банан + 2 яйца + 1 мерная ложка протеина + 30 г овсяной муки — на антипригарной сковороде по 2 минуты. ~40 г белка.\n"
     "• **Домашний гейнер:** 300 мл молока + 1 ложка протеина + 1 банан + 50 г овсянки + 1 ст. ложка арахисовой пасты — в блендер. ~800 ккал, ~50 г белка.\n"
     "• **Смузи (для похудения):** 250 мл воды + 1 ложка изолята + горсть замороженных ягод + лёд. ~150 ккал.\n"
     "• **Творог с протеином:** 200 г творога или греческого йогурта + ½ ложки протеина — вместо ужина.\n\n"
     "💡 Не сыпьте протеин сразу в жидкость горячее 60 °C: сначала размешайте в небольшом количестве холодной воды.",
     "👨‍🍳 **Easy protein recipes:**\n\n"
     "• **Protein oats:** 60 g oats + 200 ml water/milk; once cooked, cool a little and stir in a scoop of protein (boiling liquid makes lumps). ~35 g protein.\n"
     "• **Pancakes:** 1 banana + 2 eggs + 1 scoop protein + 30 g oat flour — non-stick pan, 2 minutes a side. ~40 g protein.\n"
     "• **Homemade gainer:** 300 ml milk + 1 scoop protein + 1 banana + 50 g oats + 1 tbsp peanut butter — blend. ~800 kcal, ~50 g protein.\n"
     "• **Smoothie (fat loss):** 250 ml water + 1 scoop isolate + a handful of frozen berries + ice. ~150 kcal.\n"
     "• **Protein cottage cheese:** 200 g cottage cheese or Greek yoghurt + ½ scoop protein — instead of dinner.\n\n"
     "💡 Don't add protein straight to liquid hotter than 60 °C: mix it with a little cold water first."),
    ("usage", 55, "Proteinni aralashtirish: kesak va ko'pik",
     "protein kesak bo'lib qoladi\nprotein yaxshi aralashmaydi\nko'pik ko'p bo'ladi\nпротеин комки\nпротеин пенится\nprotein clumps foam",
     "kesak, aralashmaydi, ko'pik, sheyker, комки, пена, не размешивается, шейкер, clumps, lumps, foam, shaker, mix",
     "🥤 **Kesak va ko'piksiz aralashtirish:**\n\n"
     "1. Avval **suyuqlik**, keyin kukun (teskarisi — tagida kesak).\n"
     "2. **Sovuq yoki iliq** suyuqlik (issiqda oqsil ivib qoladi).\n"
     "3. Sheykerda 10–15 soniya kuchli silkiting; sharcha yoki to'r (mesh) bo'lsa yaxshi.\n"
     "4. Ko'pik ko'p bo'lsa — 1–2 daqiqa tindiring yoki kamroq silkiting; izolyat va gidrolizat ko'proq ko'piklanadi — bu normal.\n"
     "5. Qalin bo'lsa — suyuqlikni ko'paytiring (1 porsiyaga 250–350 ml).\n\n"
     "Kukun qopqoq ichida qotib qolsa yoki hidi o'zgarsa — namlik kirgan, uni ichmang.",
     "🥤 **Как размешать без комков и пены:**\n\n"
     "1. Сначала **жидкость**, потом порошок (наоборот — комки на дне).\n"
     "2. **Холодная или тёплая** жидкость (в горячей белок сворачивается).\n"
     "3. Энергично трясите шейкер 10–15 секунд; лучше с шариком или сеткой.\n"
     "4. Много пены — дайте постоять 1–2 минуты или трясите мягче; изолят и гидролизат пенятся сильнее — это нормально.\n"
     "5. Слишком густо — добавьте жидкости (250–350 мл на порцию).\n\n"
     "Если порошок в банке слипся камнем или изменился запах — попала влага, не пейте.",
     "🥤 **Mixing without lumps or foam:**\n\n"
     "1. **Liquid first**, then powder (the other way round leaves lumps at the bottom).\n"
     "2. **Cold or lukewarm** liquid (heat curdles the protein).\n"
     "3. Shake hard for 10–15 seconds; a shaker with a ball or mesh helps.\n"
     "4. Lots of foam — let it sit 1–2 minutes or shake more gently; isolate and hydrolysate foam more — that's normal.\n"
     "5. Too thick — add liquid (250–350 ml a scoop).\n\n"
     "If the powder in the tub turns rock-hard or smells different, moisture got in — don't drink it."),
    ("product", 55, "L-karnitin turlari: tartrat, ALCAR, suyuq",
     "l-karnitin qaysi turi yaxshi\nalcar nima\nsuyuq karnitin yoki kapsula\nкакой l-карнитин лучше\nацетил карнитин что это\nwhich l-carnitine is best",
     "karnitin, tartrat, alcar, atsetil, suyuq, kapsula, карнитин, тартрат, ацетил, жидкий, carnitine, tartrate, acetyl, liquid",
     "🔥 **L-karnitin turlari:**\n\n"
     "• **L-karnitin tartrat (LCLT)** — sport uchun eng ko'p o'rganilgan: tiklanish va mushak og'rig'ini kamaytirishga yordam. 1–2 g/kun.\n"
     "• **Asetil-L-karnitin (ALCAR)** — miyaga yaxshiroq o'tadi: diqqat, charchoq; ozishda ustunligi yo'q. 0,5–1,5 g/kun.\n"
     "• **Suyuq L-karnitin (base)** — tez so'riladi, ta'mi yoqimli, lekin shakar/kaloriyasiga qarang. Kapsula — qulay, shakarsiz.\n\n"
     "⚖️ Halol aytamiz: karnitin **o'zi yog' yoqmaydi** — faqat kaloriya defitsiti va kardio bilan kichik yordam beradi. Yaxshi samara 8–12 hafta muntazam ichganda, ovqat (uglevod) bilan.",
     "🔥 **Виды L-карнитина:**\n\n"
     "• **L-карнитин тартрат (LCLT)** — больше всего изучен в спорте: помогает восстановлению и уменьшает боль в мышцах. 1–2 г/день.\n"
     "• **Ацетил-L-карнитин (ALCAR)** — лучше проникает в мозг: концентрация, усталость; для похудения преимуществ нет. 0,5–1,5 г/день.\n"
     "• **Жидкий L-карнитин (base)** — быстро усваивается, приятный вкус, но смотрите на сахар/калории. Капсулы — удобно, без сахара.\n\n"
     "⚖️ Честно: карнитин **сам жир не сжигает** — лишь немного помогает на дефиците калорий и кардио. Эффект — при приёме 8–12 недель регулярно, с едой (углеводами).",
     "🔥 **Types of L-carnitine:**\n\n"
     "• **L-carnitine tartrate (LCLT)** — the most studied for sport: helps recovery and reduces muscle soreness. 1–2 g/day.\n"
     "• **Acetyl-L-carnitine (ALCAR)** — crosses into the brain better: focus, fatigue; no fat-loss advantage. 0.5–1.5 g/day.\n"
     "• **Liquid L-carnitine (base)** — absorbs fast and tastes nice, but check the sugar/calories. Capsules — handy, sugar-free.\n\n"
     "⚖️ Honestly: carnitine **doesn't burn fat by itself** — it only helps a little alongside a calorie deficit and cardio. Effects show after 8–12 weeks of regular use, with food (carbs)."),
    ("product", 50, "Ta'm tanlash va ta'msiz protein",
     "qaysi ta'm yaxshi\nqaysi ta'mni olay\nta'msiz protein nima uchun\nкакой вкус протеина лучше\nпротеин без вкуса зачем\nwhich flavour is best",
     "ta'm, ta'mli, ta'msiz, shokolad, vanil, qulupnay, вкус, без вкуса, шоколад, ваниль, клубника, flavour, flavor, unflavoured, chocolate, vanilla",
     "😋 **Ta'm tanlash:**\n\n"
     "• **Shokolad** — eng ko'p tanlanadi, suvda ham yaxshi; sut bilan desertga o'xshaydi.\n"
     "• **Vanil** — eng universal: smuzi, bo'tqa, quymoqqa qo'shish uchun qulay.\n"
     "• **Qulupnay / mevali** — yengil, yozda suv bilan yoqimli.\n"
     "• **Cookies & cream, karamel, pista** — shirinroq, \"desert\" sevuvchilarga.\n"
     "• **Ta'msiz** — sof, shirinlashtiruvchisiz: ovqatga, kofega, retseptlarga qo'shish uchun; o'zi ichilganda ta'mi \"sut kukuni\"dek.\n\n"
     "💡 Birinchi marta katta banka olishdan oldin mashhur ta'mni (shokolad/vanil) tanlang — xavf kam. Mahsulot sahifasida mavjud ta'mlar va har biri qaysi filialda borligi ko'rinadi.",
     "😋 **Как выбрать вкус:**\n\n"
     "• **Шоколад** — самый популярный, хорош и на воде; с молоком — как десерт.\n"
     "• **Ваниль** — самый универсальный: в смузи, кашу, блины.\n"
     "• **Клубника / фруктовые** — лёгкие, летом приятны на воде.\n"
     "• **Cookies & cream, карамель, фисташка** — слаще, для любителей «десертов».\n"
     "• **Без вкуса** — чистый, без подсластителей: добавлять в еду, кофе, рецепты; сам по себе на вкус как сухое молоко.\n\n"
     "💡 Покупая большую банку впервые, берите популярный вкус (шоколад/ваниль) — меньше риск. На странице товара видны все вкусы и в каком филиале они есть.",
     "😋 **Choosing a flavour:**\n\n"
     "• **Chocolate** — the most popular, good with water too; with milk it tastes like dessert.\n"
     "• **Vanilla** — the most versatile: smoothies, oats, pancakes.\n"
     "• **Strawberry / fruit** — light, nice with water in summer.\n"
     "• **Cookies & cream, caramel, pistachio** — sweeter, for dessert lovers.\n"
     "• **Unflavoured** — pure, no sweeteners: for food, coffee and recipes; on its own it tastes like milk powder.\n\n"
     "💡 Buying a big tub for the first time? Pick a popular flavour (chocolate/vanilla) — less risk. The product page shows every flavour and which branch has it."),
]
