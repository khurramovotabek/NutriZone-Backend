"""
Teaches the assistant how the shop itself works -- the questions the support chat gets every day: cancelling an order,
pickup, paying, order tracking, the Telegram bot / Mini App, finding a product the shop doesn't list and expiry dates.
Facts follow the real flows (instant cancel before packing, 14-day returns, free pickup, coins up to the programme's
cap); live numbers (payment methods, delivery days) come from get_store_info, so these texts never name them.
Entries the shop already has (same title) are left as they are; the old seeded returns text gains the 14-day window.
"""
from django.db import migrations

ENTRIES = [
    ("policy", 80, "Buyurtmani bekor qilish",
     "buyurtmani bekor qilsam bo'ladimi\nbuyurtmani qanday bekor qilaman\nотменить заказ\nкак отменить заказ\ncancel my order",
     "bekor, otmen, отмена, cancel, buyurtma",
     "Buyurtmani **Buyurtmalarim** sahifasida o'zingiz bekor qilasiz:\n"
     "• Buyurtma hali yig'ilmagan bo'lsa (to'lov kutilmoqda yoki tasdiqlangan) — «Buyurtmani bekor qilish» tugmasi bilan darhol bekor bo'ladi; coin bilan to'langan qismi hisobingizga qaytadi.\n"
     "• Buyurtma yig'ilayotgan yoki yo'lda bo'lsa — bekor qilish so'rovini yuborasiz, do'kon tez orada javob beradi.\n"
     "Savol bo'lsa — chatga yozing, operator yordam beradi.",
     "Отменить заказ можно самостоятельно на странице **Мои заказы**:\n"
     "• Пока заказ не начали собирать (ожидает оплаты или подтверждён) — кнопка «Отменить заказ» отменяет его сразу; оплаченные коинами суммы вернутся на счёт.\n"
     "• Если заказ уже собирают или он в пути — отправьте запрос на отмену, магазин скоро ответит.\n"
     "Вопросы — пишите в чат, оператор поможет.",
     "You can cancel an order yourself on the **My orders** page:\n"
     "• Before packing starts (awaiting payment or confirmed) the “Cancel order” button cancels it at once; coins you paid with go back to your balance.\n"
     "• Once it is being packed or is on the way, send a cancellation request and the store will answer shortly.\n"
     "Questions — write in the chat and an operator will help."),
    ("policy", 75, "Do'kondan olib ketish",
     "do'kondan olib ketsam bo'ladimi\no'zim olib ketaman\nsamovyvoz\nсамовывоз\nзабрать в магазине\npickup in store",
     "olib ketish, samovyvoz, самовывоз, pickup, filial",
     "🏪 **Do'kondan olib ketish bepul.** Rasmiylashtirishda «Do'kondan olib ketish»ni tanlang — ro'yxatda har bir filialda mahsulotlaringiz bor-yo'qligi va ish vaqti ko'rinadi, «Menga eng yaqin» tugmasi eng yaqin do'konni topadi. "
     "Buyurtma tayyor bo'lgach bildirishnoma keladi; to'lovni do'konda naqd yoki karta bilan qilasiz.",
     "🏪 **Самовывоз бесплатный.** При оформлении выберите «Самовывоз из магазина» — в списке видно, в каком филиале есть все ваши товары и часы работы, кнопка «Ближайший ко мне» найдёт ближайший магазин. "
     "Когда заказ будет готов, придёт уведомление; оплатить можно в магазине наличными или картой.",
     "🏪 **In-store pickup is free.** At checkout choose “Pick up in store” — the list shows which branch has all your items and its hours, and “Nearest to me” finds the closest one. "
     "You're notified when the order is ready; pay in the store by cash or card."),
    ("policy", 75, "To'lov usullari",
     "qanday to'lasam bo'ladi\nkarta bilan to'lasa bo'ladimi\npayme bormi\nclick bilan to'lov\nкак оплатить\nоплата картой\npayment methods",
     "to'lov, tolov, оплата, payme, click, uzum, karta, naqd, payment",
     "💳 Ishlayotgan to'lov usullari rasmiylashtirishning **To'lov** bosqichida ko'rsatiladi. Har doim mavjud usul — **naqd yoki karta bilan** do'konda yoki buyurtmani qabul qilganda to'lash. "
     "«Tez kunda» belgisi turgan usullar hali ulanmagan. NutriZone Coins bilan buyurtmaning bir qismini to'lash ham mumkin.",
     "💳 Доступные способы оплаты показываются на шаге **Оплата** при оформлении. Всегда доступно — **наличными или картой** в магазине или при получении заказа. "
     "Способы с пометкой «Скоро» ещё не подключены. Часть заказа можно оплатить коинами NutriZone.",
     "💳 The payment methods that work right now are shown at the **Payment** step of checkout. Always available: **cash or card** in the store or when you receive the order. "
     "Methods marked “Coming soon” aren't connected yet. You can also pay part of an order with NutriZone Coins."),
    ("faq", 70, "Buyurtmam qayerda",
     "buyurtmam qayerda\nbuyurtma qachon keladi\nbuyurtma holati\nгде мой заказ\nкогда привезут\nwhere is my order",
     "buyurtma, holat, qachon, keladi, заказ, статус, order, status",
     "📦 Buyurtma holati **Buyurtmalarim** sahifasida bosqichma-bosqich ko'rinadi: qabul qilindi → tasdiqlandi → tayyorlanmoqda → yo'lda / olib ketishga tayyor. "
     "Har bir o'zgarishda saytda va Telegram botda bildirishnoma keladi. Kechiksa — buyurtma raqamini chatga yozing, operator darhol tekshiradi.",
     "📦 Статус заказа по шагам виден на странице **Мои заказы**: принят → подтверждён → собирается → в пути / готов к выдаче. "
     "О каждом изменении приходит уведомление на сайте и в Telegram-боте. Если задерживается — напишите номер заказа в чат, оператор сразу проверит.",
     "📦 Your order's progress is on the **My orders** page step by step: placed → confirmed → being prepared → on the way / ready for pickup. "
     "You're notified of every change on the site and in the Telegram bot. If it's late, send the order number in the chat and an operator will check right away."),
    ("faq", 60, "Telegram bot va Mini App",
     "telegram bot bormi\ntelegramdan buyurtma bersa bo'ladimi\nтелеграм бот\nзаказать через телеграм\ntelegram bot",
     "telegram, bot, mini app, телеграм, бот",
     "🤖 Telegram'da **@nutrizonebot** bor: katalog, savat va buyurtma to'g'ridan-to'g'ri Telegram ichida (Mini App) ochiladi, buyurtma holati va aksiyalar haqida xabarlar shu yerga keladi. "
     "Bot orqali kirsangiz, sayt bilan bitta hisob — savat, coinlar va buyurtmalar umumiy.",
     "🤖 В Telegram есть **@nutrizonebot**: каталог, корзина и оформление открываются прямо в Telegram (Mini App), туда же приходят статусы заказов и акции. "
     "Аккаунт общий с сайтом — корзина, коины и заказы одни и те же.",
     "🤖 We have **@nutrizonebot** on Telegram: the catalogue, cart and checkout open right inside Telegram (Mini App), and order updates and offers arrive there. "
     "It's the same account as the website — cart, coins and orders are shared."),
    ("faq", 60, "Kerakli mahsulot topilmasa",
     "sizda yo'q mahsulotni topib berasizmi\nmahsulot topilmadi\nolib kelib bera olasizmi\nнет нужного товара\nможете привезти\nfind a product",
     "topib, buyurtma, yo'q, olib kelish, привезти, нет в наличии, request",
     "🔎 Katalogda yo'q mahsulot kerak bo'lsa — hisobingizdagi **Mahsulot so'rovlari** bo'limida (nutrizone.uz/account/product-requests) nomini, brendini va hajmini yozing, istasangiz rasmini qo'shing. "
     "Jamoamiz topib, narx va muddat bilan siz bilan bog'lanadi.",
     "🔎 Если нужного товара нет в каталоге — оставьте запрос в разделе **Запросы товаров** в личном кабинете (nutrizone.uz/account/product-requests): название, бренд, объём, при желании фото. "
     "Команда найдёт товар и свяжется с вами с ценой и сроком.",
     "🔎 Can't find a product in the catalogue? Leave a request under **Product requests** in your account (nutrizone.uz/account/product-requests) with the name, brand and size, and a photo if you like. "
     "Our team will source it and get back to you with the price and timing."),
]

OLD_RETURNS_UZ = "Buyurtmalarim sahifasida qaytarish so'rovini yuborishingiz mumkin. Ochilmagan, qadoqi buzilmagan mahsulot qabul qilinadi; nuqsonli mahsulot almashtiriladi."
RETURNS = {
    "answer_uz": "Mahsulot yetkazilganidan keyin **14 kun** ichida Buyurtmalarim sahifasida qaytarish so'rovini yuborishingiz mumkin. "
                 "Ochilmagan, qadoqi buzilmagan mahsulot qabul qilinadi; nuqsonli mahsulot almashtiriladi.",
    "answer_ru": "В течение **14 дней** после доставки запрос на возврат можно отправить на странице «Мои заказы». "
                 "Принимаем невскрытый товар с целой упаковкой; бракованный — обменяем.",
    "answer_en": "You can request a return on the My orders page within **14 days** of delivery. "
                 "Unopened products with intact packaging are accepted; defective items are exchanged.",
}


def seed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    for topic, priority, title, questions, keywords, uz, ru, en in ENTRIES:
        KnowledgeEntry.objects.get_or_create(title=title, defaults={"topic": topic, "priority": priority, "questions": questions, "keywords": keywords,
                                                                    "answer_uz": uz, "answer_ru": ru, "answer_en": en, "created_by": "NutriZone"})
    # only the untouched seed text -- an answer the shop has edited stays theirs
    KnowledgeEntry.objects.filter(title="Qaytarish va almashtirish", answer_uz=OLD_RETURNS_UZ).update(**RETURNS)


def unseed(apps, schema_editor):
    KnowledgeEntry = apps.get_model("assistant", "KnowledgeEntry")
    KnowledgeEntry.objects.filter(title__in=[e[2] for e in ENTRIES], created_by="NutriZone", uses=0).delete()


class Migration(migrations.Migration):
    dependencies = [("assistant", "0007_knowledge_titles_slug")]
    operations = [migrations.RunPython(seed, unseed)]
