"""
Expert knowledge, part 2: sports supplements -- protein types, creatine questions, amino acids, stimulants, joint and
sleep products. Doses follow ISSN position stands (protein, creatine, caffeine, beta-alanine) and label-level amounts.
Data for migration 0006.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("product", 60, "Konsentrat, izolyat va gidrolizat farqi",
     "izolyat va konsentrat farqi\nqaysi protein yaxshi izolyatmi\nгидролизат что это\nизолят или концентрат\nisolate vs concentrate\nwhat is hydrolysate",
     "izolyat, konsentrat, gidrolizat, изолят, концентрат, гидролизат, isolate, concentrate, hydrolysate, whey, farqi, разница",
     "Uchalasi ham zardob (whey) oqsili, farqi tozalash darajasida:\n"
     "• **Konsentrat (WPC)** — 70–80% oqsil, ozroq laktoza va yog'; eng hamyonbop, ta'mi yaxshi. Ko'pchilik uchun yetarli.\n"
     "• **Izolyat (WPI)** — 85–90%+ oqsil, laktoza va yog' deyarli yo'q. Laktozani ko'tara olmaydiganlar, ozish va qat'iy parhez uchun.\n"
     "• **Gidrolizat** — oldindan «parchalangan», eng tez so'riladi, qimmatroq va biroz achchiq. Ko'pchilikka shart emas.\n\n"
     "Mushak o'sishi uchun asosiysi — kunlik oqsil miqdori, turi emas. Byudjet cheklangan bo'lsa — konsentrat; oshqozon bezovta qilsa — izolyat.",
     "Все три — сывороточный белок, разница в степени очистки:\n"
     "• **Концентрат (WPC)** — 70–80% белка, немного лактозы и жира; самый доступный и вкусный. Большинству достаточно.\n"
     "• **Изолят (WPI)** — 85–90%+ белка, почти без лактозы и жира. При непереносимости лактозы, на сушке и строгой диете.\n"
     "• **Гидролизат** — «предварительно расщеплён», усваивается быстрее всех, дороже и чуть горчит. Большинству не обязателен.\n\n"
     "Для роста мышц главное — суточное количество белка, а не вид. Ограничен бюджет — концентрат; беспокоит желудок — изолят.",
     "All three are whey protein; they differ in how far they're filtered:\n"
     "• **Concentrate (WPC)** — 70–80% protein with a little lactose and fat; the most affordable and tastiest. Enough for most people.\n"
     "• **Isolate (WPI)** — 85–90%+ protein, almost no lactose or fat. For lactose sensitivity, cutting and strict diets.\n"
     "• **Hydrolysate** — 'pre-digested', absorbs fastest, costs more and tastes slightly bitter. Not needed by most.\n\n"
     "For muscle growth what matters is your daily protein total, not the type. On a budget — concentrate; if your stomach complains — isolate."),

    ("usage", 55, "Kazein — kechki protein",
     "kazein nima\nkazein qachon ichiladi\nuxlashdan oldin protein\nказеин когда пить\nпротеин на ночь\nwhat is casein\nprotein before bed",
     "kazein, casein, казеин, kechasi, uxlashdan oldin, на ночь, перед сном, night, before bed, sekin",
     "Kazein — sutning «sekin» oqsili: oshqozonda quyuqlashib, 5–7 soat davomida aminokislotalarni asta-sekin beradi.\n\n"
     "• Uxlashdan oldin 30–40 g — tunda tiklanishga yordam beradi (tadqiqotlarda tasdiqlangan).\n"
     "• Ovqatlar orasida uzoq tanaffus bo'lsa ham qulay.\n• Suv yoki sut bilan; quyuqroq bo'ladi — shaker bilan yaxshi aralashtiring.\n\n"
     "Kazein majburiy emas: kechqurun tvorog yoki qatiq ham xuddi shunday ishlaydi. Asosiysi — kunlik oqsil me'yori.",
     "Казеин — «медленный» белок молока: в желудке сгущается и отдаёт аминокислоты 5–7 часов.\n\n"
     "• 30–40 г перед сном помогают ночному восстановлению (подтверждено исследованиями).\n"
     "• Удобен при длинных перерывах между едой.\n• С водой или молоком; получается гуще — хорошо взбейте в шейкере.\n\n"
     "Казеин не обязателен: творог или кефир вечером работают так же. Главное — суточная норма белка.",
     "Casein is milk's 'slow' protein: it thickens in the stomach and releases amino acids over 5–7 hours.\n\n"
     "• 30–40 g before bed supports overnight recovery (shown in studies).\n"
     "• Handy for long gaps between meals.\n• Mix with water or milk; it's thicker — shake well.\n\n"
     "Casein is optional: cottage cheese or yoghurt in the evening does the same. Your daily protein total matters most."),

    ("product", 50, "O'simlik (vegan) protein",
     "vegan protein bormi\no'simlik oqsili\nрастительный протеин\nвеганский протеин\nplant protein\nvegan protein",
     "vegan, o'simlik, no'xat, guruch, soya, растительный, веган, гороховый, соевый, plant, pea, rice, soy",
     "O'simlik proteini (no'xat, guruch, soya) vegan, vegetarianlar va sutni ko'tara olmaydiganlar uchun.\n\n"
     "• Eng yaxshisi — **aralash** (no'xat + guruch): aminokislota tarkibi zardobga yaqinlashadi.\n"
     "• Porsiyani biroz kattaroq oling (30–40 g) — leytsin kamroq bo'ladi.\n• Soya to'liq oqsil; me'yorida xavfsiz.\n\n"
     "Vegan bo'lsangiz B12, temir, omega-3 (suv o'tidan) va D vitaminiga ham e'tibor bering.",
     "Растительный протеин (гороховый, рисовый, соевый) — для веганов, вегетарианцев и тех, кто не переносит молочное.\n\n"
     "• Лучше **смесь** (горох + рис): аминокислотный профиль ближе к сыворотке.\n"
     "• Берите порцию чуть больше (30–40 г) — лейцина меньше.\n• Соя — полноценный белок, в норме безопасна.\n\n"
     "Веганам также важны B12, железо, омега-3 (из водорослей) и витамин D.",
     "Plant protein (pea, rice, soy) suits vegans, vegetarians and anyone who can't tolerate dairy.\n\n"
     "• Best is a **blend** (pea + rice): its amino-acid profile gets close to whey.\n"
     "• Use a slightly bigger serving (30–40 g) — it has less leucine.\n• Soy is a complete protein and safe in normal amounts.\n\n"
     "Vegans should also watch B12, iron, omega-3 (algae-based) and vitamin D."),

    ("faq", 55, "Kreatin haqida miflar",
     "kreatin sochni to'kadimi\nkreatin suv to'playdimi\nkreatin zararlimi\nkreatin kurs qilish kerakmi\nкреатин вредно\nкреатин выпадение волос\nкреатин задерживает воду\nis creatine safe\ncreatine hair loss\ndo i need to cycle creatine",
     "kreatin, creatine, креатин, mif, soch, suv, zarar, kurs, buyrak, миф, волосы, вода, вред, курс, почки, myth, hair, water, cycle, safe",
     "Kreatin — eng ko'p o'rganilgan sport qo'shimchasi (500 dan ortiq tadqiqot).\n"
     "• **Zararlimi?** Sog'lom odamda kuniga 3–5 g yillar davomida xavfsiz. Buyrak kasalligi bo'lsa — shifokor.\n"
     "• **Suv to'playdimi?** Suv mushak **ichida** to'planadi (1–2 kg vazn ortishi) — bu mushakni to'liqroq ko'rsatadi, teri ostida «shishish» emas.\n"
     "• **Soch to'kadimi?** Bitta kichik tadqiqotdan kelib chiqqan gumon, isbotlanmagan.\n"
     "• **Kurs qilish kerakmi?** Yo'q, uzluksiz ichsa bo'ladi; to'xtatsangiz zarari yo'q.\n"
     "• **Yuklama shartmi?** Yo'q — kuniga 3–5 g bilan 3–4 haftada to'yinasiz.\n"
     "• **Monohidrat yoki HCl?** Monohidrat — eng isbotlangan va arzon.\n\n"
     "Ayollar, 40+ yoshdagilar ham ichishi mumkin — kuch va mushakni saqlashga yordam beradi.",
     "Креатин — самая изученная спортивная добавка (более 500 исследований).\n"
     "• **Вредно?** Для здорового человека 3–5 г в день годами безопасно. При болезни почек — к врачу.\n"
     "• **Задерживает воду?** Вода накапливается **внутри** мышц (+1–2 кг) — мышцы выглядят полнее, это не отёк под кожей.\n"
     "• **Выпадение волос?** Предположение из одного маленького исследования, не доказано.\n"
     "• **Нужны курсы?** Нет, можно пить постоянно; бросить тоже без вреда.\n"
     "• **Загрузка обязательна?** Нет — на 3–5 г в день мышцы насытятся за 3–4 недели.\n"
     "• **Моногидрат или HCl?** Моногидрат — самый доказанный и недорогой.\n\n"
     "Женщинам и людям 40+ тоже можно — помогает силе и сохранению мышц.",
     "Creatine is the most-studied sports supplement (500+ studies).\n"
     "• **Is it harmful?** 3–5 g a day for years is safe in healthy people. With kidney disease, see a doctor.\n"
     "• **Water retention?** The water goes **into** the muscle (+1–2 kg) — muscles look fuller; it's not puffiness under the skin.\n"
     "• **Hair loss?** A hypothesis from one small study, not proven.\n"
     "• **Do I need to cycle it?** No, you can take it continuously; stopping is harmless too.\n"
     "• **Is loading necessary?** No — at 3–5 g a day muscles saturate in 3–4 weeks.\n"
     "• **Monohydrate or HCl?** Monohydrate is the best-proven and cheapest.\n\n"
     "Women and people over 40 can take it too — it helps strength and keeping muscle."),

    ("faq", 48, "Kreatin ayollar uchun",
     "ayollar kreatin ichsa bo'ladimi\nqizlarga kreatin\nкреатин для женщин\ncreatine for women",
     "ayollar, qizlar, kreatin, женщины, девушки, креатин, women, creatine, female",
     "Ha. Kreatin ayollarga ham kuch, mushak tonusi va tiklanishda yordam beradi; «erkakcha» qilib qo'ymaydi, gormonlarga ta'sir qilmaydi.\n\n"
     "• Kuniga 3–5 g, har kuni.\n• Birinchi haftalarda 0,5–1 kg vazn ortishi — mushak ichidagi suv, yog' emas.\n"
     "• Menopauzadan keyin suyak va mushakni saqlashga ham foydali.\n\n"
     "Homiladorlik va emizish davrida ma'lumot yetarli emas — shifokor bilan maslahatlashing.",
     "Да. Креатин помогает и женщинам: сила, тонус мышц, восстановление; «мужеподобной» не делает и на гормоны не влияет.\n\n"
     "• 3–5 г каждый день.\n• В первые недели +0,5–1 кг — это вода в мышцах, не жир.\n"
     "• После менопаузы полезен для сохранения мышц и костей.\n\n"
     "При беременности и кормлении данных мало — посоветуйтесь с врачом.",
     "Yes. Creatine helps women too — strength, muscle tone and recovery; it won't make you bulky or affect hormones.\n\n"
     "• 3–5 g every day.\n• A 0.5–1 kg gain in the first weeks is water inside muscle, not fat.\n"
     "• After menopause it also helps preserve muscle and bone.\n\n"
     "In pregnancy and breastfeeding there's too little data — ask your doctor."),

    ("product", 50, "BCAA yoki EAA",
     "bcaa yoki eaa\neaa nima\nbcaa kerakmi agar protein ichsam\nbcaa или eaa\nнужны ли bcaa если пью протеин\nbcaa vs eaa\ndo i need bcaa",
     "bcaa, eaa, aminokislota, аминокислоты, amino, leytsin, лейцин, leucine, kerakmi, нужны ли",
     "• **BCAA** — 3 ta aminokislota (leytsin, izoleytsin, valin). Yolg'iz o'zi mushak qurish uchun yetarli emas.\n"
     "• **EAA** — barcha 9 ta almashtirib bo'lmaydigan aminokislota; mushak oqsili sintezi uchun BCAA dan yaxshiroq.\n\n"
     "Kuniga yetarli oqsil (ovqat + protein) olsangiz, BCAA/EAA dan qo'shimcha foyda kam. Ular foydali bo'ladigan holatlar: och qoringa erta tongda mashq, 90 daqiqadan uzoq mashg'ulot, oqsil kam parhez yoki mashg'ulot davomida ichish uchun yengil ichimlik istasangiz.\n\n"
     "Dozasi: 5–10 g mashg'ulot oldidan yoki davomida. Pul tejamoqchi bo'lsangiz — avval protein va kreatin.",
     "• **BCAA** — 3 аминокислоты (лейцин, изолейцин, валин). Сами по себе для роста мышц недостаточны.\n"
     "• **EAA** — все 9 незаменимых аминокислот; для синтеза мышечного белка лучше BCAA.\n\n"
     "Если белка в день хватает (еда + протеин), дополнительная польза BCAA/EAA мала. Полезны: при тренировке натощак рано утром, нагрузке дольше 90 минут, малобелковой диете или если хочется лёгкого напитка во время тренировки.\n\n"
     "Доза: 5–10 г до или во время тренировки. Экономите — сначала протеин и креатин.",
     "• **BCAA** — 3 amino acids (leucine, isoleucine, valine). On their own they aren't enough to build muscle.\n"
     "• **EAA** — all 9 essential amino acids; better than BCAA for muscle protein synthesis.\n\n"
     "If you already get enough protein (food + shakes), extra benefit from BCAA/EAA is small. They make sense for fasted early-morning training, sessions over 90 minutes, low-protein diets, or as a light drink during training.\n\n"
     "Dose: 5–10 g before or during training. On a budget — protein and creatine first."),

    ("usage", 52, "Pre-workout tarkibi va xavfsizligi",
     "pre-workout ichsam terim chimchilaydi\npre-workout tarkibi\nпредтрен покалывание\nчто в предтренике\npre workout tingling\nwhat is in pre-workout",
     "pre-workout, preworkout, предтрен, chimchilash, qichishish, покалывание, tingling, kofein, beta-alanin, sitrullin, stimulyator",
     "Pre-workout odatda: **kofein** (energiya, diqqat), **beta-alanin** (chidamlilik), **sitrullin** (pamp), ba'zan kreatin, tirozin, taurin.\n\n"
     "• Teridagi chimchilash/qichishish — beta-alanin ta'siri (paresteziya), zararsiz, 30–60 daqiqada o'tadi.\n"
     "• Qizarish — niatsin (B3) ta'siri, zararsiz.\n"
     "• Yarim porsiyadan boshlang; kofein miqdorini qadoqda tekshiring (kuniga jami 400 mg dan oshmasin, qahva va energetiklarni ham hisoblang).\n"
     "• Mashg'ulotdan 20–30 daqiqa oldin, 16:00 dan keyin ichmang — uyqu buziladi.\n\n"
     "Yurak, bosim muammosi, homiladorlik, 18 yoshgacha — ichmang. Kofeinsiz (stim-free) variant ham bor.",
     "В предтрене обычно: **кофеин** (энергия, фокус), **бета-аланин** (выносливость), **цитруллин** (памп), иногда креатин, тирозин, таурин.\n\n"
     "• Покалывание/зуд кожи — эффект бета-аланина (парестезия), безвреден, проходит за 30–60 минут.\n"
     "• Покраснение — от ниацина (B3), безвредно.\n"
     "• Начните с половины порции; проверьте кофеин на упаковке (всего не больше 400 мг в день, считая кофе и энергетики).\n"
     "• За 20–30 минут до тренировки, не позже 16:00 — иначе страдает сон.\n\n"
     "При проблемах с сердцем и давлением, беременности, до 18 лет — нельзя. Есть варианты без стимуляторов (stim-free).",
     "A pre-workout usually contains **caffeine** (energy, focus), **beta-alanine** (endurance), **citrulline** (pump), sometimes creatine, tyrosine, taurine.\n\n"
     "• Skin tingling/itching comes from beta-alanine (paresthesia) — harmless, gone in 30–60 minutes.\n"
     "• Flushing comes from niacin (B3) — harmless.\n"
     "• Start with half a scoop; check the caffeine on the label (no more than 400 mg a day in total, counting coffee and energy drinks).\n"
     "• 20–30 minutes before training, not after about 4 pm — it hurts sleep.\n\n"
     "Not for heart or blood-pressure problems, pregnancy or under 18. Stimulant-free versions exist."),

    ("usage", 48, "Kofein va energetiklar",
     "kofein qancha ichish mumkin\nkuniga necha mg kofein\nэнергетик перед тренировкой\nсколько кофеина можно\nhow much caffeine is safe\ncaffeine before workout",
     "kofein, qahva, energetik, кофеин, кофе, энергетик, caffeine, coffee, energy drink, mg",
     "Kofein — eng isbotlangan stimulyator: kuch, chidamlilik va diqqatni oshiradi.\n\n"
     "• Samarali doza: mashg'ulotdan 30–60 daqiqa oldin 3 mg/kg (70 kg — ~200 mg, 2 piyola qahvaga teng).\n"
     "• Sog'lom kattalar uchun kuniga jami 400 mg dan oshmasin; homiladorlarga 200 mg gacha.\n"
     "• Uyqudan 6–8 soat oldin to'xtating.\n• Energetiklarda shakar ko'p — qahva yoki pre-workout yaxshiroq.\n\n"
     "Yurak urishi tezlashsa, xavotir, bosh og'rig'i bo'lsa — dozani kamaytiring. Yurak va bosim muammosida ichmang.",
     "Кофеин — самый доказанный стимулятор: повышает силу, выносливость и концентрацию.\n\n"
     "• Рабочая доза: 3 мг/кг за 30–60 минут до тренировки (при 70 кг ~200 мг, как 2 чашки кофе).\n"
     "• Здоровым взрослым всего не больше 400 мг в день; беременным до 200 мг.\n"
     "• Заканчивайте за 6–8 часов до сна.\n• В энергетиках много сахара — кофе или предтрен лучше.\n\n"
     "Если учащается пульс, тревога, головная боль — снизьте дозу. При проблемах с сердцем и давлением — нельзя.",
     "Caffeine is the best-proven stimulant: it raises strength, endurance and focus.\n\n"
     "• Effective dose: 3 mg/kg 30–60 minutes before training (~200 mg at 70 kg, about 2 cups of coffee).\n"
     "• Healthy adults: no more than 400 mg a day in total; in pregnancy up to 200 mg.\n"
     "• Stop 6–8 hours before sleep.\n• Energy drinks are full of sugar — coffee or a pre-workout is better.\n\n"
     "Racing heart, anxiety or headache? Lower the dose. Avoid with heart or blood-pressure problems."),

    ("usage", 46, "L-sitrullin va pamp",
     "sitrullin nima\npamp uchun nima ichish kerak\nцитруллин для чего\nдля пампа\ncitrulline malate\nfor pump",
     "sitrullin, citrulline, цитруллин, pamp, памп, pump, arginin, аргинин, arginine, oksid azot, nitric oxide",
     "L-sitrullin qon tomirlarini kengaytiradi: mushak «to'lishi» (pamp) kuchayadi va takrorlar soni biroz ortadi. Arginindan yaxshiroq ishlaydi, chunki yaxshi so'riladi.\n\n"
     "• Sitrullin malat: mashg'ulotdan 40–60 daqiqa oldin 6–8 g.\n• Kofeinsiz — kechki mashg'ulotga ham mos.\n\n"
     "Bosim tushiruvchi yoki erektil disfunksiya dorilari bilan birga — shifokor bilan.",
     "L-цитруллин расширяет сосуды: сильнее «памп» и немного больше повторений. Работает лучше аргинина, потому что лучше усваивается.\n\n"
     "• Цитруллин малат: 6–8 г за 40–60 минут до тренировки.\n• Без кофеина — подходит и для вечерних тренировок.\n\n"
     "Вместе с препаратами от давления или для потенции — только с врачом.",
     "L-citrulline widens blood vessels: a bigger pump and slightly more reps. It beats arginine because it absorbs better.\n\n"
     "• Citrulline malate: 6–8 g 40–60 minutes before training.\n• Caffeine-free — fine for evening sessions too.\n\n"
     "With blood-pressure or erectile-dysfunction medication, ask a doctor."),

    ("faq", 50, "Yog' yoqiruvchilar haqiqatdan ishlaydimi",
     "yog' yoqiruvchi ishlaydimi\nfat burner foydasi\nжиросжигатель работает ли\nfat burner does it work\nтермогеник",
     "yog' yoqiruvchi, fat burner, жиросжигатель, термогеник, thermogenic, ozish, похудение, karnitin, cla, yashil choy, green tea",
     "Halol javob: hech qaysi «yog' yoqiruvchi» kaloriya defitsitisiz ishlamaydi. Eng yaxshi holatda u ozishni biroz tezlashtiradi.\n\n"
     "• **Kofeinli termogeniklar** — ishtahani kamaytirib, energiya berishi mumkin; yurak va bosimga yuk.\n"
     "• **L-karnitin** — ta'siri kichik, faqat defitsit va kardio bilan.\n"
     "• **CLA, malina ketonlari, garcinia** — dalil kam.\n"
     "• **Yashil choy ekstrakti** — yuqori dozada och qoringa ichilganda jigarga zarar holatlari bor.\n\n"
     "Ishlaydigan formula: kaloriya defitsiti (−300…−500 kkal), yuqori oqsil (1,8–2,4 g/kg), kuch mashqlari va kuniga 8–10 ming qadam. Protein bu yerda eng foydali qo'shimcha — to'yintiradi va mushakni saqlaydi.",
     "Честно: никакой «жиросжигатель» не работает без дефицита калорий. В лучшем случае немного ускоряет похудение.\n\n"
     "• **Термогеники с кофеином** — могут снизить аппетит и дать энергию; нагрузка на сердце и давление.\n"
     "• **L-карнитин** — эффект небольшой, только с дефицитом и кардио.\n"
     "• **CLA, малиновые кетоны, гарциния** — доказательств мало.\n"
     "• **Экстракт зелёного чая** — в высоких дозах натощак описаны поражения печени.\n\n"
     "Рабочая формула: дефицит калорий (−300…−500 ккал), много белка (1,8–2,4 г/кг), силовые и 8–10 тысяч шагов в день. Протеин тут самая полезная добавка — насыщает и сохраняет мышцы.",
     "Honestly: no 'fat burner' works without a calorie deficit. At best it speeds fat loss slightly.\n\n"
     "• **Caffeine thermogenics** — can curb appetite and add energy; they load the heart and blood pressure.\n"
     "• **L-carnitine** — a small effect, only with a deficit and cardio.\n"
     "• **CLA, raspberry ketones, garcinia** — little evidence.\n"
     "• **Green tea extract** — liver injury has been reported at high doses on an empty stomach.\n\n"
     "What works: a calorie deficit (−300 to −500 kcal), high protein (1.8–2.4 g/kg), strength training and 8–10k steps a day. Protein is the most useful supplement here — it keeps you full and protects muscle."),

    ("usage", 45, "Glyukozamin va bo'g'imlar",
     "bo'g'im og'risa nima ichish kerak\ntizzam og'riydi nima ichay\nbo'g'imlarim og'riydi\nglyukozamin xondroitin\nсуставы болят что пить\nглюкозамин хондроитин\njoint pain supplement\nglucosamine",
     "bo'g'im, tizza, glyukozamin, xondroitin, msm, суставы, колени, глюкозамин, хондроитин, joints, knee, glucosamine, chondroitin, kollagen",
     "Bo'g'imlar uchun qo'shimchalarning dalillari aralash, lekin ba'zilarga og'riq kamayadi:\n"
     "• **Glyukozamin sulfat** 1500 mg + **xondroitin** 800–1200 mg kuniga, ovqat bilan, kamida 8–12 hafta — natijani shundan keyin baholang.\n"
     "• **Kollagen** (5–10 g, C vitamini bilan) — paylar va tog'ay uchun.\n• **Omega-3** — yallig'lanishni kamaytirishga yordam beradi.\n\n"
     "O'tkir og'riq, shish, jarohat bo'lsa — avval travmatolog. Dengiz mahsulotlariga allergiya yoki qon suyultiruvchi dori bo'lsa, glyukozamindan oldin shifokorga so'rang. Texnikani to'g'rilash va yuklamani bosqichma-bosqich oshirish ham muhim.",
     "Доказательства у добавок для суставов неоднозначные, но части людей боль уменьшают:\n"
     "• **Глюкозамина сульфат** 1500 мг + **хондроитин** 800–1200 мг в день с едой, не меньше 8–12 недель — оценивайте после.\n"
     "• **Коллаген** (5–10 г с витамином C) — для связок и хрящей.\n• **Омега-3** — помогает снизить воспаление.\n\n"
     "При острой боли, отёке, травме — сначала к травматологу. При аллергии на морепродукты или антикоагулянтах спросите врача про глюкозамин. Важны также техника и постепенный рост нагрузки.",
     "Joint supplements have mixed evidence, but some people get less pain:\n"
     "• **Glucosamine sulfate** 1500 mg + **chondroitin** 800–1200 mg a day with food for at least 8–12 weeks — judge it after that.\n"
     "• **Collagen** (5–10 g with vitamin C) — for tendons and cartilage.\n• **Omega-3** — helps reduce inflammation.\n\n"
     "Sharp pain, swelling or an injury — see a doctor first. With a shellfish allergy or blood thinners, ask about glucosamine. Good technique and gradual load increases matter too."),

    ("usage", 46, "Uyqu va tiklanish uchun qo'shimchalar",
     "uyqu uchun nima ichish kerak\nyaxshi uxlay olmayman\nmelatonin\nдля сна что пить\nплохо сплю\nsleep supplements\nmelatonin dose",
     "uyqu, uxlay olmayman, melatonin, magniy, ashvagandha, сон, бессонница, мелатонин, sleep, insomnia, recovery, tiklanish, восстановление",
     "Mushak uyquda tiklanadi — 7–9 soat uyqu har qanday qo'shimchadan muhim.\n\n"
     "Yordam beradiganlar:\n• **Magniy glitsinat** 200–350 mg kechqurun.\n"
     "• **Melatonin** 0,5–3 mg uxlashdan 30–60 daqiqa oldin, qisqa muddat (vaqt mintaqasi o'zgarganda, smenadan keyin).\n"
     "• **Ashvagandha** 300–600 mg — stress sababli uyqusizlikda.\n• **Kazein** — kechki oqsil, tunda tiklanish uchun.\n\n"
     "Odatlar: 16:00 dan keyin kofein yo'q (pre-workoutni ham hisoblang), qorong'i va salqin xona, uxlashdan oldin telefon kamroq. Melatonindan keyin mashina haydamang.",
     "Мышцы восстанавливаются во сне — 7–9 часов сна важнее любой добавки.\n\n"
     "Помогают:\n• **Магний глицинат** 200–350 мг вечером.\n"
     "• **Мелатонин** 0,5–3 мг за 30–60 минут до сна, короткими курсами (смена часовых поясов, после смен).\n"
     "• **Ашваганда** 300–600 мг — при бессоннице от стресса.\n• **Казеин** — вечерний белок для ночного восстановления.\n\n"
     "Привычки: без кофеина после 16:00 (учитывайте предтрен), тёмная прохладная комната, меньше телефона перед сном. После мелатонина не садитесь за руль.",
     "Muscles recover while you sleep — 7–9 hours of sleep matters more than any supplement.\n\n"
     "What helps:\n• **Magnesium glycinate** 200–350 mg in the evening.\n"
     "• **Melatonin** 0.5–3 mg 30–60 minutes before bed, short term (time-zone changes, after shifts).\n"
     "• **Ashwagandha** 300–600 mg — for stress-related poor sleep.\n• **Casein** — evening protein for overnight recovery.\n\n"
     "Habits: no caffeine after 4 pm (count your pre-workout), a dark cool room, less phone before bed. Don't drive after melatonin."),

    ("faq", 48, "Testosteron busterlar",
     "testosteron oshirish uchun nima ichish kerak\ntribulus ishlaydimi\nтестобустер работает ли\nкак поднять тестостерон\ntestosterone booster does it work",
     "testosteron, tribulus, buster, тестостерон, трибулус, тестобустер, testosterone, booster, erkak, мужчина",
     "Halol javob: tribulus, D-aspartat kislota va shunga o'xshash o'simlik busterlari sog'lom erkakda testosteronni sezilarli oshirishi isbotlanmagan.\n\n"
     "Testosteronga haqiqatan ta'sir qiladiganlar:\n• 7–9 soat uyqu.\n• D vitamini va rux — yetishmovchilik bo'lsa.\n"
     "• Yetarli kaloriya va yog' (juda qattiq parhez testosteronni tushiradi).\n• Kuch mashqlari va ortiqcha yog'ni kamaytirish.\n"
     "• Ashvagandha — ayrim tadqiqotlarda biroz ijobiy ta'sir.\n\n"
     "Belgilar bo'lsa (holsizlik, libido pasayishi) — tahlil va urolog/endokrinolog. Steroid va SARM bo'yicha maslahat bermaymiz — sog'liq uchun xavfli.",
     "Честно: трибулус, D-аспарагиновая кислота и подобные растительные бустеры заметно тестостерон у здоровых мужчин не повышают — это не доказано.\n\n"
     "Что реально влияет:\n• Сон 7–9 часов.\n• Витамин D и цинк — при дефиците.\n"
     "• Достаточно калорий и жиров (жёсткая диета снижает тестостерон).\n• Силовые тренировки и снижение лишнего жира.\n"
     "• Ашваганда — в части исследований небольшой эффект.\n\n"
     "Есть симптомы (слабость, снижение либидо) — анализы и уролог/эндокринолог. По стероидам и SARMs не консультируем — это опасно для здоровья.",
     "Honestly: tribulus, D-aspartic acid and similar herbal boosters haven't been shown to raise testosterone meaningfully in healthy men.\n\n"
     "What actually helps:\n• 7–9 hours of sleep.\n• Vitamin D and zinc — if you're deficient.\n"
     "• Enough calories and fat (harsh dieting lowers testosterone).\n• Strength training and losing excess fat.\n"
     "• Ashwagandha — a small effect in some studies.\n\n"
     "Symptoms (fatigue, low libido)? Get tested and see a urologist or endocrinologist. We don't advise on steroids or SARMs — they're dangerous to health."),

    ("faq", 46, "Probiotik va ichak salomatligi",
     "probiotik kerakmi\nprotein ichsam dam bo'laman\nproteindan dam bo'lyapman\nproteindan qornim og'riydi\nproteindan ichim ketyapti\nот протеина пучит\nпробиотик зачем\nвздутие от протеина\nprobiotic\nprotein bloating",
     "probiotik, ichak, dam bo'lish, gaz, пробиотик, кишечник, вздутие, газы, probiotic, gut, bloating, laktoza",
     "Ichak muammosi ko'pincha ovqatdan:\n"
     "• Proteindan **dam bo'lish** odatda laktoza yoki tez ichishdan — izolyatga o'ting, suv bilan, sekin iching; shirinlashtiruvchilar (sorbitol, ksilitol) ham sabab bo'lishi mumkin.\n"
     "• **Probiotiklar** antibiotik kursida va keyin, ayrim ichak muammolarida foydali; samarasi shtammga bog'liq, qadoqdagi dozada.\n"
     "• **Tola** (kuniga 25–35 g: sabzavot, dukkaklilar, suli, psillium) va yetarli suv — ich qotishiga qarshi.\n"
     "• Kefir, qatiq — tabiiy probiotik.\n\n"
     "Og'riq, qon, uzoq davom etgan ich ketishi bo'lsa — gastroenterolog.",
     "Проблемы с кишечником часто из-за еды:\n"
     "• **Вздутие** от протеина обычно из-за лактозы или быстрого питья — перейдите на изолят, на воде, пейте медленно; причиной бывают и подсластители (сорбит, ксилит).\n"
     "• **Пробиотики** полезны во время и после антибиотиков и при некоторых проблемах кишечника; эффект зависит от штамма, доза — по упаковке.\n"
     "• **Клетчатка** (25–35 г в день: овощи, бобовые, овсянка, псиллиум) и вода — против запоров.\n"
     "• Кефир, катык — природные пробиотики.\n\n"
     "Боль, кровь, затяжная диарея — к гастроэнтерологу.",
     "Gut issues often come from food:\n"
     "• **Bloating** from protein is usually lactose or drinking too fast — switch to isolate, mix with water, sip slowly; sweeteners (sorbitol, xylitol) can also cause it.\n"
     "• **Probiotics** help during and after antibiotics and with some gut problems; effects depend on the strain, use the label dose.\n"
     "• **Fibre** (25–35 g a day: vegetables, legumes, oats, psyllium) and water fight constipation.\n"
     "• Kefir and yoghurt are natural probiotics.\n\n"
     "Pain, blood or lasting diarrhoea — see a gastroenterologist."),

    ("faq", 44, "Protein va husnbuzar (akne)",
     "proteindan husnbuzar chiqadimi\nprotein yuzga toshma\nпротеин прыщи\nот протеина акне\ndoes whey cause acne",
     "husnbuzar, akne, toshma, teri, прыщи, акне, сыпь, acne, pimples, skin, whey",
     "Ba'zi odamlarda zardob (whey) proteini husnbuzarni kuchaytirishi mumkin — sut oqsillari insulin va IGF-1 ni oshiradi. Hammada emas.\n\n"
     "Agar shunday bo'lsa:\n• **Izolyat** ga o'ting yoki **o'simlik (vegan) proteini**ni sinab ko'ring.\n"
     "• Porsiyani kamaytirib, oqsilni ko'proq ovqatdan oling.\n• Shakar va geynerlarni kamaytiring.\n\n"
     "Husnbuzar kuchli bo'lsa — dermatolog.",
     "У части людей сывороточный протеин может усиливать акне — молочные белки повышают инсулин и IGF-1. Не у всех.\n\n"
     "Если это ваш случай:\n• Перейдите на **изолят** или попробуйте **растительный протеин**.\n"
     "• Уменьшите порции и добирайте белок едой.\n• Меньше сахара и гейнеров.\n\n"
     "При сильном акне — к дерматологу.",
     "In some people whey protein can worsen acne — dairy proteins raise insulin and IGF-1. Not everyone reacts.\n\n"
     "If it happens to you:\n• Switch to **isolate** or try a **plant protein**.\n"
     "• Use smaller servings and get more protein from food.\n• Cut sugar and gainers.\n\n"
     "Severe acne — see a dermatologist."),

    ("faq", 44, "Protein batonchiklar",
     "protein batonchik foydalimi\nбатончик протеиновый полезно\nprotein bar healthy",
     "batonchik, bar, батончик, protein bar, snack, перекус, gazak",
     "Protein batonchik — qulay gazak (15–25 g oqsil), ayniqsa yo'lda yoki mashg'ulotdan keyin.\n\n"
     "Tanlashda:\n• Oqsil kamida 15 g, shakar 5 g dan kam bo'lsa yaxshi.\n• Kaloriyani hisoblang — ba'zilari 250–300 kkal, ozishda bu muhim.\n"
     "• Polioli (maltit, sorbitol) ko'p bo'lsa, dam bo'lishi mumkin.\n\n"
     "Batonchik ovqat o'rnini bosmaydi, lekin shirinlik o'rniga juda yaxshi variant.",
     "Протеиновый батончик — удобный перекус (15–25 г белка), особенно в дороге или после тренировки.\n\n"
     "При выборе:\n• Белка от 15 г, сахара меньше 5 г — хорошо.\n• Считайте калории — в некоторых 250–300 ккал, на похудении это важно.\n"
     "• Много полиолов (мальтит, сорбит) — возможно вздутие.\n\n"
     "Батончик не заменяет еду, но отличная замена сладкому.",
     "A protein bar is a handy snack (15–25 g protein), especially on the go or after training.\n\n"
     "When choosing:\n• At least 15 g protein and under 5 g sugar is good.\n• Count calories — some have 250–300 kcal, which matters when cutting.\n"
     "• Lots of polyols (maltitol, sorbitol) can cause bloating.\n\n"
     "A bar doesn't replace a meal, but it's a great swap for sweets."),

    ("faq", 46, "Proteinni sut yoki suv bilan",
     "proteinni sut bilan ichsa bo'ladimi\nsuv bilanmi sut bilanmi\nпротеин на молоке или воде\nprotein with milk or water",
     "sut, suv, aralashtirish, молоко, вода, смешивать, milk, water, mix, shaker, sharbat",
     "Ikkalasi ham to'g'ri — maqsadga qarab:\n"
     "• **Suv bilan** — kamroq kaloriya, tez so'riladi, oshqozon yengil. Ozish va laktoza sezgirligida.\n"
     "• **Sut bilan** — +8 g oqsil va ~120–150 kkal (250 ml), ta'mi qaymoqliroq. Massa olishda.\n\n"
     "250–300 ml suyuqlik, avval suyuqlik keyin kukun — shunda kesak bo'lmaydi. Issiq suvga solmang (kesak bo'lib qoladi); tayyor kokteylni 1–2 soat ichida iching.",
     "Оба варианта верны — зависит от цели:\n"
     "• **На воде** — меньше калорий, быстрее усваивается, легче для желудка. На похудении и при чувствительности к лактозе.\n"
     "• **На молоке** — +8 г белка и ~120–150 ккал (250 мл), вкус сливочнее. На массе.\n\n"
     "250–300 мл жидкости, сначала жидкость, потом порошок — без комков. Не заливайте горячей водой (свернётся); готовый коктейль выпейте за 1–2 часа.",
     "Both work — it depends on your goal:\n"
     "• **With water** — fewer calories, faster absorption, lighter on the stomach. For fat loss and lactose sensitivity.\n"
     "• **With milk** — +8 g protein and ~120–150 kcal (250 ml), creamier taste. For gaining.\n\n"
     "Use 250–300 ml of liquid, liquid first then powder — no lumps. Don't use hot water (it clumps); drink the shake within 1–2 hours."),
]
