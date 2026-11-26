"""
Knowledge, part 11 (2026-11-26): the questions a 40-question replay showed the free advisor still answered off-topic
-- coins for a review, stomach trouble and protein, protein in everyday food, counting calories, eating in the evening
while cutting, how many meals a day, combat sports, team sports, protein for vegetarians, what to drink in the heat,
how fast results come, stacking safely -- plus extra phrasings for entries that existed but were not found.
Each entry also becomes a /guides/<slug> page. Data for migration 0018.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("faq", 80, "Sharh yozib coin olish",
     "sharh yozsam coin beriladimi\nsharh uchun coin\notziv yozsam bonus bormi\nsharh yozib pul ishlash\nsharh uchun 1000 coin\nqanday sharh yozaman\n"
     "коины за отзыв\nкак получить коины за отзыв\nбонус за отзыв\nдают ли бонус за отзыв\nкак оставить отзыв\n"
     "coins for a review\ndo i get coins for a review\nhow to leave a review",
     "sharh, sharhi, otziv, отзыв, review, coin, koin, коин, бонус, bonus, yulduz, звезд",
     "⭐ **Har bir buyurtma uchun bitta sharhga — 1 000 NutriZone Coins.**\n\n"
     "**Qanday ishlaydi:**\n"
     "1️⃣ Buyurtmangiz yetkazilgach, mahsulotni sinab ko'ring.\n"
     "2️⃣ Mahsulot sahifasidagi **«Sharhlar»** bo'limida baho qo'ying va bir-ikki gap yozing (kamida 30 belgi). Rasm yoki video qo'shsangiz — boshqalarga yanada foydali.\n"
     "3️⃣ Sharh saytda chiqishi bilan hisobingizga **1 000 coin** avtomatik tushadi — saytda va Telegram'da xabar keladi.\n\n"
     "**Qoidalar:**\n"
     "• **Har qanday baho** hisoblanadi — 1★ ham, 5★ ham. Bizga halol fikringiz kerak.\n"
     "• Bitta buyurtma — bitta mukofotli sharh. Keyingi buyurtmada yana olasiz.\n"
     "• Sharh buyurtma **yetkazilgandan keyin** yozilgan bo'lishi kerak.\n"
     "• Ro'yxatdan o'tgan mijozlar uchun (mehmon sifatida buyurtma berganlar — hisob ochib, keyingi buyurtmadan).\n\n"
     "1 coin = 1 so'm: keyingi xaridda to'lovning bir qismini coin bilan qoplaysiz. Balans — **Profil → Bonuslar**.",
     "⭐ **За один отзыв с каждого заказа — 1 000 NutriZone Coins.**\n\n"
     "**Как это работает:**\n"
     "1️⃣ Получите заказ и попробуйте товар.\n"
     "2️⃣ На странице товара в разделе **«Отзывы»** поставьте оценку и напишите пару предложений (от 30 символов). Фото или видео сделают отзыв ещё полезнее.\n"
     "3️⃣ Как только отзыв опубликован, на счёт автоматически поступает **1 000 коинов** — придёт уведомление на сайте и в Telegram.\n\n"
     "**Правила:**\n"
     "• Подходит **любая оценка** — и 1★, и 5★. Нам важно честное мнение.\n"
     "• Один заказ — один отзыв с бонусом. Со следующим заказом — снова.\n"
     "• Отзыв пишется **после доставки** заказа.\n"
     "• Для зарегистрированных покупателей (если заказывали гостем — создайте аккаунт, бонус будет со следующего заказа).\n\n"
     "1 коин = 1 сум: оплачивайте ими часть следующей покупки. Баланс — **Профиль → Бонусы**.",
     "⭐ **One review per order earns 1,000 NutriZone Coins.**\n\n"
     "**How it works:**\n"
     "1️⃣ Get your order and try the product.\n"
     "2️⃣ On the product page, in **Reviews**, rate it and write a sentence or two (30+ characters). A photo or video makes it even more useful.\n"
     "3️⃣ As soon as the review is published, **1,000 coins** land in your wallet automatically — you'll get a notice on the site and in Telegram.\n\n"
     "**Rules:**\n"
     "• **Any rating** counts — 1★ or 5★. We want your honest opinion.\n"
     "• One order — one rewarded review. Your next order earns it again.\n"
     "• The review is written **after delivery**.\n"
     "• For registered customers (ordered as a guest? create an account — the reward starts with your next order).\n\n"
     "1 coin = 1 UZS: pay part of your next purchase with them. Balance — **Profile → Bonuses**."),

    ("usage", 70, "Oshqozon og'rig'i, gastrit va protein",
     "oshqozonim og'riydi protein ichsam bo'ladimi\ngastrit bor protein ichsam bo'ladimi\nyara kasalligi bor kreatin ichsam bo'ladimi\nproteindan keyin oshqozon og'riyapti\n"
     "kreatindan qorin og'riydi\nоболит желудок от протеина\nгастрит можно ли протеин\nкреатин болит живот\nstomach hurts after protein\ngastritis protein",
     "oshqozon, gastrit, yara, qorin og'ri, qorni og'ri, ko'ngil ayni, желуд, гастрит, язв, живот, stomach, gastritis, ulcer, nausea",
     "🫄 **Oshqozon sezgir bo'lsa ham proteinni ko'pincha ichsa bo'ladi — to'g'ri tanlab va to'g'ri ichib.**\n\n"
     "**Nimaga og'riydi:**\n"
     "• **Laktoza** — konsentrat va sutli kokteylda sut qandi bor; sezgir odamda qorin dam bo'ladi, og'riydi.\n"
     "• **Bir martada ko'p** — 2 porsiya birdaniga yoki och qoringa juda quyuq kokteyl.\n"
     "• **Shirintirgich va qo'shimchalar** — sukraloza, sorbitol, ko'p kakao, kofeinli formulalar.\n"
     "• **Kreatin** — 10 g dan ortiq birdaniga yoki kam suv bilan ichilsa oshqozonni bezovta qiladi.\n\n"
     "**Nima qilish kerak:**\n"
     "• **Izolyat** yoki **gidrolizat** tanlang — laktoza deyarli yo'q, yengil hazm bo'ladi.\n"
     "• Porsiyani yarimdan boshlang, **suv bilan** aralashtiring, ovqatdan keyin iching.\n"
     "• Kreatin: kuniga 3–5 g, **ovqat bilan**, 250–300 ml suvda; «yuklama» (20 g) qilmang.\n"
     "• Pre-workout va yog' yoqiruvchilardan voz keching — kofein kislotalikni oshiradi.\n\n"
     "⚠️ Gastrit yoki yara **kuchaygan** davrda, qusish, qora najas, kechasi og'riq bo'lsa — qo'shimchani to'xtatib, gastroenterologga murojaat qiling.",
     "🫄 **Даже при чувствительном желудке протеин чаще всего можно — если правильно выбрать и правильно пить.**\n\n"
     "**Почему болит:**\n"
     "• **Лактоза** — в концентрате и коктейле на молоке есть молочный сахар; у чувствительных — вздутие и боль.\n"
     "• **Много за раз** — 2 порции сразу или очень густой коктейль натощак.\n"
     "• **Подсластители и добавки** — сукралоза, сорбит, много какао, формулы с кофеином.\n"
     "• **Креатин** — больше 10 г за раз или мало воды раздражает желудок.\n\n"
     "**Что делать:**\n"
     "• Берите **изолят** или **гидролизат** — лактозы почти нет, усваивается легко.\n"
     "• Начните с половины порции, мешайте **на воде**, пейте после еды.\n"
     "• Креатин: 3–5 г в день, **с едой**, в 250–300 мл воды; без «загрузки» по 20 г.\n"
     "• Откажитесь от предтренов и жиросжигателей — кофеин повышает кислотность.\n\n"
     "⚠️ При **обострении** гастрита или язвы, рвоте, чёрном стуле, ночных болях — прекратите добавки и обратитесь к гастроэнтерологу.",
     "🫄 **Even with a sensitive stomach, protein is usually fine — chosen and taken the right way.**\n\n"
     "**Why it hurts:**\n"
     "• **Lactose** — concentrate and milk shakes contain milk sugar; sensitive people get bloating and pain.\n"
     "• **Too much at once** — 2 scoops together or a very thick shake on an empty stomach.\n"
     "• **Sweeteners and extras** — sucralose, sorbitol, lots of cocoa, caffeinated formulas.\n"
     "• **Creatine** — over 10 g at once or with little water upsets the stomach.\n\n"
     "**What to do:**\n"
     "• Choose **isolate** or **hydrolysate** — almost no lactose, easy to digest.\n"
     "• Start with half a scoop, mix **with water**, drink it after a meal.\n"
     "• Creatine: 3–5 g a day **with food** in 250–300 ml water; skip the 20 g loading phase.\n"
     "• Drop pre-workouts and fat burners — caffeine raises acidity.\n\n"
     "⚠️ During a gastritis or ulcer **flare-up**, vomiting, black stools or night pain — stop supplements and see a gastroenterologist."),

    ("usage", 62, "Oddiy ovqatlarda qancha oqsil bor",
     "tuxumda qancha oqsil bor\npishgan tuxumda qancha oqsil\ntovuq go'shtida qancha oqsil\ngo'shtda qancha oqsil bor\ntvorogda qancha oqsil\nsutda qancha oqsil\nqaysi ovqatda oqsil ko'p\n"
     "сколько белка в яйце\nсколько белка в курице\nв каких продуктах много белка\nсколько белка в твороге\nhow much protein in an egg\nhigh protein foods",
     "tuxum, tuxumda, tovuq, go'sht, gosht, tvorog, sut, baliq, no'xat, loviya, yasmiq, яйц, куриц, мяс, творог, молок, рыб, egg, chicken, meat, cottage, fish, beans, foods",
     "🍳 **Oddiy ovqatlardagi oqsil (taxminiy):**\n\n"
     "| Mahsulot | Oqsil |\n|---|---|\n"
     "| Tuxum, 1 dona (55 g) | ~6–7 g |\n"
     "| Tovuq ko'kragi, pishgan, 100 g | ~30 g |\n"
     "| Mol go'shti, pishgan, 100 g | ~26 g |\n"
     "| Baliq, 100 g | ~20–22 g |\n"
     "| Tvorog 5–9%, 100 g | ~16–18 g |\n"
     "| Qattiq pishloq, 30 g | ~7–8 g |\n"
     "| Sut, 250 ml | ~8 g |\n"
     "| Qatiq / yogurt, 200 g | ~6–10 g |\n"
     "| No'xat, loviya, yasmiq (pishgan), 100 g | ~8–9 g |\n"
     "| Yong'oq, 30 g | ~5 g |\n"
     "| Guruch yoki grechka (pishgan), 100 g | ~3–4 g |\n"
     "| Protein, 1 porsiya (30 g) | ~22–25 g |\n\n"
     "**Misol:** 80 kg mashq qiluvchiga ~130–160 g kerak. 3 tuxum (20 g) + 150 g tovuq (45 g) + 200 g tvorog (34 g) + 250 ml sut (8 g) ≈ **107 g** — qolgani uchun 1–2 porsiya protein qulay.\n\n"
     "Kunlik me'yoringizni bilish uchun vazn va maqsadingizni yozing.",
     "🍳 **Белок в обычных продуктах (примерно):**\n\n"
     "| Продукт | Белок |\n|---|---|\n"
     "| Яйцо, 1 шт (55 г) | ~6–7 г |\n"
     "| Куриная грудка, готовая, 100 г | ~30 г |\n"
     "| Говядина, готовая, 100 г | ~26 г |\n"
     "| Рыба, 100 г | ~20–22 г |\n"
     "| Творог 5–9%, 100 г | ~16–18 г |\n"
     "| Твёрдый сыр, 30 г | ~7–8 г |\n"
     "| Молоко, 250 мл | ~8 г |\n"
     "| Кефир / йогурт, 200 г | ~6–10 г |\n"
     "| Нут, фасоль, чечевица (варёные), 100 г | ~8–9 г |\n"
     "| Орехи, 30 г | ~5 г |\n"
     "| Рис или гречка (варёные), 100 г | ~3–4 г |\n"
     "| Протеин, 1 порция (30 г) | ~22–25 г |\n\n"
     "**Пример:** тренирующемуся 80 кг нужно ~130–160 г. 3 яйца (20 г) + 150 г курицы (45 г) + 200 г творога (34 г) + 250 мл молока (8 г) ≈ **107 г** — остальное удобно добрать 1–2 порциями протеина.\n\n"
     "Чтобы узнать свою норму, напишите вес и цель.",
     "🍳 **Protein in everyday food (approximate):**\n\n"
     "| Food | Protein |\n|---|---|\n"
     "| Egg, 1 (55 g) | ~6–7 g |\n"
     "| Chicken breast, cooked, 100 g | ~30 g |\n"
     "| Beef, cooked, 100 g | ~26 g |\n"
     "| Fish, 100 g | ~20–22 g |\n"
     "| Cottage cheese 5–9%, 100 g | ~16–18 g |\n"
     "| Hard cheese, 30 g | ~7–8 g |\n"
     "| Milk, 250 ml | ~8 g |\n"
     "| Kefir / yogurt, 200 g | ~6–10 g |\n"
     "| Chickpeas, beans, lentils (cooked), 100 g | ~8–9 g |\n"
     "| Nuts, 30 g | ~5 g |\n"
     "| Rice or buckwheat (cooked), 100 g | ~3–4 g |\n"
     "| Protein powder, 1 scoop (30 g) | ~22–25 g |\n\n"
     "**Example:** an 80 kg lifter needs ~130–160 g. 3 eggs (20 g) + 150 g chicken (45 g) + 200 g cottage cheese (34 g) + 250 ml milk (8 g) ≈ **107 g** — 1–2 scoops cover the rest.\n\n"
     "Tell me your weight and goal to get your own number."),

    ("usage", 60, "Kaloriyani qanday hisoblash",
     "kaloriya qanday hisoblanadi\nkunlik kaloriyamni qanday bilaman\nnecha kaloriya yeyishim kerak\nkaloriya hisoblash\nкак посчитать калории\nсколько калорий мне нужно\nкак считать калории\nhow to count calories\nhow many calories do i need",
     "kaloriya, kaloriyani, kkal, калори, ккал, calorie, calories, tdee, bmr",
     "🔢 **Kunlik kaloriyani 3 qadamda hisoblaysiz:**\n\n"
     "**1. Bazaviy almashinuv (Mifflin–St Jeor):**\n"
     "• Erkak: 10 × vazn(kg) + 6,25 × bo'y(sm) − 5 × yosh + 5\n"
     "• Ayol: 10 × vazn(kg) + 6,25 × bo'y(sm) − 5 × yosh − 161\n\n"
     "**2. Faollikka ko'paytiring:** kam harakat ×1,2 · haftada 1–3 mashg'ulot ×1,375 · 3–5 mashg'ulot ×1,55 · har kuni ×1,725.\n\n"
     "**3. Maqsadga moslang:** ozish −15…20% · vaznni saqlash ±0 · massa +10% (+250…400 kkal).\n\n"
     "**Misol:** erkak, 80 kg, 180 sm, 25 yosh, haftada 4 mashg'ulot → 1 805 × 1,55 ≈ **2 800 kkal** (ozish uchun ~2 250, massa uchun ~3 100).\n\n"
     "**Amalda:** 1–2 hafta ovqatni tarozida tortib ilovada (FatSecret, MyFitnessPal) yozing; yorliqdagi «100 g uchun» qatoriga qarang. Tarozi 2 hafta joyidan qimirlamasa — 150–200 kkal o'zgartiring.\n\n"
     "Bo'y, vazn, yosh va maqsadingizni yozsangiz, aniq hisoblab beraman.",
     "🔢 **Суточные калории — в 3 шага:**\n\n"
     "**1. Базовый обмен (Миффлин–Сан Жеор):**\n"
     "• Мужчины: 10 × вес(кг) + 6,25 × рост(см) − 5 × возраст + 5\n"
     "• Женщины: 10 × вес(кг) + 6,25 × рост(см) − 5 × возраст − 161\n\n"
     "**2. Умножьте на активность:** мало движения ×1,2 · 1–3 тренировки в неделю ×1,375 · 3–5 тренировок ×1,55 · каждый день ×1,725.\n\n"
     "**3. Под цель:** похудение −15…20% · поддержание ±0 · масса +10% (+250…400 ккал).\n\n"
     "**Пример:** мужчина, 80 кг, 180 см, 25 лет, 4 тренировки в неделю → 1 805 × 1,55 ≈ **2 800 ккал** (для похудения ~2 250, для массы ~3 100).\n\n"
     "**На практике:** 1–2 недели взвешивайте еду и записывайте в приложение (FatSecret, MyFitnessPal); смотрите строку «на 100 г» на этикетке. Вес стоит 2 недели — сдвиньте на 150–200 ккал.\n\n"
     "Напишите рост, вес, возраст и цель — посчитаю точно.",
     "🔢 **Your daily calories in 3 steps:**\n\n"
     "**1. Basal metabolism (Mifflin–St Jeor):**\n"
     "• Men: 10 × weight(kg) + 6.25 × height(cm) − 5 × age + 5\n"
     "• Women: 10 × weight(kg) + 6.25 × height(cm) − 5 × age − 161\n\n"
     "**2. Multiply by activity:** sedentary ×1.2 · 1–3 workouts a week ×1.375 · 3–5 workouts ×1.55 · daily ×1.725.\n\n"
     "**3. Adjust for the goal:** fat loss −15–20% · maintain ±0 · muscle +10% (+250–400 kcal).\n\n"
     "**Example:** man, 80 kg, 180 cm, 25, 4 workouts a week → 1,805 × 1.55 ≈ **2,800 kcal** (~2,250 to lose fat, ~3,100 to gain).\n\n"
     "**In practice:** weigh and log food for 1–2 weeks in an app (FatSecret, MyFitnessPal); read the \"per 100 g\" line on labels. Scale flat for 2 weeks — adjust by 150–200 kcal.\n\n"
     "Send your height, weight, age and goal and I'll calculate it for you."),

    ("usage", 58, "Ozishda kechki ovqat",
     "ozish uchun kechqurun nima yeyish kerak\nkechqurun ovqat yesam semiramanmi\nsoat 6 dan keyin ovqat yeyish mumkinmi\nkechasi nima yesa bo'ladi\nuxlashdan oldin nima yeyish kerak\n"
     "что есть вечером при похудении\nможно ли есть после 6\nчто съесть перед сном\nwhat to eat in the evening to lose weight\ncan i eat after 6 pm",
     "kechqurun, kechki, kechasi, uxlashdan oldin, soat 6, вечер, перед сном, после 6, на ночь, evening, night, before bed",
     "🌙 **«Soat 6 dan keyin yemang» — afsona.** Ozish kunlik **jami kaloriyaga** bog'liq, soatga emas.\n\n"
     "**Kechki ovqat uchun yaxshi tanlov:**\n"
     "• **Oqsil + sabzavot:** tovuq, baliq, tuxum, mol go'shti + salat yoki dimlangan sabzavot.\n"
     "• **Tvorog yoki qatiq** (150–250 g) — sekin hazm bo'ladigan oqsil, kechasi to'qlik beradi.\n"
     "• **Kazein protein** — uxlashdan oldin 1 porsiya, mashq qiluvchilar uchun qulay.\n\n"
     "**Kamaytiring:** shirinlik, non va xamir, qovurilgan va yog'li ovqat, shakarli ichimlik, alkogol.\n\n"
     "**Qoidalar:** uxlashdan **2–3 soat oldin** asosiy ovqatni tugating; kechasi och qolib, keyin ko'p yeb qo'ymaslik uchun kunduzi oqsilni yetarli yeng.",
     "🌙 **«Не есть после шести» — миф.** Похудение зависит от **суммы калорий за день**, а не от часов.\n\n"
     "**Хороший ужин:**\n"
     "• **Белок + овощи:** курица, рыба, яйца, говядина + салат или тушёные овощи.\n"
     "• **Творог или кефир** (150–250 г) — медленный белок, сытость на ночь.\n"
     "• **Казеин** — 1 порция перед сном, удобно тем, кто тренируется.\n\n"
     "**Сократите:** сладкое, хлеб и выпечку, жареное и жирное, сладкие напитки, алкоголь.\n\n"
     "**Правила:** основной приём закончите **за 2–3 часа до сна**; днём ешьте достаточно белка, чтобы вечером не переедать от голода.",
     "🌙 **\"No food after 6 pm\" is a myth.** Fat loss depends on **total daily calories**, not the clock.\n\n"
     "**A good dinner:**\n"
     "• **Protein + vegetables:** chicken, fish, eggs, beef + salad or steamed veg.\n"
     "• **Cottage cheese or kefir** (150–250 g) — slow protein that keeps you full overnight.\n"
     "• **Casein** — 1 scoop before bed, handy if you train.\n\n"
     "**Cut back on:** sweets, bread and pastry, fried and fatty food, sugary drinks, alcohol.\n\n"
     "**Rules:** finish your main meal **2–3 hours before bed**; eat enough protein during the day so you don't overeat at night."),

    ("usage", 55, "Kuniga necha marta ovqatlanish kerak",
     "kuniga necha marta ovqatlanish kerak\nnecha mahal ovqatlanish kerak\nkuniga 2 mahal ovqatlansam bo'ladimi\ninterval ochlik\nсколько раз в день нужно есть\nдробное питание\nинтервальное голодание\nhow many meals a day\nintermittent fasting",
     "necha marta, necha mahal, mahal, ovqatlanish, интервал, дробн, сколько раз, приём пищи, meals a day, fasting, intermittent",
     "🍽 **Ovqatlanish soni — qulaylik masalasi, sehr emas.**\n\n"
     "• **3–4 mahal** — ko'pchilik uchun eng qulay: har birida 25–40 g oqsil.\n"
     "• **5–6 mahal** — massa olayotganlar uchun: ko'p kaloriyani yeyish osonlashadi.\n"
     "• **2 mahal / interval ochlik (16:8)** — ozishda ishlaydi, agar jami kaloriya va oqsil yetarli bo'lsa. Mushak o'stirishda oqsilni kamida 3 qismga bo'lgan ma'qul.\n\n"
     "**Muhimi:** kunlik **jami kaloriya** va **oqsil**, mashg'ulotdan oldin va keyin 2–3 soat ichida ovqat, uxlashdan 2–3 soat oldin oxirgi katta ovqat.\n\n"
     "Protein kokteyli bitta «mahal»ni yoki gazakni oson almashtiradi.",
     "🍽 **Число приёмов пищи — вопрос удобства, а не магии.**\n\n"
     "• **3–4 раза** — удобнее всего большинству: 25–40 г белка за приём.\n"
     "• **5–6 раз** — тем, кто набирает массу: проще съесть много калорий.\n"
     "• **2 раза / интервальное голодание (16:8)** — работает для похудения, если хватает калорий и белка. Для роста мышц белок лучше делить хотя бы на 3 приёма.\n\n"
     "**Главное:** **сумма калорий** и **белка** за день, еда за 2–3 часа до и после тренировки, последний большой приём за 2–3 часа до сна.\n\n"
     "Протеиновый коктейль легко заменяет один приём или перекус.",
     "🍽 **Meal count is about convenience, not magic.**\n\n"
     "• **3–4 meals** — easiest for most people: 25–40 g protein each.\n"
     "• **5–6 meals** — for those bulking: easier to eat a lot of calories.\n"
     "• **2 meals / intermittent fasting (16:8)** — works for fat loss if calories and protein add up. For muscle growth split protein into at least 3 meals.\n\n"
     "**What matters:** total daily **calories** and **protein**, food within 2–3 hours of training, the last big meal 2–3 hours before bed.\n\n"
     "A protein shake easily replaces one meal or a snack."),

    ("usage", 60, "Kurash, boks va yakkakurash uchun sport ozuqasi",
     "boksyorga qaysi sport ozuqasi kerak\nkurashchiga nima kerak\nboks bilan shug'ullanaman nima ichay\nmma uchun sport ozuqa\ndzyudo uchun nima kerak\nyakkakurash uchun qo'shimcha\n"
     "что пить боксёру\nспортпит для борьбы\nдобавки для единоборств\nспортпит для мма\nsupplements for boxing\nwhat should a fighter take",
     "boks, boksyor, boksyorga, kurash, kurashchi, dzyudo, mma, sambo, karate, taekvondo, yakkakurash, бокс, борьб, дзюдо, единоборств, мма, самбо, box, boxing, wrestling, fighter, judo",
     "🥊 **Yakkakurash (boks, kurash, dzyudo, MMA) uchun asosiysi:**\n\n"
     "1. **Protein** — kuniga 1,6–2,2 g/kg; zarbalar va og'ir mashg'ulotdan keyin tiklanish uchun.\n"
     "2. **Kreatin** 3–5 g — kuch va portlovchi harakat. ⚠️ Vazn toifasiga tushishdan **2–3 hafta oldin to'xtating** (1–2 kg suv ushlaydi).\n"
     "3. **Elektrolitlar** — uzoq va terli mashg'ulotda: natriy, kaliy, magniy; quvvat va tirishishga qarshi.\n"
     "4. **Kofein** 3 mg/kg mashg'ulot yoki jangdan 45–60 daqiqa oldin — chidamlilik va reaksiya (kechqurun emas).\n"
     "5. **Omega-3 va D3** — bo'g'imlar, tiklanish, immunitet.\n\n"
     "**Kerak emas:** testosteron «bustyorlari», kuchli yog' yoqiruvchilar — natija kam, xavf bor.\n"
     "⚠️ 18 yoshgacha — faqat oddiy ovqat, protein (zarur bo'lsa) va murabbiy/shifokor maslahati. Musobaqa oldidan har qanday qo'shimcha doping ro'yxatiga mosligini tekshiring.\n\n"
     "Vazningiz va toifangizni yozsangiz, aniq reja tuzib beraman.",
     "🥊 **Для единоборств (бокс, борьба, дзюдо, ММА) главное:**\n\n"
     "1. **Протеин** — 1,6–2,2 г/кг в день; восстановление после ударов и тяжёлых тренировок.\n"
     "2. **Креатин** 3–5 г — сила и взрывная работа. ⚠️ **Остановите за 2–3 недели** до сгонки в весовую категорию (держит 1–2 кг воды).\n"
     "3. **Электролиты** — на долгих потных тренировках: натрий, калий, магний; против упадка сил и судорог.\n"
     "4. **Кофеин** 3 мг/кг за 45–60 минут до тренировки или боя — выносливость и реакция (не вечером).\n"
     "5. **Омега-3 и D3** — суставы, восстановление, иммунитет.\n\n"
     "**Не нужно:** «бустеры тестостерона», жёсткие жиросжигатели — эффекта мало, риск есть.\n"
     "⚠️ До 18 лет — обычная еда, протеин (если нужно) и совет тренера/врача. Перед соревнованиями проверяйте любую добавку на соответствие допинг-листу.\n\n"
     "Напишите вес и категорию — составлю точный план.",
     "🥊 **For combat sports (boxing, wrestling, judo, MMA) the essentials:**\n\n"
     "1. **Protein** — 1.6–2.2 g/kg a day; recovery after hits and hard sessions.\n"
     "2. **Creatine** 3–5 g — strength and explosive work. ⚠️ **Stop 2–3 weeks** before cutting to a weight class (it holds 1–2 kg of water).\n"
     "3. **Electrolytes** — for long sweaty sessions: sodium, potassium, magnesium; against fading and cramps.\n"
     "4. **Caffeine** 3 mg/kg 45–60 min before training or a fight — endurance and reaction (not in the evening).\n"
     "5. **Omega-3 and D3** — joints, recovery, immunity.\n\n"
     "**Skip:** testosterone \"boosters\", harsh fat burners — little effect, real risk.\n"
     "⚠️ Under 18 — regular food, protein if needed and a coach's/doctor's advice. Before competing, check every supplement against the anti-doping list.\n\n"
     "Send your weight and class and I'll build an exact plan."),

    ("usage", 58, "Futbol va jamoaviy sport uchun sport ozuqasi",
     "futbolchiga nima kerak\nfutbol o'ynayman nima ichay\nbasketbol uchun sport ozuqa\nvoleybol uchun nima kerak\nчто нужно футболисту\nспортпит для футбола\nsupplements for football\nwhat should a footballer take",
     "futbol, futbolchi, futbolchiga, basketbol, voleybol, xokkey, футбол, баскетбол, волейбол, хоккей, football, soccer, basketball, volleyball",
     "⚽ **Futbol va jamoaviy sport uchun:**\n\n"
     "1. **Uglevod — asosiy yoqilg'i:** o'yin/mashg'ulotdan 2–4 soat oldin guruch, makaron, non, banan. 90 daqiqadan uzoq bo'lsa — tanaffusda izotonik yoki gel.\n"
     "2. **Elektrolitlar va suv:** issiqda soatiga 0,5–1 l; ko'p terlasangiz — elektrolit tabletka/kukun.\n"
     "3. **Protein:** o'yindan keyin 20–30 g (kokteyl yoki ovqat) — tiklanish va mushak.\n"
     "4. **Kreatin** 3–5 g: sprint va takroriy tezlanishlar uchun foydali.\n"
     "5. **Kofein** 3 mg/kg o'yindan 1 soat oldin — ixtiyoriy.\n"
     "6. **D3 va omega-3** — bo'g'im va immunitet.\n\n"
     "Vazningiz, yoshingiz va haftada necha marta o'ynashingizni yozsangiz, shaxsiy reja tuzaman. 18 yoshgacha — faqat ovqat, suv va zarur bo'lsa protein.",
     "⚽ **Для футбола и командных видов:**\n\n"
     "1. **Углеводы — главное топливо:** за 2–4 часа до игры/тренировки рис, макароны, хлеб, банан. Дольше 90 минут — изотоник или гель в перерыве.\n"
     "2. **Электролиты и вода:** в жару 0,5–1 л в час; сильно потеете — электролиты в таблетках/порошке.\n"
     "3. **Протеин:** после игры 20–30 г (коктейль или еда) — восстановление и мышцы.\n"
     "4. **Креатин** 3–5 г: полезен для спринтов и повторных ускорений.\n"
     "5. **Кофеин** 3 мг/кг за час до игры — по желанию.\n"
     "6. **D3 и омега-3** — суставы и иммунитет.\n\n"
     "Напишите вес, возраст и сколько раз в неделю играете — составлю личный план. До 18 лет — только еда, вода и при необходимости протеин.",
     "⚽ **For football and team sports:**\n\n"
     "1. **Carbs are the main fuel:** rice, pasta, bread, banana 2–4 hours before a game/session. Longer than 90 min — an isotonic drink or gel at half-time.\n"
     "2. **Electrolytes and water:** 0.5–1 l per hour in the heat; heavy sweater — electrolyte tabs/powder.\n"
     "3. **Protein:** 20–30 g after the game (shake or food) — recovery and muscle.\n"
     "4. **Creatine** 3–5 g: helps sprints and repeated accelerations.\n"
     "5. **Caffeine** 3 mg/kg an hour before the game — optional.\n"
     "6. **D3 and omega-3** — joints and immunity.\n\n"
     "Send your weight, age and how often you play for a personal plan. Under 18 — food, water and protein only if needed."),

    ("faq", 55, "Natija qachon ko'rinadi",
     "natija qachon ko'rinadi\nprotein ichsam qachon natija bo'ladi\nkreatin qachon ta'sir qiladi\nnega natija yo'q\n3 oydan beri zalga boraman natija yo'q\n"
     "когда будет результат\nкогда начнёт действовать креатин\nнет результата в зале\nwhen will i see results\nno results from the gym",
     "natija, natijasi, ta'sir, qachon, результат, эффект, когда, results, effect, when",
     "⏳ **Haqiqiy muddatlar:**\n\n"
     "• **Kreatin:** kuch va takrorlar 2–4 haftada (yuklama qilsangiz ~1 haftada) oshadi; birinchi haftada vazn +0,5–1,5 kg — bu mushakdagi suv.\n"
     "• **Protein:** o'zi «ta'sir qilmaydi» — kunlik oqsil me'yorini to'ldiradi. Mushak o'sishi 6–8 haftada ko'rina boshlaydi.\n"
     "• **Massa:** yangi boshlovchi oyiga 0,5–1 kg sof mushak.\n"
     "• **Ozish:** haftada 0,5–1% vazn — xavfsiz va barqaror.\n"
     "• **Vitamin D, temir:** 8–12 hafta.\n\n"
     "**Natija yo'qmi? Tekshiring:**\n"
     "1. Kunlik **kaloriya va oqsil** haqiqatan yetadimi (1–2 hafta yozib ko'ring)?\n"
     "2. Mashg'ulotda **yuklama oshib boryaptimi** (og'irlik yoki takrorlar)?\n"
     "3. **Uyqu** 7–9 soatmi?\n"
     "4. **Muntazamlik** — haftada 3+ marta, 3 oydan ortiq?\n\n"
     "Bo'y, vazn, yosh va maqsadingizni yozing — qayerda «teshik» borligini hisoblab beraman.",
     "⏳ **Реальные сроки:**\n\n"
     "• **Креатин:** сила и повторы растут через 2–4 недели (с загрузкой ~1 неделя); в первую неделю +0,5–1,5 кг — это вода в мышцах.\n"
     "• **Протеин:** сам по себе «не действует» — он закрывает норму белка. Рост мышц заметен через 6–8 недель.\n"
     "• **Масса:** новичок — 0,5–1 кг чистых мышц в месяц.\n"
     "• **Похудение:** 0,5–1% веса в неделю — безопасно и устойчиво.\n"
     "• **Витамин D, железо:** 8–12 недель.\n\n"
     "**Нет результата? Проверьте:**\n"
     "1. Действительно ли хватает **калорий и белка** (запишите 1–2 недели)?\n"
     "2. **Растёт ли нагрузка** на тренировках (вес или повторы)?\n"
     "3. **Сон** 7–9 часов?\n"
     "4. **Регулярность** — 3+ раза в неделю, дольше 3 месяцев?\n\n"
     "Напишите рост, вес, возраст и цель — посчитаю, где «дыра».",
     "⏳ **Realistic timelines:**\n\n"
     "• **Creatine:** strength and reps rise in 2–4 weeks (~1 week with loading); +0.5–1.5 kg in week one is water in the muscle.\n"
     "• **Protein:** doesn't \"kick in\" — it fills your daily protein target. Muscle growth shows after 6–8 weeks.\n"
     "• **Muscle gain:** beginners — 0.5–1 kg of lean muscle a month.\n"
     "• **Fat loss:** 0.5–1% of body weight a week — safe and lasting.\n"
     "• **Vitamin D, iron:** 8–12 weeks.\n\n"
     "**No results? Check:**\n"
     "1. Are **calories and protein** really enough (log 1–2 weeks)?\n"
     "2. Is the **load going up** in training (weight or reps)?\n"
     "3. **Sleep** 7–9 hours?\n"
     "4. **Consistency** — 3+ times a week for more than 3 months?\n\n"
     "Send your height, weight, age and goal — I'll find the gap."),

    ("usage", 55, "Bir nechta qo'shimchani birga ichish",
     "protein va kreatinni birga ichsa bo'ladimi\nhammasini birga ichsam bo'ladimi\nvitamin va protein birga\nbcaa va protein birga ichiladimi\nкак совмещать добавки\nможно ли пить все вместе\nhow to combine supplements\ncan i take everything together",
     "birga, birgalikda, hammasini, совмещ, вместе, together, combine, stack",
     "🧩 **Qo'shimchalarni birlashtirish — oddiy qoidalar:**\n\n"
     "✅ **Birga ichsa bo'ladi:** protein + kreatin (bitta kokteylda), protein + vitaminlar, kreatin + omega-3, BCAA/EAA + izotonik.\n"
     "⏱ **Vaqtini ajrating:**\n"
     "• **Temir** — kalsiy, sut, choy/qahvadan 2 soat alohida (so'rilishi kamayadi).\n"
     "• **Kalsiy va magniy/rux** — turli vaqtda.\n"
     "• **Kofeinli pre-workout** — kechki 6 soat ichida emas; boshqa kofeinli mahsulot (energetik, yog' yoqiruvchi) bilan qo'shmang.\n"
     "• **D3, omega-3, K2** — yog'li ovqat bilan.\n\n"
     "❌ **Ikki marta olmang:** ikkita multivitamin, pre-workout + yog' yoqiruvchi (kofein dozasi ikki barobar), ikkita kreatinli mahsulot.\n\n"
     "Qaysi mahsulotlarni ichayotganingizni yozsangiz, kunlik jadval tuzib beraman.",
     "🧩 **Как совмещать добавки — простые правила:**\n\n"
     "✅ **Можно вместе:** протеин + креатин (в одном коктейле), протеин + витамины, креатин + омега-3, BCAA/EAA + изотоник.\n"
     "⏱ **Разнесите по времени:**\n"
     "• **Железо** — через 2 часа от кальция, молока, чая/кофе (хуже усваивается).\n"
     "• **Кальций и магний/цинк** — в разное время.\n"
     "• **Предтрен с кофеином** — не за 6 часов до сна; не смешивайте с другим кофеином (энергетики, жиросжигатели).\n"
     "• **D3, омега-3, K2** — с жирной едой.\n\n"
     "❌ **Не дублируйте:** два мультивитамина, предтрен + жиросжигатель (двойная доза кофеина), два продукта с креатином.\n\n"
     "Напишите, что принимаете, — составлю расписание на день.",
     "🧩 **Combining supplements — simple rules:**\n\n"
     "✅ **Fine together:** protein + creatine (one shake), protein + vitamins, creatine + omega-3, BCAA/EAA + isotonic drink.\n"
     "⏱ **Space them out:**\n"
     "• **Iron** — 2 hours apart from calcium, milk, tea/coffee (absorption drops).\n"
     "• **Calcium and magnesium/zinc** — at different times.\n"
     "• **Caffeinated pre-workout** — not within 6 hours of bed; don't stack with other caffeine (energy drinks, fat burners).\n"
     "• **D3, omega-3, K2** — with a fatty meal.\n\n"
     "❌ **Don't double up:** two multivitamins, pre-workout + fat burner (double caffeine), two creatine products.\n\n"
     "Tell me what you take and I'll make a daily schedule."),

    ("faq", 60, "Mahsulotni qaytarish va almashtirish",
     "mahsulotni qaytarsa bo'ladimi\nta'mi yoqmadi qaytarsam bo'ladimi\nochilgan proteinni qaytarish\nmahsulot buzilgan keldi\nnoto'g'ri mahsulot keldi\n"
     "как вернуть товар если не подошел вкус\nможно ли вернуть протеин\nпришел не тот товар\nтовар пришел поврежденным\nвернуть деньги\ncan i return a product\nwrong item delivered",
     "qaytar, qaytarish, qaytarsa, almashtir, vozvrat, вернуть, возврат, обмен, поврежд, не тот, return, refund, exchange, damaged, wrong item",
     "↩️ **Qaytarish va almashtirish:**\n\n"
     "• **14 kun** ichida — yetkazilgan kundan boshlab.\n"
     "• **Ochilmagan**, qadoqi va himoya plyonkasi butun mahsulot qabul qilinadi.\n"
     "• **Ta'mi yoqmasa** — ochilgan ozuqa mahsuloti gigiyena sababli qaytarilmaydi. Shuning uchun keyingi safar avval kichik qadoq yoki boshqalar sharhiga qarab tanlang — operatorimiz ta'm tanlashda yordam beradi.\n"
     "• **Nuqsonli, shikastlangan yoki noto'g'ri mahsulot keldi** — **almashtirib beramiz**. Qabul qilgan kuningiz rasm/video oling va bizga yozing.\n\n"
     "**Qanday qilinadi:** Profil → **Buyurtmalarim** → buyurtma → **«Qaytarish so'rovi»**, yoki operatorga buyurtma raqami bilan yozing. Operator holatni ko'rib, almashtirish yoki pulni qaytarish tartibini aytadi.",
     "↩️ **Возврат и обмен:**\n\n"
     "• В течение **14 дней** со дня доставки.\n"
     "• Принимаем **невскрытый** товар с целой упаковкой и защитной плёнкой.\n"
     "• **Не подошёл вкус** — вскрытое спортпитание по гигиеническим причинам не возвращается. В следующий раз выбирайте сначала маленькую упаковку или по отзывам — оператор поможет подобрать вкус.\n"
     "• **Брак, повреждение или пришёл не тот товар** — **обменяем**. Снимите фото/видео в день получения и напишите нам.\n\n"
     "**Как оформить:** Профиль → **Мои заказы** → заказ → **«Запрос на возврат»**, или напишите оператору с номером заказа. Оператор рассмотрит случай и подскажет порядок обмена или возврата денег.",
     "↩️ **Returns and exchanges:**\n\n"
     "• Within **14 days** of delivery.\n"
     "• **Unopened** products with intact packaging and seal are accepted.\n"
     "• **Didn't like the taste** — opened food supplements can't be returned for hygiene reasons. Next time start with a small pack or go by reviews — our team will help pick a flavour.\n"
     "• **Faulty, damaged or the wrong item** — we **exchange it**. Take a photo/video on the day you receive it and message us.\n\n"
     "**How:** Profile → **My orders** → the order → **\"Return request\"**, or message an operator with the order number. An operator reviews the case and explains how the exchange or refund works."),
    ("usage", 62, "Vegetarianlar uchun oqsil manbalari",
     "vegetarianman oqsilni qayerdan olaman\ngo'sht yemayman oqsil qayerdan olaman\nvegetarianlarga qaysi protein\nvegan qanday oqsil oladi\nвегетарианец где взять белок\nгде взять белок вегетарианцу\nгде вегетарианцу брать белок\nне ем мясо где взять белок\nбелок для вегетарианцев\nvegetarian protein sources\ni don't eat meat where do i get protein",
     "vegetarian, vegetarianman, vegetarianlar, vegan, go'sht yemayman, вегетариан, веган, не ем мясо, vegetarian, plant",
     "🌱 **Go'shtsiz ham oqsilni yetarli olsa bo'ladi** — faqat manbalarni har kuni aralashtiring.\n\n"
     "**Sut va tuxum yesangiz (laktovegetarian):**\n"
     "• Tuxum (1 dona ~6 g), tvorog (100 g ~17 g), qatiq/yogurt, pishloq, sut.\n"
     "• **Whey protein** ham sizga to'g'ri keladi — u sutdan olinadi, go'sht emas.\n\n"
     "**Hech qanday hayvon mahsuloti yemasangiz (vegan):**\n"
     "• Yasmiq, no'xat, loviya, mosh (pishgan 100 g ~8–9 g), tofu va soya (100 g ~12–15 g), yong'oq va urug'lar, grechka, suli.\n"
     "• **O'simlik (vegan) protein** — no'xat + guruch oqsili aralashmasi aminokislotalar bo'yicha whey'ga yaqin.\n\n"
     "**Muhim:**\n"
     "• Oqsil me'yorini 10–15% ko'proq oling (o'simlik oqsili biroz kamroq so'riladi): mashq qilsangiz 1,8–2,2 g/kg.\n"
     "• **B12** — vegan uchun majburiy qo'shimcha; **temir, D3, omega-3 (suv o'tidan), rux** ni tekshirib turing.\n\n"
     "Vazn va maqsadingizni yozsangiz, kunlik reja tuzib beraman.",
     "🌱 **Без мяса белка можно получать достаточно** — просто сочетайте источники каждый день.\n\n"
     "**Если едите молочное и яйца (лактовегетарианец):**\n"
     "• Яйца (1 шт ~6 г), творог (100 г ~17 г), кефир/йогурт, сыр, молоко.\n"
     "• **Сывороточный протеин** тоже подходит — он из молока, не из мяса.\n\n"
     "**Если не едите ничего животного (веган):**\n"
     "• Чечевица, нут, фасоль, маш (варёные 100 г ~8–9 г), тофу и соя (100 г ~12–15 г), орехи и семена, гречка, овсянка.\n"
     "• **Растительный (веганский) протеин** — смесь горохового и рисового белка по аминокислотам близка к сыворотке.\n\n"
     "**Важно:**\n"
     "• Берите белка на 10–15% больше (растительный усваивается чуть хуже): при тренировках 1,8–2,2 г/кг.\n"
     "• **B12** — обязательная добавка для веганов; следите за **железом, D3, омега-3 (из водорослей), цинком**.\n\n"
     "Напишите вес и цель — составлю план на день.",
     "🌱 **You can get enough protein without meat** — just mix sources every day.\n\n"
     "**If you eat dairy and eggs (lacto-ovo vegetarian):**\n"
     "• Eggs (~6 g each), cottage cheese (100 g ~17 g), kefir/yogurt, cheese, milk.\n"
     "• **Whey protein** works for you too — it comes from milk, not meat.\n\n"
     "**If you eat no animal products (vegan):**\n"
     "• Lentils, chickpeas, beans, mung beans (cooked 100 g ~8–9 g), tofu and soy (100 g ~12–15 g), nuts and seeds, buckwheat, oats.\n"
     "• **Plant (vegan) protein** — a pea + rice blend is close to whey in amino acids.\n\n"
     "**Important:**\n"
     "• Aim 10–15% higher (plant protein absorbs a little less): 1.8–2.2 g/kg if you train.\n"
     "• **B12** is a must for vegans; keep an eye on **iron, D3, omega-3 (algae), zinc**.\n\n"
     "Send your weight and goal for a daily plan."),
]

TITLES = {
    "Sharh yozib coin olish": ("Коины за отзыв", "Coins for a review"),
    "Oshqozon og'rig'i, gastrit va protein": ("Боль в желудке, гастрит и протеин", "Stomach pain, gastritis and protein"),
    "Oddiy ovqatlarda qancha oqsil bor": ("Сколько белка в обычных продуктах", "Protein in everyday food"),
    "Kaloriyani qanday hisoblash": ("Как посчитать калории", "How to count calories"),
    "Ozishda kechki ovqat": ("Ужин при похудении", "Dinner while losing weight"),
    "Kuniga necha marta ovqatlanish kerak": ("Сколько раз в день есть", "How many meals a day"),
    "Kurash, boks va yakkakurash uchun sport ozuqasi": ("Спортпит для бокса, борьбы и единоборств", "Supplements for boxing, wrestling and combat sports"),
    "Futbol va jamoaviy sport uchun sport ozuqasi": ("Спортпит для футбола и командных видов", "Supplements for football and team sports"),
    "Natija qachon ko'rinadi": ("Когда будет результат", "When will I see results"),
    "Bir nechta qo'shimchani birga ichish": ("Как совмещать добавки", "Combining supplements"),
    "Mahsulotni qaytarish va almashtirish": ("Возврат и обмен товара", "Returns and exchanges"),
    "Vegetarianlar uchun oqsil manbalari": ("Белок для вегетарианцев", "Protein for vegetarians"),
}

# entries that already existed but the replay showed were not found for these phrasings
QUESTIONS_ADD = {
    "Mushak og'rig'i va tiklanish": "mushak og'rig'ini qanday kamaytirsa bo'ladi\nmashg'ulotdan keyin mushaklarim og'riyapti\nkrepatura\nкак уменьшить боль в мышцах\nкрепатура что делать\nsore muscles after workout",
    "Ramazonda mashg'ulot va qo'shimchalar": "ramazonda sport ozuqasini qanday ichish kerak\nro'za tutganda protein ichsa bo'ladimi\nro'zada kreatin qachon ichiladi\nкак пить спортпит в рамадан\nпротеин во время поста\nsupplements during ramadan",
    "50 yoshdan keyin sport ozuqasi": "yoshi 50 dan oshgan odamga qaysi vitamin kerak\n50 yoshdan keyin qanday vitamin ichish kerak\nkeksalar uchun protein\nкакие витамины нужны после 50\nпротеин для пожилых\nvitamins after 50",
    "Yugurish, futbol va uzoq mashg'ulotda ovqatlanish": "yugurish uchun nima ichay\nmarafon uchun nima kerak\nyuguraman qanday sport ozuqa kerak\nчто пить для бега\nспортпит для бегуна\nwhat to take for running",
    "Konsentrat, izolyat va gidrolizat farqi": "чем изолят лучше концентрата\nizolyat konsentratdan nimasi bilan yaxshi\nизолят или концентрат что лучше\nis isolate better than concentrate",
    "Ochilgan qadoqni saqlash va yaroqlilik muddati": "proteinning muddati o'tgan bo'lsa ichsa bo'ladimi\nmuddati o'tgan kreatin\nпросроченный протеин можно пить\nexpired protein safe",
    "Kuniga qancha oqsil kerak": "qizga kuniga qancha oqsil kerak\nсколько белка в день нужно девушке\nсколько белка нужно в день\nhow much protein does a woman need",
}
