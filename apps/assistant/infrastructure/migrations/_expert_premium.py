"""
Expert knowledge, part 4: what the first three parts left out -- less common supplements (glutamine, HMB, ashwagandha,
CoQ10), endurance fuelling, reading a label, protein myths (meal replacement, "anabolic window", per-meal limit),
steroids / SARMs, vitamins A / E / K2, iodine, folic acid, high-dose antioxidants, lab tests and "detox".
Doses follow ISSN position stands (HMB, nutrient timing, endurance) and NIH ODS / EFSA reference intakes and upper
limits; anything that touches a condition or a medicine sends the shopper to a doctor. Data for migration 0011.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("product", 48, "Glutamin kerakmi",
     "glutamin kerakmi\nglutamin nima uchun\nglyutamin qanday ichiladi\nглютамин нужен ли\nглютамин зачем\nis glutamine worth it\nwhat does glutamine do",
     "glutamin, glyutamin, glutamine, глютамин, aminokislota, аминокислота",
     "Glutamin — organizm o'zi yetarli ishlab chiqaradigan aminokislota; go'sht, tuxum va proteinda ham ko'p.\n"
     "• **Mushak o'sishi va kuch uchun** sog'lom, yetarli oqsil olayotgan odamda foydasi isbotlanmagan.\n"
     "• Foydasi bo'lishi mumkin: juda uzoq, og'ir mashg'ulotlar davri, ichak bezovtaligi — bunda kuniga 5 g.\n\n"
     "Pulni avval protein, kreatin va ovqatga sarflang — glutamin oxirgi navbatda.",
     "Глютамин — аминокислота, которую организм сам производит в достатке; её много в мясе, яйцах и протеине.\n"
     "• **Для роста мышц и силы** у здорового человека с достаточным белком пользы не доказано.\n"
     "• Может помочь: периоды очень долгих тяжёлых тренировок, проблемы с кишечником — тогда 5 г в день.\n\n"
     "Сначала протеин, креатин и питание — глютамин в последнюю очередь.",
     "Glutamine is an amino acid your body makes in plenty; meat, eggs and protein powder are full of it.\n"
     "• **For muscle growth and strength** there's no proven benefit in healthy people who eat enough protein.\n"
     "• It may help in periods of very long, hard training or with gut trouble — 5 g a day then.\n\n"
     "Spend on protein, creatine and food first — glutamine comes last."),

    ("product", 44, "HMB nima",
     "hmb nima\nhmb kerakmi\nhmb qanday ichiladi\nhmb что это\nhmb как принимать\nwhat is hmb\nis hmb worth it",
     "hmb, бета-гидрокси, beta-hydroxy, leytsin, лейцин, leucine",
     "HMB — leytsin aminokislotasining mahsuloti; mushak parchalanishini kamaytiradi.\n"
     "• Kimga foydali: **endi boshlaganlar**, 50 yoshdan oshganlar, kasallik yoki jarohatdan keyin mushakni saqlash, qattiq ozish davri.\n"
     "• Tajribali sportchida qo'shimcha foydasi kichik.\n"
     "• Doza: kuniga **3 g**, 2–3 qismga bo'lib, ovqat bilan; natijani 2–4 haftada baholang.\n\n"
     "Xavfsiz qo'shimcha, lekin asos — yetarli oqsil va kuch mashqlari.",
     "HMB — продукт обмена аминокислоты лейцин; уменьшает распад мышц.\n"
     "• Кому полезно: **новичкам**, людям старше 50, для сохранения мышц после болезни или травмы, при жёсткой сушке.\n"
     "• Опытным спортсменам добавляет немного.\n"
     "• Доза: **3 г** в день, в 2–3 приёма с едой; оценивайте через 2–4 недели.\n\n"
     "Добавка безопасная, но основа — достаточно белка и силовые тренировки.",
     "HMB is made from the amino acid leucine and reduces muscle breakdown.\n"
     "• Useful for **beginners**, people over 50, keeping muscle after illness or injury, and hard diets.\n"
     "• Adds little for experienced lifters.\n"
     "• Dose: **3 g** a day in 2–3 servings with food; judge it after 2–4 weeks.\n\n"
     "It's safe, but the base is enough protein and strength training."),

    ("usage", 46, "Ashvagandha: stress, uyqu va kuch",
     "ashvagandha nima\nashvagandha qanday ichiladi\nashvagandha kimga mumkin emas\nашваганда как принимать\nашваганда противопоказания\nashwagandha dosage\nis ashwagandha safe",
     "ashvagandha, ashwagandha, ашваганда, stress, стресс, adaptogen, адаптоген, uyqu, сон",
     "Ashvagandha — adaptogen o'simlik ekstrakti. Tadqiqotlarda stress va xavotirni kamaytirishi, uyquni yaxshilashi, kuch va tiklanishga biroz yordam berishi ko'rsatilgan.\n"
     "• Doza: standart ekstrakt **300–600 mg** kuniga, odatda kechqurun; natija 4–8 haftada.\n"
     "• **Mumkin emas:** homiladorlik va emizish, qalqonsimon bez kasalligi (ayniqsa gipertireoz), autoimmun kasallik, jigar kasalligi; tinchlantiruvchi, uyqu yoki qalqonsimon bez dorisi ichsangiz — avval shifokor.\n"
     "• Juda kam hollarda jigarga ta'sir qilgan — ko'z yoki teri sarg'aysa, to'q siydik bo'lsa darhol to'xtating.",
     "Ашваганда — растительный адаптоген. В исследованиях снижает стресс и тревожность, улучшает сон, немного помогает силе и восстановлению.\n"
     "• Доза: стандартизированный экстракт **300–600 мг** в день, обычно вечером; эффект через 4–8 недель.\n"
     "• **Нельзя:** при беременности и кормлении, болезнях щитовидной железы (особенно гипертиреозе), аутоиммунных и болезнях печени; если пьёте успокоительные, снотворные или гормоны щитовидки — сначала врач.\n"
     "• В редких случаях вредила печени — при пожелтении кожи или глаз, тёмной моче сразу прекратите.",
     "Ashwagandha is an adaptogenic herb extract. Studies show less stress and anxiety, better sleep and a small boost to strength and recovery.\n"
     "• Dose: **300–600 mg** of a standardised extract a day, usually in the evening; effects show in 4–8 weeks.\n"
     "• **Avoid it** in pregnancy and breastfeeding, with thyroid disease (especially hyperthyroidism), autoimmune or liver disease; on sedatives, sleeping pills or thyroid medicine, ask a doctor first.\n"
     "• Rare cases of liver injury are reported — stop at once if your skin or eyes turn yellow or urine gets dark."),

    ("usage", 52, "Yugurish, futbol va uzoq mashg'ulotda ovqatlanish",
     "marafonda nima ichish kerak\nyugurishdan oldin nima yeyish kerak\nfutbolchi uchun sport ozuqasi\nuzoq mashg'ulotda nima ichaman\nчто есть перед забегом\nпитание на марафоне\nчто пить во время долгой тренировки\nwhat to eat before a marathon\nendurance nutrition\nenergy gel",
     "marafon, yugurish, futbol, velosiped, chidamlilik, gel, uglevod, марафон, бег, футбол, велосипед, выносливость, гель, углеводы, marathon, running, football, cycling, endurance, gel, carbs",
     "Chidamlilik sportida asosiy yoqilg'i — **uglevod**:\n"
     "• **Oldidan (1–4 soat):** 1–4 g/kg uglevod — guruch, non, banan, bo'tqa; yog'li va tolali ovqatni kamaytiring.\n"
     "• **Davomida, 60–90 daqiqadan uzoq bo'lsa:** soatiga **30–60 g** uglevod (gel, izotonik ichimlik, banan); 2,5 soatdan uzoqda 90 g gacha — glyukoza + fruktoza aralashmasi.\n"
     "• **Suyuqlik:** soatiga 400–800 ml, terlasangiz — natriyli elektrolit.\n"
     "• **Keyin:** 1–1,2 g/kg uglevod + 20–30 g oqsil.\n\n"
     "Kofein (3 mg/kg, startdan 60 daqiqa oldin) va beta-alanin chidamlilikka yordam beradi. Yangi narsani musobaqa kuni emas, mashg'ulotda sinab ko'ring.",
     "Главное топливо в видах на выносливость — **углеводы**:\n"
     "• **До (за 1–4 часа):** 1–4 г/кг углеводов — рис, хлеб, банан, каша; меньше жирного и клетчатки.\n"
     "• **Во время, если дольше 60–90 минут:** **30–60 г** углеводов в час (гель, изотоник, банан); дольше 2,5 часа — до 90 г, смесь глюкозы и фруктозы.\n"
     "• **Жидкость:** 400–800 мл в час, при сильном поте — электролиты с натрием.\n"
     "• **После:** 1–1,2 г/кг углеводов + 20–30 г белка.\n\n"
     "Кофеин (3 мг/кг за 60 минут до старта) и бета-аланин помогают выносливости. Новое пробуйте на тренировке, а не в день соревнований.",
     "In endurance sport the main fuel is **carbohydrate**:\n"
     "• **Before (1–4 h):** 1–4 g/kg of carbs — rice, bread, banana, porridge; go easy on fat and fibre.\n"
     "• **During, if longer than 60–90 min:** **30–60 g** of carbs an hour (gel, sports drink, banana); beyond 2.5 h up to 90 g, glucose + fructose.\n"
     "• **Fluids:** 400–800 ml an hour; heavy sweaters add sodium electrolytes.\n"
     "• **After:** 1–1.2 g/kg of carbs + 20–30 g of protein.\n\n"
     "Caffeine (3 mg/kg, 60 minutes before the start) and beta-alanine help endurance. Try anything new in training, never on race day."),

    ("faq", 50, "Yorliqni o'qish va porsiya narxi",
     "qaysi protein foydaliroq narxiga\nyorliqni qanday o'qish kerak\nporsiyada qancha oqsil\nproteinni qanday tanlash kerak\nкак читать состав протеина\nкак выбрать протеин по цене\nсколько белка в порции\nhow to read a protein label\nprice per serving\nhow to choose a protein",
     "yorliq, tarkib, porsiya, narx, tanlash, этикетка, состав, порция, цена, выбрать, label, serving, price per serving, choose, amino spiking",
     "To'g'ri taqqoslash — banka narxi bilan emas, **bir porsiyadagi oqsil narxi** bilan:\n"
     "• Yorliqda porsiya hajmi (masalan 30 g) va undagi oqsil (masalan 24 g) yoziladi → oqsil ulushi 80%.\n"
     "• **Bitta porsiya narxi** = banka narxi ÷ porsiyalar soni. Porsiyadagi oqsil ham teng bo'lsa, arzon porsiya — foydali.\n"
     "• Aminokislota tarkibida **glitsin, taurin, arginin** juda ko'p bo'lsa va ular oqsil grammiga qo'shilgan bo'lsa — bu «amino spiking», haqiqiy oqsil kamroq.\n"
     "• Shakar, yog' va kaloriyani maqsadingizga qarab tekshiring (ozish uchun kamroq).\n"
     "• Mustaqil laboratoriya belgisi (Informed Sport, NSF) — professional sportchilar uchun muhim.\n\n"
     "Ikki mahsulotni yozing — narx va tarkibini solishtirib beraman.",
     "Сравнивайте не цену банки, а **цену белка в порции**:\n"
     "• На этикетке — размер порции (например 30 г) и белок в ней (например 24 г) → 80% белка.\n"
     "• **Цена порции** = цена банки ÷ число порций. При одинаковом белке выгоднее та, где порция дешевле.\n"
     "• Если в аминокислотном профиле очень много **глицина, таурина, аргинина** и они входят в граммы белка — это «amino spiking», настоящего белка меньше.\n"
     "• Сахар, жир и калории проверяйте под свою цель (на сушке — меньше).\n"
     "• Знак независимой лаборатории (Informed Sport, NSF) важен профессиональным спортсменам.\n\n"
     "Напишите два продукта — сравню цену и состав.",
     "Compare the **price of protein per serving**, not the price of the tub:\n"
     "• The label gives the serving size (e.g. 30 g) and its protein (e.g. 24 g) → 80% protein.\n"
     "• **Price per serving** = tub price ÷ number of servings. With equal protein, the cheaper serving wins.\n"
     "• Lots of **glycine, taurine or arginine** in the amino profile counted as protein is 'amino spiking' — less real protein.\n"
     "• Check sugar, fat and calories against your goal (less when cutting).\n"
     "• An independent-lab mark (Informed Sport, NSF) matters for tested athletes.\n\n"
     "Name two products and I'll compare price and formula."),

    ("faq", 46, "Protein ovqat o'rnini bosadimi",
     "protein ovqat o'rniga ichsa bo'ladimi\nnonushta o'rniga protein\nprotein bilan ozish mumkinmi\nпротеин вместо еды\nпротеин вместо завтрака\ncan protein replace a meal\nprotein shake instead of food",
     "ovqat o'rniga, nonushta, ozish, вместо еды, вместо завтрака, замена питания, meal replacement, instead of a meal",
     "Protein kokteyli — **oqsil manbai**, to'liq ovqat emas: unda tola, vitaminlar va yetarli kaloriya yo'q.\n"
     "• Vaqt yo'q paytda kuniga **1 ta** ovqat o'rniga ichsa bo'ladi — lekin to'liqroq qiling: protein + jo'xori (40–60 g) + meva/banan + bir qoshiq yeryong'oq pastasi yoki sut.\n"
     "• Ozishda ham asos — oddiy ovqat; kokteyl to'qlikni oshirib, oqsilni to'ldiradi.\n"
     "• Kuniga 2–3 ovqatni kokteyl bilan almashtirish tavsiya etilmaydi.",
     "Протеиновый коктейль — **источник белка**, а не полноценная еда: в нём нет клетчатки, витаминов и достаточных калорий.\n"
     "• Когда нет времени, можно заменить **1** приём пищи в день — но сделайте его полнее: протеин + овсянка (40–60 г) + банан/фрукт + ложка арахисовой пасты или молоко.\n"
     "• И при похудении основа — обычная еда; коктейль добавляет сытости и белка.\n"
     "• Заменять коктейлем 2–3 приёма пищи в день не стоит.",
     "A protein shake is **a protein source**, not a full meal — it lacks fibre, vitamins and enough calories.\n"
     "• When you're short on time it can replace **one** meal a day — make it fuller: protein + oats (40–60 g) + banana/fruit + a spoon of peanut butter or milk.\n"
     "• Even for fat loss, regular food is the base; the shake adds fullness and protein.\n"
     "• Replacing 2–3 meals a day with shakes isn't recommended."),

    ("faq", 47, "Anabolik oyna: proteinni darhol ichish shartmi",
     "mashg'ulotdan keyin darhol protein ichish kerakmi\nanabolik oyna\nproteinni qachon ichgan yaxshi\nанаболическое окно\nсразу после тренировки протеин\nanabolic window\ndo i need protein right after training",
     "anabolik oyna, darhol, mashg'ulotdan keyin, анаболическое окно, сразу после, anabolic window, right after, timing",
     "«30 daqiqalik anabolik oyna» — mubolag'a.\n"
     "• Eng muhimi — **kunlik jami oqsil** (faol odamga 1,4–2,0 g/kg) va uni kun bo'yi **3–5 ovqatga** bo'lish (har birida 0,3–0,4 g/kg, odatda 20–40 g).\n"
     "• Mashg'ulotdan oldingi va keyingi ovqat orasidagi masofa **4–6 soatdan** oshmasa — yetarli.\n"
     "• Och qoringa ertalab mashq qilsangiz — keyin tezroq ovqatlanish foydaliroq.\n\n"
     "Ya'ni protein mashg'ulotdan keyin qulay, lekin 2 soatdan keyin ichsangiz ham natija yo'qolmaydi.",
     "«Анаболическое окно 30 минут» — преувеличение.\n"
     "• Главное — **суточный белок** (активным 1,4–2,0 г/кг) и его распределение на **3–5 приёмов** (по 0,3–0,4 г/кг, обычно 20–40 г).\n"
     "• Если между едой до и после тренировки не больше **4–6 часов** — этого достаточно.\n"
     "• Тренируетесь утром натощак — тогда поесть сразу после полезнее.\n\n"
     "Протеин после тренировки удобен, но и через 2 часа результат не пропадёт.",
     "The '30-minute anabolic window' is overstated.\n"
     "• What matters most is **daily protein** (1.4–2.0 g/kg for active people) spread over **3–5 meals** (0.3–0.4 g/kg each, usually 20–40 g).\n"
     "• If your meals before and after training are no more than **4–6 hours** apart, you're covered.\n"
     "• Training fasted in the morning? Then eating soon after does help.\n\n"
     "A shake after training is convenient, but having it 2 hours later won't cost you results."),

    ("faq", 45, "Bir martada qancha oqsil so'riladi",
     "bir martada qancha protein so'riladi\n30 grammdan ortiq oqsil so'riladimi\nikki skup bir vaqtda ichsa bo'ladimi\nсколько белка усваивается за раз\nбольше 30 г белка за раз\nhow much protein can you absorb at once\ntwo scoops at once",
     "bir martada, so'riladi, ikki skup, за раз, усваивается, два скупа, at once, absorb, two scoops, per meal",
     "Oqsil bir martada «30 g dan ortig'i so'rilmaydi» degani — afsona: ichak hammasini so'radi, faqat sekinroq.\n"
     "• Mushak uchun eng samarali: har ovqatda **20–40 g** (yoki 0,3–0,4 g/kg); katta vaznli yoki 40+ yoshlilarga yuqori chegara.\n"
     "• Bir martada 50–60 g ham foydasiz emas — ta'siri uzoqroq davom etadi; lekin kun bo'yi bo'lib ichish amaliyroq.\n"
     "• Ikki skupni bir vaqtda ichsa bo'ladi — muhimi kunlik jami oqsil.",
     "«За раз усваивается не больше 30 г белка» — миф: кишечник всасывает всё, просто дольше.\n"
     "• Для мышц эффективнее всего **20–40 г** за приём (или 0,3–0,4 г/кг); крупным людям и тем, кому за 40, — ближе к верхней границе.\n"
     "• 50–60 г за раз тоже не пропадут — эффект просто длится дольше; но делить на день практичнее.\n"
     "• Два скупа за раз — можно; главное — суточная сумма.",
     "'You can only absorb 30 g of protein at once' is a myth — the gut absorbs all of it, just more slowly.\n"
     "• For muscle, **20–40 g** per meal (or 0.3–0.4 g/kg) works best; bigger people and those over 40 sit at the top of that range.\n"
     "• 50–60 g at once isn't wasted — the effect just lasts longer; spreading it through the day is more practical.\n"
     "• Two scoops at once is fine — the daily total is what counts."),

    ("policy", 58, "Steroidlar va SARM xavfi",
     "steroid sotasizmi\nsteroid ichsam bo'ladimi\nsarm nima\ntestosteron ukol\nanabolik steroidlar\nстероиды продаете\nсармы что это\nанаболики вред\ndo you sell steroids\nare sarms safe",
     "steroid, anabolik, sarm, ostarin, ligandrol, testosteron ukol, стероид, анаболик, сарм, остарин, тестостерон укол, steroids, sarms, ostarine, anabolic",
     "NutriZone **steroid, SARM va gormon preparatlarini sotmaydi** — faqat oziq-ovqat qo'shimchalari.\n"
     "Nega ulardan uzoq turish kerak:\n"
     "• Yurak va qon tomir kasalliklari, qon bosimi, xolesterin buzilishi; jigar zararlanishi.\n"
     "• O'z gormonlaringiz to'xtaydi — bepushtlik, ko'krak o'sishi (ginekomastiya), kayfiyat buzilishi; ayollarda ovozning qo'pollashishi va qayta tiklanmaydigan o'zgarishlar.\n"
     "• **SARM**lar hech qayerda dori sifatida tasdiqlanmagan, tarkibi ko'pincha yorliqqa mos kelmaydi; hammasi WADA tomonidan taqiqlangan.\n\n"
     "Testosteron kamligidan shikoyat bo'lsa — endokrinologga, tahlil bilan. Tabiiy natija uchun: kuch mashqlari, yetarli oqsil, uyqu va kreatin.",
     "NutriZone **не продаёт стероиды, SARM и гормональные препараты** — только пищевые добавки.\n"
     "Почему от них лучше держаться подальше:\n"
     "• Болезни сердца и сосудов, давление, нарушения холестерина; поражение печени.\n"
     "• Собственные гормоны отключаются — бесплодие, рост груди (гинекомастия), перепады настроения; у женщин — огрубение голоса и необратимые изменения.\n"
     "• **SARM** нигде не одобрены как лекарства, состав часто не совпадает с этикеткой; всё это запрещено WADA.\n\n"
     "Если беспокоит низкий тестостерон — к эндокринологу, с анализами. Для натурального результата: силовые, достаточно белка, сон и креатин.",
     "NutriZone **doesn't sell steroids, SARMs or hormones** — food supplements only.\n"
     "Why to stay away from them:\n"
     "• Heart and blood-vessel disease, high blood pressure, bad cholesterol; liver damage.\n"
     "• Your own hormones shut down — infertility, breast growth (gynaecomastia), mood swings; in women a deeper voice and irreversible changes.\n"
     "• **SARMs** aren't approved as medicines anywhere and often don't contain what the label says; all of them are banned by WADA.\n\n"
     "Worried about low testosterone? See an endocrinologist and get tested. For natural results: strength training, enough protein, sleep and creatine."),

    ("usage", 47, "A va E vitaminlari: ortiqchasi zararli",
     "a vitamini qancha kerak\ne vitamini nima uchun\na va e vitamini birga\nвитамин а сколько\nвитамин е зачем\nvitamin a dose\nvitamin e benefits",
     "a vitamini, e vitamini, retinol, tokoferol, beta-karotin, витамин а, витамин е, ретинол, токоферол, бета-каротин, vitamin a, vitamin e, retinol, tocopherol, beta-carotene",
     "A va E — **yog'da eriydigan** vitaminlar: organizmda to'planadi, ortiqchasi zararli.\n"
     "• **A vitamini** — ko'rish, teri, immunitet. Kunlik me'yor: erkak 900 mkg, ayol 700 mkg; tayyor A vitamini (retinol) kuniga **3000 mkg dan** oshmasin. **Homiladorlikda yuqori doza xavfli.** Chekuvchilar beta-karotin qo'shimchasini ichmasin.\n"
     "• **E vitamini** — antioksidant. Me'yor 15 mg; katta doza (300 mg+) qon ketishini kuchaytirishi mumkin, ayniqsa qon suyultiruvchi dori bilan.\n\n"
     "Sabzi, qovoq, jigar, tuxum, yong'oq va o'simlik yog'i ko'pchilikka yetarli. Qo'shimcha — multivitamin dozasida, alohida katta dozasi faqat shifokor bilan.",
     "A и E — **жирорастворимые** витамины: накапливаются, избыток вреден.\n"
     "• **Витамин A** — зрение, кожа, иммунитет. Норма: мужчинам 900 мкг, женщинам 700 мкг; готового витамина A (ретинола) не больше **3000 мкг** в день. **При беременности высокие дозы опасны.** Курящим не стоит пить бета-каротин.\n"
     "• **Витамин E** — антиоксидант. Норма 15 мг; большие дозы (300 мг+) могут усиливать кровоточивость, особенно с разжижающими кровь.\n\n"
     "Морковь, тыква, печень, яйца, орехи и растительное масло покрывают потребность большинства. Добавка — в дозе мультивитамина, отдельно большие дозы — только с врачом.",
     "A and E are **fat-soluble** vitamins: they build up in the body and too much is harmful.\n"
     "• **Vitamin A** — vision, skin, immunity. Daily need: men 900 mcg, women 700 mcg; keep preformed vitamin A (retinol) under **3000 mcg** a day. **High doses are dangerous in pregnancy.** Smokers shouldn't take beta-carotene supplements.\n"
     "• **Vitamin E** — an antioxidant. Need 15 mg; big doses (300 mg+) can increase bleeding, especially with blood thinners.\n\n"
     "Carrots, pumpkin, liver, eggs, nuts and plant oils cover most people. Supplement at multivitamin doses; large single doses only with a doctor."),

    ("usage", 49, "K2 vitamini va D3 bilan birga",
     "k2 vitamini nima uchun\nd3 k2 birga ichish kerakmi\nk2 qanday ichiladi\nвитамин к2 зачем\nд3 с к2 вместе\nvitamin k2 benefits\nd3 and k2 together",
     "k2, k2 vitamini, mk-7, menaxinon, витамин к2, менахинон, vitamin k2, menaquinone, d3 k2",
     "K2 vitamini kalsiyni suyakka yo'naltirishga yordam beradi; shuning uchun ko'pincha **D3 bilan birga** chiqariladi.\n"
     "• Odatdagi doza: **MK-7 shaklida 90–200 mkg** kuniga, yog'li ovqat bilan.\n"
     "• Profilaktik D3 dozasida (1000–2000 IU) K2 shart emas, lekin zarari yo'q; katta D3 dozasida qo'shish mantiqli.\n"
     "• **Varfarin** kabi qon suyultiruvchi dori ichsangiz — K vitaminini faqat shifokor ruxsati bilan: dori ta'sirini kamaytiradi.",
     "Витамин K2 помогает направлять кальций в кости, поэтому его часто выпускают **вместе с D3**.\n"
     "• Обычная доза: **90–200 мкг в форме MK-7** в день, с жирной едой.\n"
     "• При профилактической дозе D3 (1000–2000 МЕ) K2 не обязателен, но и не вредит; при больших дозах D3 добавить его логично.\n"
     "• Если пьёте **варфарин** или другие разжижающие кровь — витамин K только с разрешения врача: он ослабляет действие лекарства.",
     "Vitamin K2 helps direct calcium into bone, which is why it's often sold **together with D3**.\n"
     "• Usual dose: **90–200 mcg as MK-7** a day, with a meal containing fat.\n"
     "• At preventive D3 doses (1000–2000 IU) K2 isn't required but does no harm; with high D3 doses adding it makes sense.\n"
     "• On **warfarin** or similar blood thinners, take vitamin K only with your doctor's approval — it weakens the drug."),

    ("usage", 50, "Yod va qalqonsimon bez",
     "yod kerakmi\nyod qanday ichiladi\nqalqonsimon bez uchun vitamin\nйод нужен ли\nйод для щитовидки\niodine supplement\nthyroid vitamins",
     "yod, yodomarin, qalqonsimon bez, buqoq, йод, йодомарин, щитовидка, зоб, iodine, thyroid, goitre",
     "Yod qalqonsimon bez gormonlari uchun kerak. O'rta Osiyo — tabiiy yod kam mintaqa, shuning uchun eng oddiy yechim — **yodlangan tuz** ishlatish.\n"
     "• Kunlik me'yor: kattalarga **150 mkg**, homiladorlik va emizishda 220–250 mkg.\n"
     "• Yuqori chegara — kuniga 600 mkg (EFSA); ko'p yod ham bezni buzadi.\n"
     "• **Qalqonsimon bez kasalligi** (gipotireoz, gipertireoz, tugun, autoimmun tireoidit) bo'lsa yoki gormon dori ichsangiz — yod qo'shimchasini faqat endokrinolog bilan.\n\n"
     "Charchoq, sovuqqa chidamsizlik, soch to'kilishi bo'lsa — avval TTG tahlilini topshiring.",
     "Йод нужен для гормонов щитовидной железы. Средняя Азия — регион с естественным дефицитом йода, поэтому проще всего — **йодированная соль**.\n"
     "• Норма: взрослым **150 мкг**, при беременности и кормлении 220–250 мкг.\n"
     "• Верхний предел — 600 мкг в день (EFSA); избыток йода тоже вредит железе.\n"
     "• При **болезнях щитовидки** (гипо-, гипертиреоз, узлы, аутоиммунный тиреоидит) или приёме гормонов — йод только с эндокринологом.\n\n"
     "Усталость, зябкость, выпадение волос — сначала сдайте ТТГ.",
     "Iodine is needed for thyroid hormones. Central Asia is naturally low in iodine, so the simplest fix is **iodised salt**.\n"
     "• Daily need: **150 mcg** for adults, 220–250 mcg in pregnancy and breastfeeding.\n"
     "• Upper limit: 600 mcg a day (EFSA); too much iodine harms the thyroid too.\n"
     "• With **thyroid disease** (hypo-/hyperthyroidism, nodules, autoimmune thyroiditis) or on thyroid medicine, take iodine only with an endocrinologist.\n\n"
     "Tired, always cold, losing hair? Get a TSH test first."),

    ("faq", 50, "Foliy kislotasi va homiladorlikni rejalashtirish",
     "foliy kislotasi qachon ichiladi\nhomiladorlikni rejalashtirishda vitamin\nfolat qancha\nфолиевая кислота когда пить\nвитамины при планировании беременности\nfolic acid before pregnancy\nprenatal vitamins",
     "foliy kislotasi, folat, b9, homiladorlik, rejalashtirish, фолиевая кислота, фолат, беременность, планирование, folic acid, folate, pregnancy, prenatal",
     "Foliy kislotasi (B9) homilaning asab nayi nuqsonlarini kamaytiradi — shuning uchun:\n"
     "• Homiladorlikni rejalashtirayotgan ayollarga kuniga **400 mkg**, homiladorlikdan **kamida 1 oy oldin** boshlab 12-haftagacha.\n"
     "• Ba'zi holatlarda (oldingi homiladorlikda nuqson, ayrim dorilar, diabet) shifokor ko'proq doza belgilaydi — o'zingiz oshirmang.\n"
     "• Homiladorlik uchun maxsus **prenatal** kompleks tanlang (yod, temir, D bilan); oddiy sport vitaminlari va yuqori dozali A vitamini mos emas.\n\n"
     "Homiladorlik va emizish davrida har qanday qo'shimchani ginekolog bilan kelishing.",
     "Фолиевая кислота (B9) снижает риск пороков нервной трубки у плода, поэтому:\n"
     "• Планирующим беременность — **400 мкг** в день, начиная **минимум за 1 месяц** до зачатия и до 12-й недели.\n"
     "• В отдельных случаях (порок в прошлой беременности, некоторые лекарства, диабет) врач назначает дозу выше — сами не повышайте.\n"
     "• Выбирайте специальный **пренатальный** комплекс (с йодом, железом, D); обычные спортивные витамины и высокие дозы витамина A не подходят.\n\n"
     "Любые добавки при беременности и кормлении — по согласованию с гинекологом.",
     "Folic acid (B9) lowers the risk of neural-tube defects in the baby, so:\n"
     "• Women planning a pregnancy should take **400 mcg** a day, starting **at least 1 month** before conception and continuing to week 12.\n"
     "• In some cases (a previous affected pregnancy, certain medicines, diabetes) a doctor prescribes more — don't raise it yourself.\n"
     "• Choose a dedicated **prenatal** formula (with iodine, iron, D); regular sports vitamins and high-dose vitamin A aren't suitable.\n\n"
     "Agree any supplement in pregnancy and breastfeeding with your gynaecologist."),

    ("product", 44, "Koenzim Q10",
     "koenzim q10 nima uchun\nq10 qanday ichiladi\nstatin ichsam q10 kerakmi\nкоэнзим q10 зачем\nq10 при статинах\ncoq10 benefits\ncoenzyme q10 dose",
     "q10, koenzim, ubikinon, ubikinol, коэнзим, убихинон, coq10, coenzyme, ubiquinol, statin, статин",
     "Koenzim Q10 hujayra energiyasi ishlab chiqarishida qatnashadi; yosh o'tgani sari va **statin** dorilarida miqdori kamayadi.\n"
     "• Doza: kuniga **100–200 mg**, yog'li ovqat bilan (yog'da eriydi).\n"
     "• Dalillar o'rtacha: statin bilan bog'liq mushak og'rig'ida va 40+ yoshdagilarda ba'zan yordam beradi; yosh, sog'lom sportchida sezilarli foydasi yo'q.\n"
     "• **Varfarin** yoki qon bosimi dorisi ichsangiz — shifokorga ayting.",
     "Коэнзим Q10 участвует в выработке энергии клетками; с возрастом и на **статинах** его становится меньше.\n"
     "• Доза: **100–200 мг** в день с жирной едой (жирорастворим).\n"
     "• Доказательства средние: иногда помогает при мышечных болях на статинах и людям 40+; молодому здоровому спортсмену заметной пользы нет.\n"
     "• Если пьёте **варфарин** или препараты от давления — предупредите врача.",
     "Coenzyme Q10 takes part in how cells make energy; levels fall with age and on **statins**.\n"
     "• Dose: **100–200 mg** a day with a meal containing fat (it's fat-soluble).\n"
     "• The evidence is moderate: it sometimes helps statin-related muscle aches and people over 40; young healthy athletes see little benefit.\n"
     "• On **warfarin** or blood-pressure medicine, tell your doctor."),

    ("faq", 45, "Katta dozali antioksidantlar va mashg'ulot",
     "c vitaminini ko'p ichsam mushak o'sadimi\nmashg'ulotdan keyin c vitamini\nantioksidant mashg'ulotga ta'siri\nвитамин с после тренировки\nантиоксиданты и тренировки\nvitamin c after workout\nantioxidants and training",
     "antioksidant, c vitamini, e vitamini, katta doza, антиоксидант, витамин с, большие дозы, antioxidant, vitamin c, high dose, recovery",
     "Mashg'ulot paytida hosil bo'ladigan «stress» — mushakni moslashishga majburlaydigan signal.\n"
     "• Tadqiqotlarda har kuni **katta dozada** C (1000 mg) va E (400 IU) vitaminlari ichish chidamlilik va kuch mashqlariga **moslashuvni susaytirgan**.\n"
     "• Shuning uchun mashg'ulot davrida «ko'proq — yaxshiroq» emas: antioksidantlarni **meva va sabzavotdan** oling; C vitamini kerak bo'lsa — 200–500 mg, mashg'ulotdan uzoqroq vaqtda.\n"
     "• Kasallik yoki shamollash davrida qisqa muddat ko'proq C ichish — boshqa masala.",
     "«Стресс» во время тренировки — сигнал, заставляющий мышцы адаптироваться.\n"
     "• В исследованиях ежедневные **большие дозы** C (1000 мг) и E (400 МЕ) **ослабляли адаптацию** к тренировкам на выносливость и силу.\n"
     "• Поэтому «больше — лучше» не работает: антиоксиданты берите из **фруктов и овощей**; если нужен витамин C — 200–500 мг, подальше от тренировки.\n"
     "• Коротко увеличить C во время простуды — другое дело.",
     "The 'stress' of training is the signal that makes muscles adapt.\n"
     "• In studies, **high daily doses** of vitamin C (1000 mg) and E (400 IU) **blunted adaptation** to endurance and strength training.\n"
     "• So more isn't better here: get antioxidants from **fruit and vegetables**; if you need vitamin C, take 200–500 mg away from training.\n"
     "• A short boost of vitamin C while you have a cold is a different matter."),

    ("faq", 54, "Qaysi tahlillarni topshirish kerak",
     "vitamin ichishdan oldin qanday tahlil topshirish kerak\nqaysi analiz topshiray\nvitamin yetishmasligini qanday bilaman\nкакие анализы сдать\nанализы перед приёмом витаминов\nwhich blood tests should i take\nhow do i know if i'm deficient",
     "tahlil, analiz, qon tahlili, ferritin, gemoglobin, ttg, анализы, кровь, ферритин, гемоглобин, ттг, blood test, lab test, ferritin, deficiency",
     "Qo'shimchani «taxminan» emas, tahlil bo'yicha tanlash eng to'g'ri yo'l. Asosiy ro'yxat:\n"
     "• **Umumiy qon tahlili** va **ferritin** — kamqonlik va temir zaxirasi (ayniqsa ayollar, vegetarianlar, chidamlilik sportchilari).\n"
     "• **25(OH)D** — D vitamini.\n"
     "• **B12** — vegetarianlar, 50+ yosh, metformin yoki oshqozon dorisi ichadiganlar.\n"
     "• **TTG** — qalqonsimon bez (charchoq, vazn o'zgarishi, sovqotish).\n"
     "• **Glyukoza / HbA1c** va **lipidlar** — 35+ yosh, ortiqcha vazn.\n\n"
     "Ertalab och qoringa, yiliga bir marta. Natijani shifokorga ko'rsating — keyin men mos mahsulot va dozani tanlab beraman.",
     "Подбирать добавки лучше по анализам, а не «на глаз». Базовый список:\n"
     "• **Общий анализ крови** и **ферритин** — анемия и запас железа (особенно женщинам, вегетарианцам, спортсменам на выносливость).\n"
     "• **25(OH)D** — витамин D.\n"
     "• **B12** — вегетарианцам, людям 50+, тем, кто пьёт метформин или препараты от изжоги.\n"
     "• **ТТГ** — щитовидная железа (усталость, изменения веса, зябкость).\n"
     "• **Глюкоза / HbA1c** и **липиды** — после 35 лет и при лишнем весе.\n\n"
     "Утром натощак, раз в год. Покажите результат врачу — а я подберу продукт и дозу.",
     "Choose supplements from lab results, not guesswork. The core list:\n"
     "• **Complete blood count** and **ferritin** — anaemia and iron stores (especially women, vegetarians, endurance athletes).\n"
     "• **25(OH)D** — vitamin D.\n"
     "• **B12** — vegetarians, people over 50, and those on metformin or antacids.\n"
     "• **TSH** — thyroid (tiredness, weight change, feeling cold).\n"
     "• **Glucose / HbA1c** and **lipids** — over 35 or overweight.\n\n"
     "In the morning, fasting, once a year. Show the results to a doctor — then I'll match the product and dose."),

    ("faq", 44, "Detoks va «organizmni tozalash» afsonasi",
     "detoks kerakmi\norganizmni tozalash\ndetoks choy ishlaydimi\njigarni tozalash\nдетокс нужен ли\nочищение организма\nдетокс чай\ndoes detox work\ndetox tea",
     "detoks, tozalash, shlak, detoks choy, детокс, очищение, шлаки, чай для похудения, detox, cleanse, toxins, detox tea",
     "Organizmni jigar, buyrak, ichak va o'pka har kuni o'zi tozalaydi — «shlak»ni chiqaradigan maxsus choy yoki kurs kerak emas.\n"
     "• «Detoks choy»lar ko'pincha **surgi yoki siydik haydovchi** — tarozida kamaygan narsa yog' emas, suv; elektrolitlar yo'qoladi.\n"
     "• Haqiqiy yordam: yetarli suv, sabzavot va tola, uyqu, spirtli ichimlikni kamaytirish, harakat.\n"
     "• Jigar haqida tashvish bo'lsa — jigar tahlillari (ALT, AST) va shifokor.",
     "Организм каждый день очищают печень, почки, кишечник и лёгкие — специальные чаи и курсы от «шлаков» не нужны.\n"
     "• «Детокс-чаи» часто **слабительные или мочегонные** — уходит вода, а не жир; теряются электролиты.\n"
     "• Реально помогает: достаточно воды, овощи и клетчатка, сон, меньше алкоголя, движение.\n"
     "• Беспокоит печень — печёночные пробы (АЛТ, АСТ) и врач.",
     "Your liver, kidneys, gut and lungs clean the body every day — no special tea or 'toxin' cleanse is needed.\n"
     "• 'Detox teas' are often **laxatives or diuretics** — what the scale loses is water, not fat, along with electrolytes.\n"
     "• What actually helps: enough water, vegetables and fibre, sleep, less alcohol, movement.\n"
     "• Worried about your liver? Liver tests (ALT, AST) and a doctor."),
]
