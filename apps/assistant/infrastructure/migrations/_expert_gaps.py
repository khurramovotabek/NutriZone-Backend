"""
Expert knowledge, part 9 (2026-11-20): the gaps found by replaying every real question asked so far -- belly fat,
"I eat a lot but can't gain", how fast muscle really grows, water with creatine, supplements next to medicines.
Plus the wordings customers actually used for existing entries (QUESTIONS_ADD). Data for migration 0016.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("faq", 48, "Qorin yog'ini yo'qotish",
     "qorin yog'ini qanday yo'qotaman\nqorin yo'qotish uchun nima ichish kerak\nqorinni ozdirish\nqorin uchun yog' yoqiruvchi\nкак убрать живот\nкак убрать жир с живота\nhow to lose belly fat",
     "qorin, qorinni, belly, живот, живота, talia, beli, пресс",
     "🎯 **Faqat qorindan ozish mumkin emas** — yog' butun tanadan bir vaqtda ketadi, qorin esa odatda oxirgi navbatda. Press mashqlari mushakni kuchaytiradi, lekin ustidagi yog'ni yoqmaydi.\n\n"
     "Nima ishlaydi:\n"
     "• **Kaloriya defitsiti** ~300–500 kkal — haftasiga tana vaznining 0,5–1 % i (80 kg → 0,4–0,8 kg).\n"
     "• **Oqsil** 1,8–2,2 g/kg — mushak saqlanadi, to'qlik beradi (protein shu yerda yordam beradi).\n"
     "• **Kuch mashqlari** haftasiga 3 marta + kuniga 8–10 ming qadam.\n"
     "• **Uyqu** 7–8 soat va kam shakar/spirtli ichimlik — qorindagi yog'ga eng ko'p ta'sir qiladi.\n\n"
     "Yog' yoqiruvchi yoki L-karnitin bu rejaga faqat kichik qo'shimcha — ularsiz ham natija bo'ladi, ular bilan ham defitsitsiz bo'lmaydi.",
     "🎯 **Похудеть только в животе нельзя** — жир уходит со всего тела, а с живота обычно в последнюю очередь. Пресс укрепляет мышцы, но жир над ними не сжигает.\n\n"
     "Что работает:\n"
     "• **Дефицит калорий** ~300–500 ккал — 0,5–1 % веса в неделю (80 кг → 0,4–0,8 кг).\n"
     "• **Белок** 1,8–2,2 г/кг — сохраняет мышцы и насыщает (здесь и помогает протеин).\n"
     "• **Силовые** 3 раза в неделю + 8–10 тысяч шагов в день.\n"
     "• **Сон** 7–8 часов, меньше сахара и алкоголя — сильнее всего влияют на жир на животе.\n\n"
     "Жиросжигатели и L-карнитин — лишь небольшое дополнение: без них результат будет, без дефицита — не будет.",
     "🎯 **You can't lose fat from the belly alone** — fat comes off the whole body, and the belly is usually last. Ab exercises strengthen the muscle but don't burn the fat over it.\n\n"
     "What works:\n"
     "• **A calorie deficit** of ~300–500 kcal — 0.5–1 % of body weight a week (80 kg → 0.4–0.8 kg).\n"
     "• **Protein** 1.8–2.2 g/kg — keeps muscle and keeps you full (that's where a protein shake helps).\n"
     "• **Strength training** 3 times a week + 8–10k steps a day.\n"
     "• **Sleep** 7–8 hours, less sugar and alcohol — these move belly fat the most.\n\n"
     "Fat burners or L-carnitine are only a small extra: you'll get results without them, and none without a deficit."),

    ("faq", 48, "Ko'p yeyman, lekin semirmayman",
     "ko'p yeyman lekin semirmayman\nsemira olmayapman\nvazn olmayapman\nozg'inman qanday semiraman\nне могу набрать вес\nмного ем но не поправляюсь\ncan't gain weight\nhardgainer",
     "semir, semira, semirmayman, ozg'in, oriq, хардгейнер, набрать вес, hardgainer, skinny",
     "🍽 Vazn olmaslik deyarli doim **kaloriya yetishmasligi** — «ko'p yeyman» tuyulsa ham. Tekshirib ko'ring:\n\n"
     "1️⃣ **3 kun ovqatni yozing** (ilovada) — ko'pincha 2 000–2 300 kkal chiqadi, sizga esa 2 800–3 300 kerak bo'lishi mumkin.\n"
     "2️⃣ **Kuniga 4–5 marta** ovqatlaning; idishni kattalashtiring; yog'li ovqatlar (yong'oq, yog', pishloq) — kam hajmda ko'p kaloriya.\n"
     "3️⃣ **Ichimlik kaloriya** — eng oson yo'l: geyner yoki sut + banan + yong'oq pastasi + protein kokteyli (600–900 kkal).\n"
     "4️⃣ **Kuch mashqlari** haftasiga 3–4 marta, aks holda ortgan vazn mushak emas, yog' bo'ladi.\n"
     "5️⃣ Haftasiga **+0,25–0,5 kg** — ideal sur'at. 2 hafta tarozi joyida tursa, kuniga +200–300 kkal qo'shing.\n\n"
     "Agar yaxshi ovqatlanib ham vazn kamayayotgan bo'lsa (ayniqsa chanqoq, tez-tez siyish, terlash bilan) — shifokorga (qand, qalqonsimon bez).",
     "🍽 Если вес не растёт, почти всегда **не хватает калорий** — даже если кажется, что едите много. Проверьте:\n\n"
     "1️⃣ **Запишите еду 3 дня** (в приложении) — часто выходит 2 000–2 300 ккал, а вам может быть нужно 2 800–3 300.\n"
     "2️⃣ **4–5 приёмов пищи** в день, тарелка побольше; жирные продукты (орехи, масло, сыр) — много калорий в малом объёме.\n"
     "3️⃣ **Калории в напитках** — самый простой путь: гейнер или молоко + банан + арахисовая паста + протеин (600–900 ккал).\n"
     "4️⃣ **Силовые** 3–4 раза в неделю — иначе прибавка будет жиром, а не мышцами.\n"
     "5️⃣ Идеальный темп — **+0,25–0,5 кг в неделю**. Если 2 недели вес стоит — добавьте +200–300 ккал.\n\n"
     "Если при хорошем питании вес падает (особенно с жаждой, частым мочеиспусканием, потливостью) — к врачу (сахар, щитовидная железа).",
     "🍽 Not gaining is almost always **not enough calories** — even when it feels like a lot. Check:\n\n"
     "1️⃣ **Log your food for 3 days** (in an app) — it's often 2,000–2,300 kcal when you may need 2,800–3,300.\n"
     "2️⃣ Eat **4–5 times a day**, bigger plates; calorie-dense foods (nuts, oil, cheese) give a lot in a small volume.\n"
     "3️⃣ **Drink calories** — the easiest way: a gainer, or milk + banana + peanut butter + protein (600–900 kcal).\n"
     "4️⃣ **Lift** 3–4 times a week, or the extra weight will be fat, not muscle.\n"
     "5️⃣ Aim for **+0.25–0.5 kg a week**. If the scale stalls for 2 weeks, add 200–300 kcal a day.\n\n"
     "If you're losing weight while eating well (especially with thirst, frequent urination, sweating) — see a doctor (blood sugar, thyroid)."),

    ("faq", 47, "Bir oyda qancha mushak qo'shish mumkin",
     "bir oyda qancha massa olsa bo'ladi\n1 oyda 3 kg massa olmoqchiman\noyiga necha kilo mushak\ntez massa olish\nсколько мышц можно набрать за месяц\nhow much muscle can i gain in a month",
     "oyda, oyiga, tez, mushak qo'sh, за месяц, быстро, per month, fast",
     "📈 **Haqiqiy sur'at (sof mushak):**\n"
     "• Yangi boshlovchi (1-yil): oyiga **0,7–1 kg**\n"
     "• 2–3 yillik tajriba: oyiga **0,3–0,5 kg**\n"
     "• Tajribali: oyiga **0,1–0,25 kg**\n\n"
     "Oyiga 3 kg tarozida bo'lishi mumkin, lekin uning ko'pi **yog' va suv** (kreatin, uglevod) bo'ladi. Shuning uchun haftasiga 0,25–0,5 kg qo'shib boring: mushak ko'proq, yog' kamroq.\n\n"
     "Tezlashtiradigan asoslar: progressiv yuklama (har hafta og'irlik yoki takror oshadi), oqsil 1,6–2,2 g/kg, kaloriya +250–400, 7–8 soat uyqu, kreatin 3–5 g. Steroid va SARMlar — sog'liq uchun xavfli, NutriZone ularni sotmaydi.",
     "📈 **Реальный темп (чистые мышцы):**\n"
     "• Новичок (1-й год): **0,7–1 кг** в месяц\n"
     "• 2–3 года стажа: **0,3–0,5 кг** в месяц\n"
     "• Опытный: **0,1–0,25 кг** в месяц\n\n"
     "3 кг за месяц на весах возможно, но большая часть будет **жиром и водой** (креатин, углеводы). Поэтому прибавляйте 0,25–0,5 кг в неделю: больше мышц, меньше жира.\n\n"
     "Что ускоряет: прогрессия нагрузки (каждую неделю больше вес или повторы), белок 1,6–2,2 г/кг, калории +250–400, сон 7–8 часов, креатин 3–5 г. Стероиды и SARM опасны для здоровья — NutriZone их не продаёт.",
     "📈 **The real pace (lean muscle):**\n"
     "• Beginner (year 1): **0.7–1 kg** a month\n"
     "• 2–3 years in: **0.3–0.5 kg** a month\n"
     "• Advanced: **0.1–0.25 kg** a month\n\n"
     "3 kg a month on the scale is possible, but most of it will be **fat and water** (creatine, carbs). So add 0.25–0.5 kg a week: more muscle, less fat.\n\n"
     "What speeds it up: progressive overload (more weight or reps each week), protein 1.6–2.2 g/kg, +250–400 kcal, 7–8 hours of sleep, creatine 3–5 g. Steroids and SARMs are dangerous — NutriZone doesn't sell them."),

    ("usage", 55, "Kreatin bilan qancha suv ichish kerak",
     "kreatin bilan qancha suv ichish kerak\nkreatin ichganda suv\nkreatinni necha ml suvga\nсколько воды пить с креатином\nhow much water with creatine",
     "suv, suvga, ml, воды, вода, water, hydration",
     "💧 **Kreatin va suv:**\n"
     "• 1 porsiya (3–5 g) — **200–300 ml** suv yoki sharbatda aralashtiring, to'liq erishi shart emas.\n"
     "• Kun davomida odatdagidan **+0,5–1 l** ko'proq iching: umumiy mo'ljal — **35–40 ml × tana vazni** (80 kg → ~3 l), issiqda va mashg'ulot kunlari ko'proq.\n"
     "• Siydik och sariq bo'lsa — suv yetarli.\n\n"
     "Kreatin mushak ichiga suv tortadi (shuning uchun dastlab +1–2 kg) — bu yog' yoki shish emas, suvsizlanish ham bermaydi, agar yetarli ichsangiz. Buyrak kasalligi bo'lsa — avval shifokor.",
     "💧 **Креатин и вода:**\n"
     "• 1 порция (3–5 г) — в **200–300 мл** воды или сока, полностью растворяться не обязательно.\n"
     "• За день пейте на **0,5–1 л** больше обычного: ориентир — **35–40 мл × вес** (80 кг → ~3 л), в жару и в дни тренировок больше.\n"
     "• Светло-жёлтая моча — воды достаточно.\n\n"
     "Креатин притягивает воду внутрь мышц (отсюда +1–2 кг в начале) — это не жир и не отёк, и обезвоживания нет, если пить достаточно. При болезнях почек — сначала к врачу.",
     "💧 **Creatine and water:**\n"
     "• Mix 1 serving (3–5 g) in **200–300 ml** of water or juice — it doesn't have to fully dissolve.\n"
     "• Drink **0.5–1 l more** than usual across the day: aim for **35–40 ml × body weight** (80 kg → ~3 l), more in the heat and on training days.\n"
     "• Pale-yellow urine means you're drinking enough.\n\n"
     "Creatine pulls water into the muscle (hence +1–2 kg at first) — that's not fat or bloating, and it doesn't dehydrate you if you drink enough. With kidney disease, ask a doctor first."),

    ("faq", 52, "Dori ichayotganda qo'shimchalar",
     "dori ichyapman kreatin ichsam bo'ladimi\ndori bilan vitamin ichsa bo'ladimi\nqon bosimi dorisi bilan pre workout\nantibiotik bilan rux\nможно ли добавки с лекарствами\nлекарства и витамины вместе\ncan i take supplements with medication",
     "dori, dorilar, tabletka ichyapman, antibiotik, лекарств, препарат, антибиотик, medication, medicine, drugs, pills",
     "💊 **Dori ichayotgan bo'lsangiz — qo'shimchani shifokor bilan kelishing.** Eng ko'p uchraydigan to'qnashuvlar:\n\n"
     "• **Qon suyultiruvchi** (varfarin va b.) — omega-3 ko'p dozada, K2 vitamini, E vitamini, ginkgo — ta'sirini o'zgartiradi.\n"
     "• **Qon bosimi / yurak dorilari** — pre-workout, kofein, yog' yoqiruvchi, yohimbin tavsiya etilmaydi.\n"
     "• **Qalqonsimon bez gormoni** (L-tiroksin) — kalsiy, temir, magniy, multivitamin, soya proteini bilan **kamida 4 soat** oraliq.\n"
     "• **Antibiotiklar** (tetratsiklin, siprofloksatsin) — kalsiy, magniy, rux, temir bilan **2–6 soat** oraliq.\n"
     "• **Antidepressantlar** — 5-HTP, melatonin, ashvagandha, avliyo Ioann o'ti — faqat shifokor ruxsati bilan.\n"
     "• **Qandli diabet dorilari** — geyner va shakarli mahsulotlar qandni oshiradi; B12 metforminda kamayishi mumkin.\n\n"
     "Protein va kreatin ko'pchilik dorilar bilan to'qnashmaydi, lekin buyrak/jigar kasalligida — faqat shifokor ruxsati bilan.",
     "💊 **Если принимаете лекарства — согласуйте добавки с врачом.** Самые частые взаимодействия:\n\n"
     "• **Разжижающие кровь** (варфарин и др.) — высокие дозы омега-3, витамин K2, витамин E, гинкго меняют их действие.\n"
     "• **Лекарства от давления / для сердца** — предтрены, кофеин, жиросжигатели, йохимбин не рекомендуются.\n"
     "• **Гормон щитовидной железы** (L-тироксин) — кальций, железо, магний, мультивитамины, соевый протеин — с интервалом **не менее 4 часов**.\n"
     "• **Антибиотики** (тетрациклины, ципрофлоксацин) — кальций, магний, цинк, железо с интервалом **2–6 часов**.\n"
     "• **Антидепрессанты** — 5-HTP, мелатонин, ашваганда, зверобой — только с разрешения врача.\n"
     "• **Сахароснижающие** — гейнеры и сладкое повышают сахар; на метформине может снижаться B12.\n\n"
     "Протеин и креатин с большинством лекарств не взаимодействуют, но при болезнях почек/печени — только с разрешения врача.",
     "💊 **If you take medication, check supplements with your doctor.** The most common clashes:\n\n"
     "• **Blood thinners** (warfarin etc.) — high-dose omega-3, vitamin K2, vitamin E, ginkgo change how they work.\n"
     "• **Blood-pressure / heart medicines** — pre-workouts, caffeine, fat burners, yohimbine are not recommended.\n"
     "• **Thyroid hormone** (levothyroxine) — keep calcium, iron, magnesium, multivitamins and soy protein **at least 4 hours** apart.\n"
     "• **Antibiotics** (tetracyclines, ciprofloxacin) — calcium, magnesium, zinc, iron **2–6 hours** apart.\n"
     "• **Antidepressants** — 5-HTP, melatonin, ashwagandha, St John's wort only with your doctor's OK.\n"
     "• **Diabetes medicines** — gainers and sugary products raise blood sugar; metformin can lower B12.\n\n"
     "Protein and creatine don't interact with most medicines, but with kidney/liver disease only with your doctor's approval."),
]

QUESTIONS_ADD = {
    "Biotin, soch, teri va tirnoq": "soch to'kilyapti qaysi vitamin\nsochim to'kilyapti nima ichay\nsoch uchun vitamin bormi\nвыпадают волосы какие витамины\nhair falling out which vitamin",
    "Bo'lib to'lash (nasiya)": "nasiya yoki bo'lib to'lash bormi\nkreditga olsa bo'ladimi\nmuddatli to'lovga olsa bo'ladimi",
    "Immunitet uchun nima ichish kerak": "tez-tez shamollayman nima ichay\nshamollaganda nima ichish kerak\nчасто болею что пить",
    "Doimiy charchoq va holsizlik": "doim charchayman nima ichay\nenergiyam yo'q qaysi vitamin\nпостоянная усталость какие витамины",
}
