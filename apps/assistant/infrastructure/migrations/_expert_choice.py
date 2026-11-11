"""
Expert knowledge, part 6: choosing well -- lactose intolerance vs milk allergy, dairy-free protein, beef and egg protein,
picking protein for a budget, what brand quality really means, the "price of 25 g protein" maths, creatine forms,
gainer vs protein, whey blend vs isolate. Data for migration 0013 (owner request 2026-11-11: a consultant that knows
the difference between products, compares them and explains).
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("product", 80, "Laktoza ko'tarmaslik va protein",
     "laktoza ko'tarmayman qaysi protein ichsam bo'ladi\nsut ichsam qornim shishadi protein ichsam bo'ladimi\nsut mahsulotlari yoqmaydi qaysi protein\nне переношу лактозу какой протеин\nот молока вздутие можно протеин\nlactose intolerant which protein",
     "laktoza, laktozasiz, sut, sutli, qorin, shishadi, hazm, лактоза, лактозы, безлактозный, вздутие, молоко, lactose, intolerance, intolerant, bloating, dairy",
     "🥛 **Laktoza ko'tarmaslik — protein ichishga to'siq emas.** Qorin shishishi, og'irlik, ich ketishi odatda **laktoza** (sut shakari)ni parchalaydigan ferment yetishmasligidan bo'ladi.\n\n"
     "**Proteinlardagi laktoza (1 porsiyada, taxminan):**\n"
     "• Whey konsentrat — 1–3 g → sezgir odamga noqulay bo'lishi mumkin.\n"
     "• **Whey izolyat — 0,5–1 g dan kam** → ko'pchilik bemalol ko'taradi ✅\n"
     "• **Gidrolizat** — oqsil oldindan parchalangan, eng yengil hazm bo'ladi ✅\n"
     "• Kazein — laktoza kam, lekin og'ir va sekin hazm bo'ladi.\n"
     "• Vegan va mol go'shti proteini — laktoza umuman yo'q ✅\n\n"
     "💡 **Qanday ichish:** suv bilan aralashtiring (sut bilan emas), ½ qoshiqdan boshlang, 1 haftada to'liq porsiyaga o'ting. Tarkibida \"lactase\" fermenti bor proteinlar ham yengilroq.\n\n"
     "⚠️ Toshma, qichishish, lab shishishi, nafas qisishi — bu **allergiya**, laktoza emas: unda har qanday whey mumkin emas.",
     "🥛 **Непереносимость лактозы — не повод отказываться от протеина.** Вздутие, тяжесть, расстройство обычно из-за нехватки фермента, расщепляющего **лактозу** (молочный сахар).\n\n"
     "**Лактоза в протеинах (на порцию, примерно):**\n"
     "• Сывороточный концентрат — 1–3 г → у чувствительных может вызывать дискомфорт.\n"
     "• **Изолят — меньше 0,5–1 г** → большинство переносит спокойно ✅\n"
     "• **Гидролизат** — белок уже расщеплён, усваивается легче всего ✅\n"
     "• Казеин — лактозы мало, но он тяжёлый и медленный.\n"
     "• Веганский и говяжий протеин — лактозы нет совсем ✅\n\n"
     "💡 **Как пить:** с водой (не с молоком), начните с ½ ложки и за неделю дойдите до полной порции. Протеины с ферментом «lactase» тоже легче.\n\n"
     "⚠️ Сыпь, зуд, отёк губ, одышка — это **аллергия**, а не лактоза: тогда любой whey нельзя.",
     "🥛 **Lactose intolerance doesn't rule out protein.** Bloating, heaviness or an upset stomach usually come from lacking the enzyme that breaks down **lactose** (milk sugar).\n\n"
     "**Lactose in protein (per serving, roughly):**\n"
     "• Whey concentrate — 1–3 g → may bother sensitive people.\n"
     "• **Whey isolate — under 0.5–1 g** → most people tolerate it well ✅\n"
     "• **Hydrolysate** — protein pre-broken down, the easiest to digest ✅\n"
     "• Casein — little lactose, but heavy and slow.\n"
     "• Vegan and beef protein — no lactose at all ✅\n\n"
     "💡 **How to take it:** mix with water (not milk), start with half a scoop and build up over a week. Proteins with added lactase are easier too.\n\n"
     "⚠️ Rash, itching, swollen lips or shortness of breath mean an **allergy**, not lactose: then no whey at all."),
    ("product", 80, "Sut oqsiliga allergiya va laktoza farqi",
     "sutga allergiyam bor protein ichsam bo'ladimi\nkazeinga allergiya\nallergiya va laktoza farqi\nаллергия на молоко можно протеин\nаллергия на белок коровьего молока\nmilk allergy protein",
     "allergiya, allergiyam, toshma, qichishish, sut, kazein, аллергия, сыпь, белок коровьего молока, allergy, allergic, milk protein",
     "⚠️ **Allergiya va laktoza — boshqa-boshqa narsa.**\n\n"
     "• **Laktoza ko'tarmaslik** — sut *shakari*ni hazm qila olmaslik. Belgilari: qorin shishishi, gaz, ich ketishi. Izolyat yoki gidrolizat odatda mos.\n"
     "• **Sut oqsiliga allergiya** — immunitet sut *oqsillari* (kazein, zardob)ga reaksiya beradi. Belgilari: toshma, qichishish, shish, nafas qisishi. Bu holda **konsentrat, izolyat, gidrolizat, kazein — hammasi mumkin emas**, chunki ularning o'zi sut oqsili.\n\n"
     "✅ **Allergiyada mos:** vegan protein (no'xat + guruch aralashmasi), mol go'shti proteini, tuxum oqi proteini; kreatin, BCAA/EAA, vitaminlar — sutsiz.\n\n"
     "📋 Yorliqda \"Contains: Milk\" yoki \"May contain milk\" (bir zavodda ishlab chiqarilgan) yozuviga qarang. Kuchli allergiyada shifokor bilan maslahatlashing.",
     "⚠️ **Аллергия и лактоза — разные вещи.**\n\n"
     "• **Непереносимость лактозы** — организм плохо переваривает молочный *сахар*. Признаки: вздутие, газы, расстройство. Обычно подходят изолят или гидролизат.\n"
     "• **Аллергия на белок молока** — иммунитет реагирует на сами молочные *белки* (казеин, сыворотку). Признаки: сыпь, зуд, отёк, одышка. Тогда **концентрат, изолят, гидролизат, казеин — нельзя все**, ведь это и есть молочный белок.\n\n"
     "✅ **При аллергии подойдут:** веганский протеин (горох + рис), говяжий протеин, яичный протеин; креатин, BCAA/EAA, витамины — без молока.\n\n"
     "📋 Смотрите на этикетке «Contains: Milk» или «May contain milk» (общее производство). При сильной аллергии посоветуйтесь с врачом.",
     "⚠️ **An allergy and lactose intolerance are different things.**\n\n"
     "• **Lactose intolerance** — the body struggles to digest milk *sugar*. Signs: bloating, gas, an upset stomach. Isolate or hydrolysate usually suit.\n"
     "• **Milk-protein allergy** — the immune system reacts to the milk *proteins* themselves (casein, whey). Signs: rash, itching, swelling, shortness of breath. Then **concentrate, isolate, hydrolysate and casein are all out** — they are milk protein.\n\n"
     "✅ **With an allergy:** vegan protein (pea + rice), beef protein, egg-white protein; creatine, BCAA/EAA and vitamins are dairy-free.\n\n"
     "📋 Check the label for \"Contains: Milk\" or \"May contain milk\" (shared facilities). With a strong allergy, talk to a doctor."),
    ("product", 70, "Sutsiz protein manbalari: vegan, mol go'shti, tuxum",
     "sutsiz protein bormi\nvegan protein yaxshimi\nmol go'shti proteini nima\ntuxum proteini\nбезмолочный протеин\nговяжий протеин что это\nвеганский протеин хуже\ndairy free protein\nbeef protein vs whey",
     "sutsiz, vegan, o'simlik, no'xat, guruch, soya, mol go'shti, beef, tuxum, egg, безмолочный, веганский, растительный, говяжий, яичный, dairy-free, plant, pea, rice",
     "🌱 **Sutsiz protein turlari:**\n\n"
     "• **Vegan (o'simlik) protein** — no'xat, guruch, soya, kanop. Bitta manba aminokislotalarda \"teshik\" qoldiradi, shuning uchun **aralashma (no'xat + guruch)** tanlang — tarkibi whey'ga yaqinlashadi. Porsiyada 20–25 g oqsil, ta'mi biroz \"tuproqroq\", quyuqroq.\n"
     "• **Mol go'shti proteini (beef isolate)** — sutsiz, laktozasiz, tabiiy kreatin va kollagenga boy; ta'mi mevali/sharbatga o'xshash bo'ladi. Leysin whey'dan biroz kam.\n"
     "• **Tuxum oqi proteini** — sifati yuqori (to'liq aminokislotalar), sekin-o'rtacha hazm bo'ladi; tuxumga allergiya bo'lsa mumkin emas.\n\n"
     "📊 Natija uchun eng muhimi — kunlik umumiy oqsil (1,6–2,2 g/kg). To'g'ri aralashma va yetarli doza bilan vegan yoki beef protein ham whey kabi ishlaydi.",
     "🌱 **Протеин без молока:**\n\n"
     "• **Веганский (растительный)** — горох, рис, соя, конопля. Один источник даёт «провалы» по аминокислотам, поэтому берите **смесь (горох + рис)** — профиль приближается к whey. 20–25 г белка в порции, вкус более «землистый», гуще.\n"
     "• **Говяжий протеин (beef isolate)** — без молока и лактозы, богат природным креатином и коллагеном; вкусы обычно фруктовые, как сок. Лейцина чуть меньше, чем в whey.\n"
     "• **Яичный (белок яйца)** — высокое качество (полный аминокислотный профиль), усваивается средне; при аллергии на яйцо нельзя.\n\n"
     "📊 Для результата главное — общий белок за день (1,6–2,2 г/кг). С правильной смесью и достаточной дозой веганский или говяжий протеин работает как whey.",
     "🌱 **Dairy-free protein:**\n\n"
     "• **Vegan (plant) protein** — pea, rice, soy, hemp. One source leaves amino-acid \"gaps\", so pick a **blend (pea + rice)** — its profile gets close to whey. 20–25 g protein a serving, a more earthy taste, thicker.\n"
     "• **Beef protein (beef isolate)** — no dairy, no lactose, naturally rich in creatine and collagen; flavours are usually fruity, juice-like. Slightly less leucine than whey.\n"
     "• **Egg-white protein** — high quality (complete aminos), medium digestion; not for an egg allergy.\n\n"
     "📊 What drives results is total daily protein (1.6–2.2 g/kg). With the right blend and dose, vegan or beef protein works like whey."),
    ("product", 75, "Byudjetga qarab protein tanlash",
     "500 minggacha qaysi protein yaxshi\narzon va sifatli protein\nbyudjetim kam qaysi proteinni olay\nпротеин до 500 тысяч какой лучше\nнедорогой но хороший протеин\nbest protein on a budget",
     "byudjet, arzon, hamyonbop, sifatli, narx, minggacha, бюджет, недорогой, дешевый, до, тысяч, budget, cheap, affordable, value",
     "💰 **Byudjetga qarab protein tanlash — 4 qadam:**\n\n"
     "1️⃣ **Turini aniqlang:** oddiy maqsad — whey konsentrat yoki blend (eng tejamkor); qorin sezgir yoki ozish — izolyat; sut mumkin emas — vegan/beef.\n"
     "2️⃣ **Banka narxiga emas, 25 g oqsil narxiga qarang:** narx ÷ porsiyalar soni ÷ porsiyadagi oqsil × 25. Katta banka (2–2,3 kg) deyarli doim arzonroq tushadi.\n"
     "3️⃣ **Brend:** taniqli, laboratoriyada tekshiriladigan brendlar (Optimum Nutrition, Dymatize, Myprotein, Rule 1, BSN, MuscleTech va h.k.) — tarkib yorliqqa mos bo'lishi ehtimoli yuqori. NutriZone'dagi hamma mahsulot original.\n"
     "4️⃣ **Ta'm va aralashuvchanlik** — har kuni ichasiz, yoqadigan ta'mni tanlang.\n\n"
     "✍️ Menga \"*500 minggacha protein*\" deb yozing — ombordagi variantlarni shu hisob bilan solishtirib, eng yaxshisini tanlab beraman.",
     "💰 **Как выбрать протеин под бюджет — 4 шага:**\n\n"
     "1️⃣ **Определите вид:** обычная цель — сывороточный концентрат или бленд (выгоднее всего); чувствительный желудок или сушка — изолят; молочное нельзя — веганский/говяжий.\n"
     "2️⃣ **Смотрите не на цену банки, а на цену 25 г белка:** цена ÷ число порций ÷ белок в порции × 25. Большая банка (2–2,3 кг) почти всегда выходит дешевле.\n"
     "3️⃣ **Бренд:** известные бренды, проверяемые лабораториями (Optimum Nutrition, Dymatize, Myprotein, Rule 1, BSN, MuscleTech и др.), чаще соответствуют этикетке. Всё в NutriZone — оригинал.\n"
     "4️⃣ **Вкус и растворимость** — пьёте каждый день, берите вкус, который нравится.\n\n"
     "✍️ Напишите «*протеин до 500 тысяч*» — сравню варианты в наличии по этой формуле и выберу лучший.",
     "💰 **Choosing protein on a budget — 4 steps:**\n\n"
     "1️⃣ **Pick the type:** a general goal — whey concentrate or a blend (best value); sensitive stomach or cutting — isolate; no dairy — vegan/beef.\n"
     "2️⃣ **Look at the price of 25 g of protein, not the tub:** price ÷ servings ÷ protein per serving × 25. A big tub (2–2.3 kg) is almost always cheaper per gram.\n"
     "3️⃣ **Brand:** well-known, lab-tested brands (Optimum Nutrition, Dymatize, Myprotein, Rule 1, BSN, MuscleTech, etc.) are more likely to match the label. Everything at NutriZone is genuine.\n"
     "4️⃣ **Taste and mixability** — you drink it every day, so pick a flavour you like.\n\n"
     "✍️ Write \"*protein up to 500k*\" and I'll compare what's in stock with this maths and pick the best."),
    ("product", 70, "Brend sifati: nimaga qarash kerak",
     "qaysi brend yaxshi\nbrendlar farqi bormi\nqimmat brend arziydimi\nкакой бренд протеина лучше\nесть ли разница между брендами\nis an expensive brand worth it",
     "brend, brendlar, sifat, sifatli, ishonchli, qimmat, бренд, бренды, качество, надежный, дорогой, brand, brands, quality, trusted, worth",
     "🏷 **Brendlar orasidagi haqiqiy farq — 5 narsada:**\n\n"
     "1. **Yorliqqa moslik** — porsiyadagi oqsil yorliqdagidek bo'lishi. Yirik brendlar (Optimum Nutrition, Dymatize, Myprotein, Rule 1, BSN, Isopure, Applied Nutrition) mustaqil laboratoriyalarda ko'p tekshiriladi.\n"
     "2. **\"Amino spiking\" yo'qligi** — arzon formulalar glitsin, taurin qo'shib oqsilni sun'iy oshirishi mumkin; tarkibda faqat oqsil manbalari bo'lsin.\n"
     "3. **Xom ashyo** — izolyat/gidrolizat ulushi, Creapure (kreatin) kabi patentlangan xom ashyo.\n"
     "4. **Ta'm va aralashuvchanlik** — har kuni ichiladi, bu ham sifat.\n"
     "5. **Sertifikatlar** — Informed Sport, NSF Certified for Sport, GMP.\n\n"
     "💡 Qimmat brend har doim \"ko'proq natija\" degani emas: bir xil turdagi (masalan, konsentrat) proteinlarda natija deyarli bir xil, farq — ishonchlilik va ta'mda. Shuning uchun **25 g oqsil narxi + brend ishonchliligi** birga hisoblanadi.",
     "🏷 **Настоящая разница между брендами — в 5 вещах:**\n\n"
     "1. **Соответствие этикетке** — белка в порции столько, сколько написано. Крупные бренды (Optimum Nutrition, Dymatize, Myprotein, Rule 1, BSN, Isopure, Applied Nutrition) часто проверяются независимыми лабораториями.\n"
     "2. **Нет «amino spiking»** — дешёвые формулы могут добавлять глицин, таурин, искусственно завышая белок; в составе должны быть только источники белка.\n"
     "3. **Сырьё** — доля изолята/гидролизата, патентованное сырьё вроде Creapure (креатин).\n"
     "4. **Вкус и растворимость** — пьёте каждый день, это тоже качество.\n"
     "5. **Сертификаты** — Informed Sport, NSF Certified for Sport, GMP.\n\n"
     "💡 Дорогой бренд не всегда «больше результата»: у протеинов одного вида (например, концентратов) эффект почти одинаковый, разница — в надёжности и вкусе. Поэтому учитываем **цену 25 г белка + надёжность бренда** вместе.",
     "🏷 **The real difference between brands comes down to 5 things:**\n\n"
     "1. **Label accuracy** — the protein per serving matches the label. Big brands (Optimum Nutrition, Dymatize, Myprotein, Rule 1, BSN, Isopure, Applied Nutrition) are regularly third-party tested.\n"
     "2. **No amino spiking** — cheap formulas may add glycine or taurine to inflate the protein number; the formula should list protein sources only.\n"
     "3. **Raw material** — share of isolate/hydrolysate, patented ingredients like Creapure (creatine).\n"
     "4. **Taste and mixability** — you drink it daily; that's quality too.\n"
     "5. **Certificates** — Informed Sport, NSF Certified for Sport, GMP.\n\n"
     "💡 A pricier brand doesn't always mean more results: proteins of the same type (e.g. concentrates) work almost the same — the difference is reliability and taste. So we weigh **price of 25 g protein + brand trust** together."),
    ("product", 70, "Proteinlarni solishtirish hisobi",
     "proteinlarni qanday solishtiraman\nqaysi protein arzonroq tushadi\nporsiya narxini qanday hisoblayman\nкак сравнить протеины по цене\nкакой протеин выгоднее\nhow to compare protein value",
     "solishtirish, taqqoslash, hisob, hisoblash, porsiya, narxi, tejamkor, сравнить, выгоднее, расчет, порция, compare, value, per serving, per gram, calculate",
     "🧮 **Proteinlarni to'g'ri solishtirish (misol bilan):**\n\n"
     "**Formula:** 25 g oqsil narxi = narx ÷ porsiyalar soni ÷ porsiyadagi oqsil × 25\n\n"
     "• A: 450 000 so'm, 74 porsiya × 24 g → 450 000 ÷ 74 = 6 081 so'm porsiya → 25 g oqsil ≈ **6 334 so'm**\n"
     "• B: 380 000 so'm, 30 porsiya × 25 g → 12 667 so'm porsiya → 25 g oqsil ≈ **12 670 so'm**\n\n"
     "➡️ B banka arzonroq ko'rinsa ham, A **2 barobar tejamkor**.\n\n"
     "Yana qarang:\n• **Oqsil ulushi:** porsiyadagi oqsil ÷ porsiya og'irligi (izolyatda 80–90%, konsentratda 70–80%, geynerda 15–30%).\n"
     "• **Kunlik narx:** 1 kunda nechta porsiya ichasiz × porsiya narxi.\n\n"
     "✍️ \"Qaysi biri yaxshi?\" deb so'rasangiz, ko'rsatgan mahsulotlarimni shu hisob bilan solishtirib beraman.",
     "🧮 **Как правильно сравнивать протеины (на примере):**\n\n"
     "**Формула:** цена 25 г белка = цена ÷ число порций ÷ белок в порции × 25\n\n"
     "• A: 450 000 сум, 74 порции × 24 г → 6 081 сум порция → 25 г белка ≈ **6 334 сум**\n"
     "• B: 380 000 сум, 30 порций × 25 г → 12 667 сум порция → 25 г белка ≈ **12 670 сум**\n\n"
     "➡️ Хотя банка B дешевле, A **в 2 раза выгоднее**.\n\n"
     "Ещё смотрите:\n• **Долю белка:** белок в порции ÷ вес порции (изолят 80–90%, концентрат 70–80%, гейнер 15–30%).\n"
     "• **Цену дня:** сколько порций в день × цена порции.\n\n"
     "✍️ Спросите «Какой лучше?» — сравню показанные товары по этой формуле.",
     "🧮 **How to compare proteins properly (with an example):**\n\n"
     "**Formula:** price of 25 g protein = price ÷ servings ÷ protein per serving × 25\n\n"
     "• A: 450,000 UZS, 74 servings × 24 g → 6,081 UZS a serving → 25 g protein ≈ **6,334 UZS**\n"
     "• B: 380,000 UZS, 30 servings × 25 g → 12,667 UZS a serving → 25 g protein ≈ **12,670 UZS**\n\n"
     "➡️ Tub B looks cheaper, yet A is **twice the value**.\n\n"
     "Also check:\n• **Protein share:** protein per serving ÷ scoop weight (isolate 80–90%, concentrate 70–80%, gainer 15–30%).\n"
     "• **Cost per day:** servings a day × price per serving.\n\n"
     "✍️ Ask \"Which is better?\" and I'll compare the products I showed with this maths."),
    ("product", 70, "Kreatin turlari: monogidrat, HCl, Kre-Alkalyn",
     "kreatin monogidrat va hcl farqi\nqaysi kreatin yaxshi\nkre-alkalyn yaxshimi\nкакой креатин лучше моногидрат или hcl\nкреатин моногидрат или kre-alkalyn\nwhich creatine is best",
     "kreatin, monogidrat, hcl, gidroxlorid, kre-alkalyn, creapure, креатин, моногидрат, гидрохлорид, creatine, monohydrate, hydrochloride",
     "⚡ **Kreatin turlari:**\n\n"
     "• **Monogidrat** — 500+ tadqiqotda isbotlangan \"oltin standart\". Kuniga **3–5 g**, istalgan vaqtda, har kuni. Eng arzon. Creapure® belgisi — nemis xom ashyosi, eng toza.\n"
     "• **HCl (gidroxlorid)** — suvda yaxshi eriydi, dozasi kichikroq (1–2 g), qorin sezgir odamlarga qulay. Samarasi monogidratdan **ustun ekani isbotlanmagan**, narxi qimmatroq.\n"
     "• **Kre-Alkalyn (buferlangan)** — \"shishirmaydi\" deb reklama qilinadi, lekin tadqiqotlarda monogidratdan farqi topilmagan.\n\n"
     "🎯 **Xulosa:** ko'pchilik uchun eng yaxshi tanlov — **monogidrat** (iloji bo'lsa Creapure). Monogidratdan qorin bezovta bo'lsa — HCl.\n"
     "💡 Solishtirish: narx ÷ porsiyalar = 1 kunlik narx. 300 g monogidrat ≈ 60–100 kun yetadi.",
     "⚡ **Виды креатина:**\n\n"
     "• **Моногидрат** — «золотой стандарт», доказан в 500+ исследованиях. **3–5 г в день**, в любое время, ежедневно. Самый дешёвый. Знак Creapure® — немецкое сырьё, самое чистое.\n"
     "• **HCl (гидрохлорид)** — хорошо растворяется, доза меньше (1–2 г), удобен при чувствительном желудке. **Преимущество над моногидратом не доказано**, стоит дороже.\n"
     "• **Kre-Alkalyn (буферизованный)** — рекламируют как «без задержки воды», но в исследованиях отличий от моногидрата нет.\n\n"
     "🎯 **Итог:** для большинства лучший выбор — **моногидрат** (лучше Creapure). Если от моногидрата дискомфорт в желудке — HCl.\n"
     "💡 Сравнение: цена ÷ порции = цена дня. 300 г моногидрата ≈ на 60–100 дней.",
     "⚡ **Types of creatine:**\n\n"
     "• **Monohydrate** — the \"gold standard\", proven in 500+ studies. **3–5 g a day**, any time, every day. The cheapest. The Creapure® mark means German raw material, the purest.\n"
     "• **HCl (hydrochloride)** — dissolves well, smaller dose (1–2 g), easy on a sensitive stomach. **Not proven better** than monohydrate, and pricier.\n"
     "• **Kre-Alkalyn (buffered)** — marketed as \"no bloating\", but studies found no difference from monohydrate.\n\n"
     "🎯 **Bottom line:** for most people the best choice is **monohydrate** (Creapure if possible). If monohydrate upsets your stomach — HCl.\n"
     "💡 Compare: price ÷ servings = cost per day. 300 g of monohydrate lasts about 60–100 days."),
    ("product", 70, "Geyner yoki protein: qaysi biri kerak",
     "geyner yoki protein qaysi biri kerak\ngeyner va protein farqi\nozg'inman geyner olaymi proteinmi\nгейнер или протеин что выбрать\nчем гейнер отличается от протеина\ngainer or protein",
     "geyner, gainer, protein, farqi, ozg'in, semirish, massa, гейнер, протеин, отличие, худой, масса, mass, skinny, difference",
     "⚖️ **Geyner yoki protein?**\n\n"
     "• **Protein** — asosan oqsil (porsiyada 20–30 g, 100–130 kkal). Mushak uchun \"qurilish materiali\", vazn qo'shmaydi.\n"
     "• **Geyner** — uglevod + oqsil (porsiyada 500–1250 kkal, oqsil 15–30%). Kaloriya yetishmaydiganlar uchun.\n\n"
     "🎯 **Geyner kerak:** juda ozg'in (ectomorf), ishtaha yomon, kuniga 3000+ kkal yeyolmaysiz, vazn umuman qo'shilmayapti.\n"
     "🎯 **Protein kerak:** vazn normal yoki ortiqcha, yog'siz massa yoki ozish maqsadi, ovqat bilan kaloriya yetarli.\n\n"
     "💡 Oraliq yo'l: protein + suli/banan bilan o'zingiz \"geyner\" qiling — shakar kamroq, nazorat sizda. Geynerni porsiyasini yarmidan boshlang, semirish yog' hisobiga bo'lmasin.",
     "⚖️ **Гейнер или протеин?**\n\n"
     "• **Протеин** — в основном белок (20–30 г, 100–130 ккал на порцию). «Стройматериал» для мышц, вес сам по себе не добавляет.\n"
     "• **Гейнер** — углеводы + белок (500–1250 ккал на порцию, белка 15–30%). Для тех, кому не хватает калорий.\n\n"
     "🎯 **Нужен гейнер:** очень худой (эктоморф), плохой аппетит, не получается съедать 3000+ ккал, вес не растёт совсем.\n"
     "🎯 **Нужен протеин:** вес нормальный или лишний, цель — сухая масса или похудение, калорий из еды хватает.\n\n"
     "💡 Средний путь: протеин + овсянка/банан — свой «гейнер», меньше сахара, всё под контролем. Гейнер начинайте с половины порции, чтобы набирать не жир.",
     "⚖️ **Gainer or protein?**\n\n"
     "• **Protein** — mostly protein (20–30 g, 100–130 kcal a serving). Building material for muscle; doesn't add weight by itself.\n"
     "• **Gainer** — carbs + protein (500–1,250 kcal a serving, 15–30% protein). For people who can't eat enough calories.\n\n"
     "🎯 **You need a gainer if:** very skinny (ectomorph), poor appetite, can't eat 3,000+ kcal, weight won't move.\n"
     "🎯 **You need protein if:** normal or extra weight, goal is lean mass or fat loss, food gives enough calories.\n\n"
     "💡 Middle road: protein + oats/banana = your own \"gainer\" with less sugar and full control. Start a gainer at half a serving so you gain muscle, not fat."),
    ("product", 65, "Whey blend, konsentrat yoki izolyat: qaysi biri",
     "blend protein nima\nkonsentrat yoki izolyat qaysi biri yaxshi\nizolyat qimmatligiga arziydimi\nчто такое бленд протеин\nконцентрат или изолят что лучше\nis isolate worth it",
     "blend, konsentrat, izolyat, gidrolizat, aralashma, бленд, концентрат, изолят, гидролизат, concentrate, isolate, hydrolysate, worth",
     "🥤 **Konsentrat, blend, izolyat — kimga qaysi biri?**\n\n"
     "• **Konsentrat (WPC)** — 70–80% oqsil, ozgina yog' va laktoza, ta'mi boy. **Eng tejamkor**, ko'pchilik uchun yetarli.\n"
     "• **Blend** — konsentrat + izolyat (+ ba'zan gidrolizat) aralashmasi: narx va sifat o'rtasi (masalan, Gold Standard 100% Whey).\n"
     "• **Izolyat (WPI)** — 85–90% oqsil, laktoza va yog' deyarli yo'q. Qorin sezgir, laktoza, qattiq parhez/quritishda — **arziydi**.\n"
     "• **Gidrolizat** — eng tez va yengil hazm bo'ladi, eng qimmat; professional sportchilar, juda sezgir qorin uchun.\n\n"
     "🎯 **Oddiy qoida:** qorin muammosi yo'q va byudjet muhim → konsentrat yoki blend. Laktoza/ozish → izolyat. Mushak o'sishiga ta'siri kunlik oqsil yetarli bo'lsa deyarli bir xil.",
     "🥤 **Концентрат, бленд, изолят — кому что?**\n\n"
     "• **Концентрат (WPC)** — 70–80% белка, немного жира и лактозы, насыщенный вкус. **Самый выгодный**, большинству достаточно.\n"
     "• **Бленд** — смесь концентрата и изолята (+ иногда гидролизата): золотая середина цены и качества (например, Gold Standard 100% Whey).\n"
     "• **Изолят (WPI)** — 85–90% белка, почти без лактозы и жира. При чувствительном желудке, лактозе, строгой диете/сушке — **стоит своих денег**.\n"
     "• **Гидролизат** — усваивается быстрее и легче всех, самый дорогой; для профи и очень чувствительного желудка.\n\n"
     "🎯 **Простое правило:** желудок в порядке и важен бюджет → концентрат или бленд. Лактоза/похудение → изолят. На рост мышц при достаточном белке за день влияют почти одинаково.",
     "🥤 **Concentrate, blend, isolate — which one for whom?**\n\n"
     "• **Concentrate (WPC)** — 70–80% protein, a little fat and lactose, rich taste. **Best value**, enough for most people.\n"
     "• **Blend** — concentrate + isolate (+ sometimes hydrolysate): the middle ground of price and quality (e.g. Gold Standard 100% Whey).\n"
     "• **Isolate (WPI)** — 85–90% protein, almost no lactose or fat. **Worth it** for a sensitive stomach, lactose issues, strict dieting/cutting.\n"
     "• **Hydrolysate** — fastest and easiest to digest, the priciest; for athletes and very sensitive stomachs.\n\n"
     "🎯 **Simple rule:** no stomach issues and budget matters → concentrate or blend. Lactose/fat loss → isolate. With enough daily protein, muscle growth is about the same."),
    ("product", 60, "Protein va kreatin: har xil vazifa",
     "kreatin kerak protein kerakmi\nkreatin protein o'rnini bosadimi\nkreatin va proteinni birga ichsa bo'ladimi\nкреатин заменяет протеин\nможно ли креатин и протеин вместе\ndoes creatine replace protein",
     "kreatin, protein, birga, o'rnini, vazifa, farq, креатин, протеин, вместе, заменяет, creatine, protein, together, replace",
     "🧩 **Protein va kreatin — bir-birining o'rnini bosmaydi:**\n\n"
     "• **Protein** — mushak uchun qurilish materiali (oqsil). Ovqatdan kunlik oqsil yetmasa kerak.\n"
     "• **Kreatin** — mushak energiyasi (ATF) zaxirasi: kuch, portlovchi harakat, takrorlar soni oshadi. Oqsil emas, kaloriyasi yo'q.\n\n"
     "✅ Birga ichsa bo'ladi — eng ko'p o'rganilgan juftlik: kreatin 3–5 g ni protein kokteyliga qo'shib ichish qulay.\n"
     "🎯 Faqat kuch/natija kerak, oqsil ovqatdan yetarli → **kreatin**. Oqsil yetishmaydi → **protein**. Massa olish → ikkalasi.",
     "🧩 **Протеин и креатин не заменяют друг друга:**\n\n"
     "• **Протеин** — строительный материал для мышц (белок). Нужен, если белка из еды не хватает.\n"
     "• **Креатин** — запас энергии в мышцах (АТФ): больше силы, взрывности, повторений. Это не белок, калорий нет.\n\n"
     "✅ Можно вместе — самая изученная пара: 3–5 г креатина удобно добавить в протеиновый коктейль.\n"
     "🎯 Нужна только сила, белка из еды хватает → **креатин**. Не хватает белка → **протеин**. Набор массы → оба.",
     "🧩 **Protein and creatine don't replace each other:**\n\n"
     "• **Protein** — building material for muscle. Needed when food doesn't give enough protein.\n"
     "• **Creatine** — the muscles' energy reserve (ATP): more strength, power and reps. It isn't protein and has no calories.\n\n"
     "✅ Fine together — the most studied pair: stir 3–5 g of creatine into your protein shake.\n"
     "🎯 Only strength wanted and food gives enough protein → **creatine**. Short on protein → **protein**. Building mass → both."),
]
