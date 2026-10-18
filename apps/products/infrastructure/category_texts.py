"""
Long uz / ru / en category descriptions (2026-10-18): what the product type is, how it works, who it suits, how it is
typically used and what to look for when choosing. Dosing follows widely accepted guidance (e.g. the International
Society of Sports Nutrition position stands) and always defers to the label. Keyed by the category's English name as
in category_catalog.TREE; applied by `manage.py seed_descriptions`.
"""
from __future__ import annotations

# English name → (uz, ru, en)
CATEGORY_TEXTS: dict[str, tuple[str, str, str]] = {
    # ================================================================ Sports Nutrition
    "Sports Nutrition": (
        "Sport ozuqalari — mashg'ulot natijasini oshirish, mushaklarni tiklash va kundalik ovqatlanishdagi kamchiliklarni to'ldirish uchun yaratilgan mahsulotlar. Ular oddiy ovqatning o'rnini bosmaydi, balki uni aniq va qulay tarzda to'ldiradi.\n\n"
        "Bo'limda: proteinlar (mushak o'sishi va tiklanishi), kreatin (kuch va chidamlilik), geynerlar (vazn yig'ish), aminokislotalar, gidratatsiya, pre-workout va pump kompleksi, tiklanish vositalari va yog' yoquvchilar. Eng ko'p ilmiy isbotlangan mahsulotlar — protein, kreatin, kofein va beta-alanin.\n\n"
        "Qanday tanlash kerak: avval maqsadni aniqlang (massa, relyef, kuch, chidamlilik), keyin asosiy mahsulotlardan boshlang — protein va kreatin. Tarkibni o'qing, original mahsulotni ishonchli do'kondan oling. NutriZone'dagi barcha mahsulotlar rasmiy yetkazib beruvchilardan.\n\n"
        "Muhim: surunkali kasallik, homiladorlik yoki dori qabul qilayotgan bo'lsangiz, avval shifokor bilan maslahatlashing.",
        "Спортивное питание — продукты, которые помогают улучшить результат тренировок, восстановить мышцы и восполнить пробелы в рационе. Они не заменяют обычную еду, а точно и удобно её дополняют.\n\n"
        "В разделе: протеины (рост и восстановление мышц), креатин (сила и выносливость), гейнеры (набор веса), аминокислоты, гидратация, предтренировочные и памп-комплексы, средства восстановления и жиросжигатели. Наиболее научно доказанные продукты — протеин, креатин, кофеин и бета-аланин.\n\n"
        "Как выбирать: сначала определите цель (масса, рельеф, сила, выносливость), затем начните с базы — протеина и креатина. Читайте состав и покупайте оригинал в надёжном магазине. Вся продукция NutriZone — от официальных поставщиков.\n\n"
        "Важно: при хронических заболеваниях, беременности или приёме лекарств сначала проконсультируйтесь с врачом.",
        "Sports nutrition covers products designed to improve training results, help muscles recover and fill gaps in your everyday diet. They don't replace real food — they complement it precisely and conveniently.\n\n"
        "This section includes proteins (muscle growth and recovery), creatine (strength and endurance), gainers (weight gain), amino acids, hydration, pre-workout and pump formulas, recovery aids and fat burners. The best-researched products are protein, creatine, caffeine and beta-alanine.\n\n"
        "How to choose: define your goal first (size, definition, strength, endurance), then start with the basics — protein and creatine. Read the label and buy originals from a trusted store. Everything at NutriZone comes from official suppliers.\n\n"
        "Important: if you have a chronic condition, are pregnant or take medication, talk to a doctor first.",
    ),
    "Proteins": (
        "Protein (oqsil) — mushaklarning asosiy qurilish materiali. Sport proteini — oqsilning qulay, tez tayyorlanadigan va aniq dozalangan manbai: bir porsiyada odatda 20–30 g toza oqsil bo'ladi.\n\n"
        "Turlari: whey konsentrati (eng ommabop, narx-sifat), izolyat (90% gacha oqsil, laktoza kam), gidrolizat (eng tez so'riladi), kazein (sekin, kechasi uchun), mol go'shti proteini (sutsiz) va vegan protein (no'xat, guruch, soya).\n\n"
        "Qancha kerak: faol shug'ullanuvchilar uchun kuniga tana vaznining har kilogrammiga taxminan 1.4–2 g oqsil tavsiya etiladi (umumiy ovqat bilan birga). Proteinni mashg'ulotdan keyin, nonushtada yoki ovqatlar orasida ichish qulay.\n\n"
        "Tanlashda: porsiyadagi oqsil miqdori, uglevod va shakar, laktozaga sezgirlik, ta'mi va eruvchanligiga qarang.",
        "Протеин (белок) — главный строительный материал мышц. Спортивный протеин — удобный, быстро готовящийся и точно дозированный источник белка: в порции обычно 20–30 г чистого белка.\n\n"
        "Виды: концентрат сыворотки (самый популярный, баланс цены и качества), изолят (до 90% белка, мало лактозы), гидролизат (усваивается быстрее всего), казеин (медленный, на ночь), говяжий протеин (без молочного) и веганский протеин (горох, рис, соя).\n\n"
        "Сколько нужно: активно тренирующимся рекомендуют около 1,4–2 г белка на кг массы тела в сутки (вместе с обычной едой). Протеин удобно пить после тренировки, на завтрак или между приёмами пищи.\n\n"
        "При выборе смотрите на количество белка в порции, углеводы и сахар, чувствительность к лактозе, вкус и растворимость.",
        "Protein is the main building block of muscle. Sports protein is a convenient, quick and precisely dosed source of it, usually 20–30 g of pure protein per serving.\n\n"
        "Types: whey concentrate (the most popular, best value), isolate (up to 90% protein, low lactose), hydrolysate (fastest absorbing), casein (slow, for night-time), beef protein (dairy-free) and vegan protein (pea, rice, soy).\n\n"
        "How much: active people are generally advised to get about 1.4–2 g of protein per kg of body weight per day (including food). A shake is handy after training, at breakfast or between meals.\n\n"
        "When choosing, look at protein per serving, carbs and sugar, lactose sensitivity, taste and mixability.",
    ),
    "Whey Protein": (
        "Whey (zardob) proteini — sut zardobidan olinadigan, eng ko'p o'rganilgan va eng ommabop protein. U tez so'riladi, mushak o'sishini «yoqadigan» leysin aminokislotasiga boy va to'liq aminokislota tarkibiga ega.\n\n"
        "Konsentrat odatda 70–80% oqsil saqlaydi, ta'mi yumshoq va narxi maqbul. Mashg'ulotdan keyin 20–30 g, shuningdek nonushtada yoki ovqatlar orasida ichish mumkin. Laktozaga kuchli sezgir bo'lsangiz, izolyat yoki gidrolizatni tanlang.",
        "Сывороточный протеин (whey) получают из молочной сыворотки; это самый изученный и популярный протеин. Он быстро усваивается, богат лейцином — аминокислотой, «запускающей» рост мышц, — и имеет полный аминокислотный профиль.\n\n"
        "Концентрат обычно содержит 70–80% белка, у него мягкий вкус и доступная цена. Принимают 20–30 г после тренировки, а также на завтрак или между едой. При сильной чувствительности к лактозе выбирайте изолят или гидролизат.",
        "Whey protein comes from milk whey and is the most researched and popular protein. It absorbs quickly, is rich in leucine — the amino acid that switches on muscle growth — and has a complete amino-acid profile.\n\n"
        "Concentrate usually contains 70–80% protein, tastes smooth and is affordable. Take 20–30 g after training, at breakfast or between meals. If you are very lactose-sensitive, choose an isolate or hydrolysate.",
    ),
    "Whey Isolate": (
        "Whey izolyati — qo'shimcha filtrlash orqali yog', laktoza va uglevodlardan tozalangan zardob proteini: odatda 85–90% va undan ko'p oqsil. Shuning uchun u quritish (relyef) davri va laktozaga sezgirlar uchun eng yaxshi tanlov.\n\n"
        "Izolyat suvda oson eriydi, tez so'riladi va porsiyada kaloriyasi kam. Mashg'ulotdan keyin 25–30 g ichish odatiy. Tanlashda porsiyadagi oqsil foizi va «amino spiking» (aminokislotalar bilan sun'iy oshirish) yo'qligiga qarang.",
        "Изолят сывороточного протеина — белок, дополнительно очищенный фильтрацией от жира, лактозы и углеводов: обычно 85–90% белка и больше. Поэтому это лучший выбор на сушке и при чувствительности к лактозе.\n\n"
        "Изолят легко растворяется, быстро усваивается и малокалориен. Обычно принимают 25–30 г после тренировки. При выборе смотрите процент белка в порции и отсутствие «amino spiking» (искусственного завышения белка аминокислотами).",
        "Whey isolate is whey protein further filtered to remove fat, lactose and carbs, usually 85–90% protein or more — the best choice when cutting or if you are lactose-sensitive.\n\n"
        "It mixes easily, absorbs quickly and is low in calories. 25–30 g after training is typical. When choosing, check the protein percentage per serving and that there is no amino spiking (inflating protein with added amino acids).",
    ),
    "Hydrolyzed Whey": (
        "Gidrolizat — fermentlar yordamida qisman «parchalangan» zardob proteini. Oqsil kichik peptidlarga bo'linganligi sababli eng tez so'riladigan protein hisoblanadi va oshqozonga eng yengil.\n\n"
        "U intensiv mashg'ulotlardan keyin tez tiklanish, kuniga ikki marta shug'ullanadiganlar va hazm qilishi sezgir odamlar uchun qulay. Ta'mi biroz achchiqroq bo'lishi mumkin, narxi esa konsentrat va izolyatdan yuqori — bu yuqori tozalik va tezlik uchun to'lov.",
        "Гидролизат — сывороточный протеин, частично «расщеплённый» ферментами. Так как белок разбит на короткие пептиды, это самый быстро усваиваемый и самый лёгкий для желудка протеин.\n\n"
        "Он удобен для быстрого восстановления после интенсивных тренировок, при двух тренировках в день и при чувствительном пищеварении. Вкус может быть чуть горьковатым, а цена выше концентрата и изолята — это плата за чистоту и скорость.",
        "Hydrolysed whey is whey protein partly broken down by enzymes into short peptides, making it the fastest-absorbing and gentlest protein on the stomach.\n\n"
        "It suits fast recovery after intense sessions, people who train twice a day and those with a sensitive gut. It can taste slightly bitter and costs more than concentrate or isolate — the price of purity and speed.",
    ),
    "Casein": (
        "Kazein — sutdagi asosiy oqsil (80% ga yaqin). Oshqozonda gelga aylanib, aminokislotalarni 6–8 soat davomida sekin chiqaradi, shuning uchun uni «tungi protein» deyishadi.\n\n"
        "Uxlashdan oldin 30–40 g kazein tunda mushaklarning parchalanishini kamaytirishga va ertalabgacha to'qlik hissini saqlashga yordam beradi. Shuningdek, ovqatlanish orasida uzoq tanaffus bo'lganda ham qulay. Mitsellar kazein — eng sifatli shakli.",
        "Казеин — основной белок молока (около 80%). В желудке он образует гель и медленно высвобождает аминокислоты в течение 6–8 часов, поэтому его называют «ночным протеином».\n\n"
        "30–40 г казеина перед сном помогают уменьшить ночной распад мышц и сохранить сытость до утра. Он удобен и при длинных перерывах между едой. Мицеллярный казеин — самая качественная форма.",
        "Casein is milk's main protein (about 80%). It forms a gel in the stomach and releases amino acids slowly over 6–8 hours, which is why it's called the night-time protein.\n\n"
        "30–40 g before bed helps reduce overnight muscle breakdown and keeps you full until morning; it's also useful for long gaps between meals. Micellar casein is the highest-quality form.",
    ),
    "Beef Protein": (
        "Mol go'shti proteini — mol go'shtidan gidroliz usulida olinadigan izolyat. Tarkibida sut, laktoza va soya yo'q, shuning uchun sut mahsulotlarini ko'tara olmaydiganlar va paleo ovqatlanish tarafdorlari uchun ajoyib muqobil.\n\n"
        "Ko'pincha unga kreatin va BCAA qo'shiladi. Aminokislota tarkibi whey'dan biroz farq qiladi (kollagen aminokislotalariga boyroq), shuning uchun kunlik oqsil normasini turli manbalardan to'ldirish tavsiya etiladi. Ta'mi mevali yoki shokoladli bo'lib, suvda yaxshi eriydi.",
        "Говяжий протеин — изолят, получаемый из говядины методом гидролиза. В нём нет молока, лактозы и сои, поэтому это отличная альтернатива для тех, кто не переносит молочное, и для сторонников палео.\n\n"
        "Часто в него добавляют креатин и BCAA. Аминокислотный профиль немного отличается от сывороточного (больше «коллагеновых» аминокислот), поэтому дневную норму белка лучше набирать из разных источников. Вкусы обычно фруктовые или шоколадные, растворяется хорошо.",
        "Beef protein is an isolate made by hydrolysing beef. It contains no dairy, lactose or soy, so it's a great alternative for people who can't tolerate milk and for paleo eaters.\n\n"
        "It often comes with added creatine and BCAAs. Its amino-acid profile differs slightly from whey (richer in collagen-type amino acids), so it's best to get daily protein from several sources. Flavours are usually fruity or chocolate, and it mixes well with water.",
    ),
    "Vegan Protein": (
        "Vegan protein — o'simlik manbalaridan (no'xat, guruch, soya, kanop, nut) olinadigan protein. Hayvon mahsulotlarisiz ovqatlanuvchilar, laktozaga sezgirlar va ekologik tanlovni afzal ko'radiganlar uchun.\n\n"
        "Eng yaxshi vegan proteinlar bir necha manbani aralashtiradi (masalan, no'xat + guruch) — shunda aminokislota tarkibi to'liq bo'ladi. Porsiyada odatda 20–25 g oqsil. Tanlashda tarkibdagi manbalar, leysin miqdori va ta'miga e'tibor bering; o'simlik proteinlari biroz quyuqroq bo'ladi.",
        "Веганский протеин получают из растительных источников (горох, рис, соя, конопля, нут). Он для тех, кто не ест продукты животного происхождения, чувствителен к лактозе или делает экологичный выбор.\n\n"
        "Лучшие веганские протеины сочетают несколько источников (например, горох + рис), чтобы аминокислотный профиль был полным. В порции обычно 20–25 г белка. Смотрите на источники, количество лейцина и вкус; растительные протеины обычно чуть гуще.",
        "Vegan protein comes from plants (pea, rice, soy, hemp, chickpea). It's for people who avoid animal products, are lactose-sensitive or prefer a greener choice.\n\n"
        "The best vegan proteins blend several sources (such as pea + rice) to give a complete amino-acid profile, usually 20–25 g of protein per serving. Check the sources, leucine content and taste; plant proteins tend to be a little thicker.",
    ),
    "Creatine": (
        "Kreatin — dunyodagi eng ko'p o'rganilgan va samaradorligi isbotlangan sport qo'shimchasi. U mushaklardagi fosfokreatin zaxirasini oshirib, qisqa va kuchli harakatlar (shtanga, sprint, sakrash) uchun energiyani tez tiklaydi.\n\n"
        "Natija: ko'proq takrorlash, kuch va mushak hajmining o'sishi, mashg'ulotlar orasida tezroq tiklanish. Tadqiqotlar kreatinning miya faoliyati uchun foydasini ham o'rganmoqda.\n\n"
        "Qanday ichiladi: kuniga 3–5 g, har kuni (dam olish kunlari ham) — vaqti unchalik muhim emas. «Zagruzka» (5–7 kun kuniga 20 g) natijani tezlashtiradi, lekin shart emas. Yetarlicha suv iching.\n\n"
        "Turlari: monogidrat (eng ko'p isbotlangan, maqbul narx), HCl (yaxshi eriydi, kichik doza), Kre-Alkalyn (buferlangan shakl).",
        "Креатин — самая изученная и доказанно эффективная спортивная добавка в мире. Он увеличивает запасы фосфокреатина в мышцах и быстро восстанавливает энергию для коротких мощных усилий (штанга, спринт, прыжки).\n\n"
        "Результат: больше повторений, рост силы и объёма мышц, более быстрое восстановление между подходами. Исследуется и польза креатина для работы мозга.\n\n"
        "Как принимать: 3–5 г в день ежедневно (и в дни отдыха) — время приёма не так важно. «Загрузка» (20 г в день 5–7 дней) ускоряет эффект, но не обязательна. Пейте достаточно воды.\n\n"
        "Виды: моногидрат (самый доказанный и доступный), HCl (хорошо растворяется, маленькая доза), Kre-Alkalyn (буферизованная форма).",
        "Creatine is the most researched supplement in the world with proven effectiveness. It raises phosphocreatine stores in muscle and quickly restores energy for short, powerful efforts such as lifting, sprinting and jumping.\n\n"
        "The result: more reps, gains in strength and muscle size, and faster recovery between sets. Its benefits for brain function are also being studied.\n\n"
        "How to take it: 3–5 g every day (rest days too) — timing matters little. A loading phase (20 g a day for 5–7 days) speeds up results but isn't required. Drink enough water.\n\n"
        "Types: monohydrate (the most proven and affordable), HCl (dissolves well, small dose) and Kre-Alkalyn (a buffered form).",
    ),
    "Creatine Monohydrate": (
        "Kreatin monogidrat — kreatinning «oltin standarti»: yuzlab ilmiy tadqiqotlar uning kuch, quvvat va mushak hajmi uchun samaradorligi va xavfsizligini tasdiqlagan. Eng maqbul narxdagi va eng ishonchli shakl.\n\n"
        "Kuniga 3–5 g suv yoki sharbat bilan ichiladi. Mikronlashtirilgan (micronized) monogidrat suvda yaxshiroq eriydi. Creapure® belgisi — Germaniyada ishlab chiqarilgan yuqori tozalikdagi monogidratni bildiradi. Dastlabki haftalarda 1–2 kg vazn ortishi — mushaklardagi suv, bu normal.",
        "Креатин моногидрат — «золотой стандарт» креатина: сотни исследований подтвердили его эффективность для силы, мощности и объёма мышц, а также безопасность. Это самая доступная и надёжная форма.\n\n"
        "Принимают 3–5 г в день с водой или соком. Микронизированный моногидрат лучше растворяется. Знак Creapure® означает моногидрат высокой чистоты немецкого производства. Прибавка 1–2 кг в первые недели — это вода в мышцах, это нормально.",
        "Creatine monohydrate is the gold standard: hundreds of studies confirm its effectiveness for strength, power and muscle size, and its safety. It's the most affordable and reliable form.\n\n"
        "Take 3–5 g a day with water or juice. Micronised monohydrate dissolves better, and the Creapure® mark indicates high-purity monohydrate made in Germany. Gaining 1–2 kg in the first weeks is water stored in muscle — completely normal.",
    ),
    "Creatine HCL": (
        "Kreatin gidroxlorid (HCl) — kreatinning xlorid kislotasi bilan bog'langan shakli. U suvda monogidratdan ancha yaxshi eriydi, shuning uchun kichik dozada (odatda 1–2 g) qabul qilinadi va «zagruzka» talab qilmaydi.\n\n"
        "Monogidratdan oshqozon noqulayligi yoki «shishish» sezganlar uchun qulay muqobil. Bugungi tadqiqotlar HCl va monogidratning samaradorligi o'xshash ekanini ko'rsatadi; asosiy farq — qulaylik va kichik doza.",
        "Креатин гидрохлорид (HCl) — форма креатина, связанная с соляной кислотой. Он растворяется в воде намного лучше моногидрата, поэтому принимается маленькой дозой (обычно 1–2 г) и не требует «загрузки».\n\n"
        "Удобная альтернатива для тех, у кого моногидрат вызывает дискомфорт в желудке или «отёчность». Текущие исследования показывают сходную эффективность HCl и моногидрата; главное отличие — удобство и малая доза.",
        "Creatine hydrochloride (HCl) is creatine bound to hydrochloric acid. It dissolves far better than monohydrate, so it's taken in a small dose (usually 1–2 g) with no loading phase.\n\n"
        "It's a convenient alternative if monohydrate causes stomach discomfort or bloating. Current research shows similar effectiveness to monohydrate — the main difference is convenience and a smaller dose.",
    ),
    "Kre-Alkalyn": (
        "Kre-Alkalyn — pH darajasi oshirilgan («buferlangan») kreatin. Ishlab chiqaruvchilar uning oshqozonda barqarorroq ekanini va kichikroq dozada ishlashini ta'kidlaydi.\n\n"
        "Odatda kuniga 1.5–3 g kapsulada qabul qilinadi, «zagruzka» kerak emas. Mustaqil tadqiqotlar uni monogidratga yaqin samaradorlikda ko'rsatadi — shuning uchun u asosan qulaylikni va oshqozonga yengillikni qadrlaydiganlar uchun tanlov.",
        "Kre-Alkalyn — креатин с повышенным pH («буферизованный»). Производители указывают, что он стабильнее в желудке и работает в меньшей дозе.\n\n"
        "Обычно принимают 1,5–3 г в день в капсулах, без «загрузки». Независимые исследования показывают эффективность, близкую к моногидрату, — так что это выбор прежде всего для тех, кто ценит удобство и комфорт для желудка.",
        "Kre-Alkalyn is a pH-buffered creatine. Manufacturers say it is more stable in the stomach and works at a lower dose.\n\n"
        "It's usually taken as 1.5–3 g a day in capsules, with no loading. Independent studies show effectiveness close to monohydrate, so it's mainly a choice for people who value convenience and an easy stomach.",
    ),
    "Gainers": (
        "Geynerlar — uglevod va protein aralashmasi bo'lib, kunlik kaloriya miqdorini oshirish va vazn (massa) yig'ishga yordam beradi. Bir porsiyada 400–1200 kkal, 25–60 g protein bo'lishi mumkin.\n\n"
        "Ular asosan tabiatan ozg'in, tez metabolizmli («ektomorf») odamlar va ovqat bilan yetarli kaloriya olishga ulgurmaydiganlar uchun. Geyner mashg'ulotdan keyin yoki ovqatlar orasida ichiladi.\n\n"
        "Turlari: mass gainer (yuqori kaloriyali, uglevod ko'p) va lean gainer (protein ulushi yuqori, «toza» massa uchun). Tanlashda protein-uglevod nisbati, shakar miqdori va porsiya hajmiga qarang. Ortiqcha vazn yig'ishga moyil bo'lsangiz, oddiy protein va ratsion yetarli.",
        "Гейнеры — смесь углеводов и белка, которая помогает увеличить суточную калорийность и набрать вес (массу). В порции может быть 400–1200 ккал и 25–60 г белка.\n\n"
        "Они прежде всего для худощавых людей с быстрым метаболизмом («эктоморфов») и для тех, кто не успевает добрать калории едой. Гейнер пьют после тренировки или между приёмами пищи.\n\n"
        "Виды: mass gainer (высококалорийный, много углеводов) и lean gainer (больше белка, для «чистой» массы). При выборе смотрите соотношение белка и углеводов, сахар и размер порции. Если вы склонны к лишнему весу, достаточно обычного протеина и рациона.",
        "Gainers are carbohydrate-and-protein blends that raise your daily calorie intake and help you gain weight and mass. A serving can contain 400–1,200 kcal and 25–60 g of protein.\n\n"
        "They're mainly for naturally slim people with a fast metabolism (hard-gainers) and anyone who can't eat enough calories from food. Drink one after training or between meals.\n\n"
        "Types: mass gainers (high-calorie, carb-heavy) and lean gainers (more protein, for cleaner mass). Check the protein-to-carb ratio, sugar and serving size. If you gain fat easily, regular protein and a good diet are enough.",
    ),
    "Mass Gainer": (
        "Mass gainer — yuqori kaloriyali geyner: porsiyada odatda 700–1250 kkal, uglevodlar va proteinning nisbati taxminan 3:1 yoki 4:1. Vazn yig'ishda qiynalayotgan ozg'in odamlar uchun eng tez yo'l.\n\n"
        "Kunlik porsiyani 2–3 qismga bo'lib ichish oshqozonga yengilroq. Sifatli geynerda murakkab uglevodlar (maltodekstrin, suli) bor va shakar kam. Natija uchun kuch mashg'ulotlari shart — aks holda ortiqcha kaloriya yog'ga aylanadi.",
        "Mass gainer — высококалорийный гейнер: в порции обычно 700–1250 ккал, соотношение углеводов и белка примерно 3:1 или 4:1. Самый быстрый путь для худощавых, которым трудно набрать вес.\n\n"
        "Суточную порцию легче делить на 2–3 приёма. В качественном гейнере сложные углеводы (мальтодекстрин, овёс) и мало сахара. Для результата обязательны силовые тренировки — иначе лишние калории уйдут в жир.",
        "A mass gainer is a high-calorie gainer, usually 700–1,250 kcal per serving with roughly a 3:1 or 4:1 carb-to-protein ratio — the fastest route for slim people who struggle to gain weight.\n\n"
        "Splitting the daily serving into 2–3 shakes is easier on the stomach. Quality gainers use complex carbs (maltodextrin, oats) and little sugar. Strength training is essential — otherwise the extra calories turn into fat.",
    ),
    "Lean Gainer": (
        "Lean gainer — protein ulushi yuqoriroq (odatda 1:1 dan 2:1 gacha uglevodga) va kaloriyasi o'rtacha bo'lgan geyner. U ortiqcha yog'siz «toza» mushak massasi yig'ish uchun mo'ljallangan.\n\n"
        "Normal tana tuzilishidagi, yog' yig'ishga moyil bo'lgan, lekin massa ustida ishlayotgan sportchilar uchun mos. Ko'pincha tarkibiga kreatin, MCT yoki suli uni qo'shiladi. Mashg'ulotdan keyin yoki nonushtaga qo'shimcha sifatida ichiladi.",
        "Lean gainer — гейнер с более высокой долей белка (обычно от 1:1 до 2:1 к углеводам) и умеренной калорийностью. Он рассчитан на набор «чистой» мышечной массы без лишнего жира.\n\n"
        "Подходит спортсменам с нормальным телосложением, склонным к набору жира, но работающим на массу. Часто содержит креатин, MCT или овсяную муку. Пьют после тренировки или как дополнение к завтраку.",
        "A lean gainer has more protein (usually a 1:1 to 2:1 carb-to-protein ratio) and moderate calories. It's designed for clean muscle gain without excess fat.\n\n"
        "It suits athletes with an average build who gain fat easily but are working on mass. It often includes creatine, MCTs or oat flour. Drink it after training or alongside breakfast.",
    ),
    "Amino Acids": (
        "Aminokislotalar — oqsilni tashkil etuvchi «g'ishtlar». Organizm 9 ta almashtirib bo'lmaydigan aminokislotani (EAA) o'zi ishlab chiqara olmaydi, ulardan uchtasi — leysin, izoleysin va valin — BCAA deb ataladi.\n\n"
        "Aminokislota qo'shimchalari mashg'ulot paytida va undan keyin mushaklarni himoya qilish, charchoqni kamaytirish va tiklanishni qo'llab-quvvatlash uchun ishlatiladi. Ular ayniqsa och qoringa mashq qilganda, uzoq yoki ikki martalik mashg'ulotlarda va kaloriya cheklangan (quritish) davrda foydali.\n\n"
        "Bilish kerak: kunlik protein yetarli bo'lsa, aminokislotalarning qo'shimcha samarasi kichikroq. To'liq EAA kompleksi odatda faqat BCAA'dan samaraliroq.",
        "Аминокислоты — «кирпичики», из которых состоит белок. Организм не может сам синтезировать 9 незаменимых аминокислот (EAA); три из них — лейцин, изолейцин и валин — называют BCAA.\n\n"
        "Аминокислотные добавки применяют во время и после тренировки, чтобы защитить мышцы, уменьшить усталость и поддержать восстановление. Особенно полезны при тренировках натощак, длинных или двойных тренировках и в период сушки с дефицитом калорий.\n\n"
        "Стоит знать: если белка в рационе достаточно, дополнительный эффект аминокислот меньше. Полный комплекс EAA обычно эффективнее, чем только BCAA.",
        "Amino acids are the building blocks of protein. The body can't make the 9 essential amino acids (EAAs) itself; three of them — leucine, isoleucine and valine — are called BCAAs.\n\n"
        "Amino supplements are used during and after training to protect muscle, reduce fatigue and support recovery. They're especially useful for fasted, long or twice-a-day sessions and during a calorie-restricted cut.\n\n"
        "Good to know: if you already eat enough protein, the extra benefit is smaller. A complete EAA complex is usually more effective than BCAAs alone.",
    ),
    "BCAA": (
        "BCAA — tarmoqlangan zanjirli uchta aminokislota: leysin, izoleysin va valin (ko'pincha 2:1:1 nisbatda). Leysin mushak oqsili sintezini ishga tushiradi, izoleysin va valin esa energiya va charchoqni kamaytirishda ishtirok etadi.\n\n"
        "Odatda mashg'ulot davomida 5–10 g suvda eritilgan holda ichiladi — mazali ichimlik suv ichishni ham rag'batlantiradi. Ko'p BCAA'larga elektrolitlar qo'shilgan. Shakar va kaloriya deyarli yo'q, shuning uchun quritish davri uchun qulay.",
        "BCAA — три аминокислоты с разветвлённой цепью: лейцин, изолейцин и валин (часто в соотношении 2:1:1). Лейцин запускает синтез мышечного белка, а изолейцин и валин участвуют в энергообеспечении и снижении усталости.\n\n"
        "Обычно 5–10 г растворяют в воде и пьют во время тренировки — вкусный напиток ещё и помогает пить больше воды. Во многие BCAA добавлены электролиты. Сахара и калорий почти нет, поэтому они удобны на сушке.",
        "BCAAs are the three branched-chain amino acids — leucine, isoleucine and valine (often in a 2:1:1 ratio). Leucine switches on muscle-protein synthesis, while isoleucine and valine support energy and help reduce fatigue.\n\n"
        "Usually 5–10 g is mixed with water and sipped during training — a tasty drink also helps you drink more. Many BCAAs include electrolytes, and with almost no sugar or calories they're handy when cutting.",
    ),
    "EAA": (
        "EAA — organizm o'zi ishlab chiqara olmaydigan barcha 9 ta almashtirib bo'lmaydigan aminokislota (BCAA'ni ham o'z ichiga oladi). Mushak oqsili sintezi uchun barcha 9 tasi kerak, shuning uchun EAA faqat BCAA'dan ko'ra to'liqroq va samaraliroq tanlov hisoblanadi.\n\n"
        "Mashg'ulot davomida yoki undan keyin 8–15 g ichiladi. Ayniqsa ovqatdan uzoq vaqt o'tib yoki och qoringa shug'ullanadiganlar, vegetarianlar va kaloriyasi cheklangan sportchilar uchun foydali.",
        "EAA — все 9 незаменимых аминокислот, которые организм не синтезирует сам (включая BCAA). Для синтеза мышечного белка нужны все девять, поэтому EAA — более полный и эффективный выбор, чем только BCAA.\n\n"
        "Принимают 8–15 г во время или после тренировки. Особенно полезны тем, кто тренируется натощак или спустя долгое время после еды, вегетарианцам и спортсменам с ограничением калорий.",
        "EAAs are all 9 essential amino acids your body can't make (BCAAs included). Muscle-protein synthesis needs all nine, so EAAs are a more complete and effective choice than BCAAs alone.\n\n"
        "Take 8–15 g during or after training. They're especially useful for fasted training or long gaps after meals, for vegetarians and for athletes on a calorie deficit.",
    ),
    "Amino Complex": (
        "Aminokompleks — to'liq aminokislota tarkibiga ega mahsulot: ko'pincha gidrolizlangan oqsil (zardob yoki mol go'shti) asosida tabletka yoki kapsulada. U proteinning «ixcham» shakli — suv va shaker kerak emas.\n\n"
        "Mashg'ulotdan oldin, keyin yoki ovqatlar orasida bir necha tabletka qabul qilinadi. Yo'lda, ishda yoki protein ichish noqulay bo'lgan vaziyatlarda qulay. Tanlashda bir porsiyadagi aminokislotalar miqdoriga qarang.",
        "Аминокомплекс — продукт с полным аминокислотным профилем, часто на основе гидролизованного белка (сывороточного или говяжьего) в таблетках или капсулах. Это «компактная» форма протеина — не нужны вода и шейкер.\n\n"
        "Принимают несколько таблеток до, после тренировки или между едой. Удобно в дороге, на работе и там, где пить протеин неудобно. При выборе смотрите количество аминокислот в порции.",
        "An amino complex provides a full amino-acid profile, often from hydrolysed protein (whey or beef) in tablets or capsules — a compact form of protein with no water or shaker needed.\n\n"
        "Take a few tablets before or after training or between meals. Handy on the go, at work or anywhere a shake is impractical. Check the amount of amino acids per serving.",
    ),
    "Hydration": (
        "Gidratatsiya — mashg'ulot paytida suv-tuz balansini saqlash. Terlash bilan organizm faqat suvni emas, balki elektrolitlarni — natriy, kaliy, magniy va xloridni ham yo'qotadi. Tana vaznining atigi 2% suvsizlanishi chidamlilik va diqqatni sezilarli pasaytiradi.\n\n"
        "Bo'limda izotonik ichimliklar (tez energiya + elektrolitlar) va elektrolit kukunlari/tabletkalari (shakarsiz suv-tuz balansi) bor.\n\n"
        "Kimga kerak: 60 daqiqadan uzoq mashg'ulotlar, issiq havoda yoki yopiq zalda ko'p terlaydiganlar, yuguruvchilar, futbolchilar, velosipedchilar va jang san'atlari bilan shug'ullanuvchilar. Oddiy 30–45 daqiqalik mashg'ulot uchun toza suv odatda yetarli.",
        "Гидратация — поддержание водно-солевого баланса во время тренировки. С потом организм теряет не только воду, но и электролиты — натрий, калий, магний и хлориды. Обезвоживание всего на 2% массы тела заметно снижает выносливость и концентрацию.\n\n"
        "В разделе изотоники (быстрая энергия + электролиты) и электролиты в порошке и таблетках (водно-солевой баланс без сахара).\n\n"
        "Кому нужно: при тренировках дольше 60 минут, при сильном потоотделении в жару или в зале, бегунам, футболистам, велосипедистам и единоборцам. Для обычной тренировки на 30–45 минут обычно достаточно чистой воды.",
        "Hydration is about keeping your fluid and salt balance during training. Sweat removes not only water but also electrolytes — sodium, potassium, magnesium and chloride. Losing just 2% of body weight as fluid noticeably reduces endurance and focus.\n\n"
        "This section has isotonic drinks (quick energy plus electrolytes) and electrolyte powders and tablets (fluid balance without sugar).\n\n"
        "Who needs it: anyone training for more than 60 minutes, heavy sweaters in the heat or indoors, runners, footballers, cyclists and combat-sports athletes. For a regular 30–45-minute session, plain water is usually enough.",
    ),
    "Isotonic": (
        "Izotonik — qon plazmasiga yaqin konsentratsiyadagi ichimlik: tarkibidagi uglevodlar (odatda 6–8%) va elektrolitlar tez so'riladi. U bir vaqtning o'zida suyuqlik, energiya va tuzlarni to'ldiradi.\n\n"
        "Uzoq (60–90 daqiqadan ortiq) va intensiv mashg'ulotlar, musobaqalar, yugurish va jamoaviy sport turlari uchun mo'ljallangan. Kukunni ko'rsatilgan miqdordagi suvda eritib, mashg'ulot davomida kichik qultumlar bilan ichiladi.",
        "Изотоник — напиток с концентрацией, близкой к плазме крови: углеводы (обычно 6–8%) и электролиты из него быстро усваиваются. Он одновременно восполняет жидкость, энергию и соли.\n\n"
        "Рассчитан на длительные (более 60–90 минут) и интенсивные тренировки, соревнования, бег и командные виды спорта. Порошок разводят в указанном количестве воды и пьют небольшими глотками во время тренировки.",
        "An isotonic drink has a concentration close to blood plasma, so its carbs (usually 6–8%) and electrolytes are absorbed fast, replacing fluid, energy and salts at the same time.\n\n"
        "It's designed for long (60–90+ minutes) and intense training, competition, running and team sports. Mix the powder with the stated amount of water and sip during training.",
    ),
    "Electrolytes": (
        "Elektrolitlar — natriy, kaliy, magniy va xlorid: ular asab signallari, mushak qisqarishi va suv balansini boshqaradi. Ularning yetishmasligi charchoq, bosh og'rig'i va mushak tirishishiga olib kelishi mumkin.\n\n"
        "Elektrolit kukunlari va tabletkalari odatda shakarsiz yoki kam shakarli bo'ladi — ko'p terlaganda, issiq havoda, uzoq mashg'ulotlarda, past uglevodli (keto) ovqatlanishda va saunadan keyin qulay. Suvga qo'shib, mashg'ulot paytida va keyin ichiladi.",
        "Электролиты — натрий, калий, магний и хлориды: они управляют нервными сигналами, сокращением мышц и водным балансом. Их нехватка может вызывать усталость, головную боль и судороги.\n\n"
        "Электролиты в порошке и таблетках обычно без сахара или с минимумом сахара — удобны при сильном потоотделении, в жару, на длинных тренировках, на низкоуглеводном (кето) питании и после сауны. Добавляют в воду и пьют во время и после тренировки.",
        "Electrolytes — sodium, potassium, magnesium and chloride — control nerve signals, muscle contraction and fluid balance. Running low can cause fatigue, headaches and cramps.\n\n"
        "Electrolyte powders and tablets are usually sugar-free or low in sugar — handy when you sweat a lot, in hot weather, during long sessions, on a low-carb (keto) diet and after the sauna. Add to water and drink during and after training.",
    ),
    "Performance": (
        "Performance (sport unumdorligi) bo'limida chidamlilik, kuch va mashg'ulot sifatini oshirishga yordam beradigan aminokislotalar bor: arginin, sitrullin va beta-alanin.\n\n"
        "Arginin va sitrullin azot oksidi (NO) hosil bo'lishini qo'llab-quvvatlaydi — bu qon tomirlarining kengayishi, mushaklarga qon va kislorod oqimi va «pump» hissi uchun muhim. Sitrullin tadqiqotlarda argininga qaraganda samaraliroq ekanligini ko'rsatgan. Beta-alanin esa mushaklardagi karnozin zaxirasini oshirib, 1–4 daqiqalik intensiv yuklamalarda charchoqni kechiktiradi.\n\n"
        "Bu mahsulotlarni alohida yoki o'z pre-workout aralashmangizga qo'shish mumkin — dozani aniq nazorat qilishni yoqtiradiganlar uchun qulay.",
        "В разделе Performance (спортивная производительность) — аминокислоты, которые помогают повысить выносливость, силу и качество тренировки: аргинин, цитруллин и бета-аланин.\n\n"
        "Аргинин и цитруллин поддерживают образование оксида азота (NO) — это расширение сосудов, приток крови и кислорода к мышцам и ощущение пампа. В исследованиях цитруллин показал себя эффективнее аргинина. Бета-аланин увеличивает запасы карнозина в мышцах и отодвигает усталость при интенсивных нагрузках длительностью 1–4 минуты.\n\n"
        "Эти продукты можно принимать отдельно или добавлять в свой предтренировочный «микс» — удобно тем, кто любит точно контролировать дозировки.",
        "The Performance section covers amino acids that help improve endurance, strength and training quality: arginine, citrulline and beta-alanine.\n\n"
        "Arginine and citrulline support nitric oxide (NO) production — wider blood vessels, more blood and oxygen to the muscles and that pump feeling; in studies citrulline has proved more effective than arginine. Beta-alanine raises muscle carnosine and delays fatigue during intense efforts lasting 1–4 minutes.\n\n"
        "Take them on their own or add them to your own pre-workout mix — ideal if you like full control over doses.",
    ),
    "Arginine": (
        "L-arginin — azot oksidi (NO) hosil bo'lishida ishtirok etuvchi aminokislota. NO qon tomirlarini kengaytirib, mushaklarga qon oqimini yaxshilaydi; shuningdek arginin immunitet va o'sish gormonlari almashinuvida ham ishtirok etadi.\n\n"
        "Odatda mashg'ulotdan 30–60 daqiqa oldin 3–6 g qabul qilinadi. Arginin ichakda qisman parchalanadi, shuning uchun ko'pincha sitrullin bilan birga ishlatiladi. Qon bosimini tushiruvchi dorilar qabul qilayotgan bo'lsangiz, shifokor bilan maslahatlashing.",
        "L-аргинин — аминокислота, участвующая в образовании оксида азота (NO). NO расширяет сосуды и улучшает приток крови к мышцам; аргинин также участвует в работе иммунитета и обмене гормонов роста.\n\n"
        "Обычно принимают 3–6 г за 30–60 минут до тренировки. Аргинин частично разрушается в кишечнике, поэтому его часто сочетают с цитруллином. При приёме препаратов, снижающих давление, проконсультируйтесь с врачом.",
        "L-arginine is an amino acid involved in making nitric oxide (NO), which widens blood vessels and improves blood flow to muscles; arginine also plays a role in immunity and growth-hormone metabolism.\n\n"
        "A typical dose is 3–6 g 30–60 minutes before training. Some arginine is broken down in the gut, so it's often combined with citrulline. If you take blood-pressure medication, check with your doctor.",
    ),
    "Citrulline": (
        "L-sitrullin — tarvuzda ko'p uchraydigan aminokislota. Organizmda u argininga aylanadi va argininning o'zidan ko'ra qondagi arginin darajasini samaraliroq oshiradi — natijada azot oksidi ko'proq hosil bo'ladi.\n\n"
        "Tadqiqotlarda sitrullin malat (6–8 g mashg'ulotdan oldin) takrorlashlar sonini oshirgan va mashg'ulotdan keyingi mushak og'rig'ini kamaytirgan. U kuchli «pump» va chidamlilik uchun eng yaxshi stimulyatorsiz ingredientlardan biri. Sof L-sitrullin uchun doza odatda 3–6 g.",
        "L-цитруллин — аминокислота, которой много в арбузе. В организме он превращается в аргинин и повышает его уровень в крови эффективнее, чем сам аргинин, — в результате образуется больше оксида азота.\n\n"
        "В исследованиях цитруллин малат (6–8 г перед тренировкой) увеличивал число повторений и уменьшал мышечную боль после тренировки. Это один из лучших ингредиентов без стимуляторов для пампа и выносливости. Для чистого L-цитруллина доза обычно 3–6 г.",
        "L-citrulline is an amino acid found in watermelon. The body converts it into arginine, raising blood arginine more effectively than arginine itself and producing more nitric oxide.\n\n"
        "In studies, citrulline malate (6–8 g before training) increased reps and reduced post-workout soreness — one of the best stimulant-free ingredients for pump and endurance. Pure L-citrulline is usually dosed at 3–6 g.",
    ),
    "Beta-Alanine": (
        "Beta-alanin — mushaklardagi karnozin miqdorini oshiruvchi aminokislota. Karnozin intensiv mashg'ulot paytida to'planadigan kislotalikni neytrallab, charchoqni kechiktiradi — ayniqsa 1–4 daqiqalik yuklamalarda (ko'p takrorli setlar, sprint, krossfit, kurash).\n\n"
        "Samara asta-sekin to'planadi: kuniga 3.2–6.4 g, kamida 2–4 hafta muntazam. Terida vaqtinchalik «sanchiluvchi» his (paresteziya) paydo bo'lishi zararsiz; uni kamaytirish uchun dozani bir necha qismga bo'ling.",
        "Бета-аланин — аминокислота, повышающая содержание карнозина в мышцах. Карнозин нейтрализует закисление при интенсивной работе и отодвигает усталость — особенно при нагрузках 1–4 минуты (многоповторные подходы, спринт, кроссфит, единоборства).\n\n"
        "Эффект накапливается постепенно: 3,2–6,4 г в день регулярно минимум 2–4 недели. Временное «покалывание» кожи (парестезия) безвредно; чтобы его уменьшить, делите дозу на несколько приёмов.",
        "Beta-alanine raises muscle carnosine, which buffers the acidity that builds up during intense work and delays fatigue — especially in efforts lasting 1–4 minutes (high-rep sets, sprints, CrossFit, combat sports).\n\n"
        "The effect builds up over time: 3.2–6.4 g a day for at least 2–4 weeks. A temporary tingling of the skin (paraesthesia) is harmless; split the dose to reduce it.",
    ),
    "Pre-Workout": (
        "Pre-workout — mashg'ulotdan 20–30 daqiqa oldin ichiladigan kompleks: energiya, diqqat, kuch va «pump»ni oshirish uchun. Odatda tarkibida kofein, sitrullin, beta-alanin, betain, tirozin va boshqa ingredientlar bo'ladi.\n\n"
        "Turlari: stimulyatorli (kofein va boshqa stimulyatorlar — kuchli energiya), stimulyatorsiz (kechki mashg'ulotlar va kofeinga sezgirlar uchun) va hardcore (juda yuqori dozalar, faqat tajribali sportchilar uchun).\n\n"
        "Xavfsizlik: kofeinning kunlik umumiy miqdori sog'lom kattalar uchun odatda 400 mg dan oshmasligi tavsiya etiladi (qahva va energetiklar bilan birga). Birinchi marta yarim porsiyadan boshlang, uxlashdan 6 soat oldin ichmang. Yurak, qon bosimi muammolari, homiladorlik va 18 yoshgacha bo'lganlarga stimulyatorli pre-workout tavsiya etilmaydi.",
        "Предтренировочный комплекс (pre-workout) пьют за 20–30 минут до тренировки, чтобы повысить энергию, концентрацию, силу и памп. Обычно в составе кофеин, цитруллин, бета-аланин, бетаин, тирозин и другие ингредиенты.\n\n"
        "Виды: со стимуляторами (кофеин и другие — мощная энергия), без стимуляторов (для вечерних тренировок и чувствительных к кофеину) и hardcore (очень высокие дозы, только для опытных спортсменов).\n\n"
        "Безопасность: здоровым взрослым обычно рекомендуют не превышать 400 мг кофеина в сутки (вместе с кофе и энергетиками). Начинайте с половины порции, не принимайте менее чем за 6 часов до сна. Стимуляторные предтреники не рекомендуются при проблемах с сердцем и давлением, при беременности и до 18 лет.",
        "A pre-workout is taken 20–30 minutes before training to boost energy, focus, strength and pump. Typical ingredients include caffeine, citrulline, beta-alanine, betaine and tyrosine.\n\n"
        "Types: stim (caffeine and other stimulants for strong energy), stim-free (for evening sessions and caffeine-sensitive people) and hardcore (very high doses, for experienced athletes only).\n\n"
        "Safety: healthy adults are generally advised to stay under 400 mg of caffeine a day in total (including coffee and energy drinks). Start with half a scoop and avoid taking it within 6 hours of sleep. Stimulant pre-workouts are not recommended with heart or blood-pressure problems, during pregnancy or under 18.",
    ),
    "Stim": (
        "Stimulyatorli pre-workoutlar asosida kofein (odatda porsiyada 150–300 mg) va ba'zan boshqa stimulyatorlar bo'ladi. Ular tez energiya, kuchli diqqat va «yonib» shug'ullanish hissini beradi, charchoqni kamroq sezdiradi.\n\n"
        "Ertalabki va kunduzgi mashg'ulotlar uchun eng mos. Kunlik kofein miqdoringizni hisobga oling, bo'sh qoringa ichganda ta'sir kuchliroq bo'ladi. Doimiy ichganda tolerantlik paydo bo'ladi — vaqti-vaqti bilan 1–2 haftalik tanaffus qiling.",
        "Предтреники со стимуляторами основаны на кофеине (обычно 150–300 мг в порции) и иногда других стимуляторах. Они дают быструю энергию, мощный фокус и ощущение «заряда», меньше чувствуется усталость.\n\n"
        "Лучше всего подходят для утренних и дневных тренировок. Учитывайте суточное количество кофеина; натощак действие сильнее. При постоянном приёме развивается привыкание — периодически делайте перерыв на 1–2 недели.",
        "Stimulant pre-workouts are built on caffeine (usually 150–300 mg per serving) and sometimes other stimulants. They give fast energy, sharp focus and that fired-up feeling, while making fatigue less noticeable.\n\n"
        "Best for morning and daytime sessions. Count your daily caffeine; the effect is stronger on an empty stomach. Tolerance builds with daily use, so take a 1–2-week break now and then.",
    ),
    "Stim-Free": (
        "Stimulyatorsiz pre-workoutlar kofeinsiz ishlaydi: ular sitrullin, arginin, beta-alanin, betain, glitserin va nootroplar (masalan, alfa-GPC, tirozin) hisobiga «pump», chidamlilik va diqqatni oshiradi.\n\n"
        "Kechki mashg'ulotlar (uyquni buzmaydi), kofeinga sezgirlar va qahva ichadiganlar uchun ideal. Shuningdek, stimulyatorli pre-workoutdan tanaffus olayotgan paytda ham qulay. Natijasi «portlovchi» energiya emas, balki toza pump va barqaror ishlash qobiliyati.",
        "Предтреники без стимуляторов работают без кофеина: за счёт цитруллина, аргинина, бета-аланина, бетаина, глицерина и ноотропов (например, альфа-GPC, тирозина) они усиливают памп, выносливость и концентрацию.\n\n"
        "Идеальны для вечерних тренировок (не мешают сну), для чувствительных к кофеину и любителей кофе, а также на время перерыва от стимуляторных предтреников. Результат — не «взрывная» энергия, а чистый памп и стабильная работоспособность.",
        "Stim-free pre-workouts contain no caffeine and boost pump, endurance and focus through citrulline, arginine, beta-alanine, betaine, glycerol and nootropics such as alpha-GPC and tyrosine.\n\n"
        "They're ideal for evening sessions (no effect on sleep), for caffeine-sensitive people and coffee drinkers, and for breaks from stimulant pre-workouts. The result is clean pump and steady performance rather than explosive energy.",
    ),
    "Hardcore": (
        "Hardcore pre-workoutlar — juda yuqori dozali, kuchli stimulyatorli formulalar (porsiyada ko'pincha 300 mg+ kofein va qo'shimcha stimulyatorlar). Ular faqat stimulyatorlarga ko'nikkan tajribali sportchilar uchun.\n\n"
        "Albatta yarim porsiyadan boshlang, boshqa kofeinli ichimliklar bilan birga ichmang va kechqurun qabul qilmang. Yurak-qon tomir kasalliklari, bosim, xavotir, uyqu buzilishi bo'lsa yoki doping nazoratidan o'tadigan bo'lsangiz — tanlamang. Tarkibni har doim yorliqdan tekshiring.",
        "Hardcore предтреники — формулы с очень высокими дозами и мощными стимуляторами (часто 300+ мг кофеина и дополнительные стимуляторы в порции). Они только для опытных спортсменов, привыкших к стимуляторам.\n\n"
        "Обязательно начинайте с половины порции, не сочетайте с другими кофеиносодержащими напитками и не принимайте вечером. Не выбирайте их при болезнях сердца и сосудов, давлении, тревожности, нарушениях сна или если проходите допинг-контроль. Всегда проверяйте состав на этикетке.",
        "Hardcore pre-workouts are very high-dose, strongly stimulant formulas (often 300+ mg of caffeine plus extra stimulants per serving). They're for experienced, stimulant-tolerant athletes only.\n\n"
        "Always start with half a scoop, don't combine with other caffeinated drinks and don't take in the evening. Avoid them if you have heart or blood-pressure issues, anxiety or sleep problems, or are drug-tested. Always check the label.",
    ),
    "Pump": (
        "Pump — mashg'ulot paytida mushaklarning qon bilan to'lishi natijasida yuzaga keladigan «to'lish», hajm va qattiqlik hissi. Pump komplekslari azot oksidi (NO) hosil bo'lishini, qon oqimini va mushak hujayralarida suv ushlanishini qo'llab-quvvatlaydi.\n\n"
        "Asosiy ingredientlar: sitrullin, arginin, nitratlar (lavlagi ekstrakti), agmatin va glitserin. Ko'pchilik pump formulalari stimulyatorsiz — shuning uchun ularni kechki mashg'ulotlarda yoki stimulyatorli pre-workout bilan birga ichish mumkin.\n\n"
        "Kimga mos: bodibilding va fitnes, mushak hajmi va «aqliy-mushak bog'lanishi»ni his qilish muhim bo'lgan mashg'ulotlar. Ta'sir mashg'ulotdan 20–40 daqiqa oldin ichilganda eng yaxshi.",
        "Памп — ощущение «наполненности», объёма и твёрдости мышц, когда во время тренировки они наполняются кровью. Памп-комплексы поддерживают образование оксида азота (NO), кровоток и задержку воды в мышечных клетках.\n\n"
        "Ключевые ингредиенты: цитруллин, аргинин, нитраты (экстракт свёклы), агматин и глицерин. Большинство памп-формул без стимуляторов — их можно пить вечером или вместе со стимуляторным предтреником.\n\n"
        "Кому подойдёт: бодибилдинг и фитнес — тренировки, где важны объём мышц и нейромышечная связь. Лучший эффект — при приёме за 20–40 минут до тренировки.",
        "Pump is that full, swollen, hard feeling as muscles fill with blood during training. Pump formulas support nitric oxide (NO) production, blood flow and water in muscle cells.\n\n"
        "Key ingredients include citrulline, arginine, nitrates (beetroot extract), agmatine and glycerol. Most pump formulas are stimulant-free, so they can be taken in the evening or stacked with a stimulant pre-workout.\n\n"
        "Who it suits: bodybuilding and fitness — training where muscle volume and the mind-muscle connection matter. Take it 20–40 minutes before training for the best effect.",
    ),
    "Pump Formula": (
        "Pump formula — «pump» uchun maxsus ishlab chiqilgan tayyor kompleks: sitrullin, nitratlar, glitserin, agmatin va antioksidantlarning sinergik aralashmasi. Bitta porsiya bir nechta alohida mahsulot o'rnini bosadi.\n\n"
        "Mashg'ulotdan 20–30 daqiqa oldin suv bilan ichiladi; ko'p suv ichish samarani kuchaytiradi. Ko'pincha stimulyatorsiz bo'ladi va sevimli stimulyatorli pre-workout bilan birga ishlatiladi.",
        "Pump formula — готовый комплекс, созданный специально для пампа: синергичная смесь цитруллина, нитратов, глицерина, агматина и антиоксидантов. Одна порция заменяет несколько отдельных продуктов.\n\n"
        "Принимают с водой за 20–30 минут до тренировки; обильное питьё усиливает эффект. Часто без стимуляторов и сочетается с любимым стимуляторным предтреником.",
        "A pump formula is a ready-made complex designed for pump: a synergistic blend of citrulline, nitrates, glycerol, agmatine and antioxidants. One serving replaces several separate products.\n\n"
        "Take it with water 20–30 minutes before training; drinking plenty boosts the effect. It's usually stimulant-free and stacks well with your favourite stim pre-workout.",
    ),
    "Nitric Oxide": (
        "Azot oksidi (NO) boosterlari organizmda NO hosil bo'lishini qo'llab-quvvatlaydi: NO qon tomir devorlarini bo'shashtirib, mushaklarga qon, kislorod va ozuqa moddalari yetkazilishini yaxshilaydi.\n\n"
        "Asosiy manbalar — L-sitrullin, L-arginin va tabiiy nitratlar (lavlagi ekstrakti). Natija: kuchli pump, chidamlilik va mashg'ulot paytida yaxshiroq ishlash. Qon bosimini tushiruvchi yoki erektil disfunksiya dorilarini qabul qilayotgan bo'lsangiz, shifokor bilan maslahatlashing.",
        "Бустеры оксида азота (NO) поддерживают образование NO в организме: он расслабляет стенки сосудов и улучшает доставку крови, кислорода и питательных веществ к мышцам.\n\n"
        "Основные источники — L-цитруллин, L-аргинин и натуральные нитраты (экстракт свёклы). Результат: сильный памп, выносливость и лучшая работоспособность. При приёме препаратов от давления или эректильной дисфункции проконсультируйтесь с врачом.",
        "Nitric-oxide (NO) boosters support the body's own NO production, which relaxes blood-vessel walls and improves delivery of blood, oxygen and nutrients to muscle.\n\n"
        "The main sources are L-citrulline, L-arginine and natural nitrates (beetroot extract). The result: a strong pump, endurance and better performance. If you take blood-pressure or erectile-dysfunction medication, consult your doctor.",
    ),
    "Stim-Free Pump": (
        "Stimulyatorsiz pump — kofein va boshqa stimulyatorlarsiz faqat qon oqimi, pump va chidamlilikka qaratilgan formula. U uyquga ta'sir qilmaydi, yurak urishini tezlashtirmaydi va tolerantlik hosil qilmaydi.\n\n"
        "Kechki mashg'ulotlar, kofeinga sezgirlar va stimulyatorli pre-workoutni pump bilan «kuchaytirmoqchi» bo'lganlar uchun ideal. Mashg'ulotdan 20–40 daqiqa oldin, yetarli suv bilan ichiladi.",
        "Памп без стимуляторов — формула без кофеина и других стимуляторов, нацеленная только на кровоток, памп и выносливость. Она не влияет на сон, не учащает пульс и не вызывает привыкания.\n\n"
        "Идеальна для вечерних тренировок, для чувствительных к кофеину и для тех, кто хочет «усилить» стимуляторный предтреник пампом. Принимают за 20–40 минут до тренировки с достаточным количеством воды.",
        "A stim-free pump formula focuses purely on blood flow, pump and endurance — no caffeine or other stimulants. It doesn't affect sleep, raise your heart rate or build tolerance.\n\n"
        "Ideal for evening sessions, caffeine-sensitive people and anyone who wants to boost a stim pre-workout with extra pump. Take it 20–40 minutes before training with plenty of water.",
    ),
    "Recovery": (
        "Tiklanish — natijaning yarmi: mushaklar mashg'ulot paytida emas, balki dam olish paytida o'sadi va kuchayadi. Tiklanish mahsulotlari mushak parchalanishini kamaytirish, glikogen zaxirasini to'ldirish va keyingi mashg'ulotga tezroq tayyor bo'lishga yordam beradi.\n\n"
        "Bo'limda: HMB (mushaklarni parchalanishdan himoya), glutamin (immunitet va ichak salomatligi), mol go'shti aminokislotalari va uglevodlar (glikogenni tez tiklash).\n\n"
        "Eslatma: eng muhim tiklanish omillari — yetarli uyqu (7–9 soat), kunlik protein va kaloriya, suv. Qo'shimchalar ularni to'ldiradi, lekin o'rnini bosmaydi.",
        "Восстановление — половина результата: мышцы растут и становятся сильнее не во время тренировки, а во время отдыха. Продукты для восстановления помогают уменьшить распад мышц, восполнить гликоген и быстрее подготовиться к следующей тренировке.\n\n"
        "В разделе: HMB (защита мышц от распада), глютамин (иммунитет и здоровье кишечника), говяжьи аминокислоты и углеводы (быстрое восстановление гликогена).\n\n"
        "Помните: главные факторы восстановления — достаточный сон (7–9 часов), суточные белок и калории, вода. Добавки их дополняют, но не заменяют.",
        "Recovery is half the result: muscles grow and get stronger not during training but while you rest. Recovery products help reduce muscle breakdown, refill glycogen and get you ready for the next session faster.\n\n"
        "This section includes HMB (protects muscle from breakdown), glutamine (immunity and gut health), beef amino acids and carbohydrates (fast glycogen recovery).\n\n"
        "Remember: the biggest recovery factors are enough sleep (7–9 hours), daily protein and calories, and water. Supplements complement them but don't replace them.",
    ),
    "HMB": (
        "HMB (beta-gidroksi-beta-metilbutirat) — leysin aminokislotasining metaboliti. U mushak oqsilining parchalanishini kamaytirishga yordam beradi, shuning uchun ayniqsa yangi boshlovchilar, mashg'ulot hajmini keskin oshirganlar, kaloriya cheklangan davr va yoshi kattaroq sportchilar uchun foydali.\n\n"
        "Odatiy doza — kuniga 3 g, 2–3 qismga bo'lib. Samara bir necha hafta muntazam qabul qilganda seziladi. Ko'pincha kreatin bilan birga ishlatiladi.",
        "HMB (бета-гидрокси-бета-метилбутират) — метаболит аминокислоты лейцин. Он помогает уменьшить распад мышечного белка, поэтому особенно полезен новичкам, тем, кто резко увеличил объём тренировок, в период дефицита калорий и спортсменам старшего возраста.\n\n"
        "Обычная доза — 3 г в день в 2–3 приёма. Эффект заметен при регулярном приёме в течение нескольких недель. Часто сочетается с креатином.",
        "HMB (beta-hydroxy-beta-methylbutyrate) is a metabolite of the amino acid leucine. It helps reduce muscle-protein breakdown, making it especially useful for beginners, people who sharply increase training volume, anyone in a calorie deficit and older athletes.\n\n"
        "The usual dose is 3 g a day split into 2–3 servings, with effects noticeable after several weeks of regular use. It's often combined with creatine.",
    ),
    "Glutamine": (
        "L-glutamin — organizmdagi eng ko'p tarqalgan aminokislota. U immun hujayralari va ichak devori hujayralari uchun asosiy «yoqilg'i», og'ir va uzoq mashg'ulotlar paytida esa uning zaxirasi kamayadi.\n\n"
        "Sportchilar glutaminni asosan immunitet va ichak salomatligini qo'llab-quvvatlash, intensiv mashg'ulot davrlarida tez-tez kasallanishni kamaytirish uchun qabul qiladi. Odatiy doza — kuniga 5–10 g, mashg'ulotdan keyin yoki uxlashdan oldin. Ta'msiz kukun protein yoki suvga qo'shiladi.",
        "L-глютамин — самая распространённая аминокислота в организме. Это главное «топливо» для иммунных клеток и клеток стенки кишечника, а при тяжёлых и длительных тренировках его запасы снижаются.\n\n"
        "Спортсмены принимают глютамин в основном для поддержки иммунитета и здоровья кишечника, чтобы реже болеть в периоды интенсивных нагрузок. Обычная доза — 5–10 г в день, после тренировки или перед сном. Порошок без вкуса добавляют в протеин или воду.",
        "L-glutamine is the most abundant amino acid in the body. It's the main fuel for immune cells and the cells of the gut wall, and stores drop during hard, prolonged training.\n\n"
        "Athletes mainly take it to support immunity and gut health and to get ill less often during intense training blocks. The usual dose is 5–10 g a day after training or before bed; the unflavoured powder mixes into protein or water.",
    ),
    "Beef Amino": (
        "Beef Amino — mol go'shti oqsili gidrolizatidan olingan aminokislota tabletkalari. Ular barcha almashtirib bo'lmaydigan aminokislotalarni o'z ichiga oladi va kollagen aminokislotalariga (glitsin, prolin) boy — bu bo'g'im va pay salomatligi uchun ham foydali.\n\n"
        "Odatda mashg'ulotdan oldin va keyin bir necha tabletka qabul qilinadi; sutsiz bo'lgani sababli laktozaga sezgirlar uchun mos. Protein ichish noqulay bo'lgan paytda oqsil miqdorini to'ldirishning qulay usuli.",
        "Beef Amino — аминокислоты в таблетках на основе гидролизата говяжьего белка. Они содержат все незаменимые аминокислоты и богаты коллагеновыми аминокислотами (глицин, пролин), что полезно и для суставов и связок.\n\n"
        "Обычно принимают несколько таблеток до и после тренировки; так как продукт без молочного, он подходит людям с чувствительностью к лактозе. Удобный способ добрать белок, когда пить протеин неудобно.",
        "Beef Amino tablets are amino acids from hydrolysed beef protein. They contain all the essential amino acids and are rich in collagen amino acids (glycine, proline), which also benefit joints and tendons.\n\n"
        "Take a few tablets before and after training; being dairy-free, they suit lactose-sensitive people. A handy way to top up protein when a shake isn't practical.",
    ),
    "Carbohydrates": (
        "Uglevodlar — intensiv mashg'ulotlar uchun asosiy yoqilg'i. Ular mushaklar va jigarda glikogen sifatida saqlanadi; glikogen tugaganda kuch va chidamlilik keskin pasayadi.\n\n"
        "Sport uglevodlari (maltodekstrin, dekstroza, siklik dekstrin, sekin uglevodlar) uzoq mashg'ulotlar paytida energiya berish va mashg'ulotdan keyin glikogenni tez tiklash uchun ishlatiladi; protein bilan birga ichilganda tiklanish yanada samarali. Ayniqsa chidamlilik sportlari, kuniga ikki martalik mashg'ulotlar va massa yig'ish davri uchun foydali.",
        "Углеводы — основное топливо для интенсивных тренировок. Они запасаются в мышцах и печени в виде гликогена; когда гликоген заканчивается, сила и выносливость резко падают.\n\n"
        "Спортивные углеводы (мальтодекстрин, декстроза, цикличный декстрин, медленные углеводы) дают энергию во время длительных тренировок и быстро восстанавливают гликоген после них; вместе с белком восстановление ещё эффективнее. Особенно полезны в видах спорта на выносливость, при двух тренировках в день и в период набора массы.",
        "Carbohydrates are the main fuel for intense training. They're stored in muscles and the liver as glycogen, and when glycogen runs out, strength and endurance drop sharply.\n\n"
        "Sports carbs (maltodextrin, dextrose, cyclic dextrin, slow carbs) provide energy during long sessions and quickly refill glycogen afterwards — even more effectively with protein. They're especially useful in endurance sports, for twice-a-day training and when building mass.",
    ),
    "Fat Burners": (
        "Yog' yoquvchilar — vazn yo'qotish va relyefga erishishda yordamchi vositalar. Ular metabolizmni bir oz tezlashtirish, energiya berish, ishtahani nazorat qilish yoki yog'larni energiyaga aylantirish jarayonini qo'llab-quvvatlash orqali ishlaydi.\n\n"
        "Turlari: termogeniklar (kofein, yashil choy ekstrakti, sinefrin — energiya va kaloriya sarfi) va L-karnitin (stimulyatorsiz, yog' kislotalarini energiyaga tashish).\n\n"
        "Halol gap: yog' yoquvchi faqat kaloriya defitsiti, to'g'ri ovqatlanish, mashg'ulot va uyqu bilan birga ishlaydi — u «sehrli tabletka» emas. Stimulyatorli mahsulotlarni yarim dozadan boshlang, kechqurun ichmang; yurak, qalqonsimon bez muammolari, homiladorlik va 18 yoshgacha bo'lganlarga tavsiya etilmaydi.",
        "Жиросжигатели — вспомогательные средства для снижения веса и рельефа. Они работают за счёт небольшого ускорения метаболизма, энергии, контроля аппетита или поддержки превращения жиров в энергию.\n\n"
        "Виды: термогеники (кофеин, экстракт зелёного чая, синефрин — энергия и расход калорий) и L-карнитин (без стимуляторов, транспорт жирных кислот в «энергостанции» клеток).\n\n"
        "Честно: жиросжигатель работает только вместе с дефицитом калорий, правильным питанием, тренировками и сном — это не «волшебная таблетка». Стимуляторные продукты начинайте с половины дозы, не принимайте вечером; не рекомендуются при проблемах с сердцем и щитовидной железой, при беременности и до 18 лет.",
        "Fat burners are aids for losing weight and getting lean. They work by slightly raising metabolism, providing energy, helping control appetite or supporting the use of fat for energy.\n\n"
        "Types: thermogenics (caffeine, green-tea extract, synephrine — energy and calorie burn) and L-carnitine (stimulant-free, carries fatty acids into the cell's power plants).\n\n"
        "Honestly: a fat burner only works alongside a calorie deficit, good nutrition, training and sleep — it's not a magic pill. Start stimulant products at half a dose and avoid them in the evening; not recommended with heart or thyroid issues, during pregnancy or under 18.",
    ),
    "Thermogenics": (
        "Termogeniklar — tana haroratini va energiya sarfini biroz oshiradigan stimulyatorli yog' yoquvchilar. Tarkibida odatda kofein, yashil choy ekstrakti (EGCG), sinefrin, qalampir ekstrakti (kapsaitsin) va yohimbin bo'ladi.\n\n"
        "Ular energiya va diqqatni oshiradi, ishtahani kamaytirishga yordam beradi va kaloriya defitsitini saqlashni osonlashtiradi. Ertalab yoki mashg'ulotdan oldin, kofeinning kunlik limitini hisobga olgan holda qabul qilinadi. Odatda 4–8 haftalik kurslardan keyin tanaffus qilinadi.",
        "Термогеники — стимуляторные жиросжигатели, немного повышающие температуру тела и расход энергии. В составе обычно кофеин, экстракт зелёного чая (EGCG), синефрин, экстракт перца (капсаицин) и йохимбин.\n\n"
        "Они повышают энергию и концентрацию, помогают снизить аппетит и легче удерживать дефицит калорий. Принимают утром или перед тренировкой с учётом суточного лимита кофеина. Обычно после курса 4–8 недель делают перерыв.",
        "Thermogenics are stimulant fat burners that slightly raise body temperature and energy expenditure. They usually contain caffeine, green-tea extract (EGCG), synephrine, pepper extract (capsaicin) and yohimbine.\n\n"
        "They boost energy and focus, help curb appetite and make a calorie deficit easier to sustain. Take them in the morning or before training, within your daily caffeine limit, usually in 4–8-week cycles followed by a break.",
    ),
    "L-Carnitine": (
        "L-karnitin — yog' kislotalarini hujayralarning «energiya stansiyalari» (mitoxondriyalar)ga tashuvchi modda. U stimulyatorsiz ishlaydi, shuning uchun yurak urishini tezlashtirmaydi va kechki mashg'ulotlar uchun ham mos.\n\n"
        "Odatda kuniga 1–3 g mashg'ulotdan oldin suyuq, kapsula yoki kukun shaklida qabul qilinadi. L-karnitin tartrat tiklanish uchun, asetil-L-karnitin (ALCAR) esa diqqat va miya faoliyati uchun ham qadrlanadi. Eng yaxshi natija — kardio va kaloriya defitsiti bilan birga.",
        "L-карнитин переносит жирные кислоты в «энергостанции» клеток — митохондрии. Он работает без стимуляторов, не учащает пульс и подходит даже для вечерних тренировок.\n\n"
        "Обычно принимают 1–3 г в день перед тренировкой в жидкой форме, капсулах или порошке. L-карнитин тартрат ценят для восстановления, ацетил-L-карнитин (ALCAR) — ещё и для концентрации и работы мозга. Лучший результат — вместе с кардио и дефицитом калорий.",
        "L-carnitine carries fatty acids into the cell's power plants, the mitochondria. It's stimulant-free, doesn't raise your heart rate and suits evening workouts too.\n\n"
        "The usual dose is 1–3 g a day before training as a liquid, capsules or powder. L-carnitine tartrate is valued for recovery, and acetyl-L-carnitine (ALCAR) also for focus and brain function. Best results come with cardio and a calorie deficit.",
    ),
}

from apps.products.infrastructure.category_texts_more import MORE_CATEGORY_TEXTS  # noqa: E402

CATEGORY_TEXTS.update(MORE_CATEGORY_TEXTS)
