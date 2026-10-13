"""
Telegram bot translations -- Phase 15G.

Reuses the existing, real `User.language` field (backed by
`apps.identity.domain.enums.LanguagePreference`: uz/ru/en) as the
single source of truth for a customer's language -- no second locale
system was introduced. Every string this bot has sent since Phase 15B
is covered here; the callback router/views/checkout modules now look
up text through `t(key, lang, **kwargs)` instead of hardcoding Uzbek.
"""
from __future__ import annotations

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "cart_header": {
        "uz": "🛒 <b>SAVATCHA</b> · {units} dona",
        "ru": "🛒 <b>КОРЗИНА</b> · {units} шт",
        "en": "🛒 <b>CART</b> · {units} items",
    },
    "cart_grand_total": {
        "uz": "💰 <b>Jami: {total}</b>",
        "ru": "💰 <b>Итого: {total}</b>",
        "en": "💰 <b>Total: {total}</b>",
    },
    "cart_shared_note": {
        "uz": "<i>Savatingiz botda ham, Mini App'da ham bir xil.</i>",
        "ru": "<i>Корзина общая — в боте и в Mini App.</i>",
        "en": "<i>One cart — in the bot and in the Mini App.</i>",
    },
    "cart_open_app": {
        "uz": "📱 Mini App'da ochish",
        "ru": "📱 Открыть в Mini App",
        "en": "📱 Open in the Mini App",
    },
    "welcome_registered": {
        "uz": "🎉 <b>Xush kelibsiz, {name}!</b>\n\nHisobingiz tayyor. Endi:\n🛍 Do'konni pastdagi tugma orqali oching — avtomatik kirasiz, kod kerak emas\n🪙 Har bir xariddan NutriZone Coins yig'iladi\n📦 Buyurtma holati shu chatga keladi",
        "ru": "🎉 <b>Добро пожаловать, {name}!</b>\n\nАккаунт готов. Теперь:\n🛍 Откройте магазин кнопкой ниже — вход автоматический, без кодов\n🪙 С каждой покупки — NutriZone Coins\n📦 Статус заказа придёт в этот чат",
        "en": "🎉 <b>Welcome, {name}!</b>\n\nYour account is ready. Now:\n🛍 Open the shop with the button below — you're signed in automatically, no codes\n🪙 Earn NutriZone Coins on every purchase\n📦 Order updates arrive in this chat",
    },
    "menu_greeting": {
        "uz": "👋 {name}",
        "ru": "👋 {name}",
        "en": "👋 {name}",
    },
    "menu_cart_line": {
        "uz": "🛒 Savatda: <b>{units} dona</b> · {total}",
        "ru": "🛒 В корзине: <b>{units} шт</b> · {total}",
        "en": "🛒 In your cart: <b>{units}</b> · {total}",
    },
    "menu_button_label": {
        "uz": "🛍 Do'kon",
        "ru": "🛍 Магазин",
        "en": "🛍 Shop",
    },
    "menu_news": {
        "uz": "\U0001F4F0 Yangiliklar va aksiyalar",
        "ru": "\U0001F4F0 Новости и акции",
        "en": "\U0001F4F0 News & promotions",
    },
    "welcome_new": {
        "uz": "\U0001F44B NutriZone'ga xush kelibsiz!\n\nIltimos, ism-familiyangizni to'liq kiriting.",
        "ru": "\U0001F44B Добро пожаловать в NutriZone!\n\nПожалуйста, введите ваше полное имя.",
        "en": "\U0001F44B Welcome to NutriZone!\n\nPlease enter your full name.",
    },
    "ask_phone_after_name": {
        "uz": "Rahmat, {full_name}! Endi telefon raqamingizni ulashing.",
        "ru": "Спасибо, {full_name}! Теперь поделитесь своим номером телефона.",
        "en": "Thank you, {full_name}! Now please share your phone number.",
    },
    "share_contact_button": {
        "uz": "\U0001F4F1 Telefon raqamini ulashish",
        "ru": "\U0001F4F1 Поделиться номером",
        "en": "\U0001F4F1 Share phone number",
    },
    "ask_delivery_location": {
        "uz": "\U0001F4CD Buyurtmangizni yetkazib berish uchun joylashuvingizni ulashing.",
        "ru": "\U0001F4CD Пожалуйста, поделитесь своим местоположением для доставки заказа.",
        "en": "\U0001F4CD Please share your location so we can deliver your order.",
    },
    "share_location_button": {
        "uz": "\U0001F4CD Joylashuvni ulashish",
        "ru": "\U0001F4CD Поделиться местоположением",
        "en": "\U0001F4CD Share location",
    },
    "full_name_prompt": {
        "uz": "Ism va familiyangizni kiriting:\nMasalan: Otabek Xurramov",
        "ru": "Введите имя и фамилию:\nНапример: Отабек Хуррамов",
        "en": "Enter your full name:\nExample: Otabek Xurramov",
    },
    "onboarding_confirmation_summary": {
        "uz": "Ma'lumotlaringizni tekshiring:\n\nIsm: {full_name}\nTelefon: {phone_number}\nTil: {language_name}",
        "ru": "Проверьте свои данные:\n\nИмя: {full_name}\nТелефон: {phone_number}\nЯзык: {language_name}",
        "en": "Please review your details:\n\nName: {full_name}\nPhone: {phone_number}\nLanguage: {language_name}",
    },
    "onboarding_confirm_button": {
        "uz": "\u2705 Tasdiqlash",
        "ru": "\u2705 Подтвердить",
        "en": "\u2705 Confirm",
    },
    "onboarding_edit_button": {
        "uz": "\u270F\uFE0F O'zgartirish",
        "ru": "\u270F\uFE0F Изменить",
        "en": "\u270F\uFE0F Edit",
    },
    "onboarding_cancel_button": {
        "uz": "\u274C Bekor qilish",
        "ru": "\u274C Отмена",
        "en": "\u274C Cancel",
    },
    "onboarding_cancelled": {
        "uz": "Ro'yxatdan o'tish bekor qilindi. Qayta boshlash uchun /start yuboring.",
        "ru": "Регистрация отменена. Отправьте /start, чтобы начать заново.",
        "en": "Registration cancelled. Send /start to begin again.",
    },
    "onboarding_expired": {
        "uz": "Sessiya muddati tugadi. Iltimos, /start buyrug'ini qayta yuboring.",
        "ru": "Сессия истекла. Пожалуйста, отправьте команду /start снова.",
        "en": "Session expired. Please send /start again.",
    },
    "language_name_uz": {"uz": "O'zbekcha", "ru": "O'zbekcha", "en": "O'zbekcha"},
    "language_name_ru": {"uz": "Русский", "ru": "Русский", "en": "Русский"},
    "language_name_en": {"uz": "English", "ru": "English", "en": "English"},
    "full_name_too_short": {
        "uz": "Iltimos, haqiqiy ism-familiyangizni kiriting (kamida 2 ta belgi).",
        "ru": "Пожалуйста, введите настоящее полное имя (минимум 2 символа).",
        "en": "Please enter your real full name (at least 2 characters).",
    },
    "registration_success": {
        "uz": "\u2705 Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!",
        "ru": "\u2705 Регистрация успешно завершена!",
        "en": "\u2705 Registration completed successfully!",
    },
    "account_found": {
        "uz": "\u2705 Akkauntingiz topildi.",
        "ru": "\u2705 Ваш аккаунт найден.",
        "en": "\u2705 Your account was found.",
    },
    "contact_ownership_violation": {
        "uz": "Iltimos, faqat o'zingizning telefon raqamingizni yuboring.",
        "ru": "Пожалуйста, отправьте только свой собственный номер телефона.",
        "en": "Please share only your own phone number.",
    },
    "already_linked_elsewhere": {
        "uz": "Bu telefon raqami boshqa hisobga bog'langan. Yordam uchun operator bilan bog'laning.",
        "ru": "Этот номер телефона привязан к другому аккаунту. Обратитесь к оператору за помощью.",
        "en": "This phone number is linked to a different account. Please contact support.",
    },
    "technical_error": {
        "uz": "Texnik xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
        "ru": "Произошла техническая ошибка. Пожалуйста, попробуйте снова.",
        "en": "A technical error occurred. Please try again.",
    },
    "otp_resend_too_soon_with_time": {
        "uz": "Iltimos, yangi kod so'rashdan oldin {seconds} soniya kuting.",
        "ru": "Пожалуйста, подождите {seconds} секунд перед повторным запросом кода.",
        "en": "Please wait {seconds} seconds before requesting another code.",
    },
    "otp_resend_too_soon": {
        "uz": "Iltimos, biroz kutib, keyin qayta urinib ko'ring.",
        "ru": "Пожалуйста, подождите немного и попробуйте снова.",
        "en": "Please wait a moment and try again.",
    },
    "otp_max_attempts": {
        "uz": "Bir soat ichida juda ko'p marta kod so'raldi. Iltimos, birozdan so'ng qayta urinib ko'ring.",
        "ru": "Слишком много запросов кода за последний час. Пожалуйста, попробуйте немного позже.",
        "en": "Too many code requests in the last hour. Please try again a bit later.",
    },
    "please_register": {
        "uz": "Iltimos, avval ro'yxatdan o'ting: /start",
        "ru": "Пожалуйста, сначала зарегистрируйтесь: /start",
        "en": "Please register first: /start",
    },
    "unknown_action": {
        "uz": "Noma'lum amal.",
        "ru": "Неизвестное действие.",
        "en": "Unknown action.",
    },
    "not_found": {
        "uz": "Mahsulot yoki savat topilmadi.",
        "ru": "Товар или корзина не найдены.",
        "en": "Product or cart not found.",
    },
    "main_menu": {
        "uz": "\U0001F944 <b>NUTRIZONE</b>\n\nQuyidagi bo'limlardan birini tanlang.\n\U0001F50E <i>Yoki mahsulot nomini yozing — masalan, «protein» yoki «ozish uchun».</i>",
        "ru": "\U0001F944 <b>NUTRIZONE</b>\n\nВыберите один из разделов.\n\U0001F50E <i>Или просто напишите, что ищете — например, «протеин» или «для похудения».</i>",
        "en": "\U0001F944 <b>NUTRIZONE</b>\n\nChoose a section below.\n\U0001F50E <i>Or just type what you're looking for — e.g. “protein” or “weight loss”.</i>",
    },
    "search_found": {
        "uz": "\U0001F50E «<b>{query}</b>» bo'yicha <b>{count}</b> ta mahsulot topildi:",
        "ru": "\U0001F50E По запросу «<b>{query}</b>» найдено товаров: <b>{count}</b>",
        "en": "\U0001F50E Found <b>{count}</b> product(s) for “<b>{query}</b>”:",
    },
    "search_no_results": {
        "uz": "\U0001F614 «<b>{query}</b>» bo'yicha hech narsa topilmadi.\n\nBoshqacha yozib ko'ring yoki katalogni ko'ring. Kerakli mahsulotni topishda operatorimiz yordam beradi.",
        "ru": "\U0001F614 По запросу «<b>{query}</b>» ничего не найдено.\n\nПопробуйте написать иначе или откройте каталог. Наш оператор поможет найти нужный товар.",
        "en": "\U0001F614 Nothing found for “<b>{query}</b>”.\n\nTry another spelling or browse the catalog. Our support team can help you find it.",
    },
    "menu_catalog": {
        "uz": "\U0001F6CD Katalog",
        "ru": "\U0001F6CD Каталог",
        "en": "\U0001F6CD Catalog",
    },
    "menu_cart": {
        "uz": "\U0001F6D2 Savatcha",
        "ru": "\U0001F6D2 Корзина",
        "en": "\U0001F6D2 Cart",
    },
    "menu_products": {
        "uz": "\U0001F4E6 Mahsulotlar",
        "ru": "\U0001F4E6 Товары",
        "en": "\U0001F4E6 Products",
    },
    "menu_brands": {
        "uz": "\U0001F3F7 Brendlar",
        "ru": "\U0001F3F7 Бренды",
        "en": "\U0001F3F7 Brands",
    },
    "menu_stores": {
        "uz": "\U0001F3EA Do'konlar",
        "ru": "\U0001F3EA Магазины",
        "en": "\U0001F3EA Stores",
    },
    "menu_loyalty": {
        "uz": "\U0001FA99 Bonuslarim",
        "ru": "\U0001FA99 Мои бонусы",
        "en": "\U0001FA99 My rewards",
    },
    "menu_orders": {
        "uz": "\U0001F4CB Buyurtmalarim",
        "ru": "\U0001F4CB Мои заказы",
        "en": "\U0001F4CB My Orders",
    },
    "menu_open_shop": {
        "uz": "\U0001F6CD Do'konni ochish",
        "ru": "\U0001F6CD Открыть магазин",
        "en": "\U0001F6CD Open the shop",
    },
    "menu_autologin": {
        "uz": "\U0001F310 Saytga avtomatik kirish",
        "ru": "\U0001F310 Автоматический вход на сайт",
        "en": "\U0001F310 Auto-login to website",
    },
    "menu_getcode": {
        "uz": "\U0001F511 Sayt uchun kod olish",
        "ru": "\U0001F511 Получить код для сайта",
        "en": "\U0001F511 Get website login code",
    },
    "menu_social": {
        "uz": "\U0001F4E2 Ijtimoiy tarmoqlar",
        "ru": "\U0001F4E2 Социальные сети",
        "en": "\U0001F4E2 Social media",
    },
    "menu_chat": {
        "uz": "\U0001F4AC Yordam / Chat",
        "ru": "\U0001F4AC Поддержка / Чат",
        "en": "\U0001F4AC Support / Chat",
    },
    "brands_list_title": {
        "uz": "\U0001F3F7 Brendlar",
        "ru": "\U0001F3F7 Бренды",
        "en": "\U0001F3F7 Brands",
    },
    "no_brands": {
        "uz": "Hozircha brendlar mavjud emas.",
        "ru": "Пока нет доступных брендов.",
        "en": "No brands available yet.",
    },
    "stores_list_title": {
        "uz": "\U0001F3EA Bizning do'konlarimiz",
        "ru": "\U0001F3EA Наши магазины",
        "en": "\U0001F3EA Our stores",
    },
    "no_stores": {
        "uz": "Hozircha do'konlar mavjud emas.",
        "ru": "Пока нет доступных магазинов.",
        "en": "No stores available yet.",
    },
    "my_orders_title": {
        "uz": "\U0001F4CB Sizning buyurtmalaringiz",
        "ru": "\U0001F4CB Ваши заказы",
        "en": "\U0001F4CB Your orders",
    },
    "no_orders": {
        "uz": "Sizda hali buyurtmalar yo'q.",
        "ru": "У вас пока нет заказов.",
        "en": "You have no orders yet.",
    },
    "social_links_text": {
        "uz": "\U0001F4E2 Bizni kuzatib boring:",
        "ru": "\U0001F4E2 Следите за нами:",
        "en": "\U0001F4E2 Follow us:",
    },
    "no_social_links_yet": {
        "uz": "Ijtimoiy tarmoq havolalari hali sozlanmagan.",
        "ru": "Ссылки на соцсети пока не настроены.",
        "en": "Social media links have not been configured yet.",
    },
    "chat_prompt": {
        "uz": "\U0001F4AC Xabaringizni yozing, yordam xizmatimiz tez orada javob beradi.",
        "ru": "\U0001F4AC Напишите ваше сообщение, служба поддержки скоро ответит.",
        "en": "\U0001F4AC Type your message, our support team will reply soon.",
    },
    "chat_message_sent": {
        "uz": "\u2705 Xabaringiz yuborildi. Tez orada javob beramiz!",
        "ru": "\u2705 Ваше сообщение отправлено. Скоро ответим!",
        "en": "\u2705 Your message has been sent. We'll reply soon!",
    },
    "end_chat_button": {
        "uz": "\U0001F519 Chatni tugatish",
        "ru": "\U0001F519 Завершить чат",
        "en": "\U0001F519 End chat",
    },
    "login_code_sent": {
        # Real, product-required change: this message now carries an
        # inline keyboard ("Open website" / "Get a new code"), sent via
        # `LiveTelegramGateway.send_message_with_keyboard` (the only
        # method that accepts `reply_markup`), which always sends with
        # `parse_mode: "HTML"` -- not plain send_message's legacy
        # Markdown this template used before. `<code>...</code>` is
        # HTML's own monospace/tap-to-copy formatting, the direct
        # equivalent of the single backticks used previously -- this is
        # what actually delivers the "maxsus copy formatida chiroyli
        # tartibli" requirement.
        "uz": "\U0001F511 Sayt uchun kodingiz:\n\n<code>{code}</code>\n\n\u261D Kodga bosib, uni nusxalab olishingiz mumkin.\n\u23F1 {minutes} daqiqa davomida amal qiladi.\n\u26A0\uFE0F Hech kim bilan baham ko'rmang.",
        "ru": "\U0001F511 Ваш код для сайта:\n\n<code>{code}</code>\n\n\u261D Нажмите на код, чтобы скопировать его.\n\u23F1 Действителен {minutes} мин.\n\u26A0\uFE0F Никому не сообщайте его.",
        "en": "\U0001F511 Your website login code:\n\n<code>{code}</code>\n\n\u261D Tap the code to copy it.\n\u23F1 Valid for {minutes} minutes.\n\u26A0\uFE0F Never share it with anyone.",
    },
    "resend_code_button": {
        "uz": "\U0001F504 Yangi kod olish",
        "ru": "\U0001F504 Получить новый код",
        "en": "\U0001F504 Get a new code",
    },
    "autologin_link_text": {
        "uz": "⚡ Quyidagi tugma sizni kod so'ramasdan darhol saytga kirgizadi:",
        "ru": "⚡ Кнопка ниже сразу войдёт на сайт без запроса кода:",
        "en": "⚡ The button below logs you in instantly -- no code needed:",
    },
    # Real, confirmed bug this closes: this button and "enter_code_button"
    # below both used to say the exact same "Saytga o'tish"/"Open
    # website", even though they go to two completely different real
    # destinations -- one instantly authenticates (/auto-login?session=,
    # no code needed), the other opens the plain code-entry page (/login,
    # requires typing the 6-digit code). Identical labels on two
    # different-behavior buttons is exactly what let a customer land on
    # the wrong one and report "the button skips straight past the login
    # page" -- the fix is making the two buttons impossible to confuse,
    # not touching either destination (both were already correct).
    "open_website_button": {
        "uz": "⚡ Bir bosishda kirish",
        "ru": "⚡ Войти в один клик",
        "en": "⚡ One-tap login",
    },
    "enter_code_button": {
        "uz": "\U0001F511 Kodni kiritish sahifasi",
        "ru": "\U0001F511 Страница ввода кода",
        "en": "\U0001F511 Enter code page",
    },
    "home_button": {
        "uz": "\U0001F3E0 Bosh menyu",
        "ru": "\U0001F3E0 Главное меню",
        "en": "\U0001F3E0 Main menu",
    },
    "back_button": {
        "uz": "\u2b05\ufe0f Orqaga",
        "ru": "\u2b05\ufe0f Назад",
        "en": "\u2b05\ufe0f Back",
    },
    "no_categories": {
        "uz": "Hozircha kategoriyalar mavjud emas.",
        "ru": "Категории пока недоступны.",
        "en": "No categories available yet.",
    },
    "catalog_title": {
        "uz": "\U0001F6CD <b>NUTRIZONE KATALOG</b>\n\nKategoriyani tanlang:",
        "ru": "\U0001F6CD <b>КАТАЛОГ NUTRIZONE</b>\n\nВыберите категорию:",
        "en": "\U0001F6CD <b>NUTRIZONE CATALOG</b>\n\nChoose a category:",
    },
    "no_products_in_category": {
        "uz": "Bu kategoriyada hozircha mahsulot yo'q.",
        "ru": "В этой категории пока нет товаров.",
        "en": "There are no products in this category yet.",
    },
    "products_count": {
        "uz": "\U0001F6CD Mahsulotlar ({count} ta):",
        "ru": "\U0001F6CD Товары ({count} шт.):",
        "en": "\U0001F6CD Products ({count}):",
    },
    "product_not_found": {
        "uz": "Mahsulot topilmadi yoki hozircha mavjud emas.",
        "ru": "Товар не найден или временно недоступен.",
        "en": "Product not found or currently unavailable.",
    },
    "available": {
        "uz": "\u2705 Mavjud",
        "ru": "\u2705 В наличии",
        "en": "\u2705 Available",
    },
    "unavailable": {
        "uz": "\u274c Hozircha mavjud emas",
        "ru": "\u274c Временно недоступно",
        "en": "\u274c Currently unavailable",
    },
    "added_to_cart": {
        "uz": "\u2705 Mahsulot savatchaga qo'shildi.",
        "ru": "\u2705 Товар добавлен в корзину.",
        "en": "\u2705 Item added to your cart.",
    },
    "view_cart_button": {
        "uz": "\U0001F6D2 Savatchani ko'rish",
        "ru": "\U0001F6D2 Открыть корзину",
        "en": "\U0001F6D2 View cart",
    },
    "continue_shopping_button": {
        "uz": "\U0001F6CD Xaridni davom ettirish",
        "ru": "\U0001F6CD Продолжить покупки",
        "en": "\U0001F6CD Continue shopping",
    },
    "cart_title": {
        "uz": "\U0001F6D2 <b>SAVATCHA</b>\n",
        "ru": "\U0001F6D2 <b>КОРЗИНА</b>\n",
        "en": "\U0001F6D2 <b>CART</b>\n",
    },
    "cart_empty": {
        "uz": "\U0001F6D2 Savatchangiz hozircha bo'sh.",
        "ru": "\U0001F6D2 Ваша корзина пока пуста.",
        "en": "\U0001F6D2 Your cart is currently empty.",
    },
    "cart_total": {
        "uz": "Jami: {total} {currency}",
        "ru": "Итого: {total} {currency}",
        "en": "Total: {total} {currency}",
    },
    "price_pending": {
        "uz": "(narx aniqlanmoqda)",
        "ru": "(цена уточняется)",
        "en": "(price pending)",
    },
    "checkout_button": {
        "uz": "\u2705 Buyurtma berish",
        "ru": "\u2705 Оформить заказ",
        "en": "\u2705 Place order",
    },
    "checkout_title": {
        "uz": "\U0001F9FE <b>BUYURTMA</b>\n\n\U0001F4B0 Jami: {total} {currency}\n\n\U0001F4B5 To'lov: Naqd\n\nBuyurtmani tasdiqlaysizmi?",
        "ru": "\U0001F9FE <b>ЗАКАЗ</b>\n\n\U0001F4B0 Итого: {total} {currency}\n\n\U0001F4B5 Оплата: Наличными\n\nПодтвердить заказ?",
        "en": "\U0001F9FE <b>ORDER</b>\n\n\U0001F4B0 Total: {total} {currency}\n\n\U0001F4B5 Payment: Cash\n\nConfirm this order?",
    },
    "checkout_confirm_button": {
        "uz": "\u2705 Buyurtmani tasdiqlash",
        "ru": "\u2705 Подтвердить заказ",
        "en": "\u2705 Confirm order",
    },
    "checkout_cancel_button": {
        "uz": "\u274c Bekor qilish",
        "ru": "\u274c Отменить",
        "en": "\u274c Cancel",
    },
    "checkout_cancelled": {
        "uz": "Buyurtma berish jarayoni bekor qilindi.",
        "ru": "Оформление заказа отменено.",
        "en": "Checkout was cancelled.",
    },
    "checkout_not_ready_prices": {
        "uz": "Ba'zi mahsulotlar narxi hali tasdiqlanmagan. Iltimos, savatchani qayta tekshiring.",
        "ru": "Цены на некоторые товары ещё не подтверждены. Пожалуйста, проверьте корзину ещё раз.",
        "en": "Some items still need price confirmation. Please check your cart again.",
    },
    "checkout_not_ready_generic": {
        "uz": "Savatcha buyurtma berishga tayyor emas. Iltimos, qayta urinib ko'ring.",
        "ru": "Корзина не готова к оформлению заказа. Пожалуйста, попробуйте снова.",
        "en": "Your cart is not ready for checkout. Please try again.",
    },
    "order_already_placed": {
        "uz": "\U0001F389 Buyurtmangiz allaqachon qabul qilingan!\n\n\U0001F9FE Buyurtma \u2116 {order_number}",
        "ru": "\U0001F389 Ваш заказ уже принят!\n\n\U0001F9FE Заказ \u2116 {order_number}",
        "en": "\U0001F389 Your order was already placed!\n\n\U0001F9FE Order \u2116 {order_number}",
    },
    "checkout_choose_payment": {
        "uz": "\U0001F9FE <b>BUYURTMA</b>\n\n\U0001F4B0 Jami: {total} {currency}\n\nTo'lov usulini tanlang:",
        "ru": "\U0001F9FE <b>ЗАКАЗ</b>\n\n\U0001F4B0 Итого: {total} {currency}\n\nВыберите способ оплаты:",
        "en": "\U0001F9FE <b>ORDER</b>\n\n\U0001F4B0 Total: {total} {currency}\n\nChoose how to pay:",
    },
    "checkout_pay_cash_button": {
        "uz": "\U0001F4B5 Naqd — yetkazib berishda",
        "ru": "\U0001F4B5 Наличными при получении",
        "en": "\U0001F4B5 Cash on delivery",
    },
    "checkout_pay_online_button": {
        "uz": "\U0001F4B3 {provider} orqali onlayn",
        "ru": "\U0001F4B3 Онлайн через {provider}",
        "en": "\U0001F4B3 Online with {provider}",
    },
    "order_placed_online": {
        "uz": "\U0001F389 Buyurtmangiz qabul qilindi!\n\n\U0001F9FE Buyurtma \u2116 {order_number}\n\U0001F4B0 Jami: {total} {currency}\n\U0001F4B3 To'lov: {provider}\n\nQuyidagi tugma orqali to'lang — to'lov tushishi bilan buyurtma avtomatik tasdiqlanadi.",
        "ru": "\U0001F389 Ваш заказ принят!\n\n\U0001F9FE Заказ \u2116 {order_number}\n\U0001F4B0 Итого: {total} {currency}\n\U0001F4B3 Оплата: {provider}\n\nОплатите кнопкой ниже — заказ подтвердится автоматически, как только поступит оплата.",
        "en": "\U0001F389 Your order has been placed!\n\n\U0001F9FE Order \u2116 {order_number}\n\U0001F4B0 Total: {total} {currency}\n\U0001F4B3 Payment: {provider}\n\nPay with the button below — the order is confirmed automatically as soon as the payment arrives.",
    },
    "pay_cash_ok": {
        "uz": "\u2705 Kelishdik! {order_number} buyurtmasi uchun kuryerga naqd to'laysiz. Operator tez orada siz bilan bog'lanadi.",
        "ru": "\u2705 Договорились! За заказ {order_number} вы заплатите курьеру наличными. Оператор скоро свяжется с вами.",
        "en": "\u2705 Done! You'll pay the courier in cash for order {order_number}. An operator will contact you shortly.",
    },
    "pay_cash_paid": {
        "uz": "\u2705 {order_number} buyurtmasi allaqachon to'langan.",
        "ru": "\u2705 Заказ {order_number} уже оплачен.",
        "en": "\u2705 Order {order_number} is already paid.",
    },
    "pay_cash_in_flight": {
        "uz": "\u23F3 To'lov hozir amalga oshirilmoqda. Bir necha daqiqadan so'ng qayta urinib ko'ring.",
        "ru": "\u23F3 Оплата сейчас проводится. Попробуйте снова через несколько минут.",
        "en": "\u23F3 A payment is in progress right now. Please try again in a few minutes.",
    },
    "pay_cash_not_open": {
        "uz": "Bu buyurtmaning to'lov usulini endi o'zgartirib bo'lmaydi.",
        "ru": "Способ оплаты этого заказа уже нельзя изменить.",
        "en": "The payment method of this order can no longer be changed.",
    },
    "order_placed": {
        "uz": "\U0001F389 Buyurtmangiz qabul qilindi!\n\n\U0001F9FE Buyurtma \u2116 {order_number}\n\U0001F4B0 Jami: {total} {currency}\n\U0001F4B5 To'lov: Naqd\n\nOperator tez orada siz bilan bog'lanadi.",
        "ru": "\U0001F389 Ваш заказ принят!\n\n\U0001F9FE Заказ \u2116 {order_number}\n\U0001F4B0 Итого: {total} {currency}\n\U0001F4B5 Оплата: Наличными\n\nОператор свяжется с вами в ближайшее время.",
        "en": "\U0001F389 Your order has been placed!\n\n\U0001F9FE Order \u2116 {order_number}\n\U0001F4B0 Total: {total} {currency}\n\U0001F4B5 Payment: Cash\n\nAn operator will contact you shortly.",
    },
    "auth_login_confirm_prompt": {
        "uz": "\U0001F510 NutriZone saytiga kirish\n\nSaytga kirish uchun so'rov yuborildi.\n\nDavom etishni xohlaysizmi?",
        "ru": "\U0001F510 Вход в NutriZone\n\nПоступил запрос на вход на сайт.\n\nВы хотите продолжить?",
        "en": "\U0001F510 NutriZone login\n\nA login request was made from the website.\n\nDo you want to continue?",
    },
    "auth_login_confirm_button": {
        "uz": "\u2705 Tasdiqlash",
        "ru": "\u2705 Подтвердить",
        "en": "\u2705 Confirm login",
    },
    "auth_login_cancel_button": {
        "uz": "\u274C Bekor qilish",
        "ru": "\u274C Отменить",
        "en": "\u274C Cancel",
    },
    "auth_login_confirmed": {
        "uz": "\u2705 Saytga muvaffaqiyatli kirdingiz. Endi saytga qaytishingiz mumkin.",
        "ru": "\u2705 Вы успешно вошли на сайт. Теперь можете вернуться на сайт.",
        "en": "\u2705 You have successfully logged in. You can now return to the website.",
    },
    "auth_login_cancelled": {
        "uz": "Kirish so'rovi bekor qilindi.",
        "ru": "Запрос на вход отменён.",
        "en": "The login request was cancelled.",
    },
    "auth_login_expired": {
        "uz": "Bu kirish so'rovi muddati tugagan. Saytda qaytadan urinib ko'ring.",
        "ru": "Срок действия этого запроса на вход истёк. Попробуйте снова на сайте.",
        "en": "This login request has expired. Please try again on the website.",
    },
    "auth_login_invalid": {
        "uz": "Kirish havolasi yaroqsiz yoki allaqachon ishlatilgan.",
        "ru": "Ссылка для входа недействительна или уже использована.",
        "en": "This login link is invalid or has already been used.",
    },
    "auth_login_not_linked": {
        "uz": "Bu Telegram akkaunti hech qanday NutriZone akkauntiga ulanmagan. Avval telefon raqamingizni yuboring.",
        "ru": "Этот аккаунт Telegram не связан ни с одним аккаунтом NutriZone. Сначала отправьте свой номер телефона.",
        "en": "This Telegram account is not linked to any NutriZone account. Please share your phone number first.",
    },
    # --- Product browsing (premium mini-store upgrade) ---
    "products_menu_title": {
        "uz": "\U0001F6CD <b>NUTRIZONE MAHSULOTLARI</b>\n\nMahsulotlarni tanlang:",
        "ru": "\U0001F6CD <b>ТОВАРЫ NUTRIZONE</b>\n\nВыберите товары:",
        "en": "\U0001F6CD <b>NUTRIZONE PRODUCTS</b>\n\nChoose products:",
    },
    "products_menu_sale": {
        "uz": "\U0001F4B0 Aksiyadagi mahsulotlar",
        "ru": "\U0001F4B0 Товары со скидкой",
        "en": "\U0001F4B0 On sale",
    },
    "no_sale_products": {
        "uz": "\U0001F4B0 Hozircha aksiyadagi mahsulot yo'q. Yangi chegirmalar haqida \U0001F4E2 Yangiliklar bo'limida xabar beramiz.",
        "ru": "\U0001F4B0 Сейчас нет товаров со скидкой. О новых акциях сообщим в разделе \U0001F4E2 Новости.",
        "en": "\U0001F4B0 Nothing is on sale right now. We announce new deals in \U0001F4E2 News.",
    },
    "products_menu_best": {
        "uz": "\U0001F525 Eng ko'p sotilganlar",
        "ru": "\U0001F525 Самые продаваемые",
        "en": "\U0001F525 Best sellers",
    },
    "products_menu_new": {
        "uz": "\U0001F195 Yangi mahsulotlar",
        "ru": "\U0001F195 Новые товары",
        "en": "\U0001F195 New products",
    },
    "products_menu_all": {
        "uz": "\U0001F4E6 Barcha mahsulotlar",
        "ru": "\U0001F4E6 Все товары",
        "en": "\U0001F4E6 All products",
    },
    "reviews_count": {
        "uz": "{count} ta sharh",
        "ru": "{count} отзывов",
        "en": "{count} reviews",
    },
    "no_reviews_yet": {
        "uz": "Hali sharhlar yo'q",
        "ru": "Пока нет отзывов",
        "en": "No reviews yet",
    },
    "stock_available": {
        "uz": "\U0001F7E2 Mavjud · {stock} dona",
        "ru": "\U0001F7E2 В наличии · {stock} шт.",
        "en": "\U0001F7E2 In stock · {stock} pcs",
    },
    "stock_unavailable": {
        "uz": "\U0001F534 Mavjud emas",
        "ru": "\U0001F534 Нет в наличии",
        "en": "\U0001F534 Out of stock",
    },
    "btn_add_to_cart": {
        "uz": "\U0001F6D2 Savatga qo'shish",
        "ru": "\U0001F6D2 В корзину",
        "en": "\U0001F6D2 Add to cart",
    },
    "btn_view_detail": {
        "uz": "\U0001F441 Batafsil",
        "ru": "\U0001F441 Подробнее",
        "en": "\U0001F441 Details",
    },
    "btn_wishlist_add": {
        "uz": "❤️ Wishlist",
        "ru": "❤️ В избранное",
        "en": "❤️ Wishlist",
    },
    "btn_wishlist_added": {
        "uz": "\U0001F49A Wishlist'da",
        "ru": "\U0001F49A В избранном",
        "en": "\U0001F49A In wishlist",
    },
    "btn_buy_now": {
        "uz": "⚡ Hozir sotib olish",
        "ru": "⚡ Купить сейчас",
        "en": "⚡ Buy now",
    },
    "btn_view_website": {
        "uz": "\U0001F310 Saytda ko'rish",
        "ru": "\U0001F310 Смотреть на сайте",
        "en": "\U0001F310 View on website",
    },
    "btn_filter": {
        "uz": "\U0001F3AF Filtrlash",
        "ru": "\U0001F3AF Фильтр",
        "en": "\U0001F3AF Filter",
    },
    "wishlist_added_toast": {
        "uz": "❤️ Wishlist'ga qo'shildi",
        "ru": "❤️ Добавлено в избранное",
        "en": "❤️ Added to wishlist",
    },
    "wishlist_removed_toast": {
        "uz": "Wishlist'dan olib tashlandi",
        "ru": "Удалено из избранного",
        "en": "Removed from wishlist",
    },
    "empty_products": {
        "uz": "\U0001F50D Hech qanday mahsulot topilmadi.\n\nFiltrlarni o'zgartirib ko'ring.",
        "ru": "\U0001F50D Товары не найдены.\n\nПопробуйте изменить фильтры.",
        "en": "\U0001F50D No products found.\n\nTry changing your filters.",
    },
    "btn_clear_filters": {
        "uz": "\U0001F504 Filtrlarni tozalash",
        "ru": "\U0001F504 Сбросить фильтры",
        "en": "\U0001F504 Clear filters",
    },
    "product_gone": {
        "uz": "Ushbu mahsulot endi mavjud emas.",
        "ru": "Этот товар больше недоступен.",
        "en": "This product is no longer available.",
    },
    "session_expired_reopen": {
        "uz": "Ushbu ro'yxat muddati tugagan. Iltimos, mahsulotlar bo'limini qayta oching.",
        "ru": "Срок действия этого списка истёк. Пожалуйста, откройте раздел товаров заново.",
        "en": "This list has expired. Please reopen the products section.",
    },
    # --- Filter panel ---
    "filter_menu_title": {
        "uz": "\U0001F3AF <b>FILTRLASH</b>\n\nQaysi mezon bo'yicha saralashni xohlaysiz?",
        "ru": "\U0001F3AF <b>ФИЛЬТР</b>\n\nПо какому критерию отфильтровать?",
        "en": "\U0001F3AF <b>FILTER</b>\n\nWhich criterion would you like to filter by?",
    },
    "filter_brand": {
        "uz": "\U0001F3F7 Brend",
        "ru": "\U0001F3F7 Бренд",
        "en": "\U0001F3F7 Brand",
    },
    "filter_category": {
        "uz": "\U0001F4E6 Kategoriya",
        "ru": "\U0001F4E6 Категория",
        "en": "\U0001F4E6 Category",
    },
    "filter_rating": {
        "uz": "⭐ Reyting",
        "ru": "⭐ Рейтинг",
        "en": "⭐ Rating",
    },
    "filter_price": {
        "uz": "\U0001F4B0 Narx",
        "ru": "\U0001F4B0 Цена",
        "en": "\U0001F4B0 Price",
    },
    "inline_in_stock": {
        "uz": "Sotuvda bor",
        "ru": "В наличии",
        "en": "In stock",
    },
    "inline_out_of_stock": {
        "uz": "Hozircha tugagan",
        "ru": "Нет в наличии",
        "en": "Out of stock",
    },
    "inline_open_in_bot": {
        "uz": "\U0001F6D2 Botda xarid qilish",
        "ru": "\U0001F6D2 Купить в боте",
        "en": "\U0001F6D2 Buy in the bot",
    },
    "inline_shop_button": {
        "uz": "\U0001F6CD NutriZone do'konini ochish",
        "ru": "\U0001F6CD Открыть магазин NutriZone",
        "en": "\U0001F6CD Open the NutriZone shop",
    },
    "filter_rating_title": {
        "uz": "⭐ <b>REYTING</b>\n\nMijozlar bahosi shundan past bo'lmagan mahsulotlar:",
        "ru": "⭐ <b>РЕЙТИНГ</b>\n\nТовары с оценкой покупателей не ниже:",
        "en": "⭐ <b>RATING</b>\n\nProducts rated by customers at least:",
    },
    "filter_price_title": {
        "uz": "\U0001F4B0 <b>NARX</b>\n\nNarx oralig'ini tanlang:",
        "ru": "\U0001F4B0 <b>ЦЕНА</b>\n\nВыберите диапазон цен:",
        "en": "\U0001F4B0 <b>PRICE</b>\n\nChoose a price range:",
    },
    "currency_som": {
        "uz": "so'm",
        "ru": "сум",
        "en": "UZS",
    },
    "filter_not_supported_yet": {
        "uz": "Bu filtr hozircha qo'llab-quvvatlanmaydi.",
        "ru": "Этот фильтр пока не поддерживается.",
        "en": "This filter isn't supported yet.",
    },
    "filter_brand_select_title": {
        "uz": "\U0001F3F7 <b>BREND TANLANG</b>",
        "ru": "\U0001F3F7 <b>ВЫБЕРИТЕ БРЕНД</b>",
        "en": "\U0001F3F7 <b>SELECT A BRAND</b>",
    },
    "filter_active_brand": {
        "uz": "\U0001F3F7 Brend: {name}",
        "ru": "\U0001F3F7 Бренд: {name}",
        "en": "\U0001F3F7 Brand: {name}",
    },
    "filter_active_category": {
        "uz": "\U0001F4E6 Kategoriya: {name}",
        "ru": "\U0001F4E6 Категория: {name}",
        "en": "\U0001F4E6 Category: {name}",
    },
    "no_brands": {
        "uz": "Hozircha brendlar mavjud emas.",
        "ru": "Пока нет доступных брендов.",
        "en": "No brands available yet.",
    },
    # --- Brand detail ---
    "brand_products_count": {
        "uz": "{count} ta mahsulot",
        "ru": "{count} товаров",
        "en": "{count} products",
    },
    # --- Order detail ---
    "order_detail_title": {
        "uz": "\U0001F4E6 <b>BUYURTMA #{number}</b>",
        "ru": "\U0001F4E6 <b>ЗАКАЗ #{number}</b>",
        "en": "\U0001F4E6 <b>ORDER #{number}</b>",
    },
    "order_status_label": {
        "uz": "Holat:",
        "ru": "Статус:",
        "en": "Status:",
    },
    "order_products_label": {
        "uz": "Mahsulotlar:",
        "ru": "Товары:",
        "en": "Products:",
    },
    "order_total_label": {
        "uz": "Jami:",
        "ru": "Итого:",
        "en": "Total:",
    },
    "order_address_label": {
        "uz": "Manzil:",
        "ru": "Адрес:",
        "en": "Address:",
    },
    "btn_order_detail": {
        "uz": "Batafsil",
        "ru": "Подробнее",
        "en": "Details",
    },
    "order_not_found": {
        "uz": "Buyurtma topilmadi.",
        "ru": "Заказ не найден.",
        "en": "Order not found.",
    },
    # --- Generic error/empty states ---
    "service_unavailable": {
        "uz": "⚠️ Hozircha xizmat bilan bog'lanib bo'lmadi.\n\nIltimos, birozdan so'ng qayta urinib ko'ring.",
        "ru": "⚠️ Не удалось связаться со службой.\n\nПожалуйста, повторите попытку позже.",
        "en": "⚠️ Could not reach the service right now.\n\nPlease try again shortly.",
    },
    "btn_retry": {
        "uz": "\U0001F504 Qayta urinish",
        "ru": "\U0001F504 Повторить",
        "en": "\U0001F504 Retry",
    },
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """
    Looks up a translation by key and language, formatting any
    provided keyword arguments. Falls back to English, then to the
    key itself (never raises) so a missing/unsupported language never
    breaks message delivery.
    """
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key
    from apps.platform.infrastructure.branding import rebrand

    text = rebrand(entry.get(lang) or entry.get("en") or next(iter(entry.values())))
    return text.format(**kwargs) if kwargs else text
