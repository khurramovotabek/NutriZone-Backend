"""
Expert knowledge, part 3: nutrition and training -- calories for gaining and cutting, protein per meal, meal timing,
recovery, special groups (women, 50+, teens, Ramadan), anti-doping. ISSN / ACSM guidance. Data for migration 0006.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("usage", 58, "Kuniga qancha oqsil kerak",
     "kuniga qancha oqsil kerak\nbir martada qancha protein so'riladi\nсколько белка в день\nсколько белка усваивается за раз\nhow much protein per day\nhow much protein per meal",
     "oqsil, protein, gramm, kuniga, bir martada, белок, в день, за раз, protein per day, per meal, g/kg",
     "Mo'ljal (tana vazniga):\n"
     "• Mashq qilmaydigan kattalar: 0,8–1,0 g/kg.\n• Muntazam mashq qiluvchi: 1,4–2,0 g/kg.\n"
     "• Ozish (mushakni saqlash): 1,8–2,4 g/kg.\n• 50 yoshdan oshganlar: kamida 1,2 g/kg.\n\n"
     "Bir ovqatda 20–40 g (taxminan 0,3–0,4 g/kg) oqsil, kuniga 3–5 marta — mushak uchun eng samarali taqsimot. «Bir martada faqat 30 g so'riladi» degan gap mif: ko'proq ham so'riladi, faqat sekinroq.\n\n"
     "Masalan 80 kg, massa olish: ~140–160 g/kun — ovqatdan (go'sht, tuxum, tvorog, dukkaklilar) va 1–2 porsiya protein bilan.",
     "Ориентир (на кг веса):\n"
     "• Без тренировок: 0,8–1,0 г/кг.\n• Регулярные тренировки: 1,4–2,0 г/кг.\n"
     "• Похудение (сохранить мышцы): 1,8–2,4 г/кг.\n• После 50 лет: не меньше 1,2 г/кг.\n\n"
     "20–40 г белка (примерно 0,3–0,4 г/кг) за приём, 3–5 раз в день — самое эффективное распределение для мышц. «За раз усваивается только 30 г» — миф: усваивается и больше, просто медленнее.\n\n"
     "Например, 80 кг на массе: ~140–160 г в день — из еды (мясо, яйца, творог, бобовые) и 1–2 порции протеина.",
     "Targets (per kg of body weight):\n"
     "• Not training: 0.8–1.0 g/kg.\n• Training regularly: 1.4–2.0 g/kg.\n"
     "• Cutting (keeping muscle): 1.8–2.4 g/kg.\n• Over 50: at least 1.2 g/kg.\n\n"
     "20–40 g of protein per meal (about 0.3–0.4 g/kg), 3–5 times a day, is the most effective split for muscle. 'You can only absorb 30 g at once' is a myth — more is absorbed, just more slowly.\n\n"
     "E.g. 80 kg and gaining: ~140–160 g a day — from food (meat, eggs, cottage cheese, legumes) plus 1–2 protein shakes."),

    ("usage", 56, "Massa olish uchun ovqatlanish",
     "massa olish uchun qancha kaloriya\nvazn olish uchun qanday ovqatlanish kerak\nozg'inman semira olmayman\nкак набрать массу питание\nне могу набрать вес\nhow to bulk\ncan't gain weight",
     "massa, vazn olish, semirish, kaloriya, profitsit, набор массы, набрать вес, профицит, калории, bulk, gain weight, hardgainer, ozg'in, худой",
     "Massa uchun kaloriya **profitsiti** kerak: kunlik me'yoringizdan +250…+500 kkal. Maqsad — haftasiga tana vaznining 0,25–0,5% ortishi (70 kg — 200–350 g); tezrog'i asosan yog'.\n\n"
     "• Oqsil 1,6–2,2 g/kg, qolgani uglevod (energiya) va yog'.\n• Kuniga 4–5 ovqat, kaloriyali va hajmi kichik ovqatlar: yong'oq, quritilgan meva, guruch, non, sut, yog'li baliq.\n"
     "• Kuch mashqlari haftasiga 3–4 marta, yuklamani bosqichma-bosqich oshirib.\n• Uyqu 7–9 soat.\n\n"
     "Qo'shimchalar: protein + kreatin asosiy; ovqat bilan kaloriya to'plash qiyin bo'lsa — geyner. 2–3 hafta vazn o'zgarmasa, kaloriyani yana 200 kkal oshiring.",
     "Для массы нужен **профицит**: +250…+500 ккал к суточной норме. Цель — +0,25–0,5% веса в неделю (при 70 кг — 200–350 г); быстрее — в основном жир.\n\n"
     "• Белок 1,6–2,2 г/кг, остальное — углеводы (энергия) и жиры.\n• 4–5 приёмов пищи, калорийная и компактная еда: орехи, сухофрукты, рис, хлеб, молоко, жирная рыба.\n"
     "• Силовые 3–4 раза в неделю с постепенным ростом нагрузки.\n• Сон 7–9 часов.\n\n"
     "Добавки: основа — протеин + креатин; если трудно добрать калории едой — гейнер. Вес стоит 2–3 недели — добавьте ещё 200 ккал.",
     "Gaining needs a calorie **surplus**: +250 to +500 kcal over maintenance. Aim for +0.25–0.5% of body weight a week (200–350 g at 70 kg); faster is mostly fat.\n\n"
     "• Protein 1.6–2.2 g/kg, the rest carbs (energy) and fat.\n• 4–5 meals a day with calorie-dense, compact food: nuts, dried fruit, rice, bread, milk, oily fish.\n"
     "• Strength training 3–4 times a week, adding load gradually.\n• Sleep 7–9 hours.\n\n"
     "Supplements: protein + creatine are the base; if eating enough is hard — a gainer. Weight flat for 2–3 weeks? Add another 200 kcal."),

    ("usage", 56, "To'g'ri ozish: kaloriya va tezlik",
     "qanday qilib to'g'ri ozish mumkin\nhaftasiga necha kilo ozish normal\nozish uchun qancha kaloriya\nкак правильно похудеть\nсколько кг в неделю худеть\nhow fast should i lose weight\ncalories for fat loss",
     "ozish, vazn tashlash, defitsit, kaloriya, похудение, дефицит, калории, сушка, fat loss, deficit, cut, lose weight, kilo",
     "Ozish uchun kaloriya **defitsiti** kerak: me'yordan −300…−500 kkal. Xavfsiz tezlik — haftasiga tana vaznining 0,5–1% (80 kg — 0,4–0,8 kg). Tezroq ozish mushak, kuch va energiyani yo'qotadi.\n\n"
     "• Oqsil yuqori: 1,8–2,4 g/kg — to'yintiradi va mushakni saqlaydi.\n• Kuch mashqlari haftasiga 2–4 marta (mushakni saqlash uchun eng muhim).\n"
     "• Kuniga 8–10 ming qadam + kardio xohishga ko'ra.\n• Sabzavot, tola va suv ko'p; shakarli ichimliklar yo'q.\n• Uyqu 7–9 soat — kam uyqu ishtahani oshiradi.\n\n"
     "Qo'shimchalar: protein (izolyat), xohlasangiz kreatin (mushakni saqlaydi), multivitamin. «Yog' yoqiruvchi» defitsitsiz ishlamaydi.",
     "Для похудения нужен **дефицит**: −300…−500 ккал от нормы. Безопасный темп — 0,5–1% веса в неделю (при 80 кг — 0,4–0,8 кг). Быстрее — теряются мышцы, сила и энергия.\n\n"
     "• Много белка: 1,8–2,4 г/кг — насыщает и сохраняет мышцы.\n• Силовые 2–4 раза в неделю (главное для сохранения мышц).\n"
     "• 8–10 тысяч шагов в день + кардио по желанию.\n• Больше овощей, клетчатки и воды; без сладких напитков.\n• Сон 7–9 часов — недосып усиливает аппетит.\n\n"
     "Добавки: протеин (изолят), по желанию креатин (сохраняет мышцы), мультивитамины. «Жиросжигатель» без дефицита не работает.",
     "Fat loss needs a calorie **deficit**: −300 to −500 kcal below maintenance. A safe pace is 0.5–1% of body weight a week (0.4–0.8 kg at 80 kg). Faster costs muscle, strength and energy.\n\n"
     "• High protein: 1.8–2.4 g/kg — keeps you full and protects muscle.\n• Strength training 2–4 times a week (the key to keeping muscle).\n"
     "• 8–10k steps a day + cardio if you like.\n• Plenty of vegetables, fibre and water; no sugary drinks.\n• Sleep 7–9 hours — short sleep raises appetite.\n\n"
     "Supplements: protein (isolate), optionally creatine (protects muscle), a multivitamin. A 'fat burner' doesn't work without a deficit."),

    ("usage", 50, "Mashg'ulotdan oldin va keyin ovqatlanish",
     "mashg'ulotdan oldin nima yeyish kerak\nmashg'ulotdan keyin nima yeyish kerak\nanabolik oyna\nчто есть до тренировки\nчто есть после тренировки\nанаболическое окно\nwhat to eat before workout\nwhat to eat after workout",
     "mashg'ulotdan oldin, keyin, ovqat, anabolik oyna, до тренировки, после тренировки, анаболическое окно, pre workout meal, post workout meal, anabolic window",
     "• **Oldin (1,5–3 soat):** uglevod + oqsil, kam yog' — masalan guruch/grechka + tovuq, suli + tuxum, banan + qatiq. 30–60 daqiqa qolgan bo'lsa — yengil: banan yoki protein kokteyl.\n"
     "• **Keyin (1–2 soat ichida):** 20–40 g oqsil + uglevod — ovqat yoki protein + meva.\n\n"
     "«30 daqiqalik anabolik oyna» qat'iy emas: kunlik oqsil va kaloriya muhimroq. Lekin och qoringa mashq qilgan bo'lsangiz, keyin tezroq ovqatlaning. Mashg'ulot 90 daqiqadan uzoq bo'lsa, davomida ham uglevod (sport ichimligi) foydali.",
     "• **До (за 1,5–3 часа):** углеводы + белок, мало жира — например рис/гречка + курица, овсянка + яйца, банан + йогурт. Осталось 30–60 минут — что-то лёгкое: банан или протеиновый коктейль.\n"
     "• **После (в течение 1–2 часов):** 20–40 г белка + углеводы — еда или протеин + фрукт.\n\n"
     "«30-минутное анаболическое окно» не строгое: важнее суточные белок и калории. Но если тренировались натощак — поешьте скорее. Тренировка дольше 90 минут — углеводы и во время (спортивный напиток).",
     "• **Before (1.5–3 hours):** carbs + protein, little fat — e.g. rice/buckwheat + chicken, oats + eggs, banana + yoghurt. Only 30–60 minutes left? Something light: a banana or a protein shake.\n"
     "• **After (within 1–2 hours):** 20–40 g protein + carbs — a meal, or a shake + fruit.\n\n"
     "The '30-minute anabolic window' isn't strict: daily protein and calories matter more. But if you trained fasted, eat soon after. Sessions over 90 minutes benefit from carbs during too (a sports drink)."),

    ("faq", 48, "Plato: natija to'xtab qoldi",
     "vaznim o'zgarmayapti\nnatija yo'q\nplato\nвес стоит\nнет прогресса\nплато\nweight loss plateau\nno progress",
     "plato, vazn turibdi, natija yo'q, o'zgarmayapti, плато, вес стоит, нет прогресса, plateau, stuck, no progress",
     "Plato — normal holat. Tekshiring:\n"
     "1. **Hisob aniqmi?** 1–2 hafta ovqatni tarozida o'lchab yozing — ko'pincha yog', ichimlik va gazaklar hisobdan chiqib qoladi.\n"
     "2. **Vazn ozgani sari me'yor ham kamayadi** — kaloriyani yana 100–200 kkal o'zgartiring.\n"
     "3. **Faollik:** qadamlar kamayib ketmadimi?\n4. **Uyqu va stress** — suv ushlab, vaznni yashiradi.\n"
     "5. **Mashg'ulot:** yuklama, takror yoki og'irlikni bosqichma-bosqich oshiryapsizmi?\n\n"
     "Faqat tarozi emas — bel o'lchami, foto va kuch ko'rsatkichlarini ham kuzating: mushak ortib, yog' kamayishi mumkin.",
     "Плато — это нормально. Проверьте:\n"
     "1. **Точен ли подсчёт?** 1–2 недели взвешивайте и записывайте еду — часто «теряются» масло, напитки и перекусы.\n"
     "2. **С уменьшением веса снижается и норма** — скорректируйте калории ещё на 100–200 ккал.\n"
     "3. **Активность:** не упало ли число шагов?\n4. **Сон и стресс** — задерживают воду и маскируют результат.\n"
     "5. **Тренировки:** растут ли постепенно веса, повторы, объём?\n\n"
     "Следите не только за весами: талия, фото и силовые — мышцы могут расти, а жир уходить.",
     "Plateaus are normal. Check:\n"
     "1. **Is your tracking accurate?** Weigh and log food for 1–2 weeks — oil, drinks and snacks often go uncounted.\n"
     "2. **Maintenance drops as you lose weight** — adjust calories by another 100–200 kcal.\n"
     "3. **Activity:** have your steps dropped?\n4. **Sleep and stress** — they hold water and hide progress.\n"
     "5. **Training:** are load, reps or volume going up gradually?\n\n"
     "Track more than the scale: waist, photos and strength — you may be gaining muscle while losing fat."),

    ("faq", 45, "Mushak og'rig'i va tiklanish",
     "mashg'ulotdan keyin mushaklarim og'riyapti\nkrepatura\nqancha dam olish kerak\nкрепатура что делать\nболят мышцы после тренировки\nmuscle soreness\nhow to recover faster",
     "og'riq, krepatura, tiklanish, dam olish, крепатура, боль в мышцах, восстановление, doms, soreness, recovery, rest",
     "Mashg'ulotdan 24–72 soat keyingi mushak og'rig'i (krepatura) — yangi yoki og'ir yuklamaga normal javob; u o'sish ko'rsatkichi emas.\n\n"
     "Tezroq tiklanish uchun:\n• Uyqu 7–9 soat.\n• Yetarli oqsil (1,6–2,2 g/kg) va kaloriya.\n• Yengil harakat: yurish, velosiped, cho'zilish.\n"
     "• Bir mushak guruhiga 48–72 soat dam.\n• Omega-3 va kreatin tiklanishga biroz yordam berishi mumkin.\n\n"
     "O'tkir, bir joyda kuchli og'riq, shish yoki siydik qorayishi — bu jarohat yoki rabdomioliz belgisi bo'lishi mumkin, darhol shifokorga.",
     "Боль в мышцах через 24–72 часа после тренировки (крепатура) — нормальная реакция на новую или тяжёлую нагрузку; это не показатель роста.\n\n"
     "Чтобы восстановиться быстрее:\n• Сон 7–9 часов.\n• Достаточно белка (1,6–2,2 г/кг) и калорий.\n• Лёгкое движение: ходьба, велосипед, растяжка.\n"
     "• 48–72 часа отдыха для одной группы мышц.\n• Омега-3 и креатин могут немного помочь восстановлению.\n\n"
     "Острая сильная боль в одном месте, отёк или тёмная моча — возможна травма или рабдомиолиз, срочно к врачу.",
     "Muscle soreness 24–72 hours after training (DOMS) is a normal reaction to new or hard work; it isn't a sign of growth.\n\n"
     "To recover faster:\n• Sleep 7–9 hours.\n• Enough protein (1.6–2.2 g/kg) and calories.\n• Light movement: walking, cycling, stretching.\n"
     "• 48–72 hours of rest per muscle group.\n• Omega-3 and creatine may help recovery a little.\n\n"
     "Sharp pain in one spot, swelling or dark urine can mean an injury or rhabdomyolysis — see a doctor straight away."),

    ("faq", 52, "Ramazonda mashg'ulot va qo'shimchalar",
     "ramazonda protein qachon ichiladi\nro'za paytida mashq qilsa bo'ladimi\nрамадан протеин когда пить\nтренировки во время поста\nramadan protein\ntraining while fasting",
     "ramazon, ro'za, saharlik, iftor, рамадан, пост, сухур, ифтар, ramadan, fasting, suhoor, iftar",
     "Ramazon oyida natijani saqlash mumkin:\n"
     "• **Mashg'ulot vaqti:** iftordan 1–2 soat keyin (eng yaxshisi) yoki iftordan oldin yengil mashq.\n"
     "• **Iftor:** suv, xurmo, keyin oqsil + uglevodli ovqat. Mashg'ulotdan keyin protein kokteyl.\n"
     "• **Saharlik:** sekin hazm bo'ladigan oqsil — **kazein**, tvorog, tuxum + suli/non; ko'p suv.\n"
     "• **Kreatin:** iftor yoki saharlikda 3–5 g — davom ettiring.\n"
     "• **Suv:** iftordan saharlikkacha 2–3 litr, bo'lib-bo'lib; elektrolitlar foydali.\n"
     "• Kofeinni kamaytiring — uyqu va suv balansiga ta'sir qiladi.\n\n"
     "Hajmni 20–30% kamaytirib, kuchni saqlashga e'tibor bering. Kasalligi bor kishilar ro'za va mashg'ulotni shifokor bilan kelishsin.",
     "В Рамадан результат можно сохранить:\n"
     "• **Время тренировки:** через 1–2 часа после ифтара (лучше всего) или лёгкая тренировка перед ифтаром.\n"
     "• **Ифтар:** вода, финики, затем еда с белком и углеводами. После тренировки — протеиновый коктейль.\n"
     "• **Сухур:** медленный белок — **казеин**, творог, яйца + овсянка/хлеб; много воды.\n"
     "• **Креатин:** 3–5 г на ифтар или сухур — продолжайте.\n"
     "• **Вода:** 2–3 литра от ифтара до сухура, понемногу; электролиты полезны.\n"
     "• Меньше кофеина — влияет на сон и водный баланс.\n\n"
     "Снизьте объём на 20–30% и сосредоточьтесь на сохранении силы. При хронических болезнях согласуйте пост и тренировки с врачом.",
     "You can keep your progress during Ramadan:\n"
     "• **Training time:** 1–2 hours after iftar (best) or a light session before iftar.\n"
     "• **Iftar:** water, dates, then a meal with protein and carbs. A protein shake after training.\n"
     "• **Suhoor:** slow protein — **casein**, cottage cheese, eggs + oats/bread; plenty of water.\n"
     "• **Creatine:** 3–5 g at iftar or suhoor — keep taking it.\n"
     "• **Water:** 2–3 litres between iftar and suhoor, spread out; electrolytes help.\n"
     "• Cut caffeine — it affects sleep and hydration.\n\n"
     "Reduce volume by 20–30% and focus on keeping strength. With a chronic illness, agree fasting and training with your doctor."),

    ("faq", 47, "Interval och qolish (intermittent fasting)",
     "interval och qolish\n16/8 parhez\nинтервальное голодание\nintermittent fasting\n16 8",
     "interval, och qolish, 16/8, интервальное голодание, голодание, intermittent fasting, fasting, if",
     "Interval och qolish (masalan 16/8 — 8 soat ichida ovqatlanish) — kaloriyani kamaytirishning bir usuli. Umumiy kaloriya teng bo'lsa, oddiy parhezdan ko'ra ko'proq yog' yoqmaydi; kimga qulay bo'lsa, shunga mos.\n\n"
     "• Ovqatlanish oynasida oqsilni 2–3 ovqatga bo'ling (har birida 30–50 g).\n• Mashg'ulotni oyna ichiga yoki boshlanishiga yaqin qo'ying.\n"
     "• Och qolish vaqtida suv, choy, qora qahva mumkin.\n\n"
     "Diabet, oshqozon yarasi, ovqatlanish buzilishi, homiladorlik va o'smirlarga tavsiya etilmaydi.",
     "Интервальное голодание (например 16/8 — еда в окне 8 часов) — один из способов снизить калории. При равных калориях жира сжигает не больше обычной диеты; подходит тем, кому так удобно.\n\n"
     "• В окне питания распределите белок на 2–3 приёма (по 30–50 г).\n• Тренировку ставьте в окно или ближе к его началу.\n"
     "• Во время голода можно воду, чай, чёрный кофе.\n\n"
     "Не рекомендуется при диабете, язве, расстройствах пищевого поведения, беременности и подросткам.",
     "Intermittent fasting (e.g. 16/8 — eating within an 8-hour window) is one way to cut calories. At equal calories it doesn't burn more fat than a normal diet; it suits people who find it convenient.\n\n"
     "• Split protein over 2–3 meals in the window (30–50 g each).\n• Train inside the window or near its start.\n"
     "• Water, tea and black coffee are fine while fasting.\n\n"
     "Not recommended with diabetes, ulcers, eating disorders, in pregnancy or for teens."),

    ("faq", 47, "Ayollar: hayz sikli, temir va qo'shimchalar",
     "ayollar uchun qanday vitaminlar kerak\nqizlar uchun sport ozuqa\nвитамины для женщин спорт\nженщинам какие добавки\nsupplements for women",
     "ayollar, qizlar, hayz, temir, женщины, девушки, цикл, железо, women, female, period, menstrual",
     "Ayollar uchun asosiylari erkaklarnikiga o'xshash: protein va kreatin xavfsiz va foydali. Qo'shimcha e'tibor:\n"
     "• **Temir** — hayz tufayli yetishmovchilik ko'p uchraydi; ferritin tahlilini topshiring.\n"
     "• **D vitamini va kalsiy** — suyak salomatligi.\n• **Foliy kislota** — homiladorlikni rejalashtirsangiz (shifokor bilan).\n"
     "• **Omega-3, magniy** — hayz oldi noqulayliklarini kamaytirishi mumkin.\n\n"
     "Juda kam kaloriya va ko'p mashg'ulot hayzni to'xtatishi mumkin — bu jiddiy signal, ginekologga murojaat qiling. Homiladorlik va emizishda har qanday qo'shimcha faqat shifokor bilan.",
     "Для женщин основа та же: протеин и креатин безопасны и полезны. Дополнительно:\n"
     "• **Железо** — из-за менструаций дефицит частый; сдайте ферритин.\n"
     "• **Витамин D и кальций** — здоровье костей.\n• **Фолиевая кислота** — если планируете беременность (с врачом).\n"
     "• **Омега-3, магний** — могут уменьшить ПМС.\n\n"
     "Слишком мало калорий и много тренировок могут остановить цикл — это серьёзный сигнал, обратитесь к гинекологу. При беременности и кормлении любые добавки — только с врачом.",
     "For women the basics are the same: protein and creatine are safe and useful. Extra attention:\n"
     "• **Iron** — deficiency is common because of periods; get ferritin tested.\n"
     "• **Vitamin D and calcium** — bone health.\n• **Folic acid** — if you're planning a pregnancy (with your doctor).\n"
     "• **Omega-3, magnesium** — may ease PMS.\n\n"
     "Too few calories with lots of training can stop your period — a serious signal, see a gynaecologist. In pregnancy and breastfeeding, any supplement only with a doctor."),

    ("faq", 46, "50 yoshdan keyin sport ozuqasi",
     "50 yoshdan keyin protein ichsa bo'ladimi\nkeksalar uchun kreatin\nпосле 50 лет протеин\nпожилым креатин\nsupplements after 50\nprotein for older adults",
     "50 yosh, keksa, qariya, после 50, пожилые, возраст, older, seniors, age, sarkopeniya, саркопения, sarcopenia",
     "Yosh o'tgan sari mushak yo'qotiladi (sarkopeniya) — kuch mashqlari va oqsil buni sekinlashtiradi.\n"
     "• **Oqsil:** 1,2–1,6 g/kg, har ovqatda 25–40 g; protein kokteyl qulay.\n"
     "• **Kreatin** 3–5 g — kuch va mushakni saqlashga yordam beradi (buyrak sog'lom bo'lsa).\n"
     "• **D vitamini va kalsiy** — suyaklar uchun.\n• **B12** — 50 yoshdan keyin so'rilishi kamayadi.\n• **Omega-3** — yurak va bo'g'imlar.\n\n"
     "Surunkali kasallik yoki dori ichsangiz (ayniqsa qon suyultiruvchi, bosim, diabet), qo'shimchalarni shifokor bilan kelishing. Pre-workout va yog' yoqiruvchilardan ehtiyot bo'ling.",
     "С возрастом теряются мышцы (саркопения) — силовые тренировки и белок это замедляют.\n"
     "• **Белок:** 1,2–1,6 г/кг, 25–40 г на приём; протеиновый коктейль удобен.\n"
     "• **Креатин** 3–5 г — помогает сохранить силу и мышцы (при здоровых почках).\n"
     "• **Витамин D и кальций** — для костей.\n• **B12** — после 50 усваивается хуже.\n• **Омега-3** — сердце и суставы.\n\n"
     "При хронических болезнях или лекарствах (особенно антикоагулянты, от давления, диабета) согласуйте добавки с врачом. С предтренами и жиросжигателями осторожно.",
     "With age we lose muscle (sarcopenia) — strength training and protein slow it down.\n"
     "• **Protein:** 1.2–1.6 g/kg, 25–40 g per meal; shakes are convenient.\n"
     "• **Creatine** 3–5 g — helps keep strength and muscle (with healthy kidneys).\n"
     "• **Vitamin D and calcium** — for bones.\n• **B12** — absorption drops after 50.\n• **Omega-3** — heart and joints.\n\n"
     "With a chronic illness or medication (especially blood thinners, blood-pressure or diabetes drugs), agree supplements with a doctor. Be careful with pre-workouts and fat burners."),

    ("faq", 50, "O'smirlar uchun sport ozuqasi",
     "16 yoshda protein ichsa bo'ladimi\no'smirlarga kreatin\nподростку протеин можно\nв 15 лет креатин\ncan teenagers take protein\nteen creatine",
     "o'smir, 14 yosh, 15 yosh, 16 yosh, 17 yosh, maktab, подросток, школьник, teen, teenager, 16 years",
     "18 yoshgacha asos — **ovqat**: go'sht, tuxum, sut mahsulotlari, dukkaklilar, uglevod va yetarli kaloriya. O'sayotgan organizmga ko'p energiya kerak.\n\n"
     "• **Protein kokteyl** — ovqatdan yetmasa, ota-ona bilan kelishib, me'yorida (kuniga 1 porsiya) mumkin; bu oddiy oziq-ovqat oqsili.\n"
     "• **Kreatin** — 18 yoshgacha tavsiya etmaymiz (sportchi bo'lsa — faqat sport shifokori bilan).\n"
     "• **Pre-workout, yog' yoqiruvchi, energetik, testosteron busterlar — mumkin emas.**\n\n"
     "Eng katta natija: to'g'ri texnika, muntazam mashg'ulot va 8–10 soat uyqu.",
     "До 18 лет основа — **еда**: мясо, яйца, молочное, бобовые, углеводы и достаточно калорий. Растущему организму нужно много энергии.\n\n"
     "• **Протеиновый коктейль** — если белка из еды не хватает, по согласованию с родителями и умеренно (1 порция в день); это обычный пищевой белок.\n"
     "• **Креатин** — до 18 лет не рекомендуем (спортсменам — только со спортивным врачом).\n"
     "• **Предтрены, жиросжигатели, энергетики, тестобустеры — нельзя.**\n\n"
     "Главный результат даёт правильная техника, регулярные тренировки и сон 8–10 часов.",
     "Under 18 the base is **food**: meat, eggs, dairy, legumes, carbs and enough calories. A growing body needs lots of energy.\n\n"
     "• **Protein shakes** — if food falls short, with parents' agreement and in moderation (1 serving a day); it's ordinary food protein.\n"
     "• **Creatine** — we don't recommend it under 18 (young athletes only with a sports doctor).\n"
     "• **Pre-workouts, fat burners, energy drinks, testosterone boosters — no.**\n\n"
     "The biggest results come from good technique, regular training and 8–10 hours of sleep."),

    ("policy", 52, "Professional sportchilar va doping nazorati",
     "doping testdan o'tadimi\nsportchiga mumkinmi doping\nдопинг тест пройдет ли\nзапрещено ли для спортсменов\nis it wada approved\nwill i fail a drug test",
     "doping, wada, antidoping, informed sport, допинг, вада, антидопинг, anti-doping, drug test, banned, taqiqlangan",
     "Doping nazoratidan o'tadigan sportchilar uchun:\n"
     "• Qo'shimchalar ifloslanishi mumkin, javobgarlik sportchining o'zida.\n"
     "• **Informed Sport / Informed Choice / NSF Certified for Sport** belgisi bor mahsulotlarni tanlang — har partiya taqiqlangan moddalarga tekshirilgan.\n"
     "• «Testosteron busteri», «gormonal» va noma'lum o'simlik aralashmali yog' yoqiruvchilardan qoching (DMAA, SARM, prohormon bo'lishi mumkin).\n"
     "• Shubha bo'lsa — mahsulot nomi va tarkibini jamoa shifokori yoki milliy antidoping agentligi bilan tekshiring.\n\n"
     "Steroid, SARM va taqiqlangan moddalar bo'yicha maslahat bermaymiz. Mahsulot sertifikatini chatda so'rashingiz mumkin.",
     "Для спортсменов, проходящих допинг-контроль:\n"
     "• Добавки могут быть загрязнены, ответственность — на самом спортсмене.\n"
     "• Выбирайте продукты со знаком **Informed Sport / Informed Choice / NSF Certified for Sport** — каждая партия проверена на запрещённые вещества.\n"
     "• Избегайте «тестобустеров», «гормональных» и жиросжигателей с непонятными растительными смесями (возможны DMAA, SARMs, прогормоны).\n"
     "• Сомневаетесь — проверьте название и состав у врача команды или в национальном антидопинговом агентстве.\n\n"
     "По стероидам, SARMs и запрещённым веществам не консультируем. Сертификат на товар можно запросить в чате.",
     "For athletes who face drug testing:\n"
     "• Supplements can be contaminated, and the athlete is responsible.\n"
     "• Choose products marked **Informed Sport / Informed Choice / NSF Certified for Sport** — every batch is tested for banned substances.\n"
     "• Avoid 'testosterone boosters', 'hormonal' products and fat burners with vague herbal blends (they may hide DMAA, SARMs or prohormones).\n"
     "• Unsure? Check the product name and ingredients with your team doctor or national anti-doping agency.\n\n"
     "We don't advise on steroids, SARMs or banned substances. Ask for any product's certificate in the chat."),

    ("faq", 45, "Mashg'ulot qilmasam protein ichsa bo'ladimi",
     "mashq qilmasam protein ichsam bo'ladimi\ndam olish kunida protein\nпротеин без тренировок\nв день отдыха протеин\nprotein without working out\nprotein on rest days",
     "mashqsiz, dam olish kuni, без тренировок, день отдыха, rest day, without training, semirib ketamanmi",
     "Ha. Protein — oddiy oziq-ovqat oqsili (sutdan), dori emas. Ovqatdan oqsil yetmasa, mashqsiz ham ichsa bo'ladi.\n\n"
     "• **Dam olish kunlari ham iching** — mushak aynan dam olganda tiklanadi va o'sadi.\n"
     "• Semirtiradimi? Yo'q, faqat umumiy kaloriya ortiqcha bo'lsa. Bir porsiya ~120 kkal.\n"
     "• Mashg'ulotsiz mushak o'smaydi — natija uchun kuch mashqlari kerak.",
     "Да. Протеин — обычный пищевой белок (из молока), не лекарство. Если белка из еды не хватает, можно и без тренировок.\n\n"
     "• **В дни отдыха — тоже пейте**: мышцы восстанавливаются и растут именно на отдыхе.\n"
     "• Поправлюсь? Нет, только если общих калорий больше нормы. Порция ~120 ккал.\n"
     "• Без тренировок мышцы не растут — для результата нужны силовые.",
     "Yes. Protein is ordinary food protein (from milk), not a drug. If food doesn't give you enough, you can take it without training.\n\n"
     "• **Take it on rest days too** — muscles recover and grow while you rest.\n"
     "• Will it make me fat? No — only total calories above your needs do. A serving is ~120 kcal.\n"
     "• Muscle won't grow without training — results need strength work."),

    ("faq", 46, "Qo'shimchalarni birga ichish",
     "kreatin va proteinni birga ichsa bo'ladimi\nhammasini birga ichsam bo'ladimi\nкреатин и протеин вместе\nможно ли смешивать добавки\ncan i take creatine and protein together\nstack supplements",
     "birga, aralashtirish, kombinatsiya, вместе, смешивать, сочетать, together, combine, stack, mix",
     "Ha, asosiy qo'shimchalar bir-biriga mos:\n"
     "• **Protein + kreatin** — bitta kokteylga qo'shsa bo'ladi.\n• **Pre-workout + kreatin** — ko'p pre-workoutlarda kreatin bor, dozani qo'shib hisoblang.\n"
     "• **Multivitamin + omega-3** — ovqat bilan birga.\n\n"
     "E'tibor bering:\n• **Kofein** — pre-workout, yog' yoqiruvchi, energetik va qahvani jamlab kuniga 400 mg dan oshirmang.\n"
     "• **Vitamin va minerallar** — bir xil moddani turli mahsulotlardan takrorlamang.\n• Temir, kalsiy va ruxni alohida iching.\n\n"
     "Yangi qo'shimchalarni birma-bir qo'shing — qaysi biri qanday ta'sir qilishini bilasiz.",
     "Да, основные добавки совместимы:\n"
     "• **Протеин + креатин** — можно в один коктейль.\n• **Предтрен + креатин** — во многих предтренах уже есть креатин, суммируйте дозу.\n"
     "• **Мультивитамины + омега-3** — вместе с едой.\n\n"
     "Внимание:\n• **Кофеин** — в сумме из предтрена, жиросжигателя, энергетика и кофе не больше 400 мг в день.\n"
     "• **Витамины и минералы** — не дублируйте одно и то же из разных продуктов.\n• Железо, кальций и цинк — отдельно.\n\n"
     "Новые добавки вводите по одной — так понятно, что как действует.",
     "Yes, the core supplements go together:\n"
     "• **Protein + creatine** — fine in one shake.\n• **Pre-workout + creatine** — many pre-workouts already contain creatine, add up the dose.\n"
     "• **Multivitamin + omega-3** — together with food.\n\n"
     "Watch out:\n• **Caffeine** — pre-workout, fat burner, energy drinks and coffee together: no more than 400 mg a day.\n"
     "• **Vitamins and minerals** — don't double up from several products.\n• Take iron, calcium and zinc separately.\n\n"
     "Add new supplements one at a time so you know what each one does."),

    ("faq", 44, "Keto parhez va sport",
     "keto parhez\nketo sportga mos keladimi\nкето диета спорт\nketo diet training",
     "keto, ketogen, uglevodsiz, кето, кетогенная, без углеводов, keto, ketogenic, low carb",
     "Keto (juda kam uglevod, ko'p yog') ba'zilarga ozishda ishtahani boshqarishga yordam beradi. Lekin kuch va tezlik mashg'ulotlarida uglevod — asosiy yoqilg'i, ketoda natija ko'pincha pasayadi.\n\n"
     "• Ozish uchun hal qiluvchi — kaloriya defitsiti, keto shart emas.\n• Ketoda ham oqsil 1,6–2,2 g/kg bo'lsin.\n"
     "• Birinchi haftalarda «keto grippi» — suv va elektrolitlar (natriy, kaliy, magniy) yordam beradi.\n\n"
     "Diabet (ayniqsa dori bilan), buyrak, jigar kasalligi, homiladorlikda — faqat shifokor nazoratida.",
     "Кето (очень мало углеводов, много жиров) некоторым помогает контролировать аппетит при похудении. Но в силовых и скоростных тренировках углеводы — главное топливо, на кето результаты часто падают.\n\n"
     "• Для похудения решает дефицит калорий, кето не обязательно.\n• И на кето белок 1,6–2,2 г/кг.\n"
     "• В первые недели «кето-грипп» — помогают вода и электролиты (натрий, калий, магний).\n\n"
     "При диабете (особенно на лекарствах), болезнях почек, печени и беременности — только под контролем врача.",
     "Keto (very low carb, high fat) helps some people control appetite while losing weight. But carbs are the main fuel for strength and speed work, so performance often drops on keto.\n\n"
     "• Fat loss comes from a calorie deficit; keto isn't required.\n• Keep protein at 1.6–2.2 g/kg on keto too.\n"
     "• The early 'keto flu' — water and electrolytes (sodium, potassium, magnesium) help.\n\n"
     "With diabetes (especially on medication), kidney or liver disease, or in pregnancy — only under medical supervision."),

    ("faq", 43, "Spirtli ichimlik va mashg'ulot",
     "spirtli ichimlik mushakka zararmi\nпиво после тренировки\nалкоголь и мышцы\nalcohol and muscle",
     "spirtli, alkogol, pivo, алкоголь, пиво, alcohol, beer",
     "Spirtli ichimlik tiklanishni sekinlashtiradi: mushak oqsili sintezini kamaytiradi, uyquni buzadi, suvsizlantiradi va bo'sh kaloriya beradi. Mashg'ulotdan keyingi kunlarda ayniqsa zararli.\n\n"
     "Natija muhim bo'lsa — imkon qadar kamaytiring. Spirtli ichimlik bilan pre-workout, yog' yoqiruvchi va kofeinli mahsulotlarni hech qachon aralashtirmang.",
     "Алкоголь замедляет восстановление: снижает синтез мышечного белка, ухудшает сон, обезвоживает и даёт пустые калории. Особенно вреден в дни после тренировки.\n\n"
     "Если важен результат — сведите к минимуму. Никогда не сочетайте алкоголь с предтренами, жиросжигателями и кофеиновыми продуктами.",
     "Alcohol slows recovery: it lowers muscle protein synthesis, disrupts sleep, dehydrates and adds empty calories. It's especially harmful in the days after training.\n\n"
     "If results matter, keep it to a minimum. Never mix alcohol with pre-workouts, fat burners or caffeine products."),

    ("faq", 44, "Ozish va massa bir vaqtda (rekompozitsiya)",
     "bir vaqtda ozib mushak olish mumkinmi\nskinny fat\nрекомпозиция\nодновременно худеть и набирать мышцы\nbody recomposition\nlose fat and gain muscle",
     "rekompozitsiya, skinny fat, bir vaqtda, рекомпозиция, одновременно, recomposition, recomp",
     "Ha, rekompozitsiya mumkin — ayniqsa yangi boshlovchilarda, ortiqcha yog'i borlarda va tanaffusdan qaytganlarda.\n\n"
     "• Kaloriya me'yorda yoki biroz defitsit (−200…−300 kkal).\n• Oqsil yuqori: 2,0–2,4 g/kg.\n"
     "• Kuch mashqlari haftasiga 3–4 marta, yuklamani doimiy oshirib.\n• Uyqu 7–9 soat.\n\n"
     "Tarozi deyarli o'zgarmasligi mumkin — bel o'lchami, foto va kuchni kuzating. Protein va kreatin bu yo'lda eng foydali qo'shimchalar.",
     "Да, рекомпозиция возможна — особенно у новичков, при лишнем жире и после перерыва.\n\n"
     "• Калории на уровне нормы или небольшой дефицит (−200…−300 ккал).\n• Много белка: 2,0–2,4 г/кг.\n"
     "• Силовые 3–4 раза в неделю с постоянным ростом нагрузки.\n• Сон 7–9 часов.\n\n"
     "Вес может почти не меняться — следите за талией, фото и силой. Протеин и креатин здесь самые полезные добавки.",
     "Yes, recomposition is possible — especially for beginners, people with extra fat and those returning after a break.\n\n"
     "• Calories at maintenance or a small deficit (−200 to −300 kcal).\n• High protein: 2.0–2.4 g/kg.\n"
     "• Strength training 3–4 times a week with steady progression.\n• Sleep 7–9 hours.\n\n"
     "The scale may barely move — track waist, photos and strength. Protein and creatine are the most useful supplements here."),

    ("faq", 45, "Halol sertifikati",
     "protein halolmi\nhalol sertifikat bormi\nжелатин в капсулах\nпротеин халяль\nis it halal",
     "halol, halal, халяль, jelatin, желатин, gelatin, cho'chqa, свинина, pork",
     "Zardob proteini sutdan olinadi. Halollik ishlab chiqaruvchiga bog'liq: ba'zi brendlarda rasmiy halal sertifikati bor, kapsulalarda esa jelatin (ba'zan hayvon jelatini) bo'lishi mumkin.\n\n"
     "• Qadoqdagi halal belgisini va tarkibni (gelatin, bovine/porcine) tekshiring.\n"
     "• Aniq mahsulotning sertifikatini chatda so'rang — xodimlarimiz hujjat bo'yicha javob beradi.\n\n"
     "Sertifikati tasdiqlanmagan mahsulotni «halol» deb ayta olmaymiz.",
     "Сывороточный протеин получают из молока. Халяльность зависит от производителя: у некоторых брендов есть официальный сертификат халяль, а в капсулах бывает желатин (иногда животный).\n\n"
     "• Проверьте знак халяль на упаковке и состав (gelatin, bovine/porcine).\n"
     "• Сертификат на конкретный товар запросите в чате — сотрудники ответят по документам.\n\n"
     "Без подтверждённого сертификата назвать продукт «халяль» мы не можем.",
     "Whey protein comes from milk. Halal status depends on the manufacturer: some brands carry an official halal certificate, and capsules may contain gelatin (sometimes animal-derived).\n\n"
     "• Check the pack for a halal mark and the ingredients (gelatin, bovine/porcine).\n"
     "• Ask in the chat for the specific product's certificate — our staff answer from the documents.\n\n"
     "We can't call a product halal without a confirmed certificate."),
]
