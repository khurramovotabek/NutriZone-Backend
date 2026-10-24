"""
Starter AI bilimlar bazasi: shop policies (same wording as the advisor's kb.py) and widely accepted sports-nutrition
guidance (ISSN position stands: creatine 3-5 g/day, beta-alanine 4-6 g/day in split doses, protein 1.4-2.0 g/kg/day
for active people). The shop edits, adds or switches entries off on the dashboard.
"""
from django.db import migrations

E = [
    # topic, priority, title, questions, keywords, uz, ru, en
    ("policy", 90, "Mahsulotlar originalmi?", "original mi\nsoxta emasmi\nоригинал\nподделка\nis it original\nfake", "original, sertifikat, soxta, оригинал, сертификат, fake, certificate",
     "Ha. NutriZone mahsulotlarni faqat rasmiy distribyutorlardan oladi va har bir partiya hujjatlarini saqlaydi. Istalgan mahsulot sertifikatini chatda so'rashingiz mumkin; qadoqdagi tekshiruv kodini ishlab chiqaruvchi saytida ham tekshirsa bo'ladi.",
     "Да. NutriZone закупает товар только у официальных дистрибьюторов и хранит документы на каждую партию. Сертификат на любой товар можно запросить в чате; код на упаковке можно проверить на сайте производителя.",
     "Yes. NutriZone buys only from official distributors and keeps the documents for every batch. Ask for any product's certificate in the chat; you can also check the code on the pack on the manufacturer's website."),
    ("policy", 85, "Yetkazib berish", "yetkazib berish bormi\nqancha vaqtda keladi\nдоставка\nкогда привезут\ndelivery\nhow long", "yetkazib, dostavka, kuryer, доставка, курьер, delivery, shipping",
     "Buyurtmani saytda yoki Telegram botda rasmiylashtirib, manzilni xaritada belgilaysiz. Yetkazish narxi va muddati manzilga qarab rasmiylashtirishda ko'rsatiladi. Shoshilinch bo'lsa — do'kondan olib ketishni tanlang: buyurtma tayyor bo'lgach xabar keladi.",
     "Оформите заказ на сайте или в Telegram-боте и отметьте адрес на карте. Стоимость и срок доставки показываются при оформлении в зависимости от адреса. Если срочно — выберите самовывоз: придёт уведомление, когда заказ будет готов.",
     "Place the order on the site or in the Telegram bot and pin your address on the map. The delivery price and time are shown at checkout for your address. In a hurry? Choose in-store pickup — you'll be notified when it's ready."),
    ("policy", 80, "Qaytarish va almashtirish", "qaytarsa bo'ladimi\nalmashtirish\nвозврат\nобмен\nreturn\nrefund", "qaytarish, almashtirish, возврат, обмен, return, refund",
     "Buyurtmalarim sahifasida qaytarish so'rovini yuborishingiz mumkin. Ochilmagan, qadoqi buzilmagan mahsulot qabul qilinadi; nuqsonli mahsulot almashtiriladi.",
     "Запрос на возврат отправляется на странице «Мои заказы». Принимаем невскрытый товар с целой упаковкой; бракованный — обменяем.",
     "Request a return on the My orders page. Unopened products with intact packaging are accepted; defective items are exchanged."),
    ("policy", 75, "NutriZone Coins", "coin nima\nbonus\nкешбэк\nкоины\ncashback\nloyalty", "coin, bonus, cashback, кешбэк, коины, бонус",
     "Har xariddan NutriZone Coins tushadi (1 coin = 1 so'm): darajangizga qarab 1% dan 8% gacha. Coinlar bilan keyingi buyurtmaning bir qismini to'lash mumkin. Balans va daraja — saytdagi «Coins» sahifasida.",
     "С каждой покупки начисляются NutriZone Coins (1 коин = 1 сум): от 1% до 8% в зависимости от уровня. Коинами можно оплатить часть следующего заказа. Баланс и уровень — на странице «Coins» на сайте.",
     "Every purchase earns NutriZone Coins (1 coin = 1 so'm): 1% to 8% depending on your tier. Use them to pay part of your next order. Balance and tier are on the Coins page on the site."),
    ("usage", 70, "Kreatin qanday ichiladi", "kreatin qanday ichiladi\nkreatin dozasi\nкак пить креатин\nдозировка креатина\nhow to take creatine", "kreatin, креатин, creatine, monohidrat, доза, dose",
     "Kreatin monohidrat: kuniga 3–5 g, har kuni (mashg'ulotsiz kunlari ham), istalgan vaqtda — suv yoki sharbat bilan. Tezroq to'yinish uchun 5–7 kun kuniga ~20 g (4×5 g) «yuklama» qilish mumkin, lekin shart emas. Ko'proq suv iching. Buyrak kasalligi bo'lsa — avval shifokor bilan maslahatlashing.",
     "Креатин моногидрат: 3–5 г в день, ежедневно (и в дни отдыха), в любое время — с водой или соком. Для быстрого насыщения можно 5–7 дней по ~20 г (4×5 г), но это не обязательно. Пейте больше воды. При болезнях почек — сначала консультация врача.",
     "Creatine monohydrate: 3–5 g a day, every day (rest days too), any time — with water or juice. An optional loading phase of ~20 g a day (4×5 g) for 5–7 days fills the muscles faster. Drink plenty of water. With kidney disease, ask a doctor first."),
    ("usage", 70, "Protein (whey) qanday ichiladi", "protein qanday ichiladi\nnechta skup\nкак пить протеин\nсколько протеина в день\nhow much protein", "protein, whey, протеин, сывороточный, skup, scoop",
     "1 porsiya (odatda 25–35 g kukun ≈ 20–25 g oqsil) suv yoki sut bilan, mashg'ulotdan keyin yoki ovqatlar orasida. Faol odamga sutkasiga taxminan 1,4–2,0 g oqsil/kg vazn kerak — protein ovqatdan yetmay qolganini to'ldiradi, ovqat o'rnini bosmaydi.",
     "1 порция (обычно 25–35 г порошка ≈ 20–25 г белка) с водой или молоком, после тренировки или между приёмами пищи. Активному человеку нужно примерно 1,4–2,0 г белка на кг веса в день — протеин дополняет питание, а не заменяет его.",
     "1 serving (usually 25–35 g powder ≈ 20–25 g protein) with water or milk, after training or between meals. Active people need roughly 1.4–2.0 g protein per kg body weight a day — protein powder tops up your diet, it doesn't replace food."),
    ("usage", 60, "Geyner kimga kerak", "geyner kimga\nmassa olish uchun geyner\nгейнер\nдля набора веса\ngainer", "geyner, gainer, гейнер, massa, вес, масса",
     "Geyner — vazn qiyin oshadigan (ozg'in, tez metabolizmli) odamlar uchun: oqsil + uglevod. Kunlik porsiyani 2 qismga bo'lib, mashg'ulotdan keyin va ovqatlar orasida iching. Ozish maqsadi bo'lsa geyner mos emas — protein tanlang.",
     "Гейнер — для тех, кому трудно набрать вес: белок + углеводы. Делите дневную порцию на 2 приёма — после тренировки и между едой. Если цель похудение — гейнер не подходит, выбирайте протеин.",
     "A gainer is for people who struggle to gain weight: protein + carbs. Split the daily serving into 2 — after training and between meals. For fat loss a gainer is the wrong choice; pick protein instead."),
    ("usage", 55, "Pre-workout xavfsiz ishlatish", "pre workout qachon ichiladi\nпредтрен\nпредтренировочный\npre-workout", "preworkout, pre-workout, предтрен, kofein, кофеин, caffeine",
     "Mashg'ulotdan 20–30 daqiqa oldin, 1 porsiyadan oshirmang. Ko'pchiligida kofein bor — kechqurun ichsangiz uyqu buzilishi mumkin; kofeinga sezgir bo'lsangiz yarim porsiyadan boshlang. 18 yoshgacha, homiladorlikda, yurak yoki bosim muammosida tavsiya qilinmaydi.",
     "За 20–30 минут до тренировки, не больше 1 порции. В большинстве есть кофеин — вечером может нарушить сон; при чувствительности начните с половины порции. Не рекомендуется до 18 лет, при беременности, проблемах с сердцем или давлением.",
     "20–30 minutes before training, no more than 1 serving. Most contain caffeine — late in the day it can hurt sleep; if you're sensitive, start with half. Not recommended under 18, in pregnancy, or with heart or blood-pressure problems."),
    ("usage", 50, "BCAA / EAA", "bcaa nima uchun\nаминокислоты\nbcaa", "bcaa, eaa, aminokislota, аминокислоты, amino",
     "BCAA/EAA mashg'ulot paytida yoki undan keyin 5–10 g ichiladi. Agar kunlik oqsilingiz (ovqat + protein) yetarli bo'lsa, foydasi kichik — avval protein va kreatin, keyin BCAA.",
     "BCAA/EAA — 5–10 г во время или после тренировки. Если белка в рационе (еда + протеин) достаточно, польза небольшая — сначала протеин и креатин, потом BCAA.",
     "BCAA/EAA: 5–10 g during or after training. If your daily protein (food + powder) is already enough, the benefit is small — get protein and creatine first, then BCAA."),
    ("usage", 50, "L-karnitin", "karnitin ozdiradimi\nкарнитин\nl-carnitine", "karnitin, карнитин, carnitine, ozish, похудение",
     "L-karnitin kardio mashg'ulotdan ~30 daqiqa oldin ichiladi. U o'zi yog' yoqmaydi — kaloriya defitsiti va harakat bilan birga yordamchi bo'ladi.",
     "L-карнитин принимают за ~30 минут до кардио. Сам по себе жир не сжигает — помогает только вместе с дефицитом калорий и нагрузкой.",
     "Take L-carnitine ~30 minutes before cardio. It doesn't burn fat by itself — it only helps alongside a calorie deficit and exercise."),
    ("usage", 45, "Omega-3", "omega 3 qanday ichiladi\nрыбий жир\nomega", "omega, omega-3, baliq yog'i, рыбий жир, fish oil",
     "Omega-3 ovqat bilan birga ichiladi (yaxshi so'riladi, baliq ta'mi kamroq). Ko'pchilik uchun kuniga 1–2 g EPA+DHA yetarli — yorliqdagi EPA va DHA miqdoriga qarang. Qon suyultiruvchi dori ichsangiz — shifokorga ayting.",
     "Омега-3 принимают во время еды (лучше усваивается, меньше рыбного привкуса). Обычно хватает 1–2 г EPA+DHA в день — смотрите на содержание EPA и DHA. Если пьёте разжижающие кровь препараты — скажите врачу.",
     "Take omega-3 with a meal (better absorption, less fishy aftertaste). For most people 1–2 g EPA+DHA a day is enough — check the EPA and DHA amounts on the label. On blood thinners? Tell your doctor."),
    ("usage", 45, "Multivitamin", "vitamin qachon ichiladi\nмультивитамины\nmultivitamin", "vitamin, multivitamin, витамины",
     "Multivitaminni nonushta yoki tushlik bilan, yorliqdagi dozada iching. Bir nechta vitamin mahsulotini birga ichsangiz, bir xil vitamin ikki marta ko'p bo'lib ketmasligiga e'tibor bering.",
     "Мультивитамины — с завтраком или обедом, в дозе с этикетки. Если пьёте несколько добавок, следите, чтобы одни и те же витамины не дублировались.",
     "Take a multivitamin with breakfast or lunch at the label dose. If you combine several supplements, make sure the same vitamins aren't doubled."),
    ("usage", 40, "Kollagen", "kollagen qanday ichiladi\nколлаген\ncollagen", "kollagen, коллаген, collagen, bo'g'im, суставы",
     "Kollagen: kuniga ~10 g, har kuni, kamida 8–12 hafta. C vitamini bilan birga ichish tavsiya qilinadi. Natija (teri, bo'g'imlar) asta-sekin seziladi.",
     "Коллаген: ~10 г в день ежедневно, минимум 8–12 недель. Желательно вместе с витамином C. Эффект (кожа, суставы) накапливается постепенно.",
     "Collagen: ~10 g a day, every day, for at least 8–12 weeks, ideally with vitamin C. Results (skin, joints) build up gradually."),
    ("usage", 40, "Beta-alanin", "beta alanin qichishadi\nбета-аланин\nbeta-alanine tingling", "beta-alanin, бета-аланин, beta-alanine",
     "Beta-alanin: kuniga 4–6 g, kamida 4 hafta. Teri qichishishi (chumoli yurgandek sezgi) — normal va zararsiz; kamaytirish uchun dozani 1,5–2 g dan bir necha marta bo'lib iching.",
     "Бета-аланин: 4–6 г в день минимум 4 недели. Покалывание кожи — нормально и безвредно; чтобы уменьшить, делите дозу на приёмы по 1,5–2 г.",
     "Beta-alanine: 4–6 g a day for at least 4 weeks. Skin tingling is normal and harmless; to reduce it, split the dose into 1.5–2 g servings."),
    ("faq", 50, "Laktoza ko'tarolmasam qaysi protein", "laktoza\nsut ko'tarolmayman\nнепереносимость лактозы\nlactose intolerant\nvegan protein", "laktoza, лактоза, lactose, izolyat, изолят, isolate, vegan",
     "Laktozaga sezgir bo'lsangiz — whey izolyat yoki gidrolizat (laktoza juda kam), yoki o'simlik (vegan) protein tanlang. Suv bilan aralashtiring.",
     "При чувствительности к лактозе выбирайте изолят или гидролизат (лактозы очень мало) либо растительный (веган) протеин. Смешивайте с водой.",
     "If you're lactose-sensitive, choose whey isolate or hydrolysate (very little lactose) or a plant (vegan) protein, mixed with water."),
    ("faq", 45, "Ayollar uchun protein", "ayollar protein ichsa bo'ladimi\nпротеин для девушек\nprotein for women", "ayollar, qizlar, девушки, женщины, women",
     "Ha, protein ayollar uchun ham xavfsiz va foydali: «katta mushak» qilib qo'ymaydi, to'yinishga va ozishda mushakni saqlashga yordam beradi. Homiladorlik va emizish davrida avval shifokor bilan maslahatlashing.",
     "Да, протеин безопасен и полезен для женщин: «перекачанности» не даёт, помогает насыщению и сохранению мышц при похудении. При беременности и кормлении — сначала консультация врача.",
     "Yes, protein is safe and useful for women: it won't make you bulky, it helps you stay full and keep muscle while losing fat. If pregnant or breastfeeding, ask a doctor first."),
    ("faq", 45, "Yangi boshlovchilar uchun nima olish kerak", "endi boshlayapman\nnovichok\nс чего начать\nbeginner", "boshlovchi, yangi, новичок, начинающий, beginner",
     "Boshlovchilar uchun eng foydali juftlik — protein + kreatin monohidrat: ikkalasi ham ko'p o'rganilgan va xavfsiz. Qolganini (pre-workout, BCAA) keyinroq qo'shsa bo'ladi. Asosiy natija baribir ovqat, uyqu va muntazam mashg'ulotdan.",
     "Новичкам лучше всего начать с протеина и креатина моногидрата: оба хорошо изучены и безопасны. Остальное (предтрен, BCAA) можно добавить позже. Главный результат всё равно даёт питание, сон и регулярные тренировки.",
     "For beginners the best pair is protein + creatine monohydrate: both are well studied and safe. Add the rest (pre-workout, BCAA) later. Results still come mainly from food, sleep and consistent training."),
    ("faq", 40, "Saqlash va yaroqlilik muddati", "qanday saqlash kerak\nсрок годности\nкак хранить\nexpiry\nhow to store", "saqlash, muddat, хранение, срок, storage, expiry",
     "Salqin, quruq joyda, qopqog'ini mahkam yopib saqlang; quyosh va namlikdan asrang. Ochilgandan keyin odatda 2–3 oy ichida ishlatgan ma'qul. Yaroqlilik muddati qadoqda ko'rsatilgan.",
     "Храните в прохладном сухом месте, плотно закрытым, вдали от солнца и влаги. После вскрытия лучше использовать за 2–3 месяца. Срок годности указан на упаковке.",
     "Keep it cool and dry, tightly closed, away from sun and moisture. Once opened, best used within 2–3 months. The expiry date is on the pack."),
    ("faq", 40, "Protein buyrakka zararmi", "protein buyrakka zarar\nпротеин вредно для почек\nprotein kidneys", "buyrak, почки, kidney, zarar, вред, harm",
     "Sog'lom odamlarda tavsiya etilgan miqdordagi protein buyrakka zarar qilishi isbotlanmagan. Buyrak kasalligi bo'lsa yoki shifokor oqsilni cheklagan bo'lsa — protein ichishdan oldin shifokor bilan maslahatlashing.",
     "У здоровых людей белок в рекомендуемых количествах вредить почкам не доказан. При болезнях почек или если врач ограничил белок — сначала консультация врача.",
     "In healthy people, protein at recommended amounts hasn't been shown to harm the kidneys. With kidney disease, or if a doctor has limited your protein, ask the doctor first."),
]


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in E:
        KnowledgeEntry.objects.get_or_create(title=title, defaults={"topic": topic, "priority": priority, "questions": questions, "keywords": keywords,
                                                                    "answer_uz": uz, "answer_ru": ru, "answer_en": en, "created_by": "NutriZone"})


class Migration(migrations.Migration):
    dependencies = [("assistant", "0003_knowledge_base")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
