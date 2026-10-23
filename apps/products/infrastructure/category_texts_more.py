"""Vitamins and Accessories & Extras parts of the category descriptions (merged into category_texts.CATEGORY_TEXTS)."""
from __future__ import annotations

_DOCTOR_UZ = "Shifokor tavsiyasisiz yuqori dozalarni uzoq muddat qabul qilmang."
_DOCTOR_RU = "Не принимайте высокие дозы длительно без рекомендации врача."
_DOCTOR_EN = "Don't take high doses long-term without medical advice."

MORE_CATEGORY_TEXTS: dict[str, tuple[str, str, str]] = {
    # ================================================================ Vitamins
    "Vitamins": (
        "Vitaminlar va minerallar — organizmdagi yuzlab jarayonlar uchun zarur mikroelementlar: energiya almashinuvi, immunitet, suyak, asab tizimi va mushak qisqarishi. Faol sport bilan shug'ullanuvchilarda ularga ehtiyoj ortadi, ratsion esa har doim ham ularni to'liq qoplamaydi.\n\n"
        "Bo'limda: multivitaminlar, alohida vitaminlar (D3, C, B guruhi, E, K2), minerallar (magniy, rux, kalsiy, temir, selen), omega-3 (Ultra Omega, Omega + D3 + K2), bo'g'imlar uchun mahsulotlar (kollagen, glyukozamin, xondroitin), uyqu uchun vositalar, erkaklar uchun testosteron qo'llab-quvvatlovchi vositalar (tribulus, boosterlar) va bolalar vitaminlari.\n\n"
        "Qanday tanlash kerak: avvalo qon tahlili (masalan, D vitamini, ferritin) yetishmovchilikni aniqlashga yordam beradi. Kundalik asos — sifatli multivitamin, D3 va omega-3. Yaxshi so'riladigan shakllarni (xelatlar, metilfolat, D3 — D2 emas) tanlang.\n\n"
        "Muhim: «ko'p — yaxshi» emas. Yog'da eriydigan vitaminlar (A, D, E, K) va temir organizmda to'planishi mumkin. Homiladorlik, surunkali kasallik yoki dori qabul qilayotgan bo'lsangiz, shifokor bilan maslahatlashing.",
        "Витамины и минералы — микронутриенты, необходимые для сотен процессов в организме: энергетического обмена, иммунитета, костей, нервной системы и сокращения мышц. У людей, активно занимающихся спортом, потребность в них выше, а рацион не всегда покрывает её полностью.\n\n"
        "В разделе: мультивитамины, отдельные витамины (D3, C, группа B, E, K2), минералы (магний, цинк, кальций, железо, селен), омега-3 (Ultra Omega, Omega + D3 + K2), продукты для суставов (коллаген, глюкозамин, хондроитин), средства для сна, поддержка тестостерона для мужчин (трибулус, бустеры) и детские витамины.\n\n"
        "Как выбирать: анализ крови (например, витамин D, ферритин) помогает выявить дефицит. Ежедневная база — качественный мультивитамин, D3 и омега-3. Выбирайте хорошо усваиваемые формы (хелаты, метилфолат, D3, а не D2).\n\n"
        "Важно: «больше» не значит «лучше». Жирорастворимые витамины (A, D, E, K) и железо могут накапливаться в организме. При беременности, хронических заболеваниях или приёме лекарств проконсультируйтесь с врачом.",
        "Vitamins and minerals are micronutrients needed for hundreds of processes in the body — energy metabolism, immunity, bones, the nervous system and muscle contraction. Active people need more of them, and diet doesn't always cover it fully.\n\n"
        "This section includes multivitamins, single vitamins (D3, C, B-complex, E, K2), minerals (magnesium, zinc, calcium, iron, selenium), omega-3 (Ultra Omega, Omega + D3 + K2), joint support (collagen, glucosamine, chondroitin), sleep aids, testosterone support for men (tribulus, boosters) and kids' vitamins.\n\n"
        "How to choose: a blood test (for example vitamin D, ferritin) helps reveal deficiencies. A good daily base is a quality multivitamin, D3 and omega-3. Choose well-absorbed forms (chelates, methylfolate, D3 rather than D2).\n\n"
        "Important: more is not better. Fat-soluble vitamins (A, D, E, K) and iron can build up in the body. If you are pregnant, have a chronic condition or take medication, talk to a doctor.",
    ),
    "Multivitamins": (
        "Multivitaminlar — bitta tabletka yoki kapsulada asosiy vitamin va minerallarning kundalik majmuasi. Ular ratsiondagi kichik kamchiliklarni to'ldiradi va «sug'urta» vazifasini bajaradi — ayniqsa band hayot tarzi, parhez yoki intensiv mashg'ulotlarda.\n\n"
        "Turlari: har kungi (umumiy salomatlik), sport uchun (B vitaminlari, antioksidantlar va minerallar ko'proq), erkaklar uchun (rux, selen, likopen) va ayollar uchun (temir, foliy kislotasi, biotin).\n\n"
        "Qanday ichiladi: ovqat bilan, yog'da eriydigan vitaminlar yaxshi so'rilishi uchun. Bir necha tabletkaga bo'lingan dozalar kun davomida bir tekis so'riladi. Tanlashda foliy kislotasi o'rniga metilfolat, B12 ning metilkobalamin shakli va minerallarning xelat shakllari afzal.",
        "Мультивитамины — ежедневный комплекс основных витаминов и минералов в одной таблетке или капсуле. Они восполняют небольшие пробелы в рационе и работают как «страховка» — особенно при занятом образе жизни, диете или интенсивных тренировках.\n\n"
        "Виды: ежедневные (общее здоровье), для спорта (больше витаминов B, антиоксидантов и минералов), для мужчин (цинк, селен, ликопин) и для женщин (железо, фолиевая кислота, биотин).\n\n"
        "Как принимать: во время еды, чтобы лучше усвоились жирорастворимые витамины. Дозы, разделённые на несколько таблеток, усваиваются равномернее в течение дня. Предпочтительны метилфолат вместо фолиевой кислоты, B12 в форме метилкобаламина и минералы в хелатной форме.",
        "Multivitamins provide a daily complex of key vitamins and minerals in one tablet or capsule. They fill small gaps in your diet and act as insurance — especially with a busy lifestyle, dieting or intense training.\n\n"
        "Types: daily (general health), sport (more B vitamins, antioxidants and minerals), men's (zinc, selenium, lycopene) and women's (iron, folate, biotin).\n\n"
        "How to take: with food, so fat-soluble vitamins absorb better; doses split across several tablets absorb more evenly through the day. Prefer methylfolate over folic acid, B12 as methylcobalamin and minerals in chelated forms.",
    ),
    "Daily": (
        "Har kungi multivitaminlar — umumiy salomatlik, energiya va immunitet uchun muvozanatli asos. Ular kundalik me'yorlarga yaqin dozalardagi vitaminlar va minerallarni o'z ichiga oladi va har qanday turmush tarzidagi kattalar uchun mos.\n\n"
        "Kuniga 1 marta (ba'zan 2–3 tabletka) ovqat bilan qabul qilinadi. Muntazamlik muhim — natija haftalar davomida to'planadi.",
        "Ежедневные мультивитамины — сбалансированная основа для общего здоровья, энергии и иммунитета. Они содержат витамины и минералы в дозах, близких к суточным нормам, и подходят взрослым с любым образом жизни.\n\n"
        "Принимают 1 раз в день (иногда 2–3 таблетки) во время еды. Важна регулярность — эффект накапливается неделями.",
        "Daily multivitamins are a balanced base for general health, energy and immunity, with vitamins and minerals close to daily reference amounts — suitable for adults with any lifestyle.\n\n"
        "Take once a day (sometimes 2–3 tablets) with food. Consistency matters — the benefit builds over weeks.",
    ),
    "Sport": (
        "Sport multivitaminlari faol mashg'ulot qiluvchilarning ortgan ehtiyojiga moslashtirilgan: B guruhi vitaminlari (energiya almashinuvi), C va E vitaminlari (antioksidant himoya), magniy, rux va kaliy (mushak ishi va tiklanish) ko'proq.\n\n"
        "Ko'pincha ertalab va tushdan keyin ovqat bilan, porsiyani ikki qismga bo'lib ichiladi. Haftasiga 3 va undan ko'p mashg'ulot qiladiganlar uchun mos.",
        "Спортивные мультивитамины рассчитаны на повышенные потребности активно тренирующихся: больше витаминов группы B (энергетический обмен), C и E (антиоксидантная защита), магния, цинка и калия (работа мышц и восстановление).\n\n"
        "Часто порцию делят на два приёма — утром и после обеда во время еды. Подходят тем, кто тренируется 3 и более раз в неделю.",
        "Sport multivitamins are tailored to the higher needs of active people: more B vitamins (energy metabolism), vitamins C and E (antioxidant protection) and magnesium, zinc and potassium (muscle function and recovery).\n\n"
        "The serving is often split between morning and afternoon meals. Suitable for anyone training three or more times a week.",
    ),
    "Men's": (
        "Erkaklar uchun multivitaminlarda erkak organizmining ehtiyojlari hisobga olingan: rux va selen (testosteron va reproduktiv salomatlik), D vitamini, magniy, B vitaminlari va ko'pincha likopen, arra palmasi kabi prostata salomatligini qo'llab-quvvatlovchi komponentlar. Odatda temir kamroq yoki umuman yo'q.\n\n"
        "Kuniga ovqat bilan qabul qilinadi; energiya, immunitet va faol hayot tarzini qo'llab-quvvatlash uchun.",
        "В мужских мультивитаминах учтены потребности мужского организма: цинк и селен (тестостерон и репродуктивное здоровье), витамин D, магний, витамины B и часто ликопин и пальма сереноа для здоровья простаты. Железа обычно меньше или нет совсем.\n\n"
        "Принимают ежедневно во время еды — для поддержки энергии, иммунитета и активного образа жизни.",
        "Men's multivitamins reflect men's needs: zinc and selenium (testosterone and reproductive health), vitamin D, magnesium, B vitamins and often lycopene or saw palmetto for prostate health. They usually contain little or no iron.\n\n"
        "Take daily with food to support energy, immunity and an active lifestyle.",
    ),
    "Women's": (
        "Ayollar uchun multivitaminlarda temir (hayz davrida yo'qotiladigan), foliy kislotasi/metilfolat, kalsiy va D vitamini (suyaklar uchun), shuningdek teri, soch va tirnoqlar uchun biotin bor. Ba'zilarida gormonal muvozanat uchun o'simlik ekstraktlari mavjud.\n\n"
        "Kuniga ovqat bilan qabul qilinadi. Homiladorlikni rejalashtirayotgan yoki homilador ayollar uchun maxsus prenatal vitaminlar tanlanadi — shifokor bilan maslahatlashing.",
        "В женских мультивитаминах есть железо (теряемое во время менструации), фолиевая кислота/метилфолат, кальций и витамин D (для костей), а также биотин для кожи, волос и ногтей. В некоторых — растительные экстракты для гормонального баланса.\n\n"
        "Принимают ежедневно во время еды. При планировании беременности и во время неё выбирают специальные пренатальные витамины — проконсультируйтесь с врачом.",
        "Women's multivitamins include iron (lost during menstruation), folate or methylfolate, calcium and vitamin D for bones, plus biotin for skin, hair and nails; some add herbal extracts for hormonal balance.\n\n"
        "Take daily with food. If you're planning a pregnancy or pregnant, choose a dedicated prenatal formula — talk to your doctor.",
    ),
    "Single Vitamins": (
        "Alohida vitaminlar — aniq bir ehtiyoj yoki yetishmovchilikni nishonga olish uchun: masalan, qishda D3, sovuq mavsumda C, energiya uchun B guruhi yoki suyaklar uchun K2. Ular multivitaminga qaraganda yuqoriroq va aniq dozani beradi.\n\n"
        "Bo'limda: D3, C, B-kompleks, E va K2 vitaminlari. Eng mashhur juftlik — D3 + K2: D3 kalsiy so'rilishini oshiradi, K2 esa kalsiyni suyaklarga yo'naltiradi.\n\n"
        "Qanday tanlash kerak: dozani tahlil natijasi va maqsadga qarab tanlang. Yog'da eriydigan vitaminlar (D, E, K) yog'li ovqat bilan yaxshiroq so'riladi. " + _DOCTOR_UZ,
        "Отдельные витамины — чтобы точно закрыть конкретную потребность или дефицит: например, D3 зимой, C в сезон простуд, группа B для энергии или K2 для костей. Они дают более высокую и точную дозу, чем мультивитамин.\n\n"
        "В разделе: витамины D3, C, B-комплекс, E и K2. Самая популярная пара — D3 + K2: D3 улучшает усвоение кальция, а K2 направляет его в кости.\n\n"
        "Как выбирать: подбирайте дозу по анализам и цели. Жирорастворимые витамины (D, E, K) лучше усваиваются с жирной пищей. " + _DOCTOR_RU,
        "Single vitamins target a specific need or deficiency — D3 in winter, C during cold season, B vitamins for energy or K2 for bones — with a higher, more precise dose than a multivitamin.\n\n"
        "This section has vitamins D3, C, B-complex, E and K2. The most popular pair is D3 + K2: D3 improves calcium absorption and K2 directs calcium into bones.\n\n"
        "How to choose: pick the dose based on blood tests and your goal. Fat-soluble vitamins (D, E, K) absorb better with a meal containing fat. " + _DOCTOR_EN,
    ),
    "Vitamin D3": (
        "D3 vitamini (xolekalsiferol) suyaklar, immunitet, mushak kuchi va kayfiyat uchun muhim. Quyosh nuri kam bo'lgan oylarda va ko'p vaqtini binoda o'tkazadiganlarda uning yetishmovchiligi juda keng tarqalgan.\n\n"
        "Kattalar uchun profilaktik doza odatda kuniga 1000–2000 XB (25–50 mkg); yetishmovchilikda dozani shifokor belgilaydi (kattalar uchun umumiy yuqori chegara — kuniga 4000 XB). Yog'li ovqat bilan qabul qiling; K2 bilan birga ichish keng tarqalgan.",
        "Витамин D3 (холекальциферол) важен для костей, иммунитета, мышечной силы и настроения. Его дефицит очень распространён в месяцы с малым количеством солнца и у тех, кто много времени проводит в помещении.\n\n"
        "Профилактическая доза для взрослых обычно 1000–2000 МЕ (25–50 мкг) в день; при дефиците дозу назначает врач (общий верхний предел для взрослых — 4000 МЕ в день). Принимайте с жирной пищей; часто сочетают с K2.",
        "Vitamin D3 (cholecalciferol) matters for bones, immunity, muscle strength and mood. Deficiency is very common in months with little sun and among people who spend most of their time indoors.\n\n"
        "A typical maintenance dose for adults is 1,000–2,000 IU (25–50 mcg) a day; for deficiency your doctor sets the dose (the general adult upper limit is 4,000 IU a day). Take it with a meal containing fat; it's often paired with K2.",
    ),
    "Vitamin C": (
        "C vitamini (askorbin kislotasi) — kuchli antioksidant: immunitet, kollagen sintezi (teri, bo'g'im, pay), temir so'rilishi va intensiv mashg'ulotdan keyingi oksidlovchi stressni kamaytirish uchun muhim.\n\n"
        "Odatiy qo'shimcha doza — kuniga 200–1000 mg. Organizm C vitaminini to'play olmaydi, shuning uchun dozani kun davomida bo'lib ichish samaraliroq. Buferlangan shakllar (natriy askorbat) yoki liposomal C oshqozonga yengilroq.",
        "Витамин C (аскорбиновая кислота) — мощный антиоксидант, важный для иммунитета, синтеза коллагена (кожа, суставы, связки), усвоения железа и снижения окислительного стресса после интенсивных тренировок.\n\n"
        "Обычная дополнительная доза — 200–1000 мг в день. Организм не накапливает витамин C, поэтому дозу эффективнее делить в течение дня. Буферизованные формы (аскорбат натрия) или липосомальный C мягче для желудка.",
        "Vitamin C (ascorbic acid) is a powerful antioxidant that supports immunity, collagen synthesis (skin, joints, tendons), iron absorption and reduced oxidative stress after hard training.\n\n"
        "A typical supplemental dose is 200–1,000 mg a day. The body can't store vitamin C, so splitting the dose through the day works better. Buffered forms (sodium ascorbate) or liposomal C are gentler on the stomach.",
    ),
    "B-Complex": (
        "B-kompleks — sakkizta B guruhi vitaminlari (B1, B2, B3, B5, B6, B7-biotin, B9-folat, B12) majmuasi. Ular ovqatdan energiya olish, asab tizimi, qon hosil bo'lishi va stressga chidamlilik uchun zarur; faol sportchilarda ehtiyoj ortadi.\n\n"
        "Ertalab ovqat bilan qabul qiling (kechqurun energiya berishi mumkin). Faol shakllar — metilkobalamin (B12), metilfolat va P-5-P (B6) — yaxshiroq ishlaydi. Siydikning yorqin sariq rangi (B2 tufayli) — zararsiz holat. Vegetarianlar va veganlar uchun B12 ayniqsa muhim.",
        "B-комплекс — восемь витаминов группы B (B1, B2, B3, B5, B6, B7-биотин, B9-фолат, B12). Они нужны для получения энергии из пищи, работы нервной системы, кроветворения и устойчивости к стрессу; у активных спортсменов потребность выше.\n\n"
        "Принимайте утром во время еды (вечером может бодрить). Активные формы — метилкобаламин (B12), метилфолат и P-5-P (B6) — работают лучше. Ярко-жёлтый цвет мочи (из-за B2) безвреден. Для вегетарианцев и веганов B12 особенно важен.",
        "B-complex combines the eight B vitamins (B1, B2, B3, B5, B6, B7-biotin, B9-folate, B12), needed to turn food into energy and for the nervous system, blood formation and stress resilience; active athletes need more.\n\n"
        "Take in the morning with food (it can be energising in the evening). Active forms — methylcobalamin (B12), methylfolate and P-5-P (B6) — work better. Bright yellow urine (from B2) is harmless. B12 is especially important for vegetarians and vegans.",
    ),
    "Vitamin E": (
        "E vitamini — yog'da eriydigan antioksidant, hujayra membranalarini oksidlanishdan himoya qiladi; teri, immunitet va qon tomirlar salomatligi uchun muhim. Tabiiy shakli (d-alfa-tokoferol) va aralash tokoferollar sintetik dl-alfa-tokoferoldan yaxshiroq so'riladi.\n\n"
        "Odatda kuniga 15–200 XB yog'li ovqat bilan qabul qilinadi. Yuqori dozalar qon suyultiruvchi dorilar bilan o'zaro ta'sir qilishi mumkin — bunday dorilarni ichayotgan bo'lsangiz, shifokor bilan maslahatlashing.",
        "Витамин E — жирорастворимый антиоксидант, защищающий мембраны клеток от окисления; важен для кожи, иммунитета и сосудов. Натуральная форма (d-альфа-токоферол) и смесь токоферолов усваиваются лучше синтетического dl-альфа-токоферола.\n\n"
        "Обычно принимают 15–200 МЕ в день с жирной пищей. Высокие дозы могут взаимодействовать с разжижающими кровь препаратами — при их приёме проконсультируйтесь с врачом.",
        "Vitamin E is a fat-soluble antioxidant that protects cell membranes from oxidation and supports skin, immunity and blood vessels. The natural form (d-alpha-tocopherol) and mixed tocopherols absorb better than synthetic dl-alpha-tocopherol.\n\n"
        "Usually 15–200 IU a day is taken with a meal containing fat. High doses can interact with blood thinners — talk to your doctor if you take them.",
    ),
    "Vitamin K2": (
        "K2 vitamini (menaxinon, ayniqsa MK-7 shakli) kalsiyni suyaklar va tishlarga yo'naltiruvchi oqsillarni faollashtiradi va uning tomirlarda to'planishining oldini olishga yordam beradi. Shu sababli u D3 vitamini bilan eng yaxshi juftlik hisoblanadi.\n\n"
        "Odatiy doza — kuniga 90–200 mkg MK-7, yog'li ovqat bilan. Muhim: varfarin kabi qon ivishiga qarshi dorilar qabul qilayotgan bo'lsangiz, K vitaminini faqat shifokor ruxsati bilan iching.",
        "Витамин K2 (менахинон, особенно форма MK-7) активирует белки, направляющие кальций в кости и зубы, и помогает предотвратить его отложение в сосудах. Поэтому он — лучшая пара для витамина D3.\n\n"
        "Обычная доза — 90–200 мкг MK-7 в день с жирной пищей. Важно: если вы принимаете антикоагулянты вроде варфарина, принимайте витамин K только с разрешения врача.",
        "Vitamin K2 (menaquinone, especially the MK-7 form) activates proteins that direct calcium into bones and teeth and helps keep it out of blood vessels — which is why it pairs best with vitamin D3.\n\n"
        "The usual dose is 90–200 mcg of MK-7 a day with a meal containing fat. Important: if you take anticoagulants such as warfarin, take vitamin K only with your doctor's approval.",
    ),
    "Minerals": (
        "Minerallar — organizm o'zi ishlab chiqara olmaydigan, faqat ovqat yoki qo'shimchalar bilan keladigan elementlar. Ular mushak qisqarishi, asab signallari, suyak mustahkamligi, kislorod tashish va immunitet uchun zarur; terlash bilan sportchilar ularning bir qismini yo'qotadi.\n\n"
        "Bo'limda: magniy (mushak, asab, uyqu), rux (immunitet, gormonlar), kalsiy (suyaklar), temir (kislorod tashish) va selen (antioksidant, qalqonsimon bez).\n\n"
        "Qanday tanlash kerak: so'rilishi yaxshi bo'lgan xelat shakllarini (bisglitsinat, sitrat, pikolinat) tanlang. Ba'zi minerallar bir-biri bilan raqobatlashadi — masalan, kalsiy va temirni turli vaqtda iching. " + _DOCTOR_UZ,
        "Минералы — элементы, которые организм не производит сам и получает только с пищей или добавками. Они нужны для сокращения мышц, нервных сигналов, прочности костей, переноса кислорода и иммунитета; с потом спортсмены теряют часть из них.\n\n"
        "В разделе: магний (мышцы, нервы, сон), цинк (иммунитет, гормоны), кальций (кости), железо (перенос кислорода) и селен (антиоксидант, щитовидная железа).\n\n"
        "Как выбирать: выбирайте хорошо усваиваемые хелатные формы (бисглицинат, цитрат, пиколинат). Некоторые минералы конкурируют между собой — например, кальций и железо лучше принимать в разное время. " + _DOCTOR_RU,
        "Minerals are elements the body can't make and gets only from food or supplements. They're needed for muscle contraction, nerve signals, bone strength, oxygen transport and immunity, and athletes lose some of them in sweat.\n\n"
        "This section has magnesium (muscles, nerves, sleep), zinc (immunity, hormones), calcium (bones), iron (oxygen transport) and selenium (antioxidant, thyroid).\n\n"
        "How to choose: pick well-absorbed chelated forms (bisglycinate, citrate, picolinate). Some minerals compete with each other — take calcium and iron at different times, for example. " + _DOCTOR_EN,
    ),
    "Magnesium": (
        "Magniy 300 dan ortiq fermentativ reaksiyada ishtirok etadi: mushak bo'shashishi va qisqarishi, asab tizimi, energiya ishlab chiqarish va uyqu sifati. Yetishmovchiligi tirishish, charchoq, asabiylik va yomon uyquga olib kelishi mumkin; terlash bilan sportchilar uni ko'proq yo'qotadi.\n\n"
        "Odatiy doza — kuniga 200–400 mg elementar magniy, ko'pincha kechqurun. Eng yaxshi shakllar: bisglitsinat (tinchlantiruvchi, oshqozonga yengil), sitrat (yaxshi so'riladi) va treonat (miya uchun). Oksid shakli arzon, lekin yomon so'riladi.",
        "Магний участвует более чем в 300 ферментативных реакциях: расслабление и сокращение мышц, нервная система, выработка энергии и качество сна. Дефицит может вызывать судороги, усталость, раздражительность и плохой сон; спортсмены теряют больше магния с потом.\n\n"
        "Обычная доза — 200–400 мг элементарного магния в день, часто вечером. Лучшие формы: бисглицинат (успокаивает, мягкий для желудка), цитрат (хорошо усваивается) и треонат (для мозга). Оксид дешёвый, но плохо усваивается.",
        "Magnesium is involved in more than 300 enzyme reactions — muscle relaxation and contraction, the nervous system, energy production and sleep quality. Deficiency can cause cramps, fatigue, irritability and poor sleep, and athletes lose more in sweat.\n\n"
        "The usual dose is 200–400 mg of elemental magnesium a day, often in the evening. The best forms are bisglycinate (calming, gentle on the stomach), citrate (well absorbed) and threonate (for the brain); oxide is cheap but poorly absorbed.",
    ),
    "Zinc": (
        "Rux immunitet, yaralarning bitishi, teri, testosteron va reproduktiv salomatlik hamda ta'm va hid bilish uchun muhim. Intensiv mashg'ulot va terlash rux ehtiyojini oshiradi; vegetarianlarda yetishmovchilik ko'proq uchraydi.\n\n"
        "Odatiy doza — kuniga 10–25 mg, ovqat bilan (och qoringa ko'ngil aynishi mumkin). Uzoq muddat kuniga 40 mg dan oshirmang — u mis so'rilishini kamaytiradi. Yaxshi so'riladigan shakllar: pikolinat, bisglitsinat, sitrat.",
        "Цинк важен для иммунитета, заживления ран, кожи, тестостерона и репродуктивного здоровья, а также вкуса и обоняния. Интенсивные тренировки и потоотделение повышают потребность в цинке; у вегетарианцев дефицит встречается чаще.\n\n"
        "Обычная доза — 10–25 мг в день во время еды (натощак может подташнивать). Длительно не превышайте 40 мг в день — цинк снижает усвоение меди. Хорошо усваиваемые формы: пиколинат, бисглицинат, цитрат.",
        "Zinc matters for immunity, wound healing, skin, testosterone and reproductive health, and taste and smell. Intense training and sweating raise your needs, and deficiency is more common in vegetarians.\n\n"
        "The usual dose is 10–25 mg a day with food (it can cause nausea on an empty stomach). Don't exceed 40 mg a day long-term — zinc reduces copper absorption. Well-absorbed forms are picolinate, bisglycinate and citrate.",
    ),
    "Calcium": (
        "Kalsiy — suyak va tishlarning asosiy minerali, shuningdek mushak qisqarishi, asab signallari va qon ivishi uchun zarur. Sut mahsulotlarini kam iste'mol qiladiganlar, ayollar (ayniqsa menopauzadan keyin) va og'ir yuklamali sportchilar uchun ahamiyati katta.\n\n"
        "Bir martalik dozani 500 mg dan oshirmagan ma'qul — so'rilishi yaxshiroq bo'ladi. Sitrat shakli ovqatsiz ham so'riladi, karbonat esa ovqat bilan. D3 va K2 bilan birga ichish kalsiyning suyaklarga to'g'ri yetishiga yordam beradi; temir bilan bir vaqtda ichmang.",
        "Кальций — главный минерал костей и зубов, также нужен для сокращения мышц, нервных сигналов и свёртывания крови. Особенно важен для тех, кто мало ест молочного, для женщин (особенно после менопаузы) и спортсменов с высокими нагрузками.\n\n"
        "Разовую дозу лучше не делать больше 500 мг — так усвоение лучше. Цитрат усваивается и без еды, карбонат — с едой. Приём вместе с D3 и K2 помогает кальцию попасть в кости; не принимайте одновременно с железом.",
        "Calcium is the main mineral in bones and teeth and is also needed for muscle contraction, nerve signals and blood clotting. It's especially important for people who eat little dairy, women (particularly after menopause) and athletes under heavy load.\n\n"
        "Keep single doses to about 500 mg for better absorption. Citrate absorbs even without food, carbonate with food. Taking it with D3 and K2 helps calcium reach the bones; don't take it at the same time as iron.",
    ),
    "Iron": (
        "Temir gemoglobin tarkibida kislorodni mushaklar va organlarga tashiydi. Yetishmovchiligi charchoq, chidamlilikning pasayishi, nafas qisishi va rangparlikka olib keladi. Xavf guruhi: ayollar, chidamlilik sportchilari (ayniqsa yuguruvchilar), vegetarianlar va donorlar.\n\n"
        "Muhim: temirni faqat tahlil (gemoglobin, ferritin) yetishmovchilikni ko'rsatganda qabul qiling — ortiqcha temir zararli. C vitamini bilan birga och qoringa yaxshiroq so'riladi; choy, qahva va kalsiy so'rilishni kamaytiradi. Bisglitsinat shakli oshqozonga yengil. Bolalardan uzoqroq saqlang.",
        "Железо в составе гемоглобина переносит кислород к мышцам и органам. Его дефицит вызывает усталость, снижение выносливости, одышку и бледность. В группе риска — женщины, спортсмены на выносливость (особенно бегуны), вегетарианцы и доноры.\n\n"
        "Важно: принимайте железо только если анализы (гемоглобин, ферритин) показывают дефицит — избыток железа вреден. Лучше усваивается натощак вместе с витамином C; чай, кофе и кальций снижают усвоение. Форма бисглицинат мягче для желудка. Храните в недоступном для детей месте.",
        "Iron, as part of haemoglobin, carries oxygen to your muscles and organs. Deficiency causes fatigue, lower endurance, breathlessness and paleness. At-risk groups include women, endurance athletes (especially runners), vegetarians and blood donors.\n\n"
        "Important: take iron only if tests (haemoglobin, ferritin) show a deficiency — too much iron is harmful. It absorbs best on an empty stomach with vitamin C, while tea, coffee and calcium reduce absorption. Bisglycinate is gentlest on the stomach. Keep out of reach of children.",
    ),
    "Selenium": (
        "Selen — kuchli antioksidant fermentlar (glutation peroksidaza) tarkibiga kiradi, qalqonsimon bez gormonlari almashinuvi, immunitet va reproduktiv salomatlik uchun muhim. Uning tuproqdagi miqdori hududga qarab juda farq qiladi.\n\n"
        "Odatiy doza — kuniga 55–100 mkg (masalan, selenometionin shaklida). Uzoq muddat kuniga 400 mkg dan oshirmang — ortiqchasi zaharli. Multivitamindagi selen miqdorini ham hisobga oling.",
        "Селен входит в состав мощных антиоксидантных ферментов (глутатионпероксидаза), важен для обмена гормонов щитовидной железы, иммунитета и репродуктивного здоровья. Его содержание в почве сильно зависит от региона.\n\n"
        "Обычная доза — 55–100 мкг в день (например, в форме селенометионина). Длительно не превышайте 400 мкг в день — избыток токсичен. Учитывайте селен и в составе мультивитамина.",
        "Selenium is part of powerful antioxidant enzymes (glutathione peroxidase) and is important for thyroid-hormone metabolism, immunity and reproductive health. Soil levels vary greatly by region.\n\n"
        "The usual dose is 55–100 mcg a day (for example as selenomethionine). Don't exceed 400 mcg a day long-term — excess is toxic. Count the selenium in your multivitamin too.",
    ),
    "Omega": (
        "Omega-3 yog' kislotalari — EPA va DHA — organizm o'zi yetarli ishlab chiqara olmaydigan va asosan yog'li baliqdan olinadigan muhim yog'lar. Ular yurak va qon tomirlar, miya va ko'rish, bo'g'imlar salomatligi va yallig'lanish muvozanati uchun eng ko'p o'rganilgan qo'shimchalardan.\n\n"
        "Bo'limda: omega-3 konsentratlari, yuqori dozali Ultra Omega va D3 hamda K2 vitaminlari qo'shilgan Omega + D3 + K2 komplekslari. Sportchilar uchun omega-3 mashg'ulotdan keyingi mushak og'rig'ini kamaytirish va bo'g'imlarni qo'llab-quvvatlashda ham qadrlanadi.\n\n"
        "Qanday tanlash kerak: yorliqdagi umumiy «baliq yog'i» emas, balki EPA + DHA miqdoriga qarang (kuniga kamida 250–500 mg, sportchilar uchun ko'pincha 1–2 g). Tozalik (IFOS kabi sertifikatlar), triglitserid shakli va yangilik (baliq hidi bo'lmasligi) muhim. Qon suyultiruvchi dorilar qabul qilsangiz, shifokor bilan maslahatlashing.",
        "Омега-3 жирные кислоты — EPA и DHA — важные жиры, которые организм не может синтезировать в достаточном количестве и получает в основном из жирной рыбы. Это одни из самых изученных добавок для сердца и сосудов, мозга и зрения, суставов и баланса воспаления.\n\n"
        "В разделе: концентраты омега-3, высокодозная Ultra Omega и комплексы Omega + D3 + K2 с добавлением витаминов D3 и K2. Спортсмены ценят омега-3 и за уменьшение мышечной боли после тренировок и поддержку суставов.\n\n"
        "Как выбирать: смотрите не на общий «рыбий жир», а на количество EPA + DHA на этикетке (минимум 250–500 мг в день, спортсменам часто 1–2 г). Важны чистота (сертификаты вроде IFOS), триглицеридная форма и свежесть (без рыбного запаха). При приёме разжижающих кровь препаратов проконсультируйтесь с врачом.",
        "Omega-3 fatty acids — EPA and DHA — are important fats the body can't make in sufficient amounts and gets mainly from oily fish. They're among the best-researched supplements for heart and blood vessels, brain and vision, joints and a healthy inflammation balance.\n\n"
        "This section covers omega-3 concentrates, high-strength Ultra Omega and Omega + D3 + K2 formulas with added vitamins D3 and K2. Athletes also value omega-3 for less post-workout soreness and joint support.\n\n"
        "How to choose: look at EPA + DHA on the label rather than total fish oil (at least 250–500 mg a day, often 1–2 g for athletes). Purity (certifications such as IFOS), the triglyceride form and freshness (no fishy smell) matter. If you take blood thinners, talk to your doctor.",
    ),
    "Omega-3": (
        "Omega-3 konsentratlari — EPA va DHA miqdori yuqori bo'lgan tozalangan yog': bir kapsulada ko'pincha 500–1000 mg EPA+DHA. Shu sababli kamroq kapsula bilan kerakli dozaga erishiladi.\n\n"
        "Yurak, miya, ko'z va bo'g'imlar salomatligi, shuningdek sportchilarda tiklanish uchun. Ovqat bilan qabul qiling — so'rilishi yaxshilanadi va «baliqli kekirish» kamayadi. Muzlatgichda saqlash yangilikni uzaytiradi.",
        "Концентраты омега-3 — очищенный жир с высоким содержанием EPA и DHA: часто 500–1000 мг EPA+DHA в капсуле. Поэтому нужную дозу можно получить меньшим числом капсул.\n\n"
        "Для здоровья сердца, мозга, глаз и суставов, а также восстановления у спортсменов. Принимайте во время еды — так лучше усвоение и меньше «рыбной отрыжки». Хранение в холодильнике продлевает свежесть.",
        "Omega-3 concentrates are purified oils high in EPA and DHA — often 500–1,000 mg of EPA+DHA per capsule — so you reach the dose you need with fewer capsules.\n\n"
        "For heart, brain, eye and joint health and recovery in athletes. Take with food for better absorption and fewer fishy burps; keeping them in the fridge extends freshness.",
    ),
    "Ultra Omega": (
        "Ultra Omega — yuqori konsentratli omega-3: bir porsiyada 1000 mg va undan ko'p EPA + DHA. Oddiy baliq yog'ida bu miqdorga erishish uchun 3–4 kapsula kerak bo'lsa, bu yerda 1–2 kapsula yetadi.\n\n"
        "Kimga mos: intensiv mashg'ulot qiladigan sportchilar, yurak-qon tomir va bo'g'imlar uchun yuqori doza kerak bo'lganlar hamda kam kapsula ichishni xohlaydiganlar. Eng yaxshi shakli — qayta etirifikatsiyalangan triglitserid (rTG): u etil efir (EE) shakliga qaraganda yaxshiroq so'riladi.\n\n"
        "Qanday tanlash kerak: yorliqda «fish oil 1000 mg» emas, aynan EPA va DHA miqdori yozilganiga, IFOS kabi tozalik sertifikatiga va yangilikka e'tibor bering. Ovqat bilan qabul qiling. Kuniga 3 g dan ortiq EPA + DHA va qon suyultiruvchi dorilar bilan birga qabul qilishni shifokor bilan kelishing.",
        "Ultra Omega — высококонцентрированная омега-3: 1000 мг и больше EPA + DHA в одной порции. Если с обычным рыбьим жиром для такой дозы нужно 3–4 капсулы, здесь достаточно 1–2.\n\n"
        "Кому подойдёт: спортсменам с интенсивными тренировками, тем, кому нужна высокая доза для сердца, сосудов и суставов, и тем, кто хочет пить меньше капсул. Лучшая форма — реэтерифицированные триглицериды (rTG): они усваиваются лучше этиловых эфиров (EE).\n\n"
        "Как выбирать: смотрите на количество именно EPA и DHA, а не на «fish oil 1000 мг», на сертификат чистоты вроде IFOS и свежесть. Принимайте во время еды. Дозы выше 3 г EPA + DHA в день и приём вместе с разжижающими кровь препаратами согласуйте с врачом.",
        "Ultra Omega is high-strength omega-3: 1,000 mg or more of EPA + DHA per serving. Where regular fish oil needs 3–4 capsules to reach that dose, here 1–2 are enough.\n\n"
        "Who it suits: athletes who train hard, anyone who needs a higher dose for heart, blood vessels and joints, and people who'd rather take fewer capsules. The best form is re-esterified triglyceride (rTG), which absorbs better than the ethyl-ester (EE) form.\n\n"
        "How to choose: look for the EPA and DHA amounts rather than \"fish oil 1,000 mg\", a purity certificate such as IFOS, and freshness. Take with food. Check with a doctor before going above 3 g of EPA + DHA a day or combining it with blood thinners.",
    ),
    "Omega + D3 + K2": (
        "Omega + D3 + K2 — omega-3 (EPA va DHA), D3 vitamini va K2 vitaminini bitta kapsulada birlashtirgan kompleks. Uchala modda ham yog'da eriydi, shuning uchun baliq yog'i bilan birga yaxshi so'riladi.\n\n"
        "Nima uchun aynan shu uchlik: omega-3 yurak, miya va bo'g'imlarni qo'llab-quvvatlaydi; D3 suyaklar, mushaklar va immunitet uchun muhim va qishda ko'pchilikda yetishmaydi; K2 (ayniqsa MK-7 shakli) kalsiyni suyak va tishlarga yo'naltirishga yordam beradi. Natijada uchta alohida mahsulot o'rniga bitta qulay kapsula.\n\n"
        "Qanday tanlash kerak: EPA + DHA, D3 (odatda 1000–2000 IU) va K2 (MK-7, odatda 50–100 mkg) miqdorini yorliqda solishtiring va boshqa qo'shimchalardagi D3 ni ham hisobga oling. Ovqat bilan qabul qiling. Varfarin kabi K vitamini antagonistlari yoki qon suyultiruvchi dorilar qabul qilsangiz, K2 dozani o'zgartirishi mumkin — albatta shifokor bilan maslahatlashing.",
        "Omega + D3 + K2 — комплекс, объединяющий омега-3 (EPA и DHA), витамин D3 и витамин K2 в одной капсуле. Все три вещества жирорастворимые, поэтому хорошо усваиваются вместе с рыбьим жиром.\n\n"
        "Почему именно эта тройка: омега-3 поддерживает сердце, мозг и суставы; D3 важен для костей, мышц и иммунитета, и зимой его не хватает многим; K2 (особенно форма MK-7) помогает направлять кальций в кости и зубы. В итоге вместо трёх отдельных продуктов — одна удобная капсула.\n\n"
        "Как выбирать: сравнивайте на этикетке количество EPA + DHA, D3 (обычно 1000–2000 МЕ) и K2 (MK-7, обычно 50–100 мкг) и учитывайте D3 из других добавок. Принимайте во время еды. Если вы принимаете антагонисты витамина K (например, варфарин) или другие разжижающие кровь препараты, K2 может влиять на дозировку — обязательно проконсультируйтесь с врачом.",
        "Omega + D3 + K2 combines omega-3 (EPA and DHA), vitamin D3 and vitamin K2 in one capsule. All three are fat-soluble, so they absorb well together with fish oil.\n\n"
        "Why this trio: omega-3 supports heart, brain and joints; D3 matters for bones, muscles and immunity and many people run low in winter; K2 (especially the MK-7 form) helps direct calcium into bones and teeth. One convenient capsule instead of three separate products.\n\n"
        "How to choose: compare EPA + DHA, D3 (usually 1,000–2,000 IU) and K2 (MK-7, usually 50–100 mcg) on the label and count D3 from other supplements too. Take with food. If you take a vitamin K antagonist such as warfarin or other blood thinners, K2 can affect your dose — talk to your doctor first.",
    ),
    "Joint Support": (
        "Bo'g'im va paylar sport bilan shug'ullanishda eng ko'p zo'riqadigan tuzilmalardir. Bo'g'imlar uchun qo'shimchalar tog'ay to'qimasi, sinovial suyuqlik va biriktiruvchi to'qimalarni qo'llab-quvvatlashga mo'ljallangan.\n\n"
        "Bo'limda: kollagen (tog'ay, pay, teri), glyukozamin va xondroitin (tog'ay tuzilmasi). Ko'pincha ular MSM, gialuron kislotasi va C vitamini bilan birgalikda ishlatiladi.\n\n"
        "Qanday ishlatiladi: natija sekin to'planadi — kamida 8–12 hafta muntazam qabul qiling. Og'ir yuklamali sportchilar, yuguruvchilar, yoshi kattaroq va bo'g'imlarida noqulaylik sezadiganlar uchun foydali. Kuchli og'riq yoki shish bo'lsa, avval shifokorga murojaat qiling.",
        "Суставы и связки — структуры, которые больше всего нагружаются в спорте. Добавки для суставов поддерживают хрящевую ткань, синовиальную жидкость и соединительные ткани.\n\n"
        "В разделе: коллаген (хрящи, связки, кожа), глюкозамин и хондроитин (структура хряща). Часто их сочетают с MSM, гиалуроновой кислотой и витамином C.\n\n"
        "Как применять: эффект накапливается медленно — принимайте регулярно минимум 8–12 недель. Полезны спортсменам с высокими нагрузками, бегунам, людям старшего возраста и тем, кто чувствует дискомфорт в суставах. При сильной боли или отёке сначала обратитесь к врачу.",
        "Joints and tendons take the most strain in sport. Joint-support supplements are designed to support cartilage, synovial fluid and connective tissue.\n\n"
        "This section includes collagen (cartilage, tendons, skin), glucosamine and chondroitin (cartilage structure), often combined with MSM, hyaluronic acid and vitamin C.\n\n"
        "How to use: benefits build slowly — take them consistently for at least 8–12 weeks. They're useful for athletes under heavy load, runners, older adults and anyone with joint discomfort. For severe pain or swelling, see a doctor first.",
    ),
    "Collagen": (
        "Kollagen — organizmdagi eng ko'p oqsil, teri, tog'ay, pay, suyak va bog'lamlarning asosiy tuzilma qismi. Gidrolizlangan kollagen peptidlari yaxshi so'riladi va biriktiruvchi to'qimalarni qo'llab-quvvatlaydi.\n\n"
        "Odatiy doza — kuniga 5–10 g; paylar uchun mashg'ulotdan 30–60 daqiqa oldin C vitamini bilan qabul qilish tavsiya etiladi. II turdagi kollagen bo'g'im tog'ayi uchun, I va III turlar esa teri, soch va paylar uchun. Kollagen to'liq protein emas — mushak o'sishi uchun whey o'rnini bosmaydi.",
        "Коллаген — самый распространённый белок в организме, основная структура кожи, хрящей, сухожилий, костей и связок. Гидролизованные пептиды коллагена хорошо усваиваются и поддерживают соединительные ткани.\n\n"
        "Обычная доза — 5–10 г в день; для связок рекомендуют принимать за 30–60 минут до тренировки вместе с витамином C. Коллаген II типа — для суставного хряща, I и III типы — для кожи, волос и сухожилий. Коллаген не является полноценным белком и не заменяет whey для роста мышц.",
        "Collagen is the most abundant protein in the body and the main structural part of skin, cartilage, tendons, bones and ligaments. Hydrolysed collagen peptides absorb well and support connective tissue.\n\n"
        "The usual dose is 5–10 g a day; for tendons, take it 30–60 minutes before training with vitamin C. Type II collagen targets joint cartilage, types I and III skin, hair and tendons. Collagen isn't a complete protein and doesn't replace whey for muscle growth.",
    ),
    "Glucosamine": (
        "Glyukozamin — tog'ay to'qimasining tabiiy tarkibiy qismi va uning asosiy «qurilish materiallari»dan biri. U tog'ayni va bo'g'im harakatchanligini qo'llab-quvvatlash uchun qo'llanadi, ko'pincha xondroitin va MSM bilan birga.\n\n"
        "Odatiy doza — kuniga 1500 mg (glyukozamin sulfat shakli eng ko'p o'rganilgan), kamida 2–3 oy. Ko'pincha qisqichbaqasimonlardan olinadi — dengiz mahsulotlariga allergiyangiz bo'lsa, vegetarian shaklni tanlang. Qandli diabet bo'lsa, shifokor bilan maslahatlashing.",
        "Глюкозамин — естественный компонент хрящевой ткани и один из её главных «строительных материалов». Его применяют для поддержки хряща и подвижности суставов, часто вместе с хондроитином и MSM.\n\n"
        "Обычная доза — 1500 мг в день (наиболее изучена форма глюкозамина сульфата) минимум 2–3 месяца. Часто его получают из ракообразных — при аллергии на морепродукты выбирайте вегетарианскую форму. При диабете проконсультируйтесь с врачом.",
        "Glucosamine is a natural component of cartilage and one of its main building blocks. It's used to support cartilage and joint mobility, often with chondroitin and MSM.\n\n"
        "The usual dose is 1,500 mg a day (glucosamine sulfate is the best-studied form) for at least 2–3 months. It's often sourced from shellfish, so choose a vegetarian form if you have a seafood allergy. If you have diabetes, check with your doctor.",
    ),
    "Chondroitin": (
        "Xondroitin sulfat — tog'ayga suv ushlab turish va elastiklik beradigan modda. U tog'ayning zarbaga chidamliligini qo'llab-quvvatlaydi va glyukozamin bilan klassik juftlik hosil qiladi.\n\n"
        "Odatiy doza — kuniga 800–1200 mg, uzoq kurs bilan (kamida 3 oy). Qon suyultiruvchi dorilar qabul qilayotgan bo'lsangiz, avval shifokor bilan maslahatlashing.",
        "Хондроитин сульфат — вещество, которое помогает хрящу удерживать воду и сохранять упругость. Он поддерживает амортизирующие свойства хряща и образует классическую пару с глюкозамином.\n\n"
        "Обычная доза — 800–1200 мг в день длительным курсом (минимум 3 месяца). Если вы принимаете препараты, разжижающие кровь, сначала проконсультируйтесь с врачом.",
        "Chondroitin sulfate helps cartilage hold water and stay elastic, supporting its shock-absorbing properties, and forms the classic pair with glucosamine.\n\n"
        "The usual dose is 800–1,200 mg a day over a long course (at least 3 months). If you take blood thinners, consult your doctor first.",
    ),
    "Sleep Support": (
        "Sifatli uyqu — tiklanish, mushak o'sishi, gormonal muvozanat va diqqat uchun eng kuchli «qo'shimcha». Uyquni qo'llab-quvvatlovchi vositalar tez uxlab qolish va chuqurroq dam olishga yordam beradi.\n\n"
        "Bo'limda: melatonin (sutkalik ritmni sozlash) va uyqu komplekslari (magniy, L-teanin, glitsin, GABA, romashka va valeriana kabi o'simlik ekstraktlari).\n\n"
        "Maslahat: avval uyqu gigiyenasiga e'tibor bering — doimiy rejim, salqin va qorong'i xona, uxlashdan oldin ekrandan uzoqlashish va kechki kofeindan voz kechish. Qo'shimchalar buni to'ldiradi. Surunkali uyqusizlikda shifokorga murojaat qiling.",
        "Качественный сон — самая мощная «добавка» для восстановления, роста мышц, гормонального баланса и концентрации. Средства для сна помогают быстрее засыпать и глубже отдыхать.\n\n"
        "В разделе: мелатонин (настройка суточного ритма) и комплексы для сна (магний, L-теанин, глицин, ГАМК, растительные экстракты вроде ромашки и валерианы).\n\n"
        "Совет: сначала наладьте гигиену сна — постоянный режим, прохладная и тёмная комната, отказ от экранов перед сном и вечернего кофеина. Добавки это дополняют. При хронической бессоннице обратитесь к врачу.",
        "Quality sleep is the most powerful supplement for recovery, muscle growth, hormonal balance and focus. Sleep-support products help you fall asleep faster and rest more deeply.\n\n"
        "This section includes melatonin (resetting your daily rhythm) and sleep complexes (magnesium, L-theanine, glycine, GABA and herbal extracts such as chamomile and valerian).\n\n"
        "Tip: sort out sleep hygiene first — a regular schedule, a cool dark room, no screens before bed and no evening caffeine. Supplements complement that. For chronic insomnia, see a doctor.",
    ),
    "Melatonin": (
        "Melatonin — organizmning «uyqu gormoni»: qorong'ilik tushganda ishlab chiqariladi va uxlash vaqti kelganini bildiradi. Qo'shimcha sifatida u tez uxlab qolishga, soat mintaqalari almashganda (jet-lag) va smenali ishda ritmni tiklashga yordam beradi.\n\n"
        "Kichik dozalar ko'pincha yetarli: uxlashdan 30–60 daqiqa oldin 0.5–3 mg. Ertasi kuni uyquchanlik bo'lsa, dozani kamaytiring. Uzoq muddat muntazam ichish, homiladorlik, bolalar va dori qabul qilish holatlarida shifokor bilan maslahatlashing.",
        "Мелатонин — «гормон сна»: он вырабатывается с наступлением темноты и сигнализирует, что пора спать. Как добавка помогает быстрее заснуть и восстановить ритм при смене часовых поясов (джетлаг) и сменной работе.\n\n"
        "Часто достаточно малых доз: 0,5–3 мг за 30–60 минут до сна. Если на следующий день есть сонливость, уменьшите дозу. При длительном регулярном приёме, беременности, для детей и при приёме лекарств проконсультируйтесь с врачом.",
        "Melatonin is the body's sleep hormone: it's released when it gets dark and signals that it's time to sleep. As a supplement it helps you fall asleep faster and reset your rhythm after time-zone changes (jet lag) and shift work.\n\n"
        "Small doses are often enough: 0.5–3 mg 30–60 minutes before bed. If you feel drowsy the next day, lower the dose. For long-term daily use, pregnancy, children or if you take medication, consult a doctor.",
    ),
    "Sleep Complex": (
        "Uyqu komplekslari bir nechta tinchlantiruvchi komponentni birlashtiradi: magniy (mushak va asab bo'shashishi), L-teanin (tinch, xotirjam holat), glitsin, GABA va romashka, valeriana, lemon balzami kabi o'simlik ekstraktlari. Ba'zilarida kichik dozada melatonin ham bor.\n\n"
        "Uxlashdan 30–60 daqiqa oldin qabul qilinadi. Kechki mashg'ulotdan keyin «tinchlana olmaydigan», stress tufayli yomon uxlaydiganlar uchun mos. Spirtli ichimlik va uyqu dorilari bilan birga ichmang.",
        "Комплексы для сна сочетают несколько успокаивающих компонентов: магний (расслабление мышц и нервов), L-теанин (спокойное состояние), глицин, ГАМК и растительные экстракты — ромашку, валериану, мелиссу. В некоторых есть и небольшая доза мелатонина.\n\n"
        "Принимают за 30–60 минут до сна. Подходят тем, кто «не может успокоиться» после вечерней тренировки или плохо спит из-за стресса. Не сочетайте с алкоголем и снотворными.",
        "Sleep complexes combine several calming ingredients — magnesium (muscle and nerve relaxation), L-theanine (calm focus), glycine, GABA and herbal extracts such as chamomile, valerian and lemon balm; some also include a small dose of melatonin.\n\n"
        "Take 30–60 minutes before bed. They suit people who can't wind down after an evening workout or sleep poorly because of stress. Don't combine with alcohol or sleeping pills.",
    ),
    "Testosterone Support": (
        "Testosteron — erkaklarda mushak massasi, kuch, energiya, libido va kayfiyat uchun asosiy gormon. Uning darajasi 30 yoshdan keyin asta-sekin pasayadi, kam uyqu, stress, ortiqcha vazn va rux yoki D vitamini yetishmovchiligi esa uni yanada tushiradi.\n\n"
        "Bo'limda: tribulus va kompleks testosteron boosterlari. Ular tarkibida odatda tribulus, piskom (fenugrek), ashvaganda, D-aspartat kislotasi, tongkat ali, rux, magniy, D vitamini va bor bo'ladi — organizmning o'z testosteron ishlab chiqarishini qo'llab-quvvatlash uchun.\n\n"
        "Nimani kutish mumkin: tabiiy boosterlar gormon emas va steroidlar kabi keskin natija bermaydi. Eng sezilarli foyda — yetishmovchilik bo'lganda (rux, D vitamini, magniy), shuningdek libido va umumiy tetiklikda. Ularni yaxshi uyqu, kuch mashg'ulotlari va to'g'ri ovqatlanish bilan birga qabul qiling.\n\n"
        "Muhim: faqat 18 yoshdan katta erkaklar uchun. Gormonal kasallik, prostata muammolari, yurak-qon tomir kasalliklari bo'lsa yoki dori qabul qilsangiz, avval shifokor bilan maslahatlashing.",
        "Тестостерон — ключевой мужской гормон для мышечной массы, силы, энергии, либидо и настроения. После 30 лет его уровень постепенно снижается, а недосып, стресс, лишний вес и дефицит цинка или витамина D снижают его ещё больше.\n\n"
        "В разделе: трибулус и комплексные тестостероновые бустеры. В их составе обычно трибулус, пажитник, ашваганда, D-аспарагиновая кислота, тонгкат али, цинк, магний, витамин D и бор — для поддержки собственной выработки тестостерона.\n\n"
        "Чего ожидать: натуральные бустеры — не гормоны и не дают резкого эффекта, как стероиды. Наибольшая польза — при дефицитах (цинк, витамин D, магний), а также для либидо и общего тонуса. Принимайте их вместе с хорошим сном, силовыми тренировками и правильным питанием.\n\n"
        "Важно: только для мужчин старше 18 лет. При гормональных заболеваниях, проблемах с простатой, сердечно-сосудистых заболеваниях или приёме лекарств сначала проконсультируйтесь с врачом.",
        "Testosterone is the key male hormone for muscle mass, strength, energy, libido and mood. Levels drift down after 30, and poor sleep, stress, excess weight and low zinc or vitamin D push them lower still.\n\n"
        "This section covers tribulus and multi-ingredient testosterone boosters. They typically contain tribulus, fenugreek, ashwagandha, D-aspartic acid, tongkat ali, zinc, magnesium, vitamin D and boron — to support the body's own testosterone production.\n\n"
        "What to expect: natural boosters are not hormones and won't act like steroids. The clearest benefit comes when you're low in zinc, vitamin D or magnesium, and in libido and overall drive. Combine them with good sleep, strength training and a solid diet.\n\n"
        "Important: for men over 18 only. If you have a hormonal condition, prostate problems, heart disease or take medication, talk to a doctor first.",
    ),
    "Tribulus": (
        "Tribulus terrestris — an'anaviy tabobatda qadimdan erkaklar kuchi uchun ishlatilgan o'simlik. Uning faol moddalari — saponinlar, ayniqsa protodiosin; sifatli ekstraktda saponinlar ulushi (masalan, 40–90%) yorliqda ko'rsatiladi.\n\n"
        "Tadqiqotlarda tribulus libido va jinsiy funksiyani yaxshilashda eng ko'p foyda ko'rsatgan; sog'lom erkaklarda testosteron darajasiga ta'siri esa kuchsiz. Shuning uchun u ko'pincha kompleks boosterlar tarkibida ishlatiladi.\n\n"
        "Odatiy doza — standartlashtirilgan ekstraktdan kuniga 250–750 mg, ovqat bilan, 4–8 haftalik kurslar va ular orasida tanaffus bilan. Faqat 18 yoshdan katta erkaklar uchun; qon bosimi yoki qand dorilari qabul qilsangiz, shifokor bilan maslahatlashing.",
        "Tribulus terrestris — растение, которое в традиционной медицине издавна применяют для мужской силы. Его активные вещества — сапонины, прежде всего протодиоцин; в качественном экстракте доля сапонинов (например, 40–90%) указана на этикетке.\n\n"
        "В исследованиях трибулус лучше всего проявил себя в улучшении либидо и сексуальной функции; влияние на уровень тестостерона у здоровых мужчин слабое. Поэтому его часто используют в составе комплексных бустеров.\n\n"
        "Обычная доза — 250–750 мг стандартизированного экстракта в день во время еды, курсами по 4–8 недель с перерывами. Только для мужчин старше 18 лет; при приёме препаратов от давления или для снижения сахара проконсультируйтесь с врачом.",
        "Tribulus terrestris is a plant long used in traditional medicine for male vitality. Its active compounds are saponins, mainly protodioscin; a quality extract states its saponin content (for example 40–90%) on the label.\n\n"
        "In studies tribulus shows the most benefit for libido and sexual function, while its effect on testosterone in healthy men is weak — which is why it's often part of multi-ingredient boosters.\n\n"
        "The usual dose is 250–750 mg of standardised extract a day with food, in 4–8-week cycles with breaks. For men over 18 only; if you take blood-pressure or blood-sugar medication, talk to your doctor.",
    ),
    "Testosterone Boosters": (
        "Testosteron boosterlari — organizmning o'z testosteron ishlab chiqarishini qo'llab-quvvatlash uchun bir nechta tabiiy komponentni birlashtirgan komplekslar. Odatiy tarkib: D-aspartat kislotasi, piskom (fenugrek), ashvaganda, tongkat ali, tribulus, rux, magniy, B6 va D vitaminlari hamda bor.\n\n"
        "Kimga mos: 25–30 yoshdan katta, energiya, libido yoki mashg'ulotdagi natija pasayganini sezayotgan erkaklarga. Ashvaganda stress gormoni kortizolni kamaytirishga, rux va D vitamini esa yetishmovchilik bo'lganda testosteronni me'yorga keltirishga yordam beradi.\n\n"
        "Qanday tanlash kerak: «yashirin formula» emas, har bir komponentning dozasi ochiq yozilgan mahsulotni tanlang. Odatda 4–8 hafta qabul qilinadi, keyin tanaffus qilinadi. Bu gormon yoki steroid emas, shuning uchun natija mo''tadil bo'ladi. Faqat 18 yoshdan katta erkaklar uchun; surunkali kasallik yoki dori qabul qilsangiz, avval shifokor bilan maslahatlashing.",
        "Тестостероновые бустеры — комплексы из нескольких натуральных компонентов для поддержки собственной выработки тестостерона. Типичный состав: D-аспарагиновая кислота, пажитник, ашваганда, тонгкат али, трибулус, цинк, магний, витамины B6 и D, а также бор.\n\n"
        "Кому подойдёт: мужчинам старше 25–30 лет, которые замечают снижение энергии, либидо или результатов в тренировках. Ашваганда помогает снизить гормон стресса кортизол, а цинк и витамин D при дефиците помогают вернуть тестостерон к норме.\n\n"
        "Как выбирать: берите продукт с открыто указанной дозой каждого компонента, а не «проприетарной смесью». Обычно принимают 4–8 недель, затем делают перерыв. Это не гормон и не стероид, поэтому эффект умеренный. Только для мужчин старше 18 лет; при хронических заболеваниях или приёме лекарств сначала проконсультируйтесь с врачом.",
        "Testosterone boosters combine several natural ingredients to support the body's own testosterone production. A typical formula includes D-aspartic acid, fenugreek, ashwagandha, tongkat ali, tribulus, zinc, magnesium, vitamins B6 and D, and boron.\n\n"
        "Who they suit: men over 25–30 who notice lower energy, libido or gym performance. Ashwagandha helps lower the stress hormone cortisol, while zinc and vitamin D help bring testosterone back to normal when you're deficient.\n\n"
        "How to choose: pick a product that lists the dose of every ingredient rather than a proprietary blend. They're usually taken for 4–8 weeks, then paused. They're not hormones or steroids, so expect a moderate effect. For men over 18 only; if you have a chronic condition or take medication, talk to a doctor first.",
    ),
    "Kids' Vitamins": (
        "Bolalar o'sish davrida tez rivojlanadi: suyaklar, miya, ko'rish va immunitet uchun vitamin va minerallarga ehtiyoj yuqori, tanlab ovqatlanadigan bolalarda esa ratsion buni doim ham qoplamaydi. Bolalar vitaminlari aynan ularning yoshi va vazniga mos dozalarda tayyorlanadi.\n\n"
        "Bo'limda: bolalar multivitaminlari, bolalar uchun omega-3 (DHA), D3 vitamini va immunitet uchun vositalar. Shakllari — chaynaladigan marmeladlar (gummies), chaynaladigan tabletkalar, siroplar va tomchilar.\n\n"
        "Qanday tanlash kerak: yorliqdagi yosh chegarasiga qat'iy amal qiling, kattalar vitaminlarini bolaga bermang. Shakar va sun'iy bo'yoqlar kam bo'lgan mahsulotlarni afzal ko'ring.\n\n"
        "Muhim: shirin marmeladlarni bolalar konfet deb o'ylashi mumkin — ularni bolalar qo'li yetmaydigan joyda saqlang; ayniqsa temirli vitaminlarning ortiqcha dozasi bolalar uchun xavfli. Chaqaloqlar, surunkali kasalligi bor yoki dori qabul qilayotgan bolalar uchun avval pediatr bilan maslahatlashing.",
        "Дети быстро растут: потребность в витаминах и минералах для костей, мозга, зрения и иммунитета высока, а у детей, разборчивых в еде, рацион не всегда её покрывает. Детские витамины выпускаются в дозировках, подобранных под возраст и вес ребёнка.\n\n"
        "В разделе: детские мультивитамины, омега-3 (DHA) для детей, витамин D3 и средства для иммунитета. Формы — жевательные мармеладки (gummies), жевательные таблетки, сиропы и капли.\n\n"
        "Как выбирать: строго соблюдайте возрастные ограничения на этикетке, не давайте ребёнку взрослые витамины. Предпочитайте продукты с минимумом сахара и искусственных красителей.\n\n"
        "Важно: сладкие мармеладки дети могут принять за конфеты — храните их в недоступном для детей месте; особенно опасна передозировка витаминов с железом. Для младенцев, детей с хроническими заболеваниями или принимающих лекарства сначала проконсультируйтесь с педиатром.",
        "Children grow fast: their needs for vitamins and minerals for bones, brain, eyes and immunity are high, and picky eaters' diets don't always cover them. Kids' vitamins come in doses matched to a child's age and weight.\n\n"
        "This section covers kids' multivitamins, omega-3 (DHA) for children, vitamin D3 and immune support. Forms include chewable gummies, chewable tablets, syrups and drops.\n\n"
        "How to choose: follow the age range on the label strictly and don't give children adult vitamins. Prefer products low in sugar and artificial colours.\n\n"
        "Important: children can mistake sweet gummies for candy — keep them out of reach; an overdose of iron-containing vitamins is especially dangerous for children. For babies, children with chronic conditions or on medication, check with a paediatrician first.",
    ),
    "Kids' Multivitamins": (
        "Bolalar multivitaminlari — o'sish va rivojlanish uchun asosiy vitamin va minerallar majmuasi: A, C, D, E, B guruhi vitaminlari, rux, yod va ko'pincha kalsiy. Ular tanlab ovqatlanadigan bolalar ratsionidagi bo'shliqlarni to'ldirishga yordam beradi.\n\n"
        "Yoshga qarab tanlang: chaqaloqlar uchun tomchilar, 2–4 yoshdan chaynaladigan marmeladlar yoki siroplar, katta bolalar uchun chaynaladigan tabletkalar. Kuniga bir marta, ovqat bilan bering va yorliqdagi dozadan oshirmang. Temirli multivitaminni faqat pediatr tavsiya qilsa tanlang va bolalar qo'li yetmaydigan joyda saqlang.",
        "Детские мультивитамины — комплекс основных витаминов и минералов для роста и развития: витамины A, C, D, E, группы B, цинк, йод и часто кальций. Они помогают восполнить пробелы в рационе детей, которые плохо едят.\n\n"
        "Выбирайте по возрасту: для младенцев — капли, с 2–4 лет — жевательные мармеладки или сиропы, для детей постарше — жевательные таблетки. Давайте раз в день во время еды и не превышайте дозу на этикетке. Мультивитамины с железом выбирайте только по рекомендации педиатра и храните в недоступном для детей месте.",
        "Kids' multivitamins provide the core vitamins and minerals for growth and development: vitamins A, C, D, E and B-complex, zinc, iodine and often calcium. They help fill gaps in picky eaters' diets.\n\n"
        "Choose by age: drops for babies, chewable gummies or syrups from 2–4 years, chewable tablets for older children. Give once a day with food and don't exceed the label dose. Choose an iron-containing multivitamin only if a paediatrician recommends it, and keep it out of children's reach.",
    ),
    "Kids' Omega-3": (
        "Bolalar uchun omega-3 — asosan DHA va EPA: DHA miya, ko'rish va asab tizimi rivojlanishi uchun muhim qurilish materiali. Ko'p bolalar yog'li baliqni kam yeydi, shuning uchun omega-3 ratsionda yetishmasligi mumkin.\n\n"
        "Shakllari: mevali ta'mli suyuq baliq yog'i, kichik chaynaladigan kapsulalar va marmeladlar. Yorliqda DHA miqdoriga qarang, molekulyar distillyatsiya va IFOS kabi tozalik sertifikatlari muhim. Ovqat bilan bering; ochilgan suyuq shaklni muzlatgichda saqlang. Baliq yoki dengiz mahsulotlariga allergiyasi bor bolalarga bermang.",
        "Омега-3 для детей — это прежде всего DHA и EPA: DHA — важный строительный материал для развития мозга, зрения и нервной системы. Многие дети редко едят жирную рыбу, поэтому омега-3 в рационе может не хватать.\n\n"
        "Формы: жидкий рыбий жир с фруктовым вкусом, маленькие жевательные капсулы и мармеладки. Смотрите на количество DHA на этикетке; важны молекулярная дистилляция и сертификаты чистоты вроде IFOS. Давайте во время еды; открытую жидкую форму храните в холодильнике. Не давайте детям с аллергией на рыбу или морепродукты.",
        "Kids' omega-3 is mainly DHA and EPA: DHA is a key building block for the developing brain, eyes and nervous system. Many children rarely eat oily fish, so their diet can fall short.\n\n"
        "Forms include fruit-flavoured liquid fish oil, small chewable capsules and gummies. Check the DHA amount on the label; molecular distillation and purity certificates such as IFOS matter. Give with food and keep an opened liquid in the fridge. Don't give to children allergic to fish or seafood.",
    ),
    "Kids' Vitamin D3": (
        "D3 vitamini bolalarda suyak va tishlarning to'g'ri o'sishi, kalsiy so'rilishi va immunitet uchun zarur. Quyoshda kam bo'ladigan, ayniqsa kuz-qish oylarida, ko'p bolalarda yetishmaydi; emizikli chaqaloqlarga esa pediatrlar ko'pincha D vitaminini alohida tavsiya qiladi.\n\n"
        "Shakllari: chaqaloqlar uchun yog'li tomchilar (dozalash oson), katta bolalar uchun chaynaladigan tabletkalar va marmeladlar. Odatiy profilaktik doza chaqaloqlar uchun kuniga 400 IU, katta bolalar uchun ko'pincha 400–1000 IU, lekin aniq dozani pediatr belgilaydi. D vitamini yog'da eriydi va to'planadi — multivitamindagi D3 ni ham hisobga oling va yuqori dozalarni o'zboshimchalik bilan bermang.",
        "Витамин D3 нужен детям для правильного роста костей и зубов, усвоения кальция и иммунитета. Его не хватает многим детям, которые мало бывают на солнце, особенно осенью и зимой, а младенцам на грудном вскармливании педиатры часто рекомендуют витамин D отдельно.\n\n"
        "Формы: масляные капли для младенцев (удобно дозировать), жевательные таблетки и мармеладки для детей постарше. Обычная профилактическая доза — 400 МЕ в день для младенцев и часто 400–1000 МЕ для детей постарше, но точную дозу назначает педиатр. Витамин D жирорастворимый и накапливается — учитывайте D3 в мультивитамине и не давайте высокие дозы самостоятельно.",
        "Vitamin D3 helps children grow strong bones and teeth, absorb calcium and keep their immune system working. Many children who spend little time in the sun run low, especially in autumn and winter, and paediatricians often recommend separate vitamin D for breastfed babies.\n\n"
        "Forms include oil drops for babies (easy to dose) and chewable tablets or gummies for older children. A typical preventive dose is 400 IU a day for babies and often 400–1,000 IU for older children, but a paediatrician should set the exact dose. Vitamin D is fat-soluble and builds up — count the D3 in any multivitamin and don't give high doses on your own.",
    ),
    "Kids' Immune Support": (
        "Bolalar immuniteti uchun vositalar — bog'cha va maktab mavsumida, sovuq tushganda va tez-tez shamollaydigan bolalar uchun mo'ljallangan komplekslar. Odatiy tarkib: C vitamini, rux, D3 vitamini, qora buzina (sambucus) ekstrakti, ba'zan exinatseya va probiotiklar.\n\n"
        "Shakllari — mazali siroplar, chaynaladigan marmeladlar va pastilkalar. Ular kasallikni davolamaydi, balki immunitetni ovqatlanish, uyqu va faollik bilan birga qo'llab-quvvatlaydi. Yoshga mos mahsulotni tanlang, yorliqdagi dozaga amal qiling va kurslar orasida tanaffus qiling. Allergiyaga moyil yoki surunkali kasalligi bor bolalar uchun avval pediatr bilan maslahatlashing.",
        "Средства для иммунитета детей — комплексы для сезона садика и школы, холодов и для детей, которые часто простужаются. Типичный состав: витамин C, цинк, витамин D3, экстракт чёрной бузины (самбукус), иногда эхинацея и пробиотики.\n\n"
        "Формы — вкусные сиропы, жевательные мармеладки и пастилки. Они не лечат болезнь, а поддерживают иммунитет вместе с питанием, сном и активностью. Выбирайте продукт по возрасту, соблюдайте дозу на этикетке и делайте перерывы между курсами. Для детей, склонных к аллергии или с хроническими заболеваниями, сначала проконсультируйтесь с педиатром.",
        "Kids' immune support formulas are made for nursery and school season, the cold months and children who catch colds often. A typical formula contains vitamin C, zinc, vitamin D3, elderberry (sambucus) extract and sometimes echinacea and probiotics.\n\n"
        "Forms include tasty syrups, chewable gummies and lozenges. They don't treat illness — they support immunity alongside diet, sleep and activity. Pick an age-appropriate product, follow the label dose and take breaks between courses. For children prone to allergies or with chronic conditions, check with a paediatrician first.",
    ),
    # ================================================================ Accessories & Extras
    "Accessories & Extras": (
        "Aksessuarlar va qo'shimchalar — sport ozuqasi va vitaminlardan tashqari faol hayot uchun kerak bo'lgan hamma narsa: shakerlar va butilkalar, zal aksessuarlari, sport kiyimlari, protein snaklari, sog'lom oziq-ovqat, sport sumkalari va fitnes elektronikasi.\n\n"
        "To'g'ri anjomlar mashg'ulotni xavfsizroq va qulayroq qiladi: kamar umurtqani himoya qiladi, lyamkalar tutishni kuchaytiradi, shaker esa proteinni bir zumda tayyorlaydi. Protein snaklari va sog'lom mahsulotlar esa ratsionni mazali va to'g'ri saqlashga yordam beradi.\n\n"
        "Tanlashda: material sifati, o'lcham (kiyim va aksessuarlarda), BPA'siz plastik (butilka va shakerlarda) va protein snaklarida porsiyadagi oqsil va shakar miqdoriga e'tibor bering.",
        "Аксессуары и дополнения — всё, что нужно для активной жизни помимо спортивного питания и витаминов: шейкеры и бутылки, аксессуары для зала, спортивная одежда, протеиновые снеки, здоровые продукты, спортивные сумки и фитнес-электроника.\n\n"
        "Правильная экипировка делает тренировку безопаснее и удобнее: пояс защищает позвоночник, лямки усиливают хват, а шейкер готовит протеин за секунды. Протеиновые снеки и здоровые продукты помогают питаться вкусно и правильно.\n\n"
        "При выборе обращайте внимание на качество материалов, размер (одежда и аксессуары), пластик без BPA (бутылки и шейкеры) и количество белка и сахара в порции протеиновых снеков.",
        "Accessories & Extras covers everything an active life needs beyond sports nutrition and vitamins: shakers and bottles, gym accessories, sportswear, protein snacks, healthy food, sports bags and fitness electronics.\n\n"
        "The right gear makes training safer and more comfortable — a belt protects your spine, straps strengthen your grip and a shaker makes protein in seconds — while protein snacks and healthy foods keep your diet tasty and on track.\n\n"
        "When choosing, look at material quality, sizing (clothing and accessories), BPA-free plastic (bottles and shakers) and protein and sugar per serving in snacks.",
    ),
    "Shakers": (
        "Shaker — protein, geyner, BCAA va boshqa kukunlarni bir necha soniyada bir xil, bo'laksiz aralashtirish uchun idish. Ichidagi to'r, sharcha yoki elektr aralashtirgich kukunni mukammal eritadi.\n\n"
        "Turlari: klassik (to'r yoki sharcha bilan), blender (kuchliroq aralashtirish uchun mexanizm) va «aqlli» shakerlar (elektr aralashtirgich yoki qo'shimcha bo'limlar). Tanlashda: BPA'siz plastik, oqmaydigan qopqoq, hajm (500–800 ml) va kukun uchun alohida konteyner borligiga qarang. Har ishlatishdan keyin darhol yuving — hid qolmaydi.",
        "Шейкер — ёмкость, чтобы за несколько секунд размешать протеин, гейнер, BCAA и другие порошки однородно и без комков. Сеточка, шарик или электромиксер внутри отлично растворяют порошок.\n\n"
        "Виды: классические (с сеточкой или шариком), блендеры (механизм для более мощного смешивания) и «умные» шейкеры (электромиксер или дополнительные отсеки). При выборе смотрите: пластик без BPA, герметичная крышка, объём (500–800 мл) и отдельный контейнер для порошка. Мойте сразу после использования — запаха не будет.",
        "A shaker mixes protein, gainers, BCAAs and other powders smoothly and lump-free in seconds, thanks to a mesh, a whisk ball or an electric mixer inside.\n\n"
        "Types: classic (mesh or ball), blender (a mechanism for stronger mixing) and smart shakers (electric mixer or extra compartments). Look for BPA-free plastic, a leak-proof lid, the right volume (500–800 ml) and a separate powder container. Rinse straight after use to avoid odours.",
    ),
    "Classic": (
        "Klassik shaker — to'r yoki aralashtiruvchi sharcha bilan oddiy, ishonchli va arzon idish. Protein va BCAA uchun yetarli, yuvish oson va har qanday sport sumkasiga sig'adi.\n\n"
        "BPA'siz plastik va mahkam yopiladigan qopqoqni tanlang; o'lchov chiziqlari suvni aniq quyishga yordam beradi.",
        "Классический шейкер — простая, надёжная и недорогая ёмкость с сеточкой или шариком для смешивания. Подходит для протеина и BCAA, легко моется и помещается в любую спортивную сумку.\n\n"
        "Выбирайте пластик без BPA и плотно закрывающуюся крышку; мерная шкала помогает точно налить воду.",
        "A classic shaker is a simple, reliable, affordable bottle with a mesh or mixing ball — fine for protein and BCAAs, easy to wash and fits any gym bag.\n\n"
        "Choose BPA-free plastic and a tight-sealing lid; measurement markings help you add exactly the right amount of water.",
    ),
    "Blender": (
        "Blender shakerlar — kuchliroq aralashtirish mexanizmiga ega (spiralsimon sharcha yoki pichoqli to'r): geyner, suli va quyuq proteinlarni ham bo'laksiz aralashtiradi.\n\n"
        "Quyuq kokteyllar va katta porsiyalar tayyorlaydiganlar uchun qulay. Ko'pincha hajmi kattaroq (700–900 ml) va kukun uchun qo'shimcha bo'limlari bo'ladi.",
        "Шейкеры-блендеры оснащены более мощным механизмом смешивания (спиральный шарик или сетка с лопастями) и без комков размешивают даже гейнеры, овсянку и густые протеины.\n\n"
        "Удобны тем, кто готовит густые коктейли и большие порции. Обычно больше по объёму (700–900 мл) и с дополнительными отсеками для порошка.",
        "Blender shakers have a stronger mixing mechanism (a spiral whisk ball or bladed mesh) that blends even gainers, oats and thick proteins lump-free.\n\n"
        "Great for thick shakes and big servings, they're usually larger (700–900 ml) and often have extra powder compartments.",
    ),
    "Smart Shaker": (
        "Smart shaker — zamonaviy, ko'p funksiyali shaker: elektr aralashtirgich (tugma bosilganda o'zi aralashtiradi), kukun, tabletka va kapsulalar uchun alohida bo'limlar yoki hatto USB orqali zaryadlanadigan batareya.\n\n"
        "Ishda, yo'lda va zalda bir kunlik barcha qo'shimchalarni bitta idishda olib yurish uchun qulay.",
        "Smart shaker — современный многофункциональный шейкер: электромиксер (размешивает сам по нажатию кнопки), отдельные отсеки для порошка, таблеток и капсул или даже аккумулятор с зарядкой по USB.\n\n"
        "Удобно, чтобы носить все добавки на день в одной ёмкости — на работу, в дорогу и в зал.",
        "A smart shaker is a modern multi-function shaker: an electric mixer that blends at the push of a button, separate compartments for powder, tablets and capsules, or even a USB-rechargeable battery.\n\n"
        "Handy for carrying a whole day's supplements in one container — to work, while travelling and to the gym.",
    ),
    "Water Bottles": (
        "Sport butilkalari mashg'ulot va kun davomida yetarli suv ichishni odatga aylantiradi. Kattalarga kuniga taxminan 30–35 ml/kg suyuqlik kerak, mashg'ulot va issiq havoda esa ko'proq.\n\n"
        "Turlari: kundalik butilkalar (500–1000 ml) va gallonlar (2–3.8 l — butun kunlik suv me'yori uchun, ko'pincha vaqt belgilari bilan). Tanlashda: BPA'siz Tritan plastik yoki zanglamaydigan po'lat, oqmaydigan qopqoq, bir qo'l bilan ochilishi va yuvish qulayligi muhim.",
        "Спортивные бутылки помогают сделать достаточное питьё привычкой — на тренировке и в течение дня. Взрослым нужно примерно 30–35 мл жидкости на кг в сутки, а при тренировках и в жару — больше.\n\n"
        "Виды: повседневные бутылки (500–1000 мл) и галлоны (2–3,8 л — на всю дневную норму, часто с временными отметками). При выборе важны пластик Tritan без BPA или нержавеющая сталь, непротекающая крышка, открытие одной рукой и удобство мытья.",
        "Sports bottles make drinking enough water a habit, in training and through the day. Adults need roughly 30–35 ml of fluid per kg a day, and more when training or in the heat.\n\n"
        "Types: everyday bottles (500–1,000 ml) and gallon jugs (2–3.8 l for your whole daily intake, often with time markers). Look for BPA-free Tritan or stainless steel, a leak-proof lid, one-handed opening and easy cleaning.",
    ),
    "Bottles": (
        "Sport butilkalari — zal, yugurish va kundalik hayot uchun 500–1000 ml hajmdagi qulay idishlar. Termo butilkalar ichimlikni soatlab sovuq yoki issiq saqlaydi.\n\n"
        "BPA'siz material, oqmaydigan qopqoq va sport sumkasi yoki velosiped ushlagichiga sig'adigan shaklni tanlang.",
        "Спортивные бутылки — удобные ёмкости на 500–1000 мл для зала, бега и повседневной жизни. Термобутылки часами сохраняют напиток холодным или горячим.\n\n"
        "Выбирайте материал без BPA, непротекающую крышку и форму, которая помещается в спортивную сумку или велодержатель.",
        "Sports bottles are handy 500–1,000 ml containers for the gym, running and everyday life; insulated bottles keep drinks cold or hot for hours.\n\n"
        "Choose BPA-free material, a leak-proof lid and a shape that fits your gym bag or bike cage.",
    ),
    "Gallon Jugs": (
        "Gallon (2–3.8 l) — butun kunlik suv me'yorini bitta idishda olib yurish uchun katta butilka. Ko'pchiligida «soat 8:00 dan 20:00 gacha» kabi vaqt belgilari bor — bu kun davomida suvni bir tekis ichishga undaydi.\n\n"
        "Massa yig'ish, quritish va issiq iqlimda ko'p mashg'ulot qiladiganlar uchun ayniqsa qulay.",
        "Галлон (2–3,8 л) — большая бутылка, чтобы носить всю дневную норму воды в одной ёмкости. На многих есть временные отметки «с 8:00 до 20:00» — это мотивирует пить равномерно в течение дня.\n\n"
        "Особенно удобен при наборе массы, сушке и тренировках в жарком климате.",
        "A gallon jug (2–3.8 l) carries your whole daily water intake in one bottle. Many have time markers such as 8 am to 8 pm, encouraging you to drink steadily through the day.\n\n"
        "Especially handy when bulking, cutting or training a lot in a hot climate.",
    ),
    "Gym Accessories": (
        "Zal aksessuarlari mashg'ulotni xavfsizroq, samaraliroq va qulayroq qiladi: ular bo'g'imlarni himoya qiladi, tutishni kuchaytiradi va og'ir og'irliklar bilan texnikani saqlashga yordam beradi.\n\n"
        "Bo'limda: qo'lqoplar (kaftni himoya), lyamkalar (tortish mashqlarida tutish), kamarlar (og'ir o'tirish va o'lik tortishda umurtqa barqarorligi) va bilak bintlari (bilak bo'g'imini qo'llab-quvvatlash).\n\n"
        "Maslahat: aksessuarlarni og'ir ish setlarida ishlating, yengil mashqlarda esa tutish va stabillashtiruvchi mushaklarni o'zingiz rivojlantiring. To'g'ri o'lcham tanlash muhim.",
        "Аксессуары для зала делают тренировку безопаснее, эффективнее и удобнее: защищают суставы, усиливают хват и помогают сохранять технику с большими весами.\n\n"
        "В разделе: перчатки (защита ладоней), лямки (хват в тяговых упражнениях), пояса (стабильность позвоночника в тяжёлых приседаниях и становой тяге) и бинты на запястья (поддержка лучезапястного сустава).\n\n"
        "Совет: используйте аксессуары в тяжёлых рабочих подходах, а в лёгких развивайте хват и мышцы-стабилизаторы сами. Важно подобрать правильный размер.",
        "Gym accessories make training safer, more effective and more comfortable — they protect joints, strengthen grip and help you keep good form with heavy weights.\n\n"
        "This section includes gloves (palm protection), straps (grip on pulling exercises), belts (spinal stability in heavy squats and deadlifts) and wrist wraps (wrist support).\n\n"
        "Tip: use accessories on heavy working sets and train your grip and stabilisers without them on lighter work. Getting the right size matters.",
    ),
    "Gloves": (
        "Sport qo'lqoplari kaftni qadoq va shilinishlardan himoya qiladi, ter tufayli sirpanishni kamaytiradi va gantel, shtanga va trenajyorlarda tutishni qulaylashtiradi. Ba'zi modellarda bilakni qo'llab-quvvatlovchi tasma bor.\n\n"
        "Nafas oladigan material va qo'lga mahkam, lekin siqmaydigan o'lchamni tanlang.",
        "Спортивные перчатки защищают ладони от мозолей и натёртостей, уменьшают скольжение из-за пота и делают хват гантелей, штанги и тренажёров удобнее. У некоторых моделей есть ремень для поддержки запястья.\n\n"
        "Выбирайте дышащий материал и размер, который сидит плотно, но не сдавливает.",
        "Training gloves protect your palms from calluses and blisters, reduce slipping from sweat and make gripping dumbbells, barbells and machines more comfortable; some have a wrist-support strap.\n\n"
        "Choose breathable material and a size that fits snugly without squeezing.",
    ),
    "Straps": (
        "Lyamkalar (strapslar) shtanga yoki gantelni qo'lga «bog'lab», tortish mashqlarida (o'lik tortish, tortishlar, shrag) tutish kuchini ancha oshiradi. Shunda bilak charchasa ham orqa va trapetsiya mushaklari to'liq ishlaydi.\n\n"
        "Paxta yoki neylon materialdan, mustahkam tikilganini tanlang. Faqat og'ir ish setlarida ishlating — tutish kuchini ham mashq qilishni unutmang.",
        "Лямки (страпсы) «привязывают» штангу или гантель к руке и сильно усиливают хват в тяговых упражнениях (становая тяга, тяги, шраги). Так спина и трапеции работают в полную силу, даже когда предплечья устали.\n\n"
        "Выбирайте хлопок или нейлон с прочной прошивкой. Используйте только в тяжёлых рабочих подходах — не забывайте тренировать и хват.",
        "Lifting straps tie the bar or dumbbell to your hand and greatly increase grip on pulling exercises (deadlifts, rows, shrugs), so your back and traps can work fully even when your forearms tire.\n\n"
        "Choose cotton or nylon with strong stitching, and use them only for heavy working sets — keep training your grip too.",
    ),
    "Belts": (
        "Atletik kamar qorin ichi bosimini oshirib, og'ir o'tirish, o'lik tortish va tepaga siqishda umurtqa pog'onasini barqarorlashtiradi. Bu kuchli va xavfsizroq ko'tarish imkonini beradi.\n\n"
        "Turlari: charm/pauerlifting kamarlari (qattiq, bir xil kenglikda) va yumshoq neylon kamarlar (universal, qulay). Belingiz o'lchamiga mos tanlang va faqat og'ir setlarda taqing.",
        "Атлетический пояс повышает внутрибрюшное давление и стабилизирует позвоночник в тяжёлых приседаниях, становой тяге и жимах над головой. Это позволяет поднимать больше и безопаснее.\n\n"
        "Виды: кожаные/пауэрлифтерские пояса (жёсткие, одинаковой ширины) и мягкие нейлоновые (универсальные, удобные). Подбирайте по обхвату талии и надевайте только на тяжёлые подходы.",
        "A lifting belt increases intra-abdominal pressure and stabilises your spine in heavy squats, deadlifts and overhead presses, letting you lift more, more safely.\n\n"
        "Types: leather/powerlifting belts (stiff, uniform width) and soft nylon belts (versatile and comfortable). Size it to your waist and wear it only for heavy sets.",
    ),
    "Wrist Wraps": (
        "Bilak bintlari og'ir jim va siqish mashqlarida (jim yotib, tepaga siqish, otjimaniye) bilak bo'g'imini qo'llab-quvvatlaydi va uning ortiqcha bukilishining oldini oladi.\n\n"
        "Elastikligi va uzunligi bo'yicha tanlang: qattiqroq bintlar maksimal og'irliklar uchun, yumshoqlari esa umumiy mashg'ulotlar uchun. Har bir setdan keyin bo'shatib qo'ying.",
        "Бинты на запястья поддерживают лучезапястный сустав в тяжёлых жимах (лёжа, над головой, отжимания) и не дают ему чрезмерно сгибаться.\n\n"
        "Выбирайте по жёсткости и длине: жёсткие — для максимальных весов, мягкие — для обычных тренировок. Ослабляйте их после каждого подхода.",
        "Wrist wraps support the wrist joint in heavy pressing (bench, overhead press, push-ups) and stop it bending back too far.\n\n"
        "Choose by stiffness and length — stiffer wraps for maximal weights, softer ones for general training — and loosen them after each set.",
    ),
    "Sportswear": (
        "Sport kiyimlari mashg'ulotda erkin harakat, terni tez chiqarish va qulaylikni ta'minlaydi. To'g'ri kiyim ishqalanishni kamaytiradi, tanani quruq saqlaydi va motivatsiyani oshiradi.\n\n"
        "Bo'limda: futbolkalar, shortilar, xudilar va paypoqlar. Tanlashda nafas oladigan, namni tortib chiqaradigan (dry-fit) matolar, cho'ziluvchanlik va o'lchamga e'tibor bering; zalda, ochiq havoda va kundalik hayotda ham kiyish mumkin.",
        "Спортивная одежда обеспечивает свободу движений, быстрый отвод пота и комфорт на тренировке. Правильная одежда уменьшает натирание, сохраняет тело сухим и повышает мотивацию.\n\n"
        "В разделе: футболки, шорты, худи и носки. При выборе обращайте внимание на дышащие влагоотводящие ткани (dry-fit), эластичность и размер; такую одежду удобно носить в зале, на улице и в повседневной жизни.",
        "Sportswear gives you freedom of movement, quick sweat wicking and comfort while training. The right clothing reduces chafing, keeps you dry and boosts motivation.\n\n"
        "This section covers T-shirts, shorts, hoodies and socks. Look for breathable, moisture-wicking (dry-fit) fabrics, stretch and the right size — wearable at the gym, outdoors and every day.",
    ),
    "T-Shirts": (
        "Sport futbolkalari — yengil, nafas oladigan va terni tez chiqaradigan matodan (poliester yoki aralash). Erkin bichim harakatni cheklamaydi, «oversize» modellar esa zalda ham, kundalik hayotda ham zamonaviy ko'rinadi.\n\n"
        "O'lcham jadvalini tekshiring; bir necha marta yuvilgandan keyin ham shakl va rang saqlanishiga e'tibor bering.",
        "Спортивные футболки — из лёгкой дышащей ткани, быстро отводящей пот (полиэстер или смесовая). Свободный крой не сковывает движения, а oversize-модели стильно смотрятся и в зале, и в повседневной жизни.\n\n"
        "Сверяйтесь с таблицей размеров и обращайте внимание, чтобы форма и цвет сохранялись после стирок.",
        "Training T-shirts are made from light, breathable, quick-drying fabric (polyester or blends). A relaxed cut doesn't restrict movement, and oversized styles look good at the gym and on the street.\n\n"
        "Check the size chart and look for shirts that keep their shape and colour after washing.",
    ),
    "Shorts": (
        "Sport shortilari o'tirish, yugurish va kardio mashg'ulotlarda to'liq harakat erkinligini beradi. Elastik kamar, yengil tez quriydigan mato va ba'zan ichki qatlam (kompressiya) qulaylikni oshiradi.\n\n"
        "Telefon uchun cho'ntaklar va mashq turingizga mos uzunlikni tanlang.",
        "Спортивные шорты дают полную свободу движений в приседаниях, беге и кардио. Эластичный пояс, лёгкая быстросохнущая ткань и иногда внутренний компрессионный слой добавляют комфорта.\n\n"
        "Выбирайте карманы для телефона и длину под ваш вид тренировок.",
        "Training shorts give full freedom of movement for squats, running and cardio. An elastic waistband, light quick-drying fabric and sometimes an inner compression layer add comfort.\n\n"
        "Look for phone pockets and a length that suits your training.",
    ),
    "Hoodies": (
        "Sport xudilari — isinish (razminka), zalga borib-kelish va sovuq kunlar uchun. Ular mushaklarni issiq saqlab, mashg'ulot boshida jarohat xavfini kamaytirishga yordam beradi.\n\n"
        "Yumshoq paxta-flis yoki yengil sport trikotaji, mustahkam kapyushon va cho'ntaklarni tanlang.",
        "Спортивные худи — для разминки, дороги в зал и прохладных дней. Они сохраняют мышцы тёплыми и помогают снизить риск травм в начале тренировки.\n\n"
        "Выбирайте мягкий хлопок с флисом или лёгкий спортивный трикотаж, удобный капюшон и карманы.",
        "Training hoodies are for warm-ups, the trip to the gym and cooler days, keeping muscles warm and helping reduce injury risk at the start of a session.\n\n"
        "Choose soft cotton fleece or light sports jersey, a comfortable hood and pockets.",
    ),
    "Socks": (
        "Sport paypoqlari oyoqni quruq saqlaydi, ishqalanish va qavariqning oldini oladi. Tovon va tagdagi qalinlashtirilgan qism zarbani yumshatadi, nafas oluvchi zonalar esa haroratni muvozanatlaydi.\n\n"
        "Yugurish uchun yupqaroq, kuch mashg'ulotlari uchun esa o'rtacha qalinlikdagi va to'piqni qoplaydigan modellarni tanlang.",
        "Спортивные носки сохраняют ноги сухими и предотвращают натирание и мозоли. Уплотнения на пятке и подошве смягчают удары, а дышащие зоны регулируют температуру.\n\n"
        "Для бега выбирайте более тонкие, для силовых — средней плотности и закрывающие щиколотку.",
        "Sports socks keep feet dry and prevent chafing and blisters. Cushioned heels and soles absorb impact, while breathable zones regulate temperature.\n\n"
        "Choose thinner socks for running and medium-weight, ankle-covering ones for strength training.",
    ),
    "Protein Snacks": (
        "Protein snaklari — oddiy shirinliklarning sog'lomroq muqobili: ular oqsilga boy, shakari kam va to'yimli. Yo'lda, ishda, mashg'ulotdan keyin yoki ovqatlar orasida kunlik oqsil normasini mazali to'ldirish uchun qulay.\n\n"
        "Bo'limda: protein batonchiklar, protein pechenyelar va protein chipslar. Bitta snakda odatda 10–25 g oqsil bo'ladi.\n\n"
        "Tanlashda: porsiyadagi oqsil, shakar (ideal holda 5 g dan kam) va kaloriyaga qarang. Ba'zi snaklarda shakar spirtlari (maltit, eritrit) bor — ko'p yeyilganda ichak noqulayligi berishi mumkin. Snak to'liq ovqat o'rnini bosmaydi.",
        "Протеиновые снеки — более здоровая альтернатива обычным сладостям: богаты белком, с минимумом сахара и сытные. Удобны в дороге, на работе, после тренировки или между приёмами пищи, чтобы вкусно добрать дневную норму белка.\n\n"
        "В разделе: протеиновые батончики, протеиновое печенье и протеиновые чипсы. В одном снеке обычно 10–25 г белка.\n\n"
        "При выборе смотрите на белок, сахар (в идеале меньше 5 г) и калорийность порции. В некоторых снеках есть сахарные спирты (мальтит, эритрит) — в больших количествах они могут вызывать дискомфорт в кишечнике. Снек не заменяет полноценную еду.",
        "Protein snacks are a healthier alternative to regular treats — high in protein, low in sugar and filling. Handy on the go, at work, after training or between meals to top up your daily protein in a tasty way.\n\n"
        "This section includes protein bars, protein cookies and protein chips, usually with 10–25 g of protein each.\n\n"
        "When choosing, check protein, sugar (ideally under 5 g) and calories per serving. Some snacks contain sugar alcohols (maltitol, erythritol), which can upset the stomach in large amounts. A snack doesn't replace a proper meal.",
    ),
    "Protein Bars": (
        "Protein batonchiklar — 15–25 g oqsilli, cho'ntakka sig'adigan to'yimli snak. Ular shirinlikka bo'lgan ishtahani qondiradi va proteinni shaker siz «yeyish» imkonini beradi.\n\n"
        "Shakari kam, tolasi ko'p va tarkibida sifatli oqsil (whey, sut oqsili) bo'lgan batonchiklarni tanlang. Mashg'ulotdan keyin yoki ovqatlar orasida yeyish qulay.",
        "Протеиновые батончики — сытный снек с 15–25 г белка, который помещается в карман. Они утоляют тягу к сладкому и позволяют «съесть» протеин без шейкера.\n\n"
        "Выбирайте батончики с малым количеством сахара, большим количеством клетчатки и качественным белком (сывороточным, молочным). Удобно есть после тренировки или между приёмами пищи.",
        "Protein bars are a filling, pocket-sized snack with 15–25 g of protein that satisfies sweet cravings and lets you eat your protein without a shaker.\n\n"
        "Choose bars low in sugar, high in fibre and made with quality protein (whey, milk protein). Great after training or between meals.",
    ),
    "Protein Cookies": (
        "Protein pechenyelari — oddiy pechenye ta'mida, lekin bitta pechenyeda ko'pincha 15–20 g oqsil. Choy yoki qahva bilan mazali va foydali snak.\n\n"
        "Kaloriya va shakar miqdoriga e'tibor bering — ba'zi pechenyelar katta va to'yimli, shuning uchun ularni to'liq porsiya sifatida hisoblang.",
        "Протеиновое печенье — со вкусом обычного печенья, но часто с 15–20 г белка в одной штуке. Вкусный и полезный перекус к чаю или кофе.\n\n"
        "Обращайте внимание на калорийность и сахар — некоторые печенья большие и сытные, поэтому учитывайте их как полноценную порцию.",
        "Protein cookies taste like regular cookies but often pack 15–20 g of protein each — a tasty, useful snack with tea or coffee.\n\n"
        "Watch the calories and sugar — some cookies are large and filling, so count them as a full serving.",
    ),
    "Protein Chips": (
        "Protein chipslar — oddiy chipslarning sog'lomroq versiyasi: oqsili ko'proq (porsiyada odatda 10–20 g), yog'i va uglevodi kamroq, chunki ular qovurilmasdan pishiriladi.\n\n"
        "Sho'r ta'm xohlaganda va kino yoki uchrashuv paytida yengil, to'yimli snak sifatida ajoyib tanlov.",
        "Протеиновые чипсы — более здоровая версия обычных чипсов: больше белка (обычно 10–20 г в порции), меньше жира и углеводов, потому что их запекают, а не жарят.\n\n"
        "Отличный выбор, когда хочется солёного, — лёгкий и сытный перекус для кино или встреч.",
        "Protein chips are a healthier take on regular chips: more protein (usually 10–20 g per serving) and less fat and carbs, because they're baked rather than fried.\n\n"
        "A great pick when you crave something salty — a light, filling snack for movie night or meet-ups.",
    ),
    "Healthy Food": (
        "Sog'lom oziq-ovqat — toza ovqatlanish va to'g'ri ratsionni mazali qilish uchun mahsulotlar. Ular sport ozuqasini kundalik ovqatga qulay tarzda qo'shadi va shakarli, «bo'sh kaloriyali» mahsulotlar o'rnini egallaydi.\n\n"
        "Bo'limda: yong'oq pastalari (oqsil va foydali yog'lar), protein pankeyklar (tez va to'yimli nonushta) va shakarsiz souslar (kaloriyasiz ta'm).\n\n"
        "Tanlashda: qo'shilgan shakar, palma yog'i va tarkib uzunligiga e'tibor bering — eng yaxshi mahsulotlar qisqa va tushunarli tarkibga ega.",
        "Здоровые продукты — для того, чтобы чистое питание и правильный рацион были вкусными. Они удобно добавляют спортивное питание в повседневную еду и заменяют сладкие продукты с «пустыми калориями».\n\n"
        "В разделе: ореховые пасты (белок и полезные жиры), протеиновые панкейки (быстрый сытный завтрак) и соусы без сахара (вкус без калорий).\n\n"
        "При выборе обращайте внимание на добавленный сахар, пальмовое масло и длину состава — у лучших продуктов он короткий и понятный.",
        "Healthy food makes clean eating and a balanced diet tasty, adding sports nutrition to everyday meals and replacing sugary empty-calorie products.\n\n"
        "This section includes nut butters (protein and healthy fats), protein pancakes (a quick, filling breakfast) and sugar-free sauces (flavour without calories).\n\n"
        "When choosing, check for added sugar, palm oil and label length — the best products have short, clear ingredient lists.",
    ),
    "Peanut Butter": (
        "Yeryong'oq pastasi — oqsil, foydali yog'lar, tola, magniy va E vitaminiga boy to'yimli mahsulot. Sportchilar uni non, suli bo'tqasi, pankeyk yoki kokteylga qo'shib, ovqatning kaloriya va to'yimliligini oshiradi.\n\n"
        "Eng yaxshisi — 100% yeryong'oqdan, shakar va palma yog'isiz. Yuqori kaloriyali, shuning uchun porsiyani (1–2 osh qoshiq) nazorat qiling. Yeryong'oqqa allergiyangiz bo'lsa, iste'mol qilmang.",
        "Арахисовая паста — сытный продукт, богатый белком, полезными жирами, клетчаткой, магнием и витамином E. Спортсмены добавляют её к хлебу, овсянке, панкейкам или коктейлям, чтобы повысить калорийность и сытность.\n\n"
        "Лучшая — из 100% арахиса, без сахара и пальмового масла. Она калорийная, поэтому контролируйте порцию (1–2 столовые ложки). При аллергии на арахис не употребляйте.",
        "Peanut butter is a filling food rich in protein, healthy fats, fibre, magnesium and vitamin E. Athletes add it to bread, oatmeal, pancakes or shakes to boost calories and satiety.\n\n"
        "The best kind is 100% peanuts, with no sugar or palm oil. It's calorie-dense, so watch your portion (1–2 tablespoons). Avoid it if you're allergic to peanuts.",
    ),
    "Protein Pancakes": (
        "Protein pankeyk aralashmasi — suv yoki sut qo'shib, bir necha daqiqada oqsilga boy nonushta tayyorlash uchun. Bir porsiyada odatdagidan ancha ko'p oqsil va kam shakar bo'ladi.\n\n"
        "Mevalar, yong'oq pastasi yoki shakarsiz sirop bilan — mashg'ulotdan oldingi yoki keyingi mazali va to'yimli taom.",
        "Смесь для протеиновых панкейков — чтобы за несколько минут приготовить богатый белком завтрак, просто добавив воду или молоко. В порции намного больше белка и меньше сахара, чем в обычных блинчиках.\n\n"
        "С фруктами, ореховой пастой или сиропом без сахара — вкусная и сытная еда до или после тренировки.",
        "Protein pancake mix lets you make a high-protein breakfast in minutes by adding water or milk, with far more protein and less sugar than regular pancakes.\n\n"
        "Top with fruit, nut butter or sugar-free syrup for a tasty, filling meal before or after training.",
    ),
    "Sugar-Free Sauces": (
        "Shakarsiz souslar va siroplar (shokoladli, karamelli, ketchup, salat souslari) taomga deyarli kaloriyasiz ta'm beradi. Ular parhez yoki quritish davrida ham sevimli taomlardan voz kechmaslikka yordam beradi.\n\n"
        "Odatda sukraloza yoki eritrit bilan shirinlashtirilgan; bo'tqa, pankeyk, salat va go'sht taomlariga qo'shish mumkin.",
        "Соусы и сиропы без сахара (шоколадные, карамельные, кетчуп, соусы для салатов) добавляют вкус практически без калорий. Они помогают не отказываться от любимых блюд на диете и сушке.\n\n"
        "Обычно подслащены сукралозой или эритритом; их можно добавлять к кашам, панкейкам, салатам и мясным блюдам.",
        "Sugar-free sauces and syrups (chocolate, caramel, ketchup, salad dressings) add flavour with almost no calories, so you don't have to give up favourite dishes when dieting or cutting.\n\n"
        "They're usually sweetened with sucralose or erythritol and go well on oatmeal, pancakes, salads and meat dishes.",
    ),
    "Sports Bags": (
        "Sport sumkalari va ryukzaklar kiyim, poyabzal, shaker va qo'shimchalarni tartibli olib yurish uchun. Yaxshi sumka mashg'ulotga tayyorgarlikni tez va qulay qiladi.\n\n"
        "Bo'limda: zal sumkalari (keng asosiy bo'lim, poyabzal uchun alohida joy) va ryukzaklar (ikki yelkada qulay, noutbuk bo'limi bilan — ish va zal uchun bir vaqtda). Tanlashda suv o'tkazmaydigan mato, nam narsalar uchun ventilyatsiyalangan bo'lim va mustahkam fermuarlarga e'tibor bering.",
        "Спортивные сумки и рюкзаки — чтобы аккуратно носить одежду, обувь, шейкер и добавки. Хорошая сумка делает сборы на тренировку быстрыми и удобными.\n\n"
        "В разделе: сумки для зала (вместительное основное отделение, отдельное место для обуви) и рюкзаки (удобно на двух плечах, с отделением для ноутбука — сразу и на работу, и в зал). Обращайте внимание на водоотталкивающую ткань, вентилируемый отсек для влажных вещей и прочные молнии.",
        "Sports bags and backpacks keep your clothes, shoes, shaker and supplements organised, making it quick and easy to get ready for training.\n\n"
        "This section includes gym bags (a roomy main compartment and a separate shoe pocket) and backpacks (comfortable on both shoulders, with a laptop sleeve for work and gym in one). Look for water-repellent fabric, a ventilated pocket for damp items and sturdy zips.",
    ),
    "Gym Bags": (
        "Zal sumkasi — kiyim, sochiq, poyabzal va qo'shimchalar uchun keng, mustahkam sumka. Poyabzal uchun alohida ventilyatsiyalangan bo'lim toza va nam narsalarni ajratib turadi.\n\n"
        "Yelka kamari, suv o'tkazmaydigan mato va mayda narsalar uchun ichki cho'ntaklar bilan modellarni tanlang.",
        "Сумка для зала — вместительная и прочная сумка для одежды, полотенца, обуви и добавок. Отдельный вентилируемый отсек для обуви разделяет чистые и влажные вещи.\n\n"
        "Выбирайте модели с плечевым ремнём, водоотталкивающей тканью и внутренними карманами для мелочей.",
        "A gym bag is a roomy, sturdy bag for clothes, towel, shoes and supplements, with a separate ventilated shoe compartment that keeps clean and damp items apart.\n\n"
        "Look for a shoulder strap, water-repellent fabric and inner pockets for small items.",
    ),
    "Backpacks": (
        "Sport ryukzaklari og'irlikni ikki yelkaga teng taqsimlaydi va ish, o'qish va zal uchun bitta universal yechim bo'la oladi. Ko'pchiligida noutbuk bo'limi, shaker uchun yon cho'ntak va poyabzal bo'limi bor.\n\n"
        "Yumshoq orqa panel, sozlanadigan kamarlar va suv o'tkazmaydigan materialga e'tibor bering.",
        "Спортивные рюкзаки равномерно распределяют вес на оба плеча и могут стать одним универсальным решением для работы, учёбы и зала. У многих есть отделение для ноутбука, боковой карман для шейкера и отсек для обуви.\n\n"
        "Обращайте внимание на мягкую спинку, регулируемые лямки и водоотталкивающий материал.",
        "Sports backpacks spread weight evenly across both shoulders and can be one all-in-one bag for work, study and the gym; many have a laptop sleeve, a side pocket for your shaker and a shoe compartment.\n\n"
        "Look for a padded back panel, adjustable straps and water-repellent material.",
    ),
    "Sports Electronics": (
        "Sport elektronikasi taraqqiyotni raqamlarda kuzatishga yordam beradi: qadamlar, puls, kaloriya sarfi, uyqu sifati, vazn va tana tarkibi. O'lchanadigan narsa yaxshilanadi — aniq ma'lumot motivatsiya va to'g'ri qarorlar uchun asos.\n\n"
        "Bo'limda: fitnes trekerlar (faollik, puls, uyqu) va aqlli tarozilar (vazn, yog' va mushak foizi, ilova bilan sinxronlash).\n\n"
        "Tanlashda: telefoningiz bilan moslik (Android/iOS), batareya muddati, suvdan himoya va ilovaning qulayligiga qarang.",
        "Спортивная электроника помогает отслеживать прогресс в цифрах: шаги, пульс, расход калорий, качество сна, вес и состав тела. Что измеряется, то улучшается — точные данные дают мотивацию и основу для правильных решений.\n\n"
        "В разделе: фитнес-трекеры (активность, пульс, сон) и умные весы (вес, процент жира и мышц, синхронизация с приложением).\n\n"
        "При выборе смотрите на совместимость с телефоном (Android/iOS), время работы батареи, защиту от воды и удобство приложения.",
        "Sports electronics help you track progress in numbers — steps, heart rate, calories burned, sleep quality, weight and body composition. What gets measured gets improved, and accurate data fuels motivation and better decisions.\n\n"
        "This section includes fitness trackers (activity, heart rate, sleep) and smart scales (weight, body-fat and muscle percentage, app sync).\n\n"
        "When choosing, check phone compatibility (Android/iOS), battery life, water resistance and how good the app is.",
    ),
    "Fitness Trackers": (
        "Fitnes trekerlar va aqlli bilakuzuklar qadamlar, puls, kaloriya sarfi, mashg'ulot zonalari va uyqu bosqichlarini kuzatadi. Ular kun davomida ko'proq harakatlanishga undaydi va tiklanish holatini ko'rsatadi.\n\n"
        "Batareya muddati, suvdan himoya (suzish uchun), GPS va telefon ilovasi bilan qulay sinxronizatsiyaga e'tibor bering.",
        "Фитнес-трекеры и умные браслеты отслеживают шаги, пульс, расход калорий, тренировочные зоны и фазы сна. Они мотивируют больше двигаться в течение дня и показывают состояние восстановления.\n\n"
        "Обращайте внимание на время работы батареи, защиту от воды (для плавания), GPS и удобную синхронизацию с приложением на телефоне.",
        "Fitness trackers and smart bands track steps, heart rate, calories, training zones and sleep stages, nudging you to move more during the day and showing how well you've recovered.\n\n"
        "Look at battery life, water resistance (for swimming), GPS and smooth syncing with the phone app.",
    ),
    "Smart Scales": (
        "Aqlli tarozilar vazndan tashqari tana yog'i va mushak massasi foizi, suv miqdori va boshqa ko'rsatkichlarni (bioimpedans usulida) o'lchaydi va natijalarni telefon ilovasiga avtomatik yuboradi.\n\n"
        "Aniq taqqoslash uchun har doim bir vaqtda (masalan, ertalab och qoringa) o'lchang. Bioimpedans natijalari taxminiy — eng muhimi, vaqt o'tishi bilan dinamikani kuzatish. Yurak stimulyatori bo'lganlar uchun tavsiya etilmaydi.",
        "Умные весы помимо веса измеряют процент жира и мышечной массы, количество воды и другие показатели (методом биоимпеданса) и автоматически отправляют результаты в приложение на телефоне.\n\n"
        "Для точного сравнения взвешивайтесь всегда в одно время (например, утром натощак). Результаты биоимпеданса приблизительные — главное следить за динамикой. Не рекомендуются людям с кардиостимулятором.",
        "Smart scales measure body-fat and muscle percentage, water and other metrics (by bioimpedance) on top of weight, and send results to your phone app automatically.\n\n"
        "Weigh yourself at the same time each day (for example first thing in the morning) for accurate comparisons. Bioimpedance figures are estimates — the trend over time is what matters. Not recommended for people with a pacemaker.",
    ),
}
