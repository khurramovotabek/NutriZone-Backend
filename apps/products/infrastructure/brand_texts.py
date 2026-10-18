"""
Long uz / ru / en brand descriptions (2026-10-18): history, what each brand is known for, who it suits and a quality
score. Facts were checked against public sources (company history pages, trade press, court / regulator records) —
uncertain details (disputed founding years, unconfirmed founders) are left out rather than guessed.

Quality score (0–5) = manufacturing standard (GMP / ISO / BRC), independent testing (Informed Sport / Choice, IFOS,
in-house labs), track record and regulatory history. Applied by `manage.py seed_descriptions`.
"""
from __future__ import annotations

# official name → (uz, ru, en)
BRAND_TEXTS: dict[str, tuple[str, str, str]] = {
    "Optimum Nutrition": (
        "Optimum Nutrition (ON) — sport ozuqasi sohasidagi eng mashhur brendlardan biri. Uni 1986-yilda AQShda aka-uka Toni va Mayk Kostello asos solgan; 2008-yildan beri Irlandiyaning Glanbia kompaniyasi tarkibida. Mahsulotlari 100 dan ortiq mamlakatda sotiladi.\n\n"
        "Brendning yuzi — Gold Standard 100% Whey: dunyodagi eng ko'p sotiladigan whey proteinlardan biri, har porsiyada 24 g protein va o'nlab ta'mlar. ON sekin hazm bo'ladigan kazein toifasini Gold Standard 100% Casein bilan boshlab bergan; Amino Energy, Serious Mass va Micronized Creatine ham shu brenddan.\n\n"
        "Kimga mos: proteinni birinchi marta tanlayotganlardan tortib professional sportchilargacha — barqaror sifat va yaxshi eriydigan kukun kerak bo'lgan har kimga.\n\n"
        "⭐ Sifat bahosi: 5/5 — yirik ishlab chiqarish, qat'iy sifat nazorati va o'nlab yillik obro'.",
        "Optimum Nutrition (ON) — один из самых известных брендов спортивного питания. Его основали в 1986 году в США братья Тони и Майк Костелло; с 2008 года бренд входит в ирландскую группу Glanbia. Продукция продаётся более чем в 100 странах.\n\n"
        "Лицо бренда — Gold Standard 100% Whey: один из самых продаваемых сывороточных протеинов в мире, 24 г белка в порции и десятки вкусов. ON открыл категорию «медленного» протеина с Gold Standard 100% Casein; Amino Energy, Serious Mass и Micronized Creatine — тоже его продукты.\n\n"
        "Кому подойдёт: от тех, кто впервые выбирает протеин, до профессиональных спортсменов — всем, кому важны стабильное качество и хорошая растворимость.\n\n"
        "⭐ Оценка качества: 5/5 — крупное производство, строгий контроль качества и многолетняя репутация.",
        "Optimum Nutrition (ON) is one of the best-known names in sports nutrition. Brothers Tony and Mike Costello founded it in the USA in 1986, and since 2008 it has been part of Ireland's Glanbia group. ON products are sold in more than 100 countries.\n\n"
        "Its signature product is Gold Standard 100% Whey — one of the world's best-selling whey proteins, with 24 g of protein per serving and dozens of flavours. ON pioneered slow-digesting protein with Gold Standard 100% Casein; Amino Energy, Serious Mass and Micronized Creatine are also its classics.\n\n"
        "Who it suits: everyone from first-time protein buyers to professional athletes who want consistent quality and a powder that mixes well.\n\n"
        "⭐ Quality score: 5/5 — large-scale production, strict quality control and decades of reputation.",
    ),
    "Dymatize": (
        "Dymatize 1994-yilda AQShning Dallas (Texas) shahrida tashkil topgan va bugun premium proteinlar segmentidagi yetakchilardan. 2013-yilda Post Holdings guruhiga qo'shilgan. Kompaniya xom ashyo va tayyor kukunlarni o'zi sinovdan o'tkazadi, ta'mlarni esa o'z laboratoriyasida ishlab chiqadi.\n\n"
        "Eng mashhur mahsuloti — ISO100: gidrolizlangan whey izolyati. U tez so'riladi, laktoza va yog'i juda kam, shuning uchun sut mahsulotlariga sezgir odamlar ham ko'pincha bemalol ichadi. Super Mass Gainer va Elite 100% Whey ham keng tanilgan.\n\n"
        "Kimga mos: mashg'ulotdan keyin tez tiklanishni xohlovchilar, quruq massa va relyef ustida ishlayotganlar, sifatga qat'iy talab qo'yadiganlar.\n\n"
        "⭐ Sifat bahosi: 5/5 — o'z laboratoriyasidagi sinovlar va premium xom ashyo.",
        "Dymatize основан в 1994 году в Далласе (Техас, США) и сегодня входит в число лидеров премиального сегмента протеинов. В 2013 году бренд вошёл в группу Post Holdings. Компания сама тестирует сырьё и готовые порошки, а вкусы разрабатывает в собственной лаборатории.\n\n"
        "Самый известный продукт — ISO100, гидролизованный изолят сывороточного белка. Он быстро усваивается, почти не содержит лактозы и жира, поэтому его часто спокойно переносят даже люди, чувствительные к молочному. Также популярны Super Mass Gainer и Elite 100% Whey.\n\n"
        "Кому подойдёт: тем, кто хочет быстро восстанавливаться после тренировок, работает на сухую массу и рельеф и строго относится к качеству.\n\n"
        "⭐ Оценка качества: 5/5 — собственные лабораторные тесты и премиальное сырьё.",
        "Dymatize was founded in Dallas, Texas in 1994 and is now one of the leaders in premium protein. It joined Post Holdings in 2013. The company tests its raw materials and finished powders itself and develops its flavours in its own lab.\n\n"
        "Its best-known product is ISO100, a hydrolysed whey protein isolate: fast-absorbing and very low in lactose and fat, so many people who are sensitive to dairy tolerate it well. Super Mass Gainer and Elite 100% Whey are popular too.\n\n"
        "Who it suits: anyone who wants fast post-workout recovery, people working on lean mass and definition, and buyers who are strict about quality.\n\n"
        "⭐ Quality score: 5/5 — in-house lab testing and premium raw materials.",
    ),
    "ALLMAX Nutrition": (
        "ALLMAX Nutrition — Kanadaning Toronto shahridagi brend. U «toza tarkib» falsafasi bilan tanilgan: yorliqda har bir ingredient va uning aniq miqdori ko'rsatiladi, yashirin «proprietary blend»lar ishlatilmaydi.\n\n"
        "Flagman mahsulotlari — ISOFLEX whey izolyati (yuqori tozalikdagi protein, kam uglevod), AMINOCORE BCAA kompleksi va IMPACT Igniter pre-workouti. Kreatin va glutamin kabi bir komponentli mahsulotlari ham sifatli xom ashyosi bilan qadrlanadi.\n\n"
        "Kimga mos: tarkibni sinchiklab o'qiydiganlar, quritish (relyef) bosqichidagi sportchilar va shaffof formulani afzal ko'radiganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — shaffof yorliqlar va izolyat sifati.",
        "ALLMAX Nutrition — бренд из Торонто (Канада), известный философией «чистого состава»: на этикетке указаны все ингредиенты и их точные дозировки, без скрытых «proprietary blend».\n\n"
        "Флагманы — изолят ISOFLEX (протеин высокой степени очистки с минимумом углеводов), BCAA-комплекс AMINOCORE и предтренировочный IMPACT Igniter. Монопродукты вроде креатина и глютамина ценятся за качество сырья.\n\n"
        "Кому подойдёт: тем, кто внимательно читает состав, спортсменам на сушке и всем, кто предпочитает прозрачные формулы.\n\n"
        "⭐ Оценка качества: 4.5/5 — прозрачные этикетки и качество изолята.",
        "ALLMAX Nutrition is a brand from Toronto, Canada, known for its clean-label approach: every ingredient and its exact dose is on the label, with no hidden proprietary blends.\n\n"
        "Its flagships are ISOFLEX whey isolate (high-purity protein with minimal carbs), the AMINOCORE BCAA complex and the IMPACT Igniter pre-workout. Single-ingredient products such as creatine and glutamine are valued for their raw-material quality.\n\n"
        "Who it suits: label readers, athletes in a cutting phase and anyone who prefers transparent formulas.\n\n"
        "⭐ Quality score: 4.5/5 — transparent labels and isolate quality.",
    ),
    "BSN": (
        "BSN (Bio-Engineered Supplements & Nutrition) 2001-yilda AQShning Florida shtatida tashkil topgan va qisqa vaqtda yetakchi brendlardan biriga aylangan. 2011-yilda Glanbia guruhi (Optimum Nutrition egasi) tomonidan sotib olingan.\n\n"
        "BSN'ning eng mashhur mahsuloti — Syntha-6: whey konsentrati, izolyati va mitsellar kazeindan iborat ko'p komponentli protein. Bir necha manbadan olingani uchun oqsil uzoqroq so'riladi, ta'mi esa «milkshake»ga o'xshash yumshoq. Shuningdek, N.O.-Xplode pre-workouti va True-Mass geyneri ham mashhur.\n\n"
        "Kimga mos: ta'mi yoqimli va to'yimli protein izlayotganlar, kun davomida yoki uxlashdan oldin protein ichadiganlar, massa yig'ayotganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — Glanbia sifat tizimi va ko'p yillik retseptlar.",
        "BSN (Bio-Engineered Supplements & Nutrition) основан в 2001 году во Флориде (США) и быстро вырос в один из ведущих брендов. В 2011 году его купила группа Glanbia (владелец Optimum Nutrition).\n\n"
        "Самый известный продукт BSN — Syntha-6: многокомпонентный протеин из концентрата и изолята сыворотки и мицеллярного казеина. Благодаря нескольким источникам белок усваивается дольше, а вкус напоминает мягкий милкшейк. Также популярны предтреник N.O.-Xplode и гейнер True-Mass.\n\n"
        "Кому подойдёт: тем, кто ищет вкусный и сытный протеин, пьёт протеин в течение дня или перед сном, набирает массу.\n\n"
        "⭐ Оценка качества: 4.5/5 — система качества Glanbia и проверенные рецептуры.",
        "BSN (Bio-Engineered Supplements & Nutrition) was founded in Florida, USA in 2001 and quickly became one of the leading brands. Glanbia (owner of Optimum Nutrition) acquired it in 2011.\n\n"
        "BSN's best-known product is Syntha-6, a multi-source protein of whey concentrate, whey isolate and micellar casein. The blend digests over a longer period and tastes like a smooth milkshake. The N.O.-Xplode pre-workout and True-Mass gainer are classics too.\n\n"
        "Who it suits: anyone looking for a tasty, filling protein, people who drink protein during the day or before bed, and those building mass.\n\n"
        "⭐ Quality score: 4.5/5 — Glanbia's quality system and long-proven recipes.",
    ),
    "MuscleTech": (
        "MuscleTech 1995-yilda Kanadada MuscleTech Research and Development nomi bilan pochta orqali savdo qiluvchi kichik kompaniya sifatida boshlangan; keyinchalik Iovate Health Sciences kompaniyasiga aylangan (Ontario). Brend tadqiqotlarga asoslangan formulalari bilan tanilgan.\n\n"
        "2000-yilda chiqarilgan Nitro-Tech — whey protein va kreatin birlashtirilgan mashhur protein; Cell-Tech kreatin kompleksi, Mass-Tech geyneri va Platinum seriyasi ham keng sotiladi. Bir qator mahsulotlari bo'yicha klinik tadqiqotlar o'tkazilgan.\n\n"
        "Kimga mos: kuch va massa ustida jiddiy ishlayotganlar, protein va kreatinni bitta mahsulotda olishni xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — tadqiqotlarga tayanadigan formulalar va 30 yillik tajriba.",
        "MuscleTech начинался в 1995 году в Канаде как небольшая компания MuscleTech Research and Development с продажами по почте; позже она выросла в Iovate Health Sciences (Онтарио). Бренд известен формулами, опирающимися на исследования.\n\n"
        "Выпущенный в 2000 году Nitro-Tech — популярный протеин, объединяющий сывороточный белок и креатин; также широко продаются креатиновый комплекс Cell-Tech, гейнер Mass-Tech и серия Platinum. По ряду продуктов проводились клинические исследования.\n\n"
        "Кому подойдёт: тем, кто серьёзно работает на силу и массу и хочет получить протеин и креатин в одном продукте.\n\n"
        "⭐ Оценка качества: 4.5/5 — формулы с опорой на исследования и 30 лет опыта.",
        "MuscleTech started in Canada in 1995 as MuscleTech Research and Development, a small mail-order business, and grew into Iovate Health Sciences (Ontario). The brand is known for research-driven formulas.\n\n"
        "Nitro-Tech, launched in 2000, combines whey protein with creatine; the Cell-Tech creatine complex, Mass-Tech gainer and the Platinum series are best-sellers too. Several of its products have been the subject of clinical studies.\n\n"
        "Who it suits: people training seriously for strength and size who want protein and creatine in one product.\n\n"
        "⭐ Quality score: 4.5/5 — research-backed formulas and 30 years of experience.",
    ),
    "CBUM": (
        "CBUM — Raw Nutrition (AQSh, 2019-yilda tashkil topgan) va olti karra Classic Physique Mister Olimpiya chempioni Kris Bamsted (Chris Bumstead) hamkorligidagi seriya. Bamsted 2021-yildan Raw Nutrition hammuallifi va mahsulotlarni o'zi ishlab chiqishda qatnashadi.\n\n"
        "Seriyaga CBUM Itholate whey izolyati, Essential Pre-Workout va Creatine Monohydrate kiradi. Formulalar oddiy, dozalari ochiq ko'rsatilgan, ta'mlari esa yorqin va mashhur desertlarga o'xshatilgan. Raw Nutrition Inc. 5000 reytingida eng tez o'sayotgan sport ozuqasi kompaniyalaridan biri sifatida qayd etilgan.\n\n"
        "Kimga mos: bodibilding va fitnes bilan shug'ullanuvchilar, ochiq formulali premium mahsulot va zamonaviy ta'mlarni qadrlaydiganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — ochiq dozalar va chempion bilan birga ishlangan formulalar.",
        "CBUM — совместная линейка Raw Nutrition (США, основана в 2019 году) и шестикратного чемпиона Mr. Olympia в Classic Physique Криса Бамстеда. С 2021 года Бамстед — совладелец Raw Nutrition и сам участвует в разработке продуктов.\n\n"
        "В линейку входят изолят CBUM Itholate, Essential Pre-Workout и Creatine Monohydrate. Формулы простые, дозировки открыты, а вкусы яркие, «десертные». Raw Nutrition отмечена в рейтинге Inc. 5000 как одна из самых быстрорастущих компаний спортивного питания.\n\n"
        "Кому подойдёт: тем, кто занимается бодибилдингом и фитнесом, ценит премиальные продукты с открытой формулой и современные вкусы.\n\n"
        "⭐ Оценка качества: 4.5/5 — открытые дозировки и формулы, созданные вместе с чемпионом.",
        "CBUM is the line created by Raw Nutrition (USA, founded 2019) together with six-time Classic Physique Mr. Olympia Chris Bumstead, who became a co-owner of Raw Nutrition in 2021 and helps develop the products himself.\n\n"
        "The line includes CBUM Itholate whey isolate, Essential Pre-Workout and Creatine Monohydrate. The formulas are simple with fully disclosed doses, and the flavours are bold and dessert-inspired. Raw Nutrition has been listed in the Inc. 5000 as one of the fastest-growing sports-nutrition companies.\n\n"
        "Who it suits: bodybuilders and fitness enthusiasts who value premium, open-label products and modern flavours.\n\n"
        "⭐ Quality score: 4.5/5 — disclosed doses and formulas developed with a champion.",
    ),
    "Mutant": (
        "Mutant — Kanadaning Britaniya Kolumbiyasi provinsiyasidagi Fit Foods kompaniyasi brendi (kompaniya 1996-yilda Jim Makmaxon tomonidan asos solingan). Brend «hardcore» uslubi va og'ir mashg'ulot qiluvchilarga mo'ljallangan mahsulotlari bilan tanilgan.\n\n"
        "Eng mashhuri — Mutant Mass: yuqori kaloriyali geyner, tez massa yig'ish uchun sifatli uglevod va protein aralashmasi. Mutant Whey protein, Mutant Madness pre-workout va Mutant Creakong kreatini ham shu brenddan.\n\n"
        "Kimga mos: vazn va massa yig'ishda qiynalayotgan «ektomorf»lar, og'ir kuch mashg'ulotlari bilan shug'ullanuvchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — barqaror ishlab chiqarish va geynerlar bo'yicha kuchli tajriba.",
        "Mutant — бренд компании Fit Foods из провинции Британская Колумбия (Канада); компанию основал Джим Макмахон в 1996 году. Бренд известен «хардкорным» стилем и продуктами для тяжёлых тренировок.\n\n"
        "Самый известный — Mutant Mass: высококалорийный гейнер с качественными углеводами и белком для быстрого набора массы. Также в линейке — протеин Mutant Whey, предтреник Mutant Madness и креатин Mutant Creakong.\n\n"
        "Кому подойдёт: «эктоморфам», которым трудно набрать вес и массу, и тем, кто тренируется тяжело на силу.\n\n"
        "⭐ Оценка качества: 4/5 — стабильное производство и сильная экспертиза в гейнерах.",
        "Mutant is a brand of Fit Foods in British Columbia, Canada (the company was founded by Jim McMahon in 1996). It is known for its hardcore style and products built for heavy training.\n\n"
        "Its best-known product is Mutant Mass, a high-calorie gainer with quality carbs and protein for fast mass gain. Mutant Whey protein, Mutant Madness pre-workout and Mutant Creakong creatine complete the range.\n\n"
        "Who it suits: hard-gainers who struggle to put on weight and anyone doing heavy strength training.\n\n"
        "⭐ Quality score: 4/5 — consistent production and strong gainer expertise.",
    ),
    "Olimp Sport Nutrition": (
        "Olimp Sport Nutrition — Polshaning Dembitsa shahridagi Olimp Laboratories farmatsevtika kompaniyasi brendi. Kompaniya 1990-yildan faoliyat yuritadi, birinchi Olimp mahsuloti 1992-yilda chiqqan; bugun 600 dan ortiq mahsulot 100 dan ortiq mamlakatga eksport qilinadi.\n\n"
        "Farmatsevtika darajasidagi ishlab chiqarish brendning asosiy ustunligi: proteinlar (Whey Protein Complex 100%, Pure Whey Isolate 95), kreatinlar, aminokislotalar, vitaminlar (Vita-Min Multiple Sport) va izotoniklar. Ko'plab mahsulotlari xalqaro sport tashkilotlari bilan hamkorlikda ishlatiladi.\n\n"
        "Kimga mos: Yevropa sifatini maqbul narxda xohlovchilar, professional va havaskor sportchilar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — farmatsevtik ishlab chiqarish standarti.",
        "Olimp Sport Nutrition — бренд фармацевтической компании Olimp Laboratories из польского города Дембица. Компания работает с 1990 года, первый продукт Olimp вышел в 1992-м; сегодня более 600 продуктов экспортируются в 100+ стран.\n\n"
        "Главное преимущество бренда — производство фармацевтического уровня: протеины (Whey Protein Complex 100%, Pure Whey Isolate 95), креатины, аминокислоты, витамины (Vita-Min Multiple Sport) и изотоники.\n\n"
        "Кому подойдёт: тем, кто хочет европейское качество по разумной цене, — профессиональным и любительским спортсменам.\n\n"
        "⭐ Оценка качества: 4.5/5 — фармацевтический стандарт производства.",
        "Olimp Sport Nutrition is the sports brand of Olimp Laboratories, a pharmaceutical company from Dębica, Poland. The company has operated since 1990 and launched its first Olimp product in 1992; today more than 600 products are exported to 100+ countries.\n\n"
        "Pharmaceutical-grade manufacturing is its main strength: proteins (Whey Protein Complex 100%, Pure Whey Isolate 95), creatines, amino acids, vitamins (Vita-Min Multiple Sport) and isotonic drinks.\n\n"
        "Who it suits: professional and amateur athletes who want European quality at a fair price.\n\n"
        "⭐ Quality score: 4.5/5 — pharmaceutical manufacturing standard.",
    ),
    "USN": (
        "USN (Ultimate Sports Nutrition) 1999-yilda Janubiy Afrikaning Pretoriya shahrida Albe Geldenxeys tomonidan asos solingan. Uydagi kichik biznes sifatida boshlangan brend bugun Buyuk Britaniya, AQSh, Hindiston va Avstraliyada ham faoliyat yuritadi.\n\n"
        "USN proteinlar (Blue Lab Whey), geynerlar, kreatin, pre-workout va yog' yoqish mahsulotlari bo'yicha keng assortimentga ega. Brend amaliy va ta'mi yoqimli mahsulotlari bilan tanilgan.\n\n"
        "Kimga mos: fitnes bilan muntazam shug'ullanuvchilar, keng tanlov va maqbul narxni qadrlaydiganlar.\n\n"
        "⭐ Sifat bahosi: 4/5 — 25 yillik tajriba va xalqaro miqyosdagi ishlab chiqarish.",
        "USN (Ultimate Sports Nutrition) основал Альбе Гелденхейс в 1999 году в Претории (ЮАР). Начинавшийся как небольшой домашний бизнес, бренд сегодня работает также в Великобритании, США, Индии и Австралии.\n\n"
        "У USN широкий ассортимент: протеины (Blue Lab Whey), гейнеры, креатин, предтреники и жиросжигатели. Бренд известен практичными и вкусными продуктами.\n\n"
        "Кому подойдёт: тем, кто регулярно занимается фитнесом и ценит широкий выбор и разумную цену.\n\n"
        "⭐ Оценка качества: 4/5 — 25 лет опыта и международное производство.",
        "USN (Ultimate Sports Nutrition) was founded by Albé Geldenhuys in Pretoria, South Africa in 1999. It started as a small home business and now also operates in the UK, the USA, India and Australia.\n\n"
        "USN has a wide range of proteins (Blue Lab Whey), gainers, creatine, pre-workouts and fat burners, and is known for practical, good-tasting products.\n\n"
        "Who it suits: regular gym-goers who value choice and a fair price.\n\n"
        "⭐ Quality score: 4/5 — 25 years of experience and international production.",
    ),
    "Rule 1": (
        "Rule 1 (Rule One Proteins) — AQSh brendi, nomi «birinchi qoida — sifat» degan falsafadan kelib chiqqan. Mahsulotlar AQShdagi GMP sertifikatli korxonada ishlab chiqariladi, taqiqlangan moddalar bo'yicha sinovdan o'tkaziladi va Informed Choice tomonidan sertifikatlangan.\n\n"
        "Flagman — R1 Protein: 100% whey izolyati va gidrolizati, konsentrat, qo'shilgan shakar, quyultirgich va «amino spiking» (aminokislotalar bilan oqsil miqdorini sun'iy oshirish) yo'q. R1 Whey Blend, R1 Creatine va R1 Pre-Workout ham mavjud.\n\n"
        "Kimga mos: toza va shaffof tarkibni xohlovchilar, doping nazoratidan o'tadigan sportchilar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — Informed Choice sertifikati va «amino spiking»siz formulalar.",
        "Rule 1 (Rule One Proteins) — американский бренд, название которого отражает принцип «первое правило — качество». Продукты производятся на предприятии в США с сертификатом GMP, проверяются на запрещённые вещества и сертифицированы Informed Choice.\n\n"
        "Флагман — R1 Protein: 100% изолят и гидролизат сыворотки без концентрата, добавленного сахара, загустителей и «amino spiking» (искусственного завышения белка аминокислотами). Есть также R1 Whey Blend, R1 Creatine и R1 Pre-Workout.\n\n"
        "Кому подойдёт: тем, кому нужен чистый и прозрачный состав, и спортсменам, проходящим допинг-контроль.\n\n"
        "⭐ Оценка качества: 4.5/5 — сертификат Informed Choice и формулы без amino spiking.",
        "Rule 1 (Rule One Proteins) is a US brand whose name reflects its first rule — quality. Products are made in a GMP-certified facility in the USA, tested for banned substances and certified by Informed Choice.\n\n"
        "Its flagship R1 Protein is 100% whey isolate and hydrolysate with no concentrate, added sugar, gums or amino spiking (inflating protein content with added amino acids). R1 Whey Blend, R1 Creatine and R1 Pre-Workout complete the range.\n\n"
        "Who it suits: buyers who want a clean, transparent label and athletes subject to doping control.\n\n"
        "⭐ Quality score: 4.5/5 — Informed Choice certification and no amino spiking.",
    ),
    "OstroVit": (
        "OstroVit — Polshaning Zambruv shahrida joylashgan, o'n yildan ortiq tajribaga ega brend. Mahsulotlari 40 dan ortiq mamlakatda sotiladi; kompaniya 2026-yilda Zambruvda yangi ishlab chiqarish va logistika majmuasiga 110 mln zlotiydan ortiq sarmoya kiritishini e'lon qilgan.\n\n"
        "Assortiment juda keng: proteinlar, kreatin, aminokislotalar, vitamin to'plamlari, MCT moyi, yong'oq pastalari va vegan mahsulotlar. Brendning asosiy afzalligi — narx va sifat muvozanati, ko'p mahsulotlari bitta komponentli va oddiy tarkibga ega.\n\n"
        "Kimga mos: byudjetni tejagan holda sifatli asosiy sport ozuqasini xohlovchilar, kundalik sog'lom ovqatlanish mahsulotlarini izlayotganlar.\n\n"
        "⭐ Sifat bahosi: 4/5 — Yevropa ishlab chiqarishi va narx-sifat muvozanati.",
        "OstroVit — польский бренд из города Замбрув с опытом более десяти лет. Продукция продаётся в 40+ странах; в 2026 году компания объявила об инвестициях более 110 млн злотых в новый производственно-логистический комплекс в Замбруве.\n\n"
        "Ассортимент очень широк: протеины, креатин, аминокислоты, витаминные наборы, масло MCT, ореховые пасты и веганские продукты. Главное преимущество — баланс цены и качества, многие продукты однокомпонентные и с простым составом.\n\n"
        "Кому подойдёт: тем, кто хочет качественную базовую спортивную добавку без переплаты, и тем, кто ищет продукты для здорового питания.\n\n"
        "⭐ Оценка качества: 4/5 — европейское производство и баланс цены и качества.",
        "OstroVit is a Polish brand based in Zambrów with more than ten years of experience. Its products are sold in 40+ countries, and in 2026 the company announced an investment of over PLN 110 million in a new production and logistics complex in Zambrów.\n\n"
        "The range is very wide: proteins, creatine, amino acids, vitamin packs, MCT oil, nut butters and vegan products. Its main strength is value for money, and many products are single-ingredient with simple labels.\n\n"
        "Who it suits: anyone who wants quality basics without overpaying, and shoppers looking for everyday healthy-food products.\n\n"
        "⭐ Quality score: 4/5 — European production and strong value for money.",
    ),
    "Sports Research": (
        "Sports Research — 1980-yildan beri faoliyat yuritayotgan, Kaliforniyaning San-Pedro shahridagi oilaviy kompaniya. Kompaniya fitnes-klub egasi Jeff Pedersen Sr. tomonidan yaratilgan Sweet Sweat mahsulotidan boshlangan.\n\n"
        "Bugun brend omega-3 baliq yog'i (Triple Strength Omega-3), kollagen peptidlari, D3+K2 vitamini, MCT moyi va biotin kabi sog'liq mahsulotlari bilan tanilgan. Omega-3 mahsulotlari xalqaro IFOS standarti bo'yicha tozalik va yangilik sinovlaridan o'tadi.\n\n"
        "Kimga mos: yurak, bo'g'im, teri va umumiy salomatlik uchun sifatli omega-3 va kollagen izlayotganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — oilaviy kompaniya an'anasi va mustaqil sinovdan o'tgan omega-3.",
        "Sports Research — семейная компания из Сан-Педро (Калифорния), работающая с 1980 года. Всё началось с продукта Sweet Sweat, созданного владельцем фитнес-клуба Джеффом Педерсеном-старшим.\n\n"
        "Сегодня бренд известен продуктами для здоровья: рыбий жир омега-3 (Triple Strength Omega-3), пептиды коллагена, витамин D3+K2, масло MCT и биотин. Омега-3 проходит проверку чистоты и свежести по международному стандарту IFOS.\n\n"
        "Кому подойдёт: тем, кто ищет качественные омега-3 и коллаген для сердца, суставов, кожи и общего здоровья.\n\n"
        "⭐ Оценка качества: 4.5/5 — традиции семейной компании и омега-3 с независимой проверкой.",
        "Sports Research is a family-owned company from San Pedro, California, in business since 1980. It began with Sweet Sweat, a product created by fitness-club owner Jeff Pedersen Sr.\n\n"
        "Today the brand is known for wellness products: Triple Strength Omega-3 fish oil, collagen peptides, vitamin D3+K2, MCT oil and biotin. Its omega-3 is tested for purity and freshness under the international IFOS standard.\n\n"
        "Who it suits: anyone looking for quality omega-3 and collagen for heart, joint, skin and overall health.\n\n"
        "⭐ Quality score: 4.5/5 — family-company tradition and independently tested omega-3.",
    ),
    "Ultimate Nutrition": (
        "Ultimate Nutrition — 1979-yilda pauerlifter va biokimyogar Viktor Rubino tomonidan AQShning Konnektikut shtatida asos solingan brend. U shu kungacha Rubino oilasiga tegishli va oila tomonidan boshqariladi — bu sohada kam uchraydigan holat.\n\n"
        "Kompaniya 1990-yillar o'rtasida whey protein kukunini bankada sotgan ilk kompaniyalardan biri bo'lgan. Eng mashhur mahsuloti — ProStar 100% Whey; shuningdek, aminokislotalar, geynerlar va yog' yoquvchilar ishlab chiqariladi.\n\n"
        "Kimga mos: an'anaviy, vaqt sinovidan o'tgan protein va maqbul narxni xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — 45 yildan ortiq tajriba va oilaviy boshqaruv.",
        "Ultimate Nutrition основал в 1979 году в Коннектикуте (США) пауэрлифтер и биохимик Виктор Рубино. Компания до сих пор принадлежит семье Рубино и управляется ею — редкость для индустрии.\n\n"
        "В середине 1990-х компания одной из первых начала продавать сывороточный протеин в банках. Самый известный продукт — ProStar 100% Whey; также выпускаются аминокислоты, гейнеры и жиросжигатели.\n\n"
        "Кому подойдёт: тем, кто хочет проверенный временем протеин по разумной цене.\n\n"
        "⭐ Оценка качества: 4.5/5 — более 45 лет опыта и семейное управление.",
        "Ultimate Nutrition was founded in Connecticut, USA in 1979 by powerlifter and biochemist Victor Rubino. It is still owned and run by the Rubino family — rare in this industry.\n\n"
        "In the mid-1990s it was one of the first companies to sell whey protein powder in a tub. Its best-known product is ProStar 100% Whey; it also makes amino acids, gainers and fat burners.\n\n"
        "Who it suits: anyone who wants a time-tested protein at a fair price.\n\n"
        "⭐ Quality score: 4.5/5 — more than 45 years of experience and family ownership.",
    ),
    "BioTechUSA": (
        "BioTechUSA — Vengriyaning oilaviy kompaniyasi (Levai oilasi), 1990-yillarda sport anjomlari distributori sifatida boshlangan va bugun Yevropaning eng yirik sport ozuqasi ishlab chiqaruvchilaridan biriga aylangan. Asosiy zavodlari Budapesht yaqinidagi Szada va Dunakeszi shaharlarida; kompaniyada 2000 ga yaqin xodim ishlaydi.\n\n"
        "Mashhur mahsulotlari — Iso Whey Zero (laktoza va glutensiz izolyat), 100% Pure Whey, kreatinlar, BCAA va vitaminlar. Ta'mlarning xilma-xilligi va zamonaviy laboratoriya nazorati bilan ajralib turadi; 2026-yilda ishlab chiqarish quvvatlarini yanada kengaytirgan.\n\n"
        "Kimga mos: Yevropa sifatidagi keng tanlovni va ko'plab ta'mlarni qadrlaydiganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — o'z zavodlari va yirik Yevropa ishlab chiqarishi.",
        "BioTechUSA — венгерская семейная компания (семья Леваи), начинавшая в 1990-х как дистрибьютор спортивного инвентаря и выросшая в одного из крупнейших производителей спортивного питания в Европе. Основные заводы — в Саде и Дунакеси под Будапештом; в компании работает около 2000 человек.\n\n"
        "Популярные продукты — Iso Whey Zero (изолят без лактозы и глютена), 100% Pure Whey, креатины, BCAA и витамины. Бренд выделяется разнообразием вкусов и современным лабораторным контролем; в 2026 году компания ещё расширила производство.\n\n"
        "Кому подойдёт: тем, кто ценит широкий выбор европейского качества и множество вкусов.\n\n"
        "⭐ Оценка качества: 4.5/5 — собственные заводы и крупное европейское производство.",
        "BioTechUSA is a Hungarian family company (the Lévai family) that started in the 1990s as a gym-equipment distributor and grew into one of Europe's largest sports-nutrition manufacturers. Its main plants are in Szada and Dunakeszi near Budapest, and it employs about 2,000 people.\n\n"
        "Popular products include Iso Whey Zero (a lactose- and gluten-free isolate), 100% Pure Whey, creatines, BCAAs and vitamins. It stands out for its range of flavours and modern lab control, and expanded production again in 2026.\n\n"
        "Who it suits: anyone who values a wide choice of European-made products and lots of flavours.\n\n"
        "⭐ Quality score: 4.5/5 — own factories and large-scale European production.",
    ),
    "Maxler": (
        "Maxler — Mustaqil Davlatlar Hamdo'stligi mamlakatlarida juda mashhur xalqaro brend; mahsulotlari Germaniya va AQShdagi zavodlarda ishlab chiqariladi va 30 dan ortiq mamlakatda sotiladi.\n\n"
        "Eng ko'p sotiladigan mahsulotlari — 100% Golden Whey proteini, Ultra Whey, Special Mass Gainer, kreatin va aminokislotalar. Brend maqbul narxdagi sifatli asosiy mahsulotlar va mazali ta'mlar bilan tanilgan.\n\n"
        "Kimga mos: narx va sifat muvozanatini qadrlaydigan, endigina sport ozuqasini boshlayotgan va muntazam shug'ullanuvchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — Yevropa va AQSh zavodlarida ishlab chiqarish.",
        "Maxler — международный бренд, очень популярный в странах СНГ; продукция производится на заводах в Германии и США и продаётся более чем в 30 странах.\n\n"
        "Самые продаваемые продукты — протеин 100% Golden Whey, Ultra Whey, Special Mass Gainer, креатин и аминокислоты. Бренд известен качественной базой по разумной цене и вкусными вкусами.\n\n"
        "Кому подойдёт: тем, кто ценит баланс цены и качества, — новичкам и тем, кто тренируется регулярно.\n\n"
        "⭐ Оценка качества: 4/5 — производство на заводах в Европе и США.",
        "Maxler is an international brand that is very popular across the CIS; its products are made in factories in Germany and the USA and sold in more than 30 countries.\n\n"
        "Best-sellers include 100% Golden Whey, Ultra Whey, Special Mass Gainer, creatine and amino acids. The brand is known for quality basics at a fair price and tasty flavours.\n\n"
        "Who it suits: beginners and regular gym-goers who value a good price-to-quality balance.\n\n"
        "⭐ Quality score: 4/5 — made in European and US factories.",
    ),
    "Source Naturals": (
        "Source Naturals — 1982-yilda Ira Goldberg tomonidan Kaliforniyada (Scotts Valley) asos solingan brend. U ko'p komponentli, «bio-moslashgan» formulalar kontseptsiyasini bozorga olib kirgan kashshoflardan biri hisoblanadi.\n\n"
        "Eng mashhur mahsuloti — Wellness Formula immunitet kompleksi; shuningdek, vitaminlar, minerallar, aminokislotalar, antioksidantlar (CoQ10, alfa-lipoy kislota) va o'simlik ekstraktlari keng assortimentda.\n\n"
        "Kimga mos: immunitet va umumiy salomatlikni qo'llab-quvvatlash uchun puxta ishlangan formulalar izlayotganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — 40 yildan ortiq tajriba va sog'liq mahsulotlarida obro'.",
        "Source Naturals основан в 1982 году Айрой Голдбергом в Калифорнии (Скоттс-Вэлли). Бренд считается одним из пионеров многокомпонентных, «биосогласованных» формул.\n\n"
        "Самый известный продукт — иммунный комплекс Wellness Formula; также в широком ассортименте витамины, минералы, аминокислоты, антиоксиданты (CoQ10, альфа-липоевая кислота) и растительные экстракты.\n\n"
        "Кому подойдёт: тем, кто ищет продуманные формулы для поддержки иммунитета и общего здоровья.\n\n"
        "⭐ Оценка качества: 4.5/5 — более 40 лет опыта и репутация в сфере здоровья.",
        "Source Naturals was founded by Ira Goldberg in Scotts Valley, California in 1982 and is regarded as a pioneer of multi-ingredient, bio-aligned formulas.\n\n"
        "Its best-known product is the Wellness Formula immune complex; it also offers a wide range of vitamins, minerals, amino acids, antioxidants (CoQ10, alpha-lipoic acid) and herbal extracts.\n\n"
        "Who it suits: anyone looking for well-designed formulas to support immunity and overall health.\n\n"
        "⭐ Quality score: 4.5/5 — more than 40 years of experience and a strong wellness reputation.",
    ),
    "APS Nutrition": (
        "APS Nutrition — AQSh brendi, eng avvalo Mesomorph pre-workouti bilan tanilgan. Mesomorph birinchi bor 2013-yilda chiqqan va juda kuchli energiya, diqqat va «pump» beruvchi formula sifatida mashhur bo'lgan; keyingi yillarda formulasi bir necha bor yangilangan.\n\n"
        "Mesomorph — yuqori dozali stimulyatorli mahsulot (kofein va boshqa stimulyatorlar, sitrullin, beta-alanin). Shuning uchun u tajribali sportchilar uchun mo'ljallangan: kunlik kofein miqdorini hisobga oling, kechqurun ichmang va dozani yarim porsiyadan boshlang.\n\n"
        "Kimga mos: stimulyatorlarga ko'nikkan, juda intensiv mashg'ulot qiladigan tajribali sportchilar. Kofeinga sezgir, yurak-qon tomir muammolari bo'lganlarga tavsiya etilmaydi.\n\n"
        "⭐ Sifat bahosi: 3.5/5 — kuchli samara, lekin juda yuqori stimulyator yuklamasi.",
        "APS Nutrition — американский бренд, прежде всего известный предтреником Mesomorph. Mesomorph впервые вышел в 2013 году и прославился очень мощной энергией, фокусом и пампом; за прошедшие годы его формула несколько раз менялась.\n\n"
        "Mesomorph — высокостимуляторный продукт (кофеин и другие стимуляторы, цитруллин, бета-аланин), поэтому он рассчитан на опытных спортсменов: учитывайте суточную норму кофеина, не принимайте вечером и начинайте с половины порции.\n\n"
        "Кому подойдёт: опытным спортсменам, привыкшим к стимуляторам и тренирующимся очень интенсивно. Не рекомендуется людям, чувствительным к кофеину, и при проблемах с сердцем и сосудами.\n\n"
        "⭐ Оценка качества: 3.5/5 — сильный эффект, но очень высокая стимуляторная нагрузка.",
        "APS Nutrition is a US brand known above all for its Mesomorph pre-workout. Mesomorph first launched in 2013 and became famous for very strong energy, focus and pump; its formula has been changed several times since.\n\n"
        "Mesomorph is a high-stimulant product (caffeine and other stimulants, citrulline, beta-alanine), so it is meant for experienced users: count your daily caffeine, don't take it in the evening and start with half a scoop.\n\n"
        "Who it suits: experienced, stimulant-tolerant athletes who train very intensely. Not recommended for anyone sensitive to caffeine or with heart or blood-pressure problems.\n\n"
        "⭐ Quality score: 3.5/5 — strong effect, but a very high stimulant load.",
    ),
    "DY Nutrition": (
        "DY Nutrition — olti karra (1992–1997) Mister Olimpiya chempioni, bodibilding afsonasi Dorian Yeyts tomonidan 2011-yilda asos solingan brend. Brexit'dan keyin faoliyati Ruminiyaga ko'chirilgan; mahsulotlari 60 dan ortiq mamlakatda sotiladi.\n\n"
        "Eng mashhur mahsulotlari — Blood & Guts pre-workouti (Yeytsning shu nomdagi mashhur mashg'ulot uslubi sharafiga) va Game Changer geyneri. 2018-yilda FIBO ko'rgazmasida premium Shadow Line seriyasi taqdim etilgan. Assortimentga proteinlar, aminokislotalar va vitaminlar ham kiradi.\n\n"
        "Kimga mos: og'ir va intensiv mashg'ulotlar tarafdorlari, chempion tajribasiga tayangan mahsulotlarni qadrlaydiganlar.\n\n"
        "⭐ Sifat bahosi: 4/5 — chempion tajribasi va Yevropa ishlab chiqarishi.",
        "DY Nutrition основал в 2011 году легенда бодибилдинга, шестикратный (1992–1997) Mr. Olympia Дориан Ятс. После Brexit операционная деятельность переехала в Румынию; продукция продаётся более чем в 60 странах.\n\n"
        "Самые известные продукты — предтреник Blood & Guts (в честь знаменитого тренировочного стиля Ятса) и гейнер Game Changer. В 2018 году на выставке FIBO была представлена премиальная серия Shadow Line. В ассортименте также протеины, аминокислоты и витамины.\n\n"
        "Кому подойдёт: сторонникам тяжёлых интенсивных тренировок и тем, кто ценит продукты, созданные с опорой на опыт чемпиона.\n\n"
        "⭐ Оценка качества: 4/5 — опыт чемпиона и европейское производство.",
        "DY Nutrition was founded in 2011 by bodybuilding legend Dorian Yates, six-time Mr. Olympia (1992–1997). After Brexit its operations moved to Romania; its products are sold in more than 60 countries.\n\n"
        "Its best-known products are the Blood & Guts pre-workout (named after Yates's famous training style) and the Game Changer gainer. The premium Shadow Line was launched at FIBO 2018. The range also covers proteins, amino acids and vitamins.\n\n"
        "Who it suits: fans of heavy, intense training who value products built on a champion's experience.\n\n"
        "⭐ Quality score: 4/5 — a champion's know-how and European production.",
    ),
    "Fitness Authority": (
        "Fitness Authority (FA Nutrition) — 2004-yilda Polshada (Gdansk yaqinidagi Otomin) tashkil topgan kompaniya. U Polshadagi eng yirik sport ozuqasi importyorlari va ishlab chiqaruvchilaridan biri; uch yil ichida Yevropa Ittifoqi mamlakatlarida tanilgan brendga aylangan.\n\n"
        "Assortimentda proteinlar, geynerlar, kreatin, pre-workoutlar va vitaminlar bor; Xtreme seriyasi (masalan, Xtreme MVF) mashg'ulotdan keyingi tiklanish va asab-mushak faoliyatini qo'llab-quvvatlashga mo'ljallangan. Kompaniya sog'lom ovqatlanish mahsulotlari ham ishlab chiqaradi.\n\n"
        "Kimga mos: Yevropa ishlab chiqarishidagi keng assortimentni qulay narxda xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — 20 yillik tajriba va Yevropa Ittifoqi bozoridagi obro'.",
        "Fitness Authority (FA Nutrition) — компания, основанная в 2004 году в Польше (Отомин под Гданьском). Это один из крупнейших импортёров и производителей спортивного питания в Польше; менее чем за три года бренд стал известен в странах ЕС.\n\n"
        "В ассортименте протеины, гейнеры, креатин, предтреники и витамины; серия Xtreme (например, Xtreme MVF) рассчитана на восстановление после тренировок и поддержку нервно-мышечной функции. Компания выпускает и продукты здорового питания.\n\n"
        "Кому подойдёт: тем, кто хочет широкий ассортимент европейского производства по доступной цене.\n\n"
        "⭐ Оценка качества: 4/5 — 20 лет опыта и репутация на рынке ЕС.",
        "Fitness Authority (FA Nutrition) was founded in Poland (Otomin, near Gdańsk) in 2004. It is one of Poland's largest sports-nutrition importers and manufacturers and became a recognised brand across the EU within three years.\n\n"
        "The range covers proteins, gainers, creatine, pre-workouts and vitamins; the Xtreme series (such as Xtreme MVF) targets post-workout recovery and nerve and muscle function. The company also makes healthy-food products.\n\n"
        "Who it suits: anyone who wants a wide European-made range at an accessible price.\n\n"
        "⭐ Quality score: 4/5 — 20 years of experience and a solid EU reputation.",
    ),
    "Quamtrax": (
        "Quamtrax Nutrition — Ispaniya brendi, qariyb 20 yillik tajribaga ega va Pireney yarim orolida keng tanilgan. Formulalar ovqatlanish mutaxassislari bilan hamkorlikda ishlab chiqiladi; mahsulotlari Ispaniyadagi Decathlon do'konlarida ham sotiladi.\n\n"
        "Asosiy mahsulotlari — Whey Matrix va Whey Protein Isolate proteinlari, kreatin, BCAA va vitaminlar. Brend Yevropa sifatidagi asosiy sport ozuqasini qulay narxda taklif qiladi.\n\n"
        "Kimga mos: Yevropa ishlab chiqarishidagi oddiy va tushunarli mahsulotlarni xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — Yevropa standartlari va barqaror assortiment.",
        "Quamtrax Nutrition — испанский бренд с почти 20-летним опытом, хорошо известный на Пиренейском полуострове. Формулы разрабатываются вместе со специалистами по питанию; продукция продаётся и в магазинах Decathlon в Испании.\n\n"
        "Основные продукты — протеины Whey Matrix и Whey Protein Isolate, креатин, BCAA и витамины. Бренд предлагает базовое спортивное питание европейского качества по доступной цене.\n\n"
        "Кому подойдёт: тем, кто хочет простые и понятные продукты европейского производства.\n\n"
        "⭐ Оценка качества: 4/5 — европейские стандарты и стабильный ассортимент.",
        "Quamtrax Nutrition is a Spanish brand with almost 20 years of experience, well known across the Iberian Peninsula. Its formulas are developed with nutrition professionals, and it is also sold in Decathlon stores in Spain.\n\n"
        "Core products include Whey Matrix and Whey Protein Isolate, creatine, BCAAs and vitamins — European-quality basics at an accessible price.\n\n"
        "Who it suits: anyone who wants simple, straightforward European-made products.\n\n"
        "⭐ Quality score: 4/5 — European standards and a stable range.",
    ),
    "Hi-Tech Pharmaceuticals": (
        "Hi-Tech Pharmaceuticals — AQShning Jorjiya shtatidagi (Norkross) ishlab chiqaruvchi, yog' yoquvchilar va kuchli stimulyatorli «performance» mahsulotlari bilan tanilgan (masalan, Lipodrene seriyasi).\n\n"
        "Muhim: kompaniya va uning rahbariyati yillar davomida AQSh nazorat organlari (FTC, FDA) bilan sud jarayonlarini boshdan kechirgan. Shu sababli bu brend mahsulotlarini tanlashda tarkibni sinchkovlik bilan o'qing, stimulyatorlar dozasini hisobga oling va surunkali kasallik yoki dori qabul qilayotgan bo'lsangiz shifokor bilan maslahatlashing.\n\n"
        "Kimga mos: kuchli stimulyatorli formulalarga ko'nikkan tajribali foydalanuvchilar. Yangi boshlovchilar, kofeinga sezgir, yurak-qon tomir muammosi bor kishilar va doping nazoratidan o'tadigan sportchilarga tavsiya etilmaydi.\n\n"
        "⭐ Sifat bahosi: 3/5 — kuchli formulalar, ammo nazorat organlari bilan bog'liq tarix sabab ehtiyotkorlik talab qilinadi.",
        "Hi-Tech Pharmaceuticals — производитель из Норкросса (Джорджия, США), известный жиросжигателями и мощными стимуляторными «performance»-продуктами (например, серия Lipodrene).\n\n"
        "Важно: компания и её руководство на протяжении многих лет участвовали в судебных разбирательствах с американскими регуляторами (FTC, FDA). Поэтому при выборе продуктов этого бренда внимательно читайте состав, учитывайте дозировку стимуляторов и консультируйтесь с врачом, если у вас хронические заболевания или вы принимаете лекарства.\n\n"
        "Кому подойдёт: опытным пользователям, привыкшим к мощным стимуляторным формулам. Не рекомендуется новичкам, людям, чувствительным к кофеину, при проблемах с сердцем и спортсменам, проходящим допинг-контроль.\n\n"
        "⭐ Оценка качества: 3/5 — сильные формулы, но история с регуляторами требует осторожности.",
        "Hi-Tech Pharmaceuticals is a manufacturer from Norcross, Georgia (USA) known for fat burners and powerful stimulant-based performance products, such as the Lipodrene line.\n\n"
        "Important: the company and its management have been involved in legal proceedings with US regulators (FTC, FDA) for many years. When choosing its products, read the label carefully, count the stimulant dose and talk to a doctor if you have a chronic condition or take medication.\n\n"
        "Who it suits: experienced users accustomed to strong stimulant formulas. Not recommended for beginners, caffeine-sensitive people, anyone with heart problems or athletes subject to doping control.\n\n"
        "⭐ Quality score: 3/5 — potent formulas, but its regulatory history calls for caution.",
    ),
    "California Gold Nutrition": (
        "California Gold Nutrition — dunyoning eng yirik onlayn sog'liq do'konlaridan biri iHerb'ning shaxsiy brendi va uning eng ommabop ichki brendi. Uning asosiy afzalligi — «iTested» dasturi: mahsulotlar mustaqil laboratoriyalarda (ABC Testing, Eurofins, Alkemist) sinovdan o'tkaziladi.\n\n"
        "Sinovlar mikrobiologik tahlil va og'ir metallar tahlilini o'z ichiga oladi va har olti oyda takrorlanadi; ba'zi mahsulotlar uchun tahlil sertifikatlari (CoA) ochiq e'lon qilinadi. Assortiment: omega-3, D3 va C vitaminlari, kollagen, probiotiklar va Sport seriyasi.\n\n"
        "Kimga mos: kundalik sog'liq uchun sinovdan o'tgan, narxi maqbul vitamin va qo'shimchalar izlayotganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — muntazam mustaqil laboratoriya sinovlari.",
        "California Gold Nutrition — собственный бренд iHerb, одного из крупнейших онлайн-магазинов товаров для здоровья, и его самый популярный внутренний бренд. Главное преимущество — программа «iTested»: продукты проверяются в независимых лабораториях (ABC Testing, Eurofins, Alkemist).\n\n"
        "Тесты включают микробиологический анализ и анализ на тяжёлые металлы и повторяются каждые полгода; для некоторых продуктов сертификаты анализа (CoA) публикуются открыто. Ассортимент: омега-3, витамины D3 и C, коллаген, пробиотики и серия Sport.\n\n"
        "Кому подойдёт: тем, кто ищет проверенные витамины и добавки по разумной цене для ежедневного здоровья.\n\n"
        "⭐ Оценка качества: 4.5/5 — регулярные независимые лабораторные проверки.",
        "California Gold Nutrition is the house brand of iHerb, one of the world's largest online health stores, and its most popular in-house label. Its key strength is the iTested programme: products are checked by independent labs (ABC Testing, Eurofins, Alkemist).\n\n"
        "Testing covers microbial and heavy-metal analysis and is repeated every six months; certificates of analysis are published for some products. The range includes omega-3, vitamins D3 and C, collagen, probiotics and a Sport line.\n\n"
        "Who it suits: anyone looking for tested, fairly priced vitamins and supplements for everyday health.\n\n"
        "⭐ Quality score: 4.5/5 — regular independent lab testing.",
    ),
    "Nutrex Research": (
        "Nutrex Research 2002-yilda AQShning Florida shtatida (Oviedo) tashkil topgan. Asoschisi bungacha 1993-yildan Germaniyaning yetakchi sport ozuqasi kompaniyalaridan birini boshqargan va AQSh bozori uchun Jeff Makkarell bilan birga yangi kompaniya ochgan.\n\n"
        "Brend afsonasi Lipo-6 yog' yoquvchilar seriyasidan boshlangan; bugun Outlift va Hemo-Rage pre-workoutlari, kreatin va proteinlar ham mavjud. Lipo-6 seriyasining ko'p mahsulotlari kuchli stimulyatorli, shuning uchun dozani kamdan boshlash va kechqurun ichmaslik tavsiya etiladi.\n\n"
        "Kimga mos: quritish (yog' yoqish) bosqichidagi, stimulyatorlarga ko'nikkan foydalanuvchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — 20 yillik tajriba; stimulyatorli mahsulotlarda ehtiyotkorlik kerak.",
        "Nutrex Research основан в 2002 году во Флориде (Овьедо, США). Его основатель с 1993 года руководил одной из ведущих немецких компаний спортивного питания и для американского рынка создал новую компанию вместе с Джеффом Маккареллом.\n\n"
        "Легенда бренда началась с серии жиросжигателей Lipo-6; сегодня есть также предтреники Outlift и Hemo-Rage, креатин и протеины. Многие продукты Lipo-6 содержат сильные стимуляторы, поэтому начинайте с малой дозы и не принимайте их вечером.\n\n"
        "Кому подойдёт: тем, кто на сушке и привык к стимуляторам.\n\n"
        "⭐ Оценка качества: 4/5 — 20 лет опыта; со стимуляторными продуктами нужна осторожность.",
        "Nutrex Research was founded in Oviedo, Florida (USA) in 2002. Its founder had run one of Germany's leading sports-nutrition companies since 1993 and created a new company for the US market together with Jeff McCarrell.\n\n"
        "The brand's legend began with the Lipo-6 fat-burner line; today it also makes the Outlift and Hemo-Rage pre-workouts, creatine and proteins. Many Lipo-6 products are strongly stimulant-based, so start with a low dose and avoid taking them in the evening.\n\n"
        "Who it suits: stimulant-tolerant users in a cutting phase.\n\n"
        "⭐ Quality score: 4/5 — 20 years of experience; stimulant products call for caution.",
    ),
    "Solaray": (
        "Solaray 1973-yilda AQShning Yuta shtatida tashkil topgan va o'simliklar kombinatsiyalarini kapsulalagan ilk brendlardan biri bo'lgan. 1984-yildan to'liq vitamin va minerallar qatorini ham chiqara boshlagan.\n\n"
        "Bugun brend (Better Being Co. guruhi, avvalgi Nutraceutical) o'simlik ekstraktlari, vitaminlar, minerallar va probiotiklar bo'yicha keng assortimentga ega. Ko'plab minerallari yaxshi so'riladigan xelat (chelate) shaklda.\n\n"
        "Kimga mos: tabiiy o'simlik asosidagi qo'shimchalar va yaxshi so'riladigan minerallarni afzal ko'radiganlar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — 50 yildan ortiq tajriba.",
        "Solaray основан в 1973 году в штате Юта (США) и был одним из первых брендов, начавших выпускать комбинации трав в капсулах. С 1984 года выпускает и полную линейку витаминов и минералов.\n\n"
        "Сегодня бренд (группа Better Being Co., ранее Nutraceutical) предлагает широкий ассортимент растительных экстрактов, витаминов, минералов и пробиотиков. Многие минералы — в хорошо усваиваемой хелатной форме.\n\n"
        "Кому подойдёт: тем, кто предпочитает добавки на растительной основе и хорошо усваиваемые минералы.\n\n"
        "⭐ Оценка качества: 4.5/5 — более 50 лет опыта.",
        "Solaray was founded in Utah, USA in 1973 and was one of the first brands to put herbal combinations into capsules. Since 1984 it has also made a full line of vitamins and minerals.\n\n"
        "Today the brand (part of Better Being Co., formerly Nutraceutical) offers a wide range of herbal extracts, vitamins, minerals and probiotics, with many minerals in well-absorbed chelated forms.\n\n"
        "Who it suits: anyone who prefers plant-based supplements and well-absorbed minerals.\n\n"
        "⭐ Quality score: 4.5/5 — more than 50 years of experience.",
    ),
    "NOW Foods": (
        "NOW Foods — 1968-yilda fizik-kimyogar Elvud Richard tomonidan AQShning Illinoys shtatida asos solingan va hozir ham oila va xodimlarga tegishli kompaniya (bosh qarorgohi — Bloomingdeyl). Vitaminlar va tabiiy qo'shimchalar bozoridagi eng ishonchli nomlardan biri.\n\n"
        "Kompaniya ishlab chiqarishning har bir bosqichida qat'iy nazorat va keng qamrovli laboratoriya sinovlarini o'tkazadi. Assortimentda 1500 dan ortiq mahsulot: vitaminlar, minerallar, omega-3, aminokislotalar, sport ozuqasi (NOW Sports) va sog'lom oziq-ovqat.\n\n"
        "Kimga mos: kundalik sog'liq uchun sifatli va maqbul narxdagi vitamin va qo'shimchalarni izlayotgan har bir kishiga.\n\n"
        "⭐ Sifat bahosi: 5/5 — o'z laboratoriyalari va 55 yillik ishonch.",
        "NOW Foods основал в 1968 году физикохимик Элвуд Ричард в штате Иллинойс (США); компания до сих пор принадлежит семье и сотрудникам (штаб-квартира — Блумингдейл). Это одно из самых надёжных имён на рынке витаминов и натуральных добавок.\n\n"
        "Компания проводит строгий контроль и обширные лабораторные испытания на каждом этапе производства. В ассортименте более 1500 продуктов: витамины, минералы, омега-3, аминокислоты, спортивное питание (NOW Sports) и здоровые продукты.\n\n"
        "Кому подойдёт: всем, кто ищет качественные и доступные витамины и добавки для ежедневного здоровья.\n\n"
        "⭐ Оценка качества: 5/5 — собственные лаборатории и 55 лет доверия.",
        "NOW Foods was founded in Illinois, USA in 1968 by physical chemist Elwood Richard and is still family- and employee-owned (headquartered in Bloomingdale). It is one of the most trusted names in vitamins and natural supplements.\n\n"
        "The company applies strict controls and extensive lab testing at every stage of production. Its 1,500+ products include vitamins, minerals, omega-3, amino acids, sports nutrition (NOW Sports) and healthy foods.\n\n"
        "Who it suits: anyone looking for quality, affordable vitamins and supplements for everyday health.\n\n"
        "⭐ Quality score: 5/5 — in-house laboratories and 55 years of trust.",
    ),
    "Applied Nutrition": (
        "Applied Nutrition 2014-yilda Liverpulda (Buyuk Britaniya) Tom Rayder tomonidan kichik do'kondan boshlangan va 2024-yilda London fond birjasiga chiqqan. 2025-moliya yilida savdosi 24% o'sib, 107 mln funt sterlingga yetgan.\n\n"
        "Ishlab chiqarish GMP, ISO 22000 va BRC (eng yuqori «AA» darajasi) sertifikatlariga ega; ko'plab formulalari Informed Sport dasturida doping bo'yicha sinovdan o'tadi. Mashhur mahsulotlari — ABE (All Black Everything) pre-workouti, ISO-XP izolyati va Critical Mass geyneri.\n\n"
        "Kimga mos: zamonaviy formula va ta'mlarni qadrlaydigan, doping nazoratidan o'tadigan sportchilar va faol fitnes muxlislari.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — BRC AA va Informed Sport sinovlari.",
        "Applied Nutrition начался в 2014 году с небольшого магазина Тома Райдера в Ливерпуле (Великобритания), а в 2024 году вышел на Лондонскую фондовую биржу. В 2025 финансовом году продажи выросли на 24% — до £107 млн.\n\n"
        "Производство сертифицировано по GMP, ISO 22000 и BRC (высший уровень «AA»); многие формулы проходят антидопинговые тесты Informed Sport. Известные продукты — предтреник ABE (All Black Everything), изолят ISO-XP и гейнер Critical Mass.\n\n"
        "Кому подойдёт: тем, кто ценит современные формулы и вкусы, спортсменам, проходящим допинг-контроль, и активным любителям фитнеса.\n\n"
        "⭐ Оценка качества: 4.5/5 — BRC AA и тестирование Informed Sport.",
        "Applied Nutrition began in 2014 as Tom Ryder's small shop in Liverpool, UK, and listed on the London Stock Exchange in 2024. In the 2025 financial year its sales grew 24% to £107 million.\n\n"
        "Its manufacturing holds GMP, ISO 22000 and BRC (top 'AA' grade) certifications, and many formulas are tested under the Informed Sport anti-doping programme. Popular products include ABE (All Black Everything) pre-workout, ISO-XP isolate and Critical Mass gainer.\n\n"
        "Who it suits: people who like modern formulas and flavours, drug-tested athletes and active fitness fans.\n\n"
        "⭐ Quality score: 4.5/5 — BRC AA and Informed Sport testing.",
    ),
    "KAL": (
        "KAL — AQShdagi eng qadimgi vitamin brendlaridan biri: 1932-yilda Janubiy Kaliforniyada kalsiy-fosfor ichimligi «Kalcium» bilan boshlangan (brend nomi shundan). 1940-yillarda ilk multivitaminlardan biri — Multi-Four'ni chiqargan; bugun Yuta shtatida ishlab chiqariladi va 90 yildan ortiq tarixga ega.\n\n"
        "Assortimentda multivitaminlar, minerallar (magniy, kalsiy, rux), B guruhi vitaminlari, D3 vitamini va energiya uchun qo'shimchalar bor.\n\n"
        "Kimga mos: oddiy, vaqt sinovidan o'tgan vitamin va minerallarni maqbul narxda xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — 90 yillik tarix.",
        "KAL — один из старейших витаминных брендов США: он начался в 1932 году в Южной Калифорнии с кальциево-фосфорного напитка «Kalcium» (отсюда и название). В 1940-х выпустил один из первых мультивитаминов — Multi-Four; сегодня производится в штате Юта и имеет более чем 90-летнюю историю.\n\n"
        "В ассортименте мультивитамины, минералы (магний, кальций, цинк), витамины группы B, витамин D3 и добавки для энергии.\n\n"
        "Кому подойдёт: тем, кто хочет простые, проверенные временем витамины и минералы по разумной цене.\n\n"
        "⭐ Оценка качества: 4/5 — 90 лет истории.",
        "KAL is one of the oldest vitamin brands in the USA: it began in Southern California in 1932 with a calcium-phosphorus drink called “Kalcium” (hence the name). In the 1940s it launched one of the first multivitamins, Multi-Four; today it is made in Utah and has more than 90 years of history.\n\n"
        "The range includes multivitamins, minerals (magnesium, calcium, zinc), B vitamins, vitamin D3 and energy supplements.\n\n"
        "Who it suits: anyone who wants simple, time-tested vitamins and minerals at a fair price.\n\n"
        "⭐ Quality score: 4/5 — 90 years of history.",
    ),
    "Myprotein": (
        "Myprotein — Yevropaning eng yirik onlayn sport ozuqasi brendlaridan biri. Uni 2004-yilda Buyuk Britaniyada Oliver Kukson asos solgan; 2011-yilda THG (The Hut Group) tomonidan sotib olingan va bugun THG Nutrition'ning flagman brendi.\n\n"
        "Eng mashhur mahsuloti — Impact Whey Protein: o'nlab ta'mlar va maqbul narx. Assortiment juda keng: izolyatlar, vegan proteinlar, kreatin, vitaminlar, protein snaklari va sport kiyimlari.\n\n"
        "Kimga mos: ko'p ta'm va tanlovni yoqtiradiganlar, narx-sifat muvozanatini qadrlaydigan har bir kishi.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — yirik ishlab chiqarish va keng tanlov.",
        "Myprotein — один из крупнейших онлайн-брендов спортивного питания в Европе. Его основал Оливер Куксон в Великобритании в 2004 году; в 2011 году бренд купила THG (The Hut Group), и сегодня это флагман THG Nutrition.\n\n"
        "Самый известный продукт — Impact Whey Protein: десятки вкусов и доступная цена. Ассортимент очень широк: изоляты, веганские протеины, креатин, витамины, протеиновые снеки и спортивная одежда.\n\n"
        "Кому подойдёт: тем, кто любит много вкусов и выбора, и всем, кто ценит баланс цены и качества.\n\n"
        "⭐ Оценка качества: 4.5/5 — крупное производство и широкий выбор.",
        "Myprotein is one of Europe's largest online sports-nutrition brands. Oliver Cookson founded it in the UK in 2004; THG (The Hut Group) acquired it in 2011, and it is now the flagship of THG Nutrition.\n\n"
        "Its best-known product is Impact Whey Protein — dozens of flavours at an accessible price. The range is huge: isolates, vegan proteins, creatine, vitamins, protein snacks and sportswear.\n\n"
        "Who it suits: anyone who loves variety and values a good price-to-quality balance.\n\n"
        "⭐ Quality score: 4.5/5 — large-scale production and a wide choice.",
    ),
    "Kevin Levrone Signature Series": (
        "Kevin Levrone Signature Series — bodibilding afsonasi, Mister Olimpiyada to'rt marta ikkinchi o'rinni egallagan Kevin Levron nomidagi seriya. Seriya 2015-yilda e'lon qilingan va Polshada ishlab chiqariladi; FIBO kabi yirik xalqaro ko'rgazmalarda muntazam ishtirok etadi.\n\n"
        "Mashhur mahsulotlari — Levro Whey Supreme proteini, Anabolic Mass geyneri, LevroMono kreatini va Levro Legendary seriyasi. Brend chempion tajribasini Yevropa ishlab chiqarishi va qulay narx bilan birlashtiradi.\n\n"
        "Kimga mos: kuch va massa uchun shug'ullanuvchilar, klassik bodibilding ruhini sevuvchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — Yevropa ishlab chiqarishi va chempion nomi.",
        "Kevin Levrone Signature Series — линейка, названная в честь легенды бодибилдинга Кевина Леврона, четырежды занимавшего второе место на Mr. Olympia. Линия анонсирована в 2015 году и производится в Польше; бренд регулярно участвует в крупных выставках, таких как FIBO.\n\n"
        "Известные продукты — протеин Levro Whey Supreme, гейнер Anabolic Mass, креатин LevroMono и серия Levro Legendary. Бренд сочетает опыт чемпиона с европейским производством и доступной ценой.\n\n"
        "Кому подойдёт: тем, кто тренируется на силу и массу и любит дух классического бодибилдинга.\n\n"
        "⭐ Оценка качества: 4/5 — европейское производство и имя чемпиона.",
        "Kevin Levrone Signature Series is named after bodybuilding legend Kevin Levrone, four-time Mr. Olympia runner-up. The line was announced in 2015, is made in Poland and regularly appears at major trade fairs such as FIBO.\n\n"
        "Popular products include Levro Whey Supreme protein, Anabolic Mass gainer, LevroMono creatine and the Levro Legendary series. The brand combines a champion's name with European production and an accessible price.\n\n"
        "Who it suits: people training for strength and size who love the spirit of classic bodybuilding.\n\n"
        "⭐ Quality score: 4/5 — European production and a champion's name.",
    ),
    "Nutricost": (
        "Nutricost — AQShning Yuta shtatidagi brend, oddiy va «toza yorliqli» qo'shimchalari bilan tanilgan. Mahsulotlar GMP talablariga mos korxonada ishlab chiqariladi va mustaqil akkreditatsiyalangan laboratoriyada sinovdan o'tkaziladi.\n\n"
        "Assortimentda asosan bitta komponentli mahsulotlar: kreatin monogidrat, glutamin, beta-alanin, sitrullin, vitaminlar, minerallar, CoQ10 va omega-3. Brend ortiqcha qo'shimchalarsiz, aniq dozali formulalarni maqbul narxda taklif qiladi.\n\n"
        "Kimga mos: o'z «stack»ini o'zi yig'adigan, aniq dozalar va narx-sifat muvozanatini qadrlaydigan tajribali sportchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — mustaqil sinovlar va GMP ishlab chiqarish.",
        "Nutricost — бренд из штата Юта (США), известный простыми добавками с «чистой» этикеткой. Продукция производится на предприятии, соответствующем требованиям GMP, и проверяется в независимой аккредитованной лаборатории.\n\n"
        "В ассортименте в основном однокомпонентные продукты: креатин моногидрат, глютамин, бета-аланин, цитруллин, витамины, минералы, CoQ10 и омега-3. Бренд предлагает формулы с точной дозировкой без лишних добавок по разумной цене.\n\n"
        "Кому подойдёт: опытным спортсменам, которые сами собирают свой «стек» и ценят точные дозировки и выгодную цену.\n\n"
        "⭐ Оценка качества: 4/5 — независимые тесты и производство по GMP.",
        "Nutricost is a brand from Utah, USA known for simple, clean-label supplements. Its products are made in a GMP-compliant facility and tested by an independent accredited lab.\n\n"
        "The range is mostly single-ingredient: creatine monohydrate, glutamine, beta-alanine, citrulline, vitamins, minerals, CoQ10 and omega-3 — precisely dosed formulas without unnecessary extras at a fair price.\n\n"
        "Who it suits: experienced athletes who build their own stack and value exact doses and good value.\n\n"
        "⭐ Quality score: 4/5 — independent testing and GMP manufacturing.",
    ),
    "MuscleMeds": (
        "MuscleMeds — AQSh brendi, eng avvalo Carnivor bilan tanilgan: AQSh nazoratidan o'tgan mol go'shtidan gidroliz usulida olingan protein izolyati. U mol go'shti proteinini sport ozuqasi bozorida ommalashtirgan birinchi mahsulotlardan biri.\n\n"
        "Carnivor tarkibida sut, laktoza va shakar yo'q, unga kreatin monogidrat va BCAA qo'shilgan — sut mahsulotlarini ko'tara olmaydiganlar uchun ajoyib muqobil. Shuningdek, Carnivor Mass geyneri va Carnivor Shred kabi mahsulotlar mavjud.\n\n"
        "Kimga mos: laktozaga sezgir yoki sutsiz protein izlayotganlar, paleo ovqatlanish tarafdorlari.\n\n"
        "⭐ Sifat bahosi: 4/5 — mol go'shti proteini bo'yicha kashshof.",
        "MuscleMeds — американский бренд, прежде всего известный продуктом Carnivor: изолятом белка, полученным методом гидролиза из говядины, прошедшей проверку USDA. Это один из первых продуктов, сделавших говяжий протеин популярным в спортивном питании.\n\n"
        "Carnivor не содержит молока, лактозы и сахара, в него добавлены креатин моногидрат и BCAA — отличная альтернатива для тех, кто не переносит молочное. Также есть гейнер Carnivor Mass и Carnivor Shred.\n\n"
        "Кому подойдёт: тем, кто чувствителен к лактозе или ищет протеин без молочного, сторонникам палео-питания.\n\n"
        "⭐ Оценка качества: 4/5 — пионер говяжьего протеина.",
        "MuscleMeds is a US brand known above all for Carnivor, a protein isolate made by hydrolysing USDA-inspected beef — one of the first products to make beef protein popular in sports nutrition.\n\n"
        "Carnivor contains no dairy, lactose or sugar and includes creatine monohydrate and BCAAs, making it a great alternative for anyone who can't tolerate milk. Carnivor Mass gainer and Carnivor Shred complete the range.\n\n"
        "Who it suits: people who are lactose-sensitive or want dairy-free protein, and paleo eaters.\n\n"
        "⭐ Quality score: 4/5 — a pioneer of beef protein.",
    ),
    "CON-CRET": (
        "CON-CRET — patentlangan kreatin gidroxlorid (kreatin HCl). Bu molekulani 2003-yilda AQShning Vireo Systems kompaniyasi (asoschisi Mark Folkner) Nebraska universiteti olimlari bilan birga sintez qilgan; 2007-yildan Promera Sports orqali sotiladi, birinchi AQSh patenti 2009-yilda olingan.\n\n"
        "Kreatin HCl suvda juda yaxshi eriydi va kichik dozalarda ishlaydi: «zagruzka» bosqichi kerak emas, ko'pchilik oshqozon noqulayligi va suv ushlanishini sezmaydi. CON-CRET kukun, kapsula va chaynaladigan shakllarda chiqadi.\n\n"
        "Kimga mos: oddiy kreatin monogidratdan oshqozon noqulayligi yoki «shishish»ni sezganlar, kichik va qulay doza xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — patentlangan va tadqiqotlarga asoslangan ingredient.",
        "CON-CRET — запатентованный гидрохлорид креатина (креатин HCl). Эту молекулу синтезировала в 2003 году американская компания Vireo Systems (основатель Марк Фолкнер) вместе с учёными Университета Небраски; с 2007 года продукт продаётся через Promera Sports, первый патент США получен в 2009 году.\n\n"
        "Креатин HCl очень хорошо растворяется в воде и работает в малых дозах: «загрузка» не нужна, и большинство не ощущает дискомфорта в желудке и задержки воды. CON-CRET выпускается в виде порошка, капсул и жевательных таблеток.\n\n"
        "Кому подойдёт: тем, у кого обычный креатин моногидрат вызывает дискомфорт или «отёчность», и тем, кто хочет маленькую удобную дозу.\n\n"
        "⭐ Оценка качества: 4.5/5 — запатентованный ингредиент с научной базой.",
        "CON-CRET is patented creatine hydrochloride (creatine HCl). The molecule was synthesised in 2003 by US company Vireo Systems (founded by Mark Faulkner) together with University of Nebraska scientists; it has been sold through Promera Sports since 2007 and received its first US patent in 2009.\n\n"
        "Creatine HCl dissolves very well in water and works in small doses: no loading phase is needed, and most people don't experience stomach discomfort or water retention. CON-CRET comes as powder, capsules and chewables.\n\n"
        "Who it suits: anyone who gets stomach discomfort or bloating from regular creatine monohydrate, and people who want a small, convenient dose.\n\n"
        "⭐ Quality score: 4.5/5 — a patented, research-backed ingredient.",
    ),
    "USPLabs": (
        "USPLabs — AQShning Dallas (Texas) shahridagi kompaniya. Bugun brend asosan Modern BCAA+ bilan tanilgan: stimulyatorsiz, mazali aminokislota ichimligi, mashg'ulot davomida mushaklarni himoya qilish va suv balansini saqlash uchun.\n\n"
        "Muhim kontekst: brendning oldingi stimulyatorli mahsulotlari (Jack3d, OxyElite) 2012–2015-yillarda AQSh FDA va prokuraturasining jiddiy nazoratiga tushgan. Shu sababli NutriZone bu brend bo'yicha faqat stimulyatorsiz aminokislota mahsulotlarini tavsiya qiladi va tarkibni har doim yorliqdan tekshirishni maslahat beradi.\n\n"
        "Kimga mos: mashg'ulot davomida ichiladigan mazali BCAA izlayotganlar.\n\n"
        "⭐ Sifat bahosi: 3/5 — mashhur BCAA, ammo kompaniya tarixi ehtiyotkorlikni talab qiladi.",
        "USPLabs — компания из Далласа (Техас, США). Сегодня бренд известен в основном продуктом Modern BCAA+: вкусным напитком из аминокислот без стимуляторов для защиты мышц и водного баланса во время тренировки.\n\n"
        "Важный контекст: прежние стимуляторные продукты бренда (Jack3d, OxyElite) в 2012–2015 годах оказались под серьёзным контролем FDA и прокуратуры США. Поэтому NutriZone рекомендует по этому бренду только аминокислотные продукты без стимуляторов и советует всегда проверять состав на этикетке.\n\n"
        "Кому подойдёт: тем, кто ищет вкусные BCAA для приёма во время тренировки.\n\n"
        "⭐ Оценка качества: 3/5 — популярные BCAA, но история компании требует осторожности.",
        "USPLabs is a company from Dallas, Texas (USA). Today it is mainly known for Modern BCAA+, a tasty stimulant-free amino-acid drink for protecting muscle and keeping hydrated during training.\n\n"
        "Important context: the brand's earlier stimulant products (Jack3d, OxyElite) came under serious scrutiny from the US FDA and federal prosecutors in 2012–2015. NutriZone therefore recommends only its stimulant-free amino-acid products and advises always checking the label.\n\n"
        "Who it suits: anyone looking for a tasty intra-workout BCAA.\n\n"
        "⭐ Quality score: 3/5 — a popular BCAA, but the company's history calls for caution.",
    ),
    "GAT Sport": (
        "GAT Sport (avvalgi nomi — German American Technologies) 1990-yillar oxirida AQShda tashkil topgan va nemischa aniqlikni amerikacha innovatsiya bilan uyg'unlashtirish g'oyasiga asoslangan brend.\n\n"
        "Eng mashhur mahsuloti — Nitraflex pre-workouti: energiya, «pump» va kuch uchun. 2024-yilda chiqarilgan Nitraflex SPORT versiyasi Informed Sport sertifikatini olgan — har bir partiya sportda taqiqlangan moddalar bo'yicha sinovdan o'tkaziladi. Brendning proteinlari, aminokislotalari va JetMass kabi kreatin mahsulotlari ham bor.\n\n"
        "Kimga mos: kuchli pre-workout izlayotganlar; doping nazoratidan o'tadigan sportchilar uchun — SPORT versiyasi.\n\n"
        "⭐ Sifat bahosi: 4.5/5 — Informed Sport sertifikati (SPORT seriyasi).",
        "GAT Sport (ранее German American Technologies) основан в конце 1990-х в США; идея бренда — соединить немецкую точность с американскими инновациями.\n\n"
        "Самый известный продукт — предтреник Nitraflex для энергии, пампа и силы. Версия Nitraflex SPORT, выпущенная в 2024 году, получила сертификат Informed Sport: каждая партия проверяется на вещества, запрещённые в спорте. Также в линейке протеины, аминокислоты и креатиновые продукты, например JetMass.\n\n"
        "Кому подойдёт: тем, кто ищет мощный предтреник; спортсменам, проходящим допинг-контроль, — версия SPORT.\n\n"
        "⭐ Оценка качества: 4.5/5 — сертификат Informed Sport (серия SPORT).",
        "GAT Sport (formerly German American Technologies) was founded in the USA in the late 1990s around the idea of combining German precision with American innovation.\n\n"
        "Its best-known product is the Nitraflex pre-workout for energy, pump and strength. Nitraflex SPORT, launched in 2024, is Informed Sport certified — every batch is tested for substances banned in sport. The range also includes proteins, amino acids and creatine products such as JetMass.\n\n"
        "Who it suits: anyone after a strong pre-workout; for drug-tested athletes, the SPORT version.\n\n"
        "⭐ Quality score: 4.5/5 — Informed Sport certification (SPORT line).",
    ),
    "Solgar": (
        "Solgar 1947-yilda Nyu-Yorkning Manxetten tumanida kichik laboratoriyada tashkil topgan; birinchi mahsuloti — Naturvite multivitamini. 2021-yildan Nestlé Health Science tarkibida.\n\n"
        "Brendning «Gold Standard» sifat standarti va quyoshdan himoya qiluvchi qahrabo rangli shisha flakonlari mashhur. Assortimentda yuzlab vitaminlar, minerallar, omega-3, aminokislotalar va o'simlik ekstraktlari bor; ko'pchiligi kosher va vegetarianlar uchun mos.\n\n"
        "Kimga mos: premium sifatdagi vitamin va minerallarni xohlovchilar, uzoq muddatli sog'liq dasturini tuzayotganlar.\n\n"
        "⭐ Sifat bahosi: 5/5 — 75 yildan ortiq tarix va «Gold Standard».",
        "Solgar основан в 1947 году в небольшой лаборатории на Манхэттене (Нью-Йорк); первым продуктом стал мультивитамин Naturvite. С 2021 года бренд входит в Nestlé Health Science.\n\n"
        "Бренд знаменит стандартом качества «Gold Standard» и янтарными стеклянными флаконами, защищающими от света. В ассортименте сотни витаминов, минералов, омега-3, аминокислот и растительных экстрактов; многие подходят для кошерного и вегетарианского питания.\n\n"
        "Кому подойдёт: тем, кто хочет витамины и минералы премиального качества и составляет долгосрочную программу для здоровья.\n\n"
        "⭐ Оценка качества: 5/5 — более 75 лет истории и «Gold Standard».",
        "Solgar was founded in 1947 in a small lab in Manhattan, New York; its first product was the Naturvite multivitamin. Since 2021 it has been part of Nestlé Health Science.\n\n"
        "The brand is famous for its 'Gold Standard' of quality and its light-protecting amber glass bottles. It offers hundreds of vitamins, minerals, omega-3s, amino acids and herbal extracts, many of them suitable for kosher and vegetarian diets.\n\n"
        "Who it suits: anyone who wants premium-quality vitamins and minerals and is building a long-term health routine.\n\n"
        "⭐ Quality score: 5/5 — more than 75 years of history and its 'Gold Standard'.",
    ),
    "Nutriversum": (
        "Nutriversum — Vengriyaning Budapesht shahridagi brend (Nutriversum Kft.). 2025-yildagi ilmiy tadqiqotda BioTechUSA, Scitec Nutrition va Myprotein bilan bir qatorda Vengriya bozoridagi to'rtta yetakchi brenddan biri sifatida qayd etilgan.\n\n"
        "Assortimentda vitamin to'plamlari (Multi Pack), pre-workoutlar, proteinlar, kollagen mahsulotlari, minerallar va hatto protein tortilyalar bor. Brend zamonaviy qadoq va kundalik qulay formatlari bilan ajralib turadi.\n\n"
        "Kimga mos: sport va sog'liqni bir tizimda yuritmoqchi bo'lganlar, qulay kunlik vitamin paketlarini xohlovchilar.\n\n"
        "⭐ Sifat bahosi: 4/5 — Yevropa Ittifoqi standartlari.",
        "Nutriversum — бренд из Будапешта (Nutriversum Kft., Венгрия). В научном исследовании 2025 года он назван одним из четырёх ведущих брендов венгерского рынка наряду с BioTechUSA, Scitec Nutrition и Myprotein.\n\n"
        "В ассортименте витаминные наборы (Multi Pack), предтреники, протеины, продукты с коллагеном, минералы и даже протеиновые тортильи. Бренд выделяется современной упаковкой и удобными ежедневными форматами.\n\n"
        "Кому подойдёт: тем, кто хочет вести спорт и здоровье в одной системе и ищет удобные ежедневные витаминные пакеты.\n\n"
        "⭐ Оценка качества: 4/5 — стандарты Евросоюза.",
        "Nutriversum is a brand from Budapest, Hungary (Nutriversum Kft.). A 2025 academic study named it one of the four leading brands on the Hungarian market alongside BioTechUSA, Scitec Nutrition and Myprotein.\n\n"
        "Its range includes vitamin packs (Multi Pack), pre-workouts, proteins, collagen products, minerals and even protein tortillas, and it stands out for modern packaging and handy daily formats.\n\n"
        "Who it suits: anyone who wants to manage training and health in one system and likes convenient daily vitamin packs.\n\n"
        "⭐ Quality score: 4/5 — EU standards.",
    ),
    "Carlson Labs": (
        "Carlson Labs — 1965-yilda Jon va Syuzan Karlsonlar tomonidan AQShning Illinoys shtatida asos solingan oilaviy kompaniya; birinchi mahsuloti — E vitamini. 1982-yilda Norvegiya treska jigari yog'i va baliq yog'ini AQShga olib kirib, bu bozorda kashshof bo'lgan.\n\n"
        "Omega-3 mahsulotlari (The Very Finest Fish Oil, Maximum Omega, Cod Liver Oil) xalqaro IFOS standarti bo'yicha yangilik, quvvat va tozalik sinovlaridan o'tadi va ConsumerLab'ning «#1 Rated Omega-3» mukofotini uch marta olgan. Shuningdek D3, K2, E vitaminlari va multivitaminlar ishlab chiqariladi.\n\n"
        "Kimga mos: eng toza va yangi omega-3 izlayotganlar, yurak, miya va bo'g'imlar salomatligiga e'tibor beruvchilar, oilalar va bolalar (suyuq shakllari bor).\n\n"
        "⭐ Sifat bahosi: 5/5 — IFOS sertifikati va mustaqil mukofotlar.",
        "Carlson Labs — семейная компания, основанная Джоном и Сьюзан Карлсон в 1965 году в штате Иллинойс (США); первым продуктом был витамин E. В 1982 году компания одной из первых привезла в США норвежский жир печени трески и рыбий жир.\n\n"
        "Омега-3 (The Very Finest Fish Oil, Maximum Omega, Cod Liver Oil) проходят проверку свежести, концентрации и чистоты по международному стандарту IFOS и трижды получали награду ConsumerLab «#1 Rated Omega-3». Также выпускаются витамины D3, K2, E и мультивитамины.\n\n"
        "Кому подойдёт: тем, кто ищет максимально чистые и свежие омега-3, следит за здоровьем сердца, мозга и суставов, семьям и детям (есть жидкие формы).\n\n"
        "⭐ Оценка качества: 5/5 — сертификат IFOS и независимые награды.",
        "Carlson Labs is a family company founded by John and Susan Carlson in Illinois, USA in 1965; its first product was vitamin E. In 1982 it pioneered Norwegian cod liver oil and fish oil in the US market.\n\n"
        "Its omega-3s (The Very Finest Fish Oil, Maximum Omega, Cod Liver Oil) are tested for freshness, potency and purity under the international IFOS standard and have won ConsumerLab's '#1 Rated Omega-3' award three times. It also makes vitamins D3, K2 and E and multivitamins.\n\n"
        "Who it suits: anyone looking for the purest, freshest omega-3, people caring for heart, brain and joint health, and families and children (liquid forms are available).\n\n"
        "⭐ Quality score: 5/5 — IFOS certification and independent awards.",
    ),
}
