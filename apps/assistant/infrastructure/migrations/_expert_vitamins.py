"""
Expert knowledge, part 1: vitamins and minerals. Adult doses follow NIH Office of Dietary Supplements / EFSA reference
intakes and tolerable upper limits; anything therapeutic is sent to a doctor and a blood test. Data for migration 0006
(a leading underscore keeps Django's migration loader from treating this module as a migration).
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("usage", 62, "D vitamini: kimga va qancha",
     "d vitamini qancha ichish kerak\nd3 qanday ichiladi\nd vitamini kerakmi\nвитамин д сколько пить\nкак принимать витамин d3\nhow much vitamin d\nvitamin d dose",
     "vitamin d, d3, d vitamini, xolekalsiferol, витамин d, витамин д, холекальциферол, vitamin d3, quyosh, солнце",
     "D3 vitamini suyak, mushak kuchi va immunitet uchun kerak. O'zbekistonda qishda va quyoshda kam yuradiganlarda ko'pincha yetishmaydi.\n\n"
     "• Profilaktika uchun odatda kuniga 1000–2000 IU (25–50 mkg).\n• Yog'li ovqat bilan iching — yaxshiroq so'riladi.\n"
     "• Shifokorsiz kuniga 4000 IU dan oshirmang: D vitamini yog'da eriydi va organizmda to'planadi.\n"
     "• Aniq doza uchun qondagi 25(OH)D tahlilini topshiring; yetishmovchilik katta bo'lsa davolash dozasini shifokor belgilaydi.\n\n"
     "K2 vitamini bilan birga olish mashhur, lekin majburiy emas. Buyrak toshi, sarkoidoz yoki kalsiy yuqori bo'lsa — avval shifokor.",
     "Витамин D3 нужен для костей, силы мышц и иммунитета. В Узбекистане его часто не хватает зимой и тем, кто мало бывает на солнце.\n\n"
     "• Для профилактики обычно 1000–2000 МЕ (25–50 мкг) в день.\n• Принимайте с жирной едой — так он лучше усваивается.\n"
     "• Без врача не больше 4000 МЕ в день: витамин D жирорастворимый и накапливается.\n"
     "• Точную дозу покажет анализ 25(OH)D; лечебную дозу при выраженном дефиците назначает врач.\n\n"
     "Сочетание с K2 популярно, но не обязательно. При камнях в почках, саркоидозе или высоком кальции — сначала к врачу.",
     "Vitamin D3 supports bones, muscle strength and immunity. In Uzbekistan it often runs low in winter and in people who get little sun.\n\n"
     "• For prevention, usually 1000–2000 IU (25–50 mcg) a day.\n• Take it with a meal containing fat for better absorption.\n"
     "• Don't exceed 4000 IU a day without a doctor: vitamin D is fat-soluble and builds up.\n"
     "• A 25(OH)D blood test shows the right dose; treatment doses for a real deficiency come from a doctor.\n\n"
     "Pairing with K2 is popular but optional. With kidney stones, sarcoidosis or high calcium, see a doctor first."),

    ("usage", 58, "C vitamini",
     "c vitamini qancha ichish kerak\nc vitamini shamollashga yordam beradimi\nвитамин c сколько\nаскорбинка от простуды\nvitamin c dose\nvitamin c for colds",
     "vitamin c, c vitamini, askorbin, витамин c, аскорбиновая, ascorbic, shamollash, простуда, cold",
     "C vitamini — antioksidant, immunitet va kollagen hosil bo'lishi uchun kerak, temir so'rilishini ham oshiradi.\n\n"
     "• Kuniga 200–500 mg yetarli; ovqat bilan iching.\n• 2000 mg dan oshirmang — oshqozon buzilishi va buyrak toshi xavfi.\n"
     "• Muntazam ichish shamollash davomiyligini biroz qisqartirishi mumkin, lekin kasallikni oldini olishi isbotlanmagan.\n\n"
     "Meva va sabzavotlar (qalampir, kivi, sitrus, karam) eng yaxshi manba.",
     "Витамин C — антиоксидант, нужен для иммунитета и синтеза коллагена, улучшает усвоение железа.\n\n"
     "• Достаточно 200–500 мг в день с едой.\n• Не больше 2000 мг — расстройство желудка и риск камней в почках.\n"
     "• Регулярный приём может немного сократить простуду, но не защищает от неё полностью.\n\n"
     "Лучшие источники — перец, киви, цитрусовые, капуста.",
     "Vitamin C is an antioxidant needed for immunity and collagen, and it improves iron absorption.\n\n"
     "• 200–500 mg a day with food is enough.\n• Stay below 2000 mg — stomach upset and kidney-stone risk.\n"
     "• Taking it regularly may shorten a cold slightly, but it doesn't prevent colds.\n\n"
     "Best food sources: peppers, kiwi, citrus, cabbage."),

    ("usage", 55, "B12 va B guruhi vitaminlari",
     "b12 kimga kerak\nb12 vitamini qanday ichiladi\nb guruh vitaminlari\nвитамин b12 кому нужен\nвитамины группы б\nwho needs b12\nb complex",
     "b12, vitamin b12, kobalamin, b guruh, b kompleks, в12, витамины группы б, b complex, vegan, вегетарианец, energiya",
     "B12 qon hosil bo'lishi, asab tizimi va energiya almashinuvi uchun zarur. U deyarli faqat hayvon mahsulotlarida bo'ladi.\n\n"
     "Kimga ayniqsa kerak: vegan va vegetarianlarga, 50 yoshdan oshganlarga, metformin yoki oshqozon kislotasini kamaytiruvchi dori ichadiganlarga.\n\n"
     "• Kuniga 250–500 mkg yoki qadoqdagi dozada, ertalab.\n• Ortiqchasi siydik bilan chiqadi — xavfsiz.\n"
     "• B kompleks (B1, B2, B6, B12...) — parhezda yoki og'ir mashg'ulotda foydali; siydik sariq bo'lishi (B2) normal.\n\n"
     "Doimiy holsizlik, uvishish bo'lsa — B12 va temir tahlilini topshiring.",
     "B12 нужен для кроветворения, нервной системы и энергетического обмена. Он есть почти только в животных продуктах.\n\n"
     "Особенно нужен: веганам и вегетарианцам, людям после 50, принимающим метформин или средства от изжоги.\n\n"
     "• 250–500 мкг в день или по упаковке, утром.\n• Избыток выводится с мочой — это безопасно.\n"
     "• Комплекс группы B (B1, B2, B6, B12...) полезен на диете и при тяжёлых тренировках; яркая жёлтая моча (B2) — норма.\n\n"
     "При постоянной слабости и онемении сдайте анализ на B12 и железо.",
     "B12 is needed for blood formation, the nervous system and energy metabolism. It comes almost only from animal foods.\n\n"
     "Especially needed by: vegans and vegetarians, people over 50, anyone on metformin or acid-reducing medication.\n\n"
     "• 250–500 mcg a day or the label dose, in the morning.\n• Excess leaves in urine — it's safe.\n"
     "• A B-complex (B1, B2, B6, B12...) helps when dieting or training hard; bright yellow urine (B2) is normal.\n\n"
     "Constant fatigue or numbness? Get B12 and iron tested."),

    ("usage", 60, "Magniy: uyqu va mushak tortishishi",
     "magniy nima uchun kerak\nmagniy qanday ichiladi\nmagniy uyqu uchun\nmushak tortishsa nima ichay\noyog'im tortishadi\nмагний для чего\nмагний для сна\nсудороги в ногах что пить\nmagnesium for sleep\nmagnesium dose",
     "magniy, magnesium, магний, tortishish, судороги, cramps, uyqu, сон, sleep, glitsinat, глицинат, sitrat",
     "Magniy mushak qisqarishi, asab tizimi, uyqu va 300 dan ortiq ferment uchun kerak. Ko'p terlaydigan sportchilar uni ko'proq yo'qotadi.\n\n"
     "• Kuniga 200–350 mg qo'shimcha sifatida, kechqurun ovqat bilan.\n"
     "• Shakli muhim: glitsinat (uyqu, oshqozonga yumshoq) va sitrat yaxshi so'riladi; oksid arzon, lekin ich ketishiga sabab bo'lishi mumkin.\n"
     "• Mushak tortishishida suv va elektrolitlar ham muhim.\n\n"
     "Buyrak kasalligida faqat shifokor ruxsati bilan. Manbalar: yong'oq, urug'lar, dukkaklilar, ko'katlar, qora shokolad.",
     "Магний нужен для сокращения мышц, нервной системы, сна и сотен ферментов. Спортсмены много теряют его с потом.\n\n"
     "• 200–350 мг в день добавкой, вечером с едой.\n"
     "• Важна форма: глицинат (сон, мягко для желудка) и цитрат усваиваются хорошо; оксид дешёвый, но может слабить.\n"
     "• При судорогах важны также вода и электролиты.\n\n"
     "При болезнях почек — только с разрешения врача. Источники: орехи, семечки, бобовые, зелень, тёмный шоколад.",
     "Magnesium is needed for muscle contraction, nerves, sleep and hundreds of enzymes. Athletes lose a lot in sweat.\n\n"
     "• 200–350 mg a day as a supplement, in the evening with food.\n"
     "• Form matters: glycinate (sleep, gentle on the stomach) and citrate absorb well; oxide is cheap but can loosen the stool.\n"
     "• For cramps, water and electrolytes matter too.\n\n"
     "With kidney disease, only with a doctor's approval. Food sources: nuts, seeds, legumes, greens, dark chocolate."),

    ("usage", 55, "Rux (zinc)",
     "rux nima uchun kerak\nrux qanday ichiladi\nцинк для чего\nкак принимать цинк\nzinc dose\nzinc for immunity",
     "rux, zinc, цинк, immunitet, иммунитет, teri, кожа, testosteron",
     "Rux immunitet, teri, yara bitishi, gormonlar va tiklanish uchun kerak; terlaganda yo'qotiladi.\n\n"
     "• Kuniga 10–25 mg ovqat bilan (och qoringa ko'ngil aynitishi mumkin).\n"
     "• Uzoq muddat kuniga 40 mg dan ko'p ichmang — mis yetishmovchiligi va immunitet pasayishiga olib keladi.\n"
     "• Temir va kalsiydan 2 soat ajratib iching.\n\n"
     "Yetishmovchilik bo'lmasa, rux testosteronni oshirmaydi. Manbalar: mol go'shti, tuxum, dukkaklilar, qovoq urug'i.",
     "Цинк нужен для иммунитета, кожи, заживления, гормонов и восстановления; теряется с потом.\n\n"
     "• 10–25 мг в день с едой (натощак может тошнить).\n"
     "• Долго больше 40 мг в день нельзя — дефицит меди и снижение иммунитета.\n"
     "• Принимайте отдельно от железа и кальция на 2 часа.\n\n"
     "Без дефицита цинк тестостерон не повышает. Источники: говядина, яйца, бобовые, тыквенные семечки.",
     "Zinc supports immunity, skin, wound healing, hormones and recovery; it's lost in sweat.\n\n"
     "• 10–25 mg a day with food (it can cause nausea on an empty stomach).\n"
     "• Not above 40 mg a day long term — it causes copper deficiency and weaker immunity.\n"
     "• Take it 2 hours apart from iron and calcium.\n\n"
     "Without a deficiency zinc won't raise testosterone. Food sources: beef, eggs, legumes, pumpkin seeds."),

    ("usage", 58, "Temir va kamqonlik",
     "temir ichsam bo'ladimi\nkamqonlik uchun nima ichish kerak\nжелезо как принимать\nанемия что пить\niron supplement\nanemia",
     "temir, iron, железо, kamqonlik, анемия, anemia, ferritin, ферритин, gemoglobin, гемоглобин, holsizlik, слабость",
     "Temir qonda kislorod tashiydi. Yetishmasa holsizlik, bosh aylanishi, soch to'kilishi va chidamlilik pasayishi bo'ladi — ayniqsa hayz ko'radigan ayollar, vegetarianlar va yuguruvchilarda.\n\n"
     "Muhim: temirni **faqat tahlil bilan** (ferritin, gemoglobin) va shifokor aytgan dozada iching. Ortiqcha temir jigar va yurakka zarar qiladi; bolalar uchun zaharli — ulardan uzoqda saqlang.\n\n"
     "• C vitamini bilan birga yaxshi so'riladi.\n• Choy, qahva, sut va kalsiydan 2 soat ajratib iching.\n"
     "• Oshqozon bezovta qilsa, kun ora yoki ovqatdan keyin ichish mumkin (shifokor bilan kelishib).\n\n"
     "Ovqatdan: qizil go'sht, jigar, dukkaklilar, ismaloq (C vitamini bilan).",
     "Железо переносит кислород. При нехватке — слабость, головокружение, выпадение волос и падение выносливости, особенно у женщин, вегетарианцев и бегунов.\n\n"
     "Важно: железо принимают **только по анализам** (ферритин, гемоглобин) и в дозе от врача. Избыток вредит печени и сердцу, для детей опасен — храните от них.\n\n"
     "• Лучше усваивается с витамином C.\n• Отдельно от чая, кофе, молока и кальция на 2 часа.\n"
     "• Если беспокоит желудок — через день или после еды (по согласованию с врачом).\n\n"
     "Из еды: красное мясо, печень, бобовые, шпинат (с витамином C).",
     "Iron carries oxygen in the blood. Too little causes fatigue, dizziness, hair loss and lower endurance — especially in menstruating women, vegetarians and runners.\n\n"
     "Important: take iron **only after a blood test** (ferritin, haemoglobin) and at your doctor's dose. Excess iron harms the liver and heart and is toxic to children — keep it away from them.\n\n"
     "• Absorbs better with vitamin C.\n• Keep it 2 hours apart from tea, coffee, milk and calcium.\n"
     "• If it upsets your stomach, alternate days or after food (agree it with your doctor).\n\n"
     "Food sources: red meat, liver, legumes, spinach (with vitamin C)."),

    ("usage", 50, "Kalsiy va suyak salomatligi",
     "kalsiy ichish kerakmi\nsuyak uchun nima ichish kerak\nкальций как принимать\nдля костей что пить\ncalcium supplement\nbone health",
     "kalsiy, calcium, кальций, suyak, кости, bone, osteoporoz, остеопороз",
     "Kalsiyning asosiy manbai — ovqat: sut, qatiq, pishloq, tvorog, kunjut, ko'katlar. Kattalarga kuniga jami 1000–1200 mg kerak.\n\n"
     "• Ovqatdan yetmasa, qo'shimcha bir martada 500 mg dan ko'p emas (ko'pi so'rilmaydi), ovqat bilan.\n"
     "• D vitamini bilan birga — yaxshiroq so'riladi.\n• Temir va ruxdan alohida iching.\n"
     "• Kuch mashqlari va yetarli oqsil suyakni kalsiydan kam bo'lmagan darajada mustahkamlaydi.\n\n"
     "Buyrak toshi bo'lgan yoki menopauzadagi ayollar dozani shifokor bilan kelishsin.",
     "Главный источник кальция — еда: молоко, кефир, сыр, творог, кунжут, зелень. Взрослым нужно 1000–1200 мг в день всего.\n\n"
     "• Если из еды не хватает — добавкой не больше 500 мг за раз (больше не усвоится), с едой.\n"
     "• Вместе с витамином D усваивается лучше.\n• Отдельно от железа и цинка.\n"
     "• Силовые тренировки и достаточный белок укрепляют кости не меньше кальция.\n\n"
     "При камнях в почках и в менопаузе дозу согласуйте с врачом.",
     "Food is the main calcium source: milk, yoghurt, cheese, cottage cheese, sesame, greens. Adults need 1000–1200 mg a day in total.\n\n"
     "• If food falls short, supplement no more than 500 mg at a time (the rest isn't absorbed), with food.\n"
     "• Vitamin D improves absorption.\n• Keep it apart from iron and zinc.\n"
     "• Strength training and enough protein strengthen bones as much as calcium does.\n\n"
     "With kidney stones or in menopause, agree the dose with a doctor."),

    ("usage", 52, "Multivitamin kimga kerak",
     "multivitamin kerakmi\nqaysi vitaminlarni ichish kerak\nvitamin kompleks\nнужны ли витамины\nкакие витамины пить спортсмену\ndo i need a multivitamin\nwhich vitamins should i take",
     "multivitamin, vitamin kompleks, мультивитамины, витаминный комплекс, sportchi vitamin, спортсмен витамины, which vitamins",
     "Multivitamin ovqatdagi kichik bo'shliqlarni to'ldirish uchun «sug'urta»: parhezda, ovqatlanish bir xil bo'lsa yoki og'ir mashq qilsangiz foydali.\n\n"
     "• Kuniga 1 marta ovqat bilan (yog'da eriydigan A, D, E, K vitaminlari shunda so'riladi).\n"
     "• Bir nechta kompleksni birga ichmang — A vitamini va temir ortiqcha bo'lishi mumkin.\n"
     "• Sportchilarda ko'pincha yetishmaydiganlar: D vitamini, magniy, temir (ayollarda), omega-3 — ularni alohida tanlash ham mumkin.\n\n"
     "Vitaminlar energiya «bermaydi»: charchoq bo'lsa uyqu, ovqat va tahlilni tekshiring.",
     "Мультивитамины — «страховка» от небольших пробелов в питании: полезны на диете, при однообразной еде и тяжёлых тренировках.\n\n"
     "• 1 раз в день с едой (так усваиваются жирорастворимые A, D, E, K).\n"
     "• Не пейте несколько комплексов сразу — возможен избыток витамина A и железа.\n"
     "• Спортсменам чаще всего не хватает витамина D, магния, железа (у женщин) и омега-3 — их можно брать отдельно.\n\n"
     "Витамины не «дают» энергию: при усталости проверьте сон, питание и анализы.",
     "A multivitamin is insurance against small gaps in your diet: useful when dieting, eating the same foods or training hard.\n\n"
     "• Once a day with food (that's how fat-soluble A, D, E, K absorb).\n"
     "• Don't stack several multis — you can overdo vitamin A and iron.\n"
     "• Athletes most often lack vitamin D, magnesium, iron (women) and omega-3 — you can also take those individually.\n\n"
     "Vitamins don't 'give' energy: if you're tired, check sleep, food and blood tests."),

    ("faq", 50, "Vitaminlarni qachon va qanday birga ichish",
     "vitaminlarni qachon ichish kerak\nertalabmi kechqurunmi\nqaysi vitaminlarni birga ichib bo'lmaydi\nкогда пить витамины\nкакие витамины нельзя вместе\nwhen to take vitamins\nwhich supplements not to combine",
     "qachon ichish, ertalab, kechqurun, birga, mos kelmaydi, когда пить, совместимость, вместе, timing, combine, together",
     "Oddiy qoidalar:\n"
     "• **Ovqat bilan:** multivitamin, D, A, E, K vitaminlari, omega-3 (yog'da eriydi).\n"
     "• **Ertalab:** B guruh vitaminlari, kofeinli mahsulotlar.\n"
     "• **Kechqurun:** magniy, ZMA, kazein, melatonin.\n"
     "• **Temir** — C vitamini bilan, choy-qahva-sut va kalsiydan 2 soat ajratib.\n"
     "• **Kalsiy, temir, rux** — bir-biridan alohida (so'rilish uchun raqobatlashadi).\n"
     "• **Kreatin, protein** — vaqti muhim emas, eng muhimi muntazamlik.\n\n"
     "Dori ichsangiz (ayniqsa qon suyultiruvchi, qalqonsimon bez, antibiotik), qo'shimchani shifokor bilan kelishing.",
     "Простые правила:\n"
     "• **С едой:** мультивитамины, витамины D, A, E, K, омега-3 (жирорастворимые).\n"
     "• **Утром:** витамины группы B, всё с кофеином.\n"
     "• **Вечером:** магний, ZMA, казеин, мелатонин.\n"
     "• **Железо** — с витамином C, отдельно от чая, кофе, молока и кальция на 2 часа.\n"
     "• **Кальций, железо, цинк** — порознь (конкурируют за усвоение).\n"
     "• **Креатин, протеин** — время не важно, важна регулярность.\n\n"
     "Если принимаете лекарства (особенно антикоагулянты, гормоны щитовидки, антибиотики) — согласуйте добавки с врачом.",
     "Simple rules:\n"
     "• **With food:** multivitamins, vitamins D, A, E, K, omega-3 (fat-soluble).\n"
     "• **Morning:** B vitamins, anything with caffeine.\n"
     "• **Evening:** magnesium, ZMA, casein, melatonin.\n"
     "• **Iron** — with vitamin C, 2 hours apart from tea, coffee, milk and calcium.\n"
     "• **Calcium, iron, zinc** — apart from each other (they compete for absorption).\n"
     "• **Creatine, protein** — timing doesn't matter, consistency does.\n\n"
     "If you take medication (especially blood thinners, thyroid hormone, antibiotics), agree supplements with your doctor."),

    ("faq", 48, "Vitamin ortiqcha bo'lishi mumkinmi",
     "vitamin ko'p ichsa zararmi\nvitamin ko'p ichsam nima bo'ladi\nvitamin dozasini oshirib yuborsam\nпередозировка витаминов\nможно ли много витаминов\nvitamin overdose\ncan you overdose on vitamins\ntoo many vitamins",
     "ortiqcha, dozadan oshish, zarar, передозировка, избыток, вред, overdose, toxicity, too much",
     "Ha, «ko'p — yaxshi» emas.\n"
     "• **Yog'da eriydigan** A, D, E, K vitaminlari organizmda to'planadi — uzoq vaqt yuqori dozada zaharlanish mumkin (masalan, A vitamini homiladorlikda xavfli).\n"
     "• **Temir** ortiqchasi jigarga zarar; bolalar uchun xavfli.\n"
     "• **Rux** ko'p bo'lsa mis yetishmaydi; **B6** uzoq vaqt kuniga 100 mg dan ko'p — asab shikastlanishi.\n"
     "• Suvda eriydigan C va B vitaminlarining ortiqchasi asosan chiqib ketadi, lekin juda katta dozalar ham oshqozonni buzadi.\n\n"
     "Qadoqdagi dozaga amal qiling va bir xil moddani turli mahsulotlardan takror olmang (multivitamin + alohida D + ZMA tarkibini qo'shib hisoblang).",
     "Да, «больше — лучше» не работает.\n"
     "• **Жирорастворимые** A, D, E, K накапливаются — длительные высокие дозы токсичны (витамин A опасен при беременности).\n"
     "• Избыток **железа** вредит печени; для детей опасен.\n"
     "• Много **цинка** — дефицит меди; **B6** больше 100 мг в день долго — поражение нервов.\n"
     "• Избыток водорастворимых C и B в основном выводится, но очень большие дозы расстраивают желудок.\n\n"
     "Соблюдайте дозировку на упаковке и не дублируйте одно и то же из разных продуктов (сложите состав мультивитаминов, отдельного D и ZMA).",
     "Yes — more isn't better.\n"
     "• **Fat-soluble** A, D, E, K build up; long-term high doses are toxic (vitamin A is risky in pregnancy).\n"
     "• Excess **iron** harms the liver and is dangerous for children.\n"
     "• Too much **zinc** causes copper deficiency; **B6** above 100 mg a day long term can damage nerves.\n"
     "• Excess water-soluble C and B mostly leaves the body, but huge doses still upset the stomach.\n\n"
     "Stick to the label dose and don't double up the same nutrient from several products (add up your multi, separate D and ZMA)."),

    ("usage", 50, "Elektrolitlar va suv ichish",
     "mashg'ulotda qancha suv ichish kerak\nelektrolit kerakmi\nizotonik\nсколько воды пить на тренировке\nэлектролиты нужны ли\nhow much water during workout\nelectrolytes",
     "suv, elektrolit, izotonik, suvsizlanish, вода, электролиты, изотоник, обезвоживание, water, hydration, electrolytes, issiq, жара",
     "Suv bo'yicha mo'ljal: kuniga taxminan 30–35 ml/kg (70 kg — 2–2,5 litr) va har bir soat mashg'ulotga yana 500–750 ml.\n\n"
     "• Mashg'ulotdan 2 soat oldin 400–600 ml suv iching.\n• Davomida har 15–20 daqiqada bir necha qultum.\n"
     "• **Elektrolitlar** (natriy, kaliy, magniy) 60–90 daqiqadan uzoq, issiqda yoki ko'p terlaganda kerak — tortishish va holsizlikning oldini oladi. Qisqa mashg'ulotga oddiy suv yetarli.\n"
     "• Siydik och sariq bo'lsa — suv yetarli.\n\n"
     "Yoz jaziramasida (Toshkentda +40°C) ochiq havoda mashq qilsangiz, ayniqsa ehtiyot bo'ling.",
     "Ориентир по воде: около 30–35 мл/кг в день (при 70 кг — 2–2,5 литра) плюс 500–750 мл на каждый час тренировки.\n\n"
     "• За 2 часа до тренировки — 400–600 мл воды.\n• Во время — несколько глотков каждые 15–20 минут.\n"
     "• **Электролиты** (натрий, калий, магний) нужны при нагрузке дольше 60–90 минут, в жару или при сильном потоотделении — против судорог и слабости. Для короткой тренировки хватит воды.\n"
     "• Светло-жёлтая моча — воды достаточно.\n\n"
     "Летом в жару (+40°C) на улице будьте особенно осторожны.",
     "Water target: about 30–35 ml/kg a day (2–2.5 litres at 70 kg) plus 500–750 ml for every hour of training.\n\n"
     "• Drink 400–600 ml 2 hours before training.\n• During it, a few sips every 15–20 minutes.\n"
     "• **Electrolytes** (sodium, potassium, magnesium) matter for sessions over 60–90 minutes, in the heat or with heavy sweating — they prevent cramps and weakness. For short sessions water is enough.\n"
     "• Pale yellow urine means you're drinking enough.\n\n"
     "Take extra care training outdoors in summer heat (+40°C)."),

    ("faq", 46, "Biotin, soch, teri va tirnoq",
     "soch to'kilishiga nima ichish kerak\nbiotin\ntirnoq uchun vitamin\nвыпадение волос что пить\nбиотин\nhair loss vitamins\nbiotin hair",
     "biotin, soch, tirnoq, teri, биотин, волосы, ногти, кожа, hair, nails, skin, kollagen",
     "Soch, teri va tirnoq uchun vitaminlar faqat **yetishmovchilik bo'lsa** yordam beradi. Soch to'kilishining eng ko'p sabablari: temir (ferritin), D vitamini, oqsil kamligi, stress, qalqonsimon bez va keskin ozish.\n\n"
     "• Avval tahlil: ferritin, D vitamini, TTG.\n• Kuniga yetarli oqsil (1,2–1,6 g/kg) va kaloriya.\n"
     "• Biotin kam hollarda kerak; muhim: biotin qon tahlillarini (qalqonsimon bez, troponin) buzadi — tahlildan 2–3 kun oldin to'xtating.\n"
     "• Kollagen teri elastikligiga yordam berishi mumkin.\n\n"
     "Ko'p soch to'kilsa — dermatolog.",
     "Витамины для волос, кожи и ногтей помогают **только при дефиците**. Самые частые причины выпадения волос: железо (ферритин), витамин D, нехватка белка, стресс, щитовидная железа и резкое похудение.\n\n"
     "• Сначала анализы: ферритин, витамин D, ТТГ.\n• Достаточно белка (1,2–1,6 г/кг) и калорий.\n"
     "• Биотин нужен редко; важно: он искажает анализы (щитовидка, тропонин) — прекратите за 2–3 дня до сдачи крови.\n"
     "• Коллаген может улучшить упругость кожи.\n\n"
     "При сильном выпадении — к дерматологу.",
     "Hair, skin and nail vitamins only help **if you're deficient**. The usual causes of hair loss: low iron (ferritin), vitamin D, too little protein, stress, thyroid and crash dieting.\n\n"
     "• Test first: ferritin, vitamin D, TSH.\n• Eat enough protein (1.2–1.6 g/kg) and calories.\n"
     "• Biotin is rarely needed; note it skews blood tests (thyroid, troponin) — stop 2–3 days before a test.\n"
     "• Collagen may help skin elasticity.\n\n"
     "Heavy hair loss — see a dermatologist."),

    ("faq", 52, "Immunitet uchun nima ichish kerak",
     "immunitetni ko'tarish uchun nima ichish kerak\ntez-tez shamollayman\nдля иммунитета что пить\nчасто болею\nimmune support\ni get sick often",
     "immunitet, shamollash, иммунитет, простуда, часто болею, immune, cold, flu, gripp, грипп",
     "Immunitetni bitta «sehrli» mahsulot ko'tarmaydi. Eng muhimi: 7–9 soat uyqu, yetarli oqsil va kaloriya, meva-sabzavot, me'yoridagi mashg'ulot (haddan tashqari yuklama immunitetni pasaytiradi).\n\n"
     "Dalillari borlari:\n• **D vitamini** — yetishmovchilik bo'lsa (ayniqsa qishda).\n"
     "• **Rux** — shamollashning birinchi kunidan boshlansa, davomiyligini qisqartirishi mumkin.\n"
     "• **C vitamini** — muntazam ichganda shamollash biroz qisqaroq o'tadi.\n• **Probiotiklar** — ayrim shtammlar.\n\n"
     "Tez-tez kasal bo'lsangiz, shifokorga murojaat qilib tahlil topshiring.",
     "Иммунитет не поднимает один «волшебный» продукт. Главное: сон 7–9 часов, достаточно белка и калорий, овощи и фрукты, умеренные тренировки (перегрузки снижают иммунитет).\n\n"
     "С доказательствами:\n• **Витамин D** — при дефиците (особенно зимой).\n"
     "• **Цинк** — с первого дня простуды может сократить её длительность.\n"
     "• **Витамин C** — при регулярном приёме простуда проходит чуть быстрее.\n• **Пробиотики** — отдельные штаммы.\n\n"
     "Если болеете часто — обратитесь к врачу и сдайте анализы.",
     "No single 'magic' product boosts immunity. What matters most: 7–9 hours of sleep, enough protein and calories, fruit and vegetables, and moderate training (overtraining lowers immunity).\n\n"
     "With evidence:\n• **Vitamin D** — if you're low (especially in winter).\n"
     "• **Zinc** — started on day one of a cold, may shorten it.\n"
     "• **Vitamin C** — taken regularly, colds pass a little faster.\n• **Probiotics** — certain strains.\n\n"
     "If you're ill often, see a doctor and get tested."),

    ("faq", 45, "Doimiy charchoq va holsizlik",
     "doim charchab yuraman\nholsizlik uchun nima ichish kerak\nenergiya yo'q\nпостоянная усталость\nнет сил что пить\nalways tired\nno energy",
     "charchoq, holsizlik, energiya, усталость, слабость, нет сил, tired, fatigue, energy",
     "Doimiy charchoqni avval sababini topish kerak — qo'shimcha uni yashirib qo'ymasin.\n\n"
     "Ko'p uchraydigan sabablar: uyqu yetishmasligi, juda kam kaloriya (keskin parhez), haddan ortiq mashg'ulot, temir, B12 yoki D vitamini yetishmovchiligi, qalqonsimon bez muammolari.\n\n"
     "• Tahlil: umumiy qon tahlili, ferritin, B12, D vitamini, TTG.\n• Uyqu 7–9 soat, mashg'ulot hajmini vaqtincha kamaytiring.\n"
     "• Kaloriya va uglevod yetarli bo'lsin, ayniqsa mashg'ulot kunlari.\n\n"
     "Tahlilda yetishmovchilik chiqsa, mos qo'shimchani (temir, B12, D3) tanlashda yordam beraman.",
     "Сначала найдите причину усталости — добавка не должна её маскировать.\n\n"
     "Частые причины: недосып, слишком мало калорий (жёсткая диета), перетренированность, дефицит железа, B12 или витамина D, проблемы щитовидной железы.\n\n"
     "• Анализы: общий анализ крови, ферритин, B12, витамин D, ТТГ.\n• Сон 7–9 часов, временно снизьте объём тренировок.\n"
     "• Достаточно калорий и углеводов, особенно в дни тренировок.\n\n"
     "Если анализ покажет дефицит — помогу подобрать добавку (железо, B12, D3).",
     "Find the cause of constant fatigue first — a supplement shouldn't mask it.\n\n"
     "Common causes: too little sleep, too few calories (crash dieting), overtraining, low iron, B12 or vitamin D, thyroid problems.\n\n"
     "• Tests: full blood count, ferritin, B12, vitamin D, TSH.\n• Sleep 7–9 hours and cut training volume for a while.\n"
     "• Eat enough calories and carbs, especially on training days.\n\n"
     "If a test shows a deficiency, I'll help you pick the right supplement (iron, B12, D3)."),
]
