"""
Knowledge, part 10 (2026-11-26): how to use the shop itself -- installing the site as an app (Android, iPhone,
computer), ordering without registering, signing in through Telegram, price alerts / wishlist / compare -- plus
expert gaps customers keep asking about: making weight for wrestling/boxing, bloating from protein, training at home
without a gym, supplements while pregnant or breastfeeding. Each entry also becomes a /guides/<slug> page.
Data for migration 0017; numbers that change (coins, delivery prices) are left to get_store_info / live pages.
"""

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("faq", 70, "NutriZone ilovasini telefonga o'rnatish",
     "ilovani qanday o'rnataman\nnutrizone ilovasi bormi\nplay marketda ilova bormi\napp store da bormi\ntelefonga o'rnatish\niphone ga qanday o'rnataman\nandroidga o'rnatish\nkompyuterga o'rnatish\nприложение nutrizone\nкак установить приложение\nесть ли приложение\nhow to install the app\nis there an app",
     "ilova, ilovasi, ilovani, prilojenie, приложение, o'rnat, ornat, установ, install, app, play market, app store, iphone, android, kompyuter",
     "📲 **NutriZone ilovasi Play Market yoki App Store'siz — to'g'ridan-to'g'ri saytdan o'rnatiladi.** Hajmi 1 MB dan kam, xotira egallamaydi va o'zi yangilanadi.\n\n"
     "**Android (Chrome, Samsung Internet, Yandex):**\n"
     "1️⃣ nutrizone.uz ni oching.\n"
     "2️⃣ Pastda chiqadigan «Ilovani o'rnatish» tugmasini bosing (yoki menyu ⋮ → «Ilovani o'rnatish»).\n"
     "3️⃣ «O'rnatish»ni tasdiqlang — NutriZone belgisi telefon ekranida paydo bo'ladi.\n\n"
     "**iPhone (Safari):**\n"
     "1️⃣ nutrizone.uz ni **Safari**'da oching.\n"
     "2️⃣ Pastdagi «Ulashish» belgisini (kvadrat va yuqoriga strelka) bosing.\n"
     "3️⃣ «Ekranga qo'shish» (На экран «Домой») → «Qo'shish».\n\n"
     "**Kompyuter (Chrome, Edge, Yandex):** manzil qatoridagi o'rnatish belgisini yoki saytdagi «Kompyuterga o'rnatish» tugmasini bosing.\n\n"
     "O'rnatilgan ilova alohida oynada, brauzer panellarisiz ochiladi; savat, buyurtmalar va coinlar sayt bilan bir xil.",
     "📲 **Приложение NutriZone ставится прямо с сайта — без Play Market и App Store.** Весит меньше 1 МБ, не занимает память и обновляется само.\n\n"
     "**Android (Chrome, Samsung Internet, Яндекс):**\n"
     "1️⃣ Откройте nutrizone.uz.\n"
     "2️⃣ Нажмите кнопку «Установить приложение» внизу (или меню ⋮ → «Установить приложение»).\n"
     "3️⃣ Подтвердите «Установить» — значок NutriZone появится на экране телефона.\n\n"
     "**iPhone (Safari):**\n"
     "1️⃣ Откройте nutrizone.uz в **Safari**.\n"
     "2️⃣ Нажмите «Поделиться» внизу (квадрат со стрелкой вверх).\n"
     "3️⃣ «На экран «Домой»» → «Добавить».\n\n"
     "**Компьютер (Chrome, Edge, Яндекс):** нажмите значок установки в адресной строке или кнопку «Установить на компьютер» на сайте.\n\n"
     "Установленное приложение открывается в отдельном окне без панелей браузера; корзина, заказы и коины — те же, что на сайте.",
     "📲 **The NutriZone app installs straight from the website — no Play Store or App Store.** It's under 1 MB, takes no storage and updates itself.\n\n"
     "**Android (Chrome, Samsung Internet, Yandex):**\n"
     "1️⃣ Open nutrizone.uz.\n"
     "2️⃣ Tap the “Install the app” button at the bottom (or menu ⋮ → “Install app”).\n"
     "3️⃣ Confirm “Install” — the NutriZone icon appears on your home screen.\n\n"
     "**iPhone (Safari):**\n"
     "1️⃣ Open nutrizone.uz in **Safari**.\n"
     "2️⃣ Tap Share at the bottom (the square with an up arrow).\n"
     "3️⃣ “Add to Home Screen” → “Add”.\n\n"
     "**Computer (Chrome, Edge, Yandex):** click the install icon in the address bar or the “Install on this computer” button on the site.\n\n"
     "The installed app opens in its own window without browser bars; your cart, orders and coins are the same as on the site."),

    ("policy", 72, "Ro'yxatdan o'tmasdan buyurtma berish",
     "ro'yxatdan o'tmasdan buyurtma bersa bo'ladimi\nqanday buyurtma beraman\nbuyurtma berish tartibi\nsaytdan qanday zakaz qilaman\nzakaz qilish\nкак сделать заказ\nможно заказать без регистрации\nhow do i order\ncan i order without an account",
     "buyurtma ber, zakaz, oformit, оформить, заказать, регистрац, ro'yxatdan, registr, checkout, order",
     "🛒 **Ro'yxatdan o'tish shart emas** — buyurtma 1 daqiqada:\n\n"
     "1️⃣ Mahsulotni tanlang → ta'm/hajmni belgilang → «Savatga qo'shish».\n"
     "2️⃣ Savat → «Rasmiylashtirish».\n"
     "3️⃣ **Yetkazib berish** (manzilni xaritada belgilang yoki joylashuvingizni aniqlang) yoki **do'kondan olib ketish** (bepul) ni tanlang.\n"
     "4️⃣ Ism va telefon raqamini yozing → «Buyurtmani tasdiqlash».\n\n"
     "Buyurtma raqami ekranda chiqadi va do'kon tez orada siz bilan bog'lanadi. Telegram orqali kirsangiz, buyurtma holati, coinlar va qayta buyurtma bir joyda saqlanadi.",
     "🛒 **Регистрация не обязательна** — заказ за 1 минуту:\n\n"
     "1️⃣ Выберите товар → вкус/объём → «В корзину».\n"
     "2️⃣ Корзина → «Оформить».\n"
     "3️⃣ **Доставка** (отметьте адрес на карте или определите местоположение) или **самовывоз** (бесплатно).\n"
     "4️⃣ Имя и телефон → «Подтвердить заказ».\n\n"
     "Номер заказа появится на экране, и магазин скоро свяжется с вами. Если войти через Telegram, статус заказа, коины и повтор заказа будут в одном месте.",
     "🛒 **No account needed** — ordering takes a minute:\n\n"
     "1️⃣ Pick a product → choose flavour/size → “Add to cart”.\n"
     "2️⃣ Cart → “Checkout”.\n"
     "3️⃣ Choose **delivery** (pin the address on the map or use your location) or **store pickup** (free).\n"
     "4️⃣ Enter your name and phone → “Confirm order”.\n\n"
     "You'll see your order number on screen and the store will contact you shortly. Sign in with Telegram to keep order status, coins and reorders in one place."),

    ("faq", 65, "Saytga kirish va ro'yxatdan o'tish",
     "qanday ro'yxatdan o'taman\nsaytga qanday kiraman\nkod kelmayapti\nsms kelmadi\nparolni unutdim\nкак зарегистрироваться\nкак войти\nне приходит код\nhow to sign in\nhow to register",
     "ro'yxat, royxat, kirish, kiraman, login, kod, sms, parol, вход, войти, регистрац, код, sign in, register",
     "🔐 **Parol va SMS kerak emas** — kirish Telegram orqali:\n\n"
     "1️⃣ «Kirish» → **«Telegram orqali kirish»**.\n"
     "2️⃣ Botda **«✅ Saytga kirish»**ni bosing (yangi bo'lsangiz telefon raqamingizni ulashasiz — 30 soniya).\n"
     "3️⃣ Sayt o'zi kiradi.\n\n"
     "Kod bilan kirish ham bor: «Yoki kod bilan kirish» → bot yuborgan 6 xonali kodni yozing. Kod kelmasa — botni bir marta /start bilan oching va qayta urinib ko'ring. "
     "Kirgandan keyin: buyurtmalar tarixi, coinlar, manzillar, sevimlilar va bildirishnomalar.",
     "🔐 **Пароль и SMS не нужны** — вход через Telegram:\n\n"
     "1️⃣ «Войти» → **«Войти через Telegram»**.\n"
     "2️⃣ В боте нажмите **«✅ Войти на сайт»** (если вы новый — поделитесь номером, 30 секунд).\n"
     "3️⃣ Сайт войдёт сам.\n\n"
     "Есть и вход по коду: «Или войти по коду» → введите 6-значный код из бота. Если код не пришёл — откройте бота командой /start и попробуйте снова. "
     "После входа: история заказов, коины, адреса, избранное и уведомления.",
     "🔐 **No password or SMS** — you sign in with Telegram:\n\n"
     "1️⃣ “Sign in” → **“Sign in with Telegram”**.\n"
     "2️⃣ In the bot tap **“✅ Sign in to the site”** (new users share their phone number — 30 seconds).\n"
     "3️⃣ The site signs you in by itself.\n\n"
     "There's also a code option: “Or sign in with a code” → type the 6-digit code from the bot. No code? Open the bot once with /start and try again. "
     "Once signed in you get order history, coins, addresses, wishlist and notifications."),

    ("faq", 55, "Narx tushsa xabar, sevimlilar va solishtirish",
     "narx tushsa xabar bering\narzonlashsa qanday bilaman\nsevimlilarga qo'shish\nmahsulotlarni solishtirish\nскидка уведомление\nсообщить о снижении цены\nсравнить товары\nprice drop alert\ncompare products",
     "narx tushsa, arzonlash, sevimli, izbrann, избранное, solishtir, сравн, compare, wishlist, price alert",
     "🔔 **Narx tushsa xabar:** mahsulot sahifasidagi «Narx tushsa xabar bering» tugmasini bosing — arzonlashganda saytda va Telegram'da xabar keladi. Narx tarixi grafigida oxirgi 6 oylik narxni ko'rasiz.\n\n"
     "❤️ **Sevimlilar:** kartadagi yurakcha — keyin «Sevimlilar» sahifasidan bir bosishda savatga.\n\n"
     "⚖️ **Solishtirish:** mahsulot sahifasida «Solishtirish» — 4 tagacha mahsulotni narx, porsiya va tarkib bo'yicha yonma-yon ko'rasiz.",
     "🔔 **Уведомление о снижении цены:** нажмите «Сообщить о снижении цены» на странице товара — при удешевлении придёт уведомление на сайте и в Telegram. График показывает цену за последние 6 месяцев.\n\n"
     "❤️ **Избранное:** сердечко на карточке — потом из «Избранного» в корзину в одно касание.\n\n"
     "⚖️ **Сравнение:** «Сравнить» на странице товара — до 4 товаров рядом по цене, порциям и составу.",
     "🔔 **Price-drop alert:** tap “Notify me when the price drops” on a product page — you'll get a site and Telegram notification when it gets cheaper. The price chart shows the last 6 months.\n\n"
     "❤️ **Wishlist:** the heart on a card — later add to cart from “Wishlist” in one tap.\n\n"
     "⚖️ **Compare:** “Compare” on a product page — up to 4 products side by side by price, servings and ingredients."),

    ("usage", 50, "Vazn toifasiga tushirish: kurash, boks, dzyudo",
     "vazn haydash\nmusobaqaga vazn tushirish\nvesga tushish\nkurash uchun vazn tushirish\nсгонка веса\nкак согнать вес перед соревнованиями\nmaking weight for a fight\nweight cut",
     "vazn hayd, vesga, toifa, kategoriya, kurash, boks, dzyudo, sambo, сгонк, весовая, weight cut, making weight",
     "🥊 **Vazn toifasiga xavfsiz tushish — 2 bosqich:**\n\n"
     "**1. Musobaqaga 4–8 hafta qolganda — yog'dan.** Haftasiga tana vaznining 0,5–1 % i: kaloriya −300–500, oqsil 2–2,4 g/kg (protein/izolyat yordam beradi), kuch mashqlari davom etadi. Shunda kuch va chidamlilik saqlanadi.\n\n"
     "**2. Oxirgi 3–5 kun — suv va glikogen hisobidan** (vaznning 3–5 % idan oshmasin): kam tuzli, kam tolali ovqat, uglevodni kamaytirish. Tortishdan keyin: suv + **elektrolitlar**, oson uglevod (banan, guruch), 4–6 soatda 1–1,5 l suyuqlik.\n\n"
     "⚠️ Sauna + yugurish bilan kuniga 3–4 kg tashlash, diuretiklar va «quritish tabletkalari» — hushdan ketish, buyrak va yurak uchun xavfli; kuch ham tushib ketadi. Yosh sportchilar faqat murabbiy va shifokor nazoratida.",
     "🥊 **Безопасная сгонка — 2 этапа:**\n\n"
     "**1. За 4–8 недель до старта — за счёт жира.** 0,5–1 % веса в неделю: калории −300–500, белок 2–2,4 г/кг (поможет протеин/изолят), силовые продолжаются — сила и выносливость сохраняются.\n\n"
     "**2. Последние 3–5 дней — вода и гликоген** (не больше 3–5 % веса): меньше соли и клетчатки, меньше углеводов. После взвешивания: вода + **электролиты**, быстрые углеводы (банан, рис), 1–1,5 л жидкости за 4–6 часов.\n\n"
     "⚠️ Сгонять 3–4 кг в день сауной и бегом, мочегонные и «таблетки для сушки» — опасно для почек и сердца, риск обморока, сила падает. Юным спортсменам — только под контролем тренера и врача.",
     "🥊 **Making weight safely — 2 phases:**\n\n"
     "**1. 4–8 weeks out — lose fat.** 0.5–1 % of body weight a week: calories −300–500, protein 2–2.4 g/kg (a protein/isolate helps), keep lifting so strength and endurance stay.\n\n"
     "**2. The last 3–5 days — water and glycogen** (no more than 3–5 % of body weight): less salt and fibre, fewer carbs. After weigh-in: water + **electrolytes**, fast carbs (banana, rice), 1–1.5 L of fluid over 4–6 hours.\n\n"
     "⚠️ Dropping 3–4 kg a day with sauna and running, diuretics or “cutting pills” risks fainting, kidney and heart problems — and kills your strength. Young athletes only under a coach's and doctor's supervision."),

    ("usage", 48, "Proteindan qorin dam bo'lishi va gaz",
     "proteindan qorin dam bo'ladi\nproteindan keyin qorin og'riyapti\nprotein ichsam gaz bo'ladi\nproteindan ich ketyapti\nот протеина вздутие\nпучит от протеина\nprotein bloating\nprotein gives me gas",
     "dam bo'l, gaz, vzdutie, вздут, пучит, qorin og'ri, ich ket, diareya, bloating, gas, stomach",
     "🫧 **Proteindan qorin dam bo'lishining 4 sababi va yechimi:**\n\n"
     "1️⃣ **Laktoza** (eng ko'p) — konsentratda ko'p. Yechim: **izolyat** yoki gidrolizat (laktoza deyarli yo'q), yoki vegan/mol go'shti proteini.\n"
     "2️⃣ **Sut bilan aralashtirish** — suv bilan ichib ko'ring.\n"
     "3️⃣ **Shirinlashtiruvchi va qo'shimchalar** (sukraloza, inulin, sorbitol) — ta'msiz yoki boshqa brendni sinang.\n"
     "4️⃣ **Katta porsiya bir martada / tez ichish** — 1 skupni yarmiga bo'ling, sekin iching, kunlik oqsilni ovqat bilan bo'ling.\n\n"
     "Tolasi kam ovqat va kam suv ham ta'sir qiladi. Belgilar 1–2 haftada o'tmasa yoki qusish, qon, kuchli og'riq bo'lsa — shifokorga.",
     "🫧 **4 причины вздутия от протеина и что делать:**\n\n"
     "1️⃣ **Лактоза** (чаще всего) — её много в концентрате. Решение: **изолят** или гидролизат (лактозы почти нет), либо веган/говяжий протеин.\n"
     "2️⃣ **Смешиваете с молоком** — попробуйте на воде.\n"
     "3️⃣ **Подсластители и добавки** (сукралоза, инулин, сорбит) — попробуйте без вкуса или другой бренд.\n"
     "4️⃣ **Большая порция за раз / пьёте залпом** — делите скуп пополам, пейте медленно, распределяйте белок с едой.\n\n"
     "Влияют и мало клетчатки и воды. Если не проходит за 1–2 недели или есть рвота, кровь, сильная боль — к врачу.",
     "🫧 **4 reasons protein bloats you and the fix:**\n\n"
     "1️⃣ **Lactose** (most common) — concentrate has plenty. Fix: **isolate** or hydrolysate (almost no lactose), or a vegan/beef protein.\n"
     "2️⃣ **Mixing with milk** — try water.\n"
     "3️⃣ **Sweeteners and additives** (sucralose, inulin, sorbitol) — try unflavoured or another brand.\n"
     "4️⃣ **A big serving at once / gulping it** — split the scoop, sip slowly, spread protein across meals.\n\n"
     "Low fibre and too little water matter too. If it doesn't settle in 1–2 weeks, or there's vomiting, blood or severe pain — see a doctor."),

    ("usage", 46, "Zalsiz uyda mashg'ulot va sport ozuqasi",
     "uyda mashq qilsam protein kerakmi\nzalga bormasdan mushak\nuyda mashg'ulot\nturnikda mashq\nтренировки дома\nнужен ли протеин если тренируюсь дома\nhome workout\ntraining at home",
     "uyda, zalsiz, turnik, brus, otjimaniya, дома, без зала, турник, home workout, at home, calisthenics",
     "🏠 **Uyda ham mushak o'sadi** — muhimi og'irlik emas, **yuklamaning oshib borishi**.\n\n"
     "Haftasiga 3–4 marta, butun tana:\n"
     "• Turnikda tortilish / stol ostida tortilish — 4×max\n"
     "• Otjimaniya (oyoq baland, sekin tushish) — 4×10–20\n"
     "• Bolgarcha o'tirib-turish, bir oyoqda — 3×10–15\n"
     "• Brus/stul orasida otjimaniya — 3×max\n"
     "• Planka, oyoq ko'tarish — 3×30–60 s\n"
     "Har hafta takror qo'shing yoki sekinroq bajaring; 15–20 dan oson bo'lsa — qiyinroq variant yoki ryukzakka og'irlik.\n\n"
     "Ozuqa zal bilan bir xil: oqsil 1,6–2,2 g/kg (ovqatdan yetmasa — protein), kreatin 3–5 g/kun uyda ham kuchni oshiradi. Uyda ishlaydigan aksessuarlar — rezina lentalar, gantel, turnik — katalogda.",
     "🏠 **Мышцы растут и дома** — важен не вес, а **рост нагрузки**.\n\n"
     "3–4 раза в неделю, всё тело:\n"
     "• Подтягивания / подтягивания под столом — 4×макс\n"
     "• Отжимания (ноги выше, медленный негатив) — 4×10–20\n"
     "• Болгарские выпады, приседания на одной ноге — 3×10–15\n"
     "• Отжимания на брусьях/между стульями — 3×макс\n"
     "• Планка, подъём ног — 3×30–60 с\n"
     "Каждую неделю добавляйте повторы или замедляйте темп; если 15–20 легко — усложните или добавьте вес в рюкзак.\n\n"
     "Питание как в зале: белок 1,6–2,2 г/кг (не хватает из еды — протеин), креатин 3–5 г/день повышает силу и дома. Аксессуары для дома — резинки, гантели, турник — в каталоге.",
     "🏠 **Muscle grows at home too** — what matters is **progressive load**, not the weight itself.\n\n"
     "3–4 times a week, full body:\n"
     "• Pull-ups / under-table rows — 4×max\n"
     "• Push-ups (feet raised, slow lowering) — 4×10–20\n"
     "• Bulgarian split squats, single-leg squats — 3×10–15\n"
     "• Dips on bars/between chairs — 3×max\n"
     "• Plank, leg raises — 3×30–60 s\n"
     "Add reps or slow the tempo every week; once 15–20 is easy, take a harder variation or load a backpack.\n\n"
     "Nutrition is the same as for the gym: protein 1.6–2.2 g/kg (protein powder if food falls short), creatine 3–5 g/day builds strength at home too. Home gear — bands, dumbbells, a pull-up bar — is in the catalogue."),

    ("faq", 47, "Homiladorlik va emizish davrida sport ozuqasi",
     "homiladorlikda protein ichsa bo'ladimi\nhomilador ayolga kreatin\nemizishda protein\nko'krak suti bilan boqishda vitamin\nпротеин при беременности\nможно ли кормящей протеин\nprotein while pregnant\nsupplements while breastfeeding",
     "homilador, homila, emiz, ko'krak suti, beremen, беремен, корм, лактац, pregnan, breastfeed",
     "🤰 **Avval shifokoringiz bilan maslahatlashing** — bu davrda har bir qo'shimcha individual.\n\n"
     "Odatda tavsiya etiladi (shifokor tayinlasa): **foliy kislotasi** (homiladorlikdan oldin va 1-trimestr), **temir**, **D vitamini**, **yod**, **omega-3 (DHA)** — maxsus homiladorlar uchun vitamin komplekslarida.\n\n"
     "• **Protein (izolyat, toza tarkib)** — ovqatdan oqsil yetmasa odatda mumkin; shirinlashtiruvchi va o'simlik ekstraktlari qo'shilmaganini tanlang.\n"
     "• ❌ **Tavsiya etilmaydi:** pre-workout, yog' yoqiruvchilar, kofeinli qo'shimchalar (kofein jami kuniga 200 mg dan kam), testosteron busterlar, o'simlik aralashmalari, katta dozali A vitamini.\n"
     "• **Kreatin, BCAA** — xavfsizligi yetarli o'rganilmagan, shifokor ruxsatisiz ichmang.\n\n"
     "Emizish davrida ham shu qoidalar: kofein va o'simlik ekstraktlari sutga o'tadi.",
     "🤰 **Сначала посоветуйтесь с врачом** — в этот период любые добавки индивидуальны.\n\n"
     "Обычно рекомендуют (если назначит врач): **фолиевую кислоту** (до беременности и в 1-м триместре), **железо**, **витамин D**, **йод**, **омега-3 (DHA)** — в специальных комплексах для беременных.\n\n"
     "• **Протеин (изолят, чистый состав)** — обычно можно, если белка из еды не хватает; выбирайте без подсластителей и растительных экстрактов.\n"
     "• ❌ **Не рекомендуется:** предтреники, жиросжигатели, добавки с кофеином (всего кофеина меньше 200 мг в день), тестобустеры, травяные смеси, большие дозы витамина A.\n"
     "• **Креатин, BCAA** — безопасность изучена мало, без разрешения врача не принимайте.\n\n"
     "При кормлении грудью те же правила: кофеин и экстракты трав проходят в молоко.",
     "🤰 **Talk to your doctor first** — every supplement is individual during this time.\n\n"
     "Usually recommended (if your doctor prescribes): **folic acid** (before pregnancy and in the 1st trimester), **iron**, **vitamin D**, **iodine**, **omega-3 (DHA)** — in prenatal multivitamins.\n\n"
     "• **Protein (isolate, clean label)** — usually fine if food falls short on protein; pick one without sweeteners or herbal extracts.\n"
     "• ❌ **Not recommended:** pre-workouts, fat burners, caffeinated supplements (keep total caffeine under 200 mg a day), testosterone boosters, herbal blends, high-dose vitamin A.\n"
     "• **Creatine, BCAA** — safety isn't well studied; don't take them without your doctor's OK.\n\n"
     "The same rules apply while breastfeeding: caffeine and herbal extracts pass into milk."),
]

TITLES = {
    "NutriZone ilovasini telefonga o'rnatish": ("Как установить приложение NutriZone", "Installing the NutriZone app"),
    "Ro'yxatdan o'tmasdan buyurtma berish": ("Заказ без регистрации", "Ordering without an account"),
    "Saytga kirish va ro'yxatdan o'tish": ("Вход и регистрация на сайте", "Signing in and registering"),
    "Narx tushsa xabar, sevimlilar va solishtirish": ("Уведомление о скидке, избранное и сравнение", "Price alerts, wishlist and compare"),
    "Vazn toifasiga tushirish: kurash, boks, dzyudo": ("Сгонка веса: борьба, бокс, дзюдо", "Making weight: wrestling, boxing, judo"),
    "Proteindan qorin dam bo'lishi va gaz": ("Вздутие и газы от протеина", "Bloating and gas from protein"),
    "Zalsiz uyda mashg'ulot va sport ozuqasi": ("Тренировки дома без зала и спортпит", "Training at home without a gym"),
    "Homiladorlik va emizish davrida sport ozuqasi": ("Спортпит при беременности и кормлении", "Supplements in pregnancy and breastfeeding"),
}

# extra real wordings for entries that already exist
QUESTIONS_ADD = {
    "Telegram bot va Mini App": "telegramdan buyurtma bersa bo'ladimi\nbot orqali zakaz\nзаказ через телеграм",
    "Buyurtmam qayerda": "buyurtmam qachon keladi\nzakazim qayerda\nкогда привезут заказ",
}
