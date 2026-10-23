"""
Reference lists for the catalog -- package types, flavours and tags in uz / ru / en (images are added in the dashboard).

`seed_reference()` is idempotent: rows are matched by slug / code, missing languages are filled in, nothing an editor
changed is overwritten, and a soft-deleted row from the list is restored. Flavour names double as the vocabulary the
product grouping uses to recognise flavours inside product names (product_grouping.py).
"""
from __future__ import annotations

# slug, uz, ru, en
PACKAGES = [
    ("jar", "Banka", "Банка", "Jar"),
    ("tub", "Katta banka (tuba)", "Туба (большая банка)", "Tub"),
    ("pouch", "Doy-pak (zip-lock)", "Дой-пак (zip-lock)", "Pouch (zip-lock)"),
    ("bag", "Paket", "Пакет", "Bag"),
    ("box", "Quti", "Коробка", "Box"),
    ("bottle", "Butilka", "Бутылка", "Bottle"),
    ("capsule-bottle", "Kapsula idishi", "Флакон для капсул", "Capsule bottle"),
    ("dropper-bottle", "Tomizg'ichli flakon", "Флакон с пипеткой", "Dropper bottle"),
    ("blister", "Blister", "Блистер", "Blister pack"),
    ("sachet", "Sashe (bir porsiyalik paketcha)", "Саше (порционный пакетик)", "Sachet"),
    ("stick-pack", "Stik", "Стик", "Stick pack"),
    ("can", "Ichimlik bankasi (tayyor ichimlik)", "Жестяная банка (напиток)", "Can (ready-to-drink)"),
    ("shot", "Ampula / shot", "Ампула / шот", "Shot / ampoule"),
    ("gel-pack", "Energetik gel", "Энергетический гель", "Gel pack"),
    ("bar-wrapper", "Batonchik o'rami", "Обёртка батончика", "Bar wrapper"),
    ("sample", "Probnik (namuna)", "Пробник", "Sample"),
    ("gift-set", "Sovg'a to'plami", "Подарочный набор", "Gift set"),
]

# slug, en, uz, ru, colour (swatch shown until a photo is uploaded)
FLAVOURS = [
    ("chocolate", "Chocolate", "Shokolad", "Шоколад", "#5d3a1a"),
    ("double-rich-chocolate", "Double Rich Chocolate", "Ikki karra shokolad", "Двойной шоколад", "#3f2210"),
    ("milk-chocolate", "Milk Chocolate", "Sutli shokolad", "Молочный шоколад", "#8b5a2b"),
    ("white-chocolate", "White Chocolate", "Oq shokolad", "Белый шоколад", "#f1e3c8"),
    ("chocolate-peanut-butter", "Chocolate Peanut Butter", "Shokolad va yeryong'oq pastasi", "Шоколад с арахисовой пастой", "#7a4a23"),
    ("chocolate-mint", "Chocolate Mint", "Shokolad va yalpiz", "Шоколад с мятой", "#3e7b5b"),
    ("chocolate-hazelnut", "Chocolate Hazelnut", "Shokolad va o'rmon yong'og'i", "Шоколад с фундуком", "#6b4423"),
    ("cookies-and-cream", "Cookies & Cream", "Pechenye va qaymoq", "Печенье и крем", "#d9d2c5"),
    ("vanilla", "Vanilla", "Vanil", "Ваниль", "#f3e5ab"),
    ("french-vanilla", "French Vanilla", "Fransuz vanili", "Французская ваниль", "#ebd9a6"),
    ("vanilla-ice-cream", "Vanilla Ice Cream", "Vanilli muzqaymoq", "Ванильное мороженое", "#f6ebc8"),
    ("strawberry", "Strawberry", "Qulupnay", "Клубника", "#e8434f"),
    ("strawberry-banana", "Strawberry Banana", "Qulupnay va banan", "Клубника-банан", "#f28c6b"),
    ("banana", "Banana", "Banan", "Банан", "#f4d35e"),
    ("salted-caramel", "Salted Caramel", "Sho'r karamel", "Солёная карамель", "#c68642"),
    ("caramel", "Caramel", "Karamel", "Карамель", "#c9822b"),
    ("coconut-cream", "Coconut Cream", "Kokos kremi", "Кокосовый крем", "#f5f0e6"),
    ("coconut", "Coconut", "Kokos", "Кокос", "#ede6d6"),
    ("cappuccino", "Cappuccino", "Kapuchino", "Капучино", "#8b6a4f"),
    ("coffee", "Coffee", "Qahva", "Кофе", "#6f4e37"),
    ("mocha", "Mocha", "Mokko", "Мокко", "#4b3621"),
    ("blueberry", "Blueberry", "Chernika", "Черника", "#4f5d9a"),
    ("raspberry", "Raspberry", "Malina", "Малина", "#c2185b"),
    ("blue-raspberry", "Blue Raspberry", "Ko'k malina", "Голубая малина", "#2e86de"),
    ("cherry", "Cherry", "Olcha", "Вишня", "#a4161a"),
    ("mixed-berry", "Mixed Berry", "Rezavor mevalar", "Ягодный микс", "#8e3b6e"),
    ("mango", "Mango", "Mango", "Манго", "#ffb347"),
    ("pineapple", "Pineapple", "Ananas", "Ананас", "#f7d154"),
    ("orange", "Orange", "Apelsin", "Апельсин", "#f28c28"),
    ("lemon", "Lemon", "Limon", "Лимон", "#f9e04b"),
    ("lemon-lime", "Lemon Lime", "Limon va laym", "Лимон-лайм", "#b7d44a"),
    ("lime", "Lime", "Laym", "Лайм", "#8bc34a"),
    ("watermelon", "Watermelon", "Tarvuz", "Арбуз", "#f25f5c"),
    ("green-apple", "Green Apple", "Yashil olma", "Зелёное яблоко", "#8dc63f"),
    ("grape", "Grape", "Uzum", "Виноград", "#6f2da8"),
    ("peach", "Peach", "Shaftoli", "Персик", "#ffb07c"),
    ("fruit-punch", "Fruit Punch", "Mevali punsh", "Фруктовый пунш", "#e63946"),
    ("tropical", "Tropical", "Tropik mevalar", "Тропический", "#ff9f1c"),
    ("pink-lemonade", "Pink Lemonade", "Pushti limonad", "Розовый лимонад", "#f7a8b8"),
    ("lemon-iced-tea", "Lemon Iced Tea", "Limonli muzli choy", "Холодный чай с лимоном", "#d4a017"),
    ("cola", "Cola", "Kola", "Кола", "#3b1f0e"),
    ("tutti-frutti", "Tutti Frutti", "Tutti-frutti", "Тутти-фрутти", "#f06292"),
    ("cotton-candy", "Cotton Candy", "Shirin paxta", "Сахарная вата", "#f8bbd0"),
    ("pistachio", "Pistachio", "Pista", "Фисташка", "#93c572"),
    ("peanut-butter", "Peanut Butter", "Yeryong'oq pastasi", "Арахисовая паста", "#c68e3f"),
    ("hazelnut", "Hazelnut", "O'rmon yong'og'i", "Фундук", "#a0522d"),
    ("cinnamon-roll", "Cinnamon Roll", "Dolchinli bulochka", "Булочка с корицей", "#c68b59"),
    ("birthday-cake", "Birthday Cake", "Tug'ilgan kun torti", "Праздничный торт", "#f7c6d9"),
    ("gourmet-chocolate", "Gourmet Chocolate", "Gurme shokolad", "Шоколад гурмэ", "#4a2c17"),
    ("extreme-milk-chocolate", "Extreme Milk Chocolate", "Ekstrim sutli shokolad", "Экстремальный молочный шоколад", "#7b4a26"),
    ("chocolate-malt", "Chocolate Malt", "Shokolad va solod", "Шоколад с солодом", "#6a4328"),
    ("chocolate-caramel", "Chocolate Caramel", "Shokolad va karamel", "Шоколад с карамелью", "#8a5222"),
    ("chocolate-coconut", "Chocolate Coconut", "Shokolad va kokos", "Шоколад с кокосом", "#5c3b24"),
    ("chocolate-brownie", "Chocolate Brownie", "Shokoladli brauni", "Шоколадный брауни", "#3d2314"),
    ("rocky-road", "Rocky Road", "Roki roud", "Роки роуд", "#5a3a2a"),
    ("delicious-strawberry", "Delicious Strawberry", "Mazali qulupnay", "Восхитительная клубника", "#e23a54"),
    ("strawberry-cream", "Strawberry Cream", "Qulupnay va qaymoq", "Клубника со сливками", "#f08a9b"),
    ("banana-cream", "Banana Cream", "Banan va qaymoq", "Банановый крем", "#f2d77a"),
    ("mocha-cappuccino", "Mocha Cappuccino", "Mokko kapuchino", "Мокко капучино", "#6b4a35"),
    ("caffe-latte", "Caffè Latte", "Kofe latte", "Кофе латте", "#a47551"),
    ("cookie-dough", "Cookie Dough", "Pechenye xamiri", "Печенье с тестом", "#caa472"),
    ("cake-batter", "Cake Batter", "Tort xamiri", "Тесто для торта", "#f3d9a4"),
    ("icy-blue-razz", "Icy Blue Razz", "Muzli ko'k malina", "Ледяная голубая малина", "#2b9be0"),
    ("sour-gummy", "Sour Gummy", "Nordon marmelad", "Кислый мармелад", "#9bd14a"),
    ("rainbow-candy", "Rainbow Candy", "Kamalak konfet", "Радужные конфеты", "#c15ee0"),
    ("passion-fruit", "Passion Fruit", "Marakuyya", "Маракуйя", "#e2733a"),
    ("kiwi-strawberry", "Kiwi Strawberry", "Kivi va qulupnay", "Киви-клубника", "#d94f5c"),
    ("pomegranate", "Pomegranate", "Anor", "Гранат", "#b3203b"),
    ("unflavoured", "Unflavoured", "Ta'msiz", "Без вкуса", "#e5e7eb"),
]

# code, uz, ru, en -- merchandising and product-attribute tags (training goals live in Product.goals)
TAGS = [
    ("bestseller", "Xit", "Хит продаж", "Bestseller"),
    ("new-arrival", "Yangi", "Новинка", "New"),
    ("sale", "Chegirmada", "Скидка", "On sale"),
    ("limited-edition", "Cheklangan nashr", "Лимитированная серия", "Limited edition"),
    ("premium", "Premium", "Премиум", "Premium"),
    ("original-certified", "Original, sertifikatli", "Оригинал, сертифицировано", "Genuine, certified"),
    ("informed-sport", "Informed Sport sertifikati", "Сертификат Informed Sport", "Informed Sport certified"),
    ("high-protein", "Yuqori oqsilli", "Высокобелковый", "High protein"),
    ("low-carb", "Kam uglevodli", "Низкоуглеводный", "Low carb"),
    ("sugar-free", "Shakarsiz", "Без сахара", "Sugar-free"),
    ("lactose-free", "Laktozasiz", "Без лактозы", "Lactose-free"),
    ("gluten-free", "Glyutensiz", "Без глютена", "Gluten-free"),
    ("vegan", "Vegan", "Веган", "Vegan"),
    ("keto", "Keto", "Кето", "Keto"),
    ("halal", "Halol", "Халяль", "Halal"),
    ("caffeine-free", "Kofeinsiz", "Без кофеина", "Caffeine-free"),
    ("for-beginners", "Yangi boshlovchilar uchun", "Для новичков", "For beginners"),
    ("for-women", "Ayollar uchun", "Для женщин", "For women"),
    ("for-men", "Erkaklar uchun", "Для мужчин", "For men"),
    ("gift-idea", "Sovg'a uchun", "В подарок", "Gift idea"),
]


def _upsert_translations(model, fk_name: str, obj, names: dict[str, str]) -> None:
    for locale, name in names.items():
        row = model.objects.filter(**{fk_name: obj, "locale_code": locale}).first()
        if row is None:
            model.objects.create(**{fk_name: obj, "locale_code": locale, "name": name})


def seed_reference(stdout=None) -> dict:
    from django.db import transaction

    from apps.products.infrastructure import models as orm

    stats = {"packages": [0, 0], "flavours": [0, 0], "tags": [0, 0]}  # [created, existing]

    def restore(obj):
        if getattr(obj, "is_deleted", False):
            obj.is_deleted, obj.deleted_at = False, None
            obj.save()

    with transaction.atomic():
        for order, (slug, uz, ru, en) in enumerate(PACKAGES, start=1):
            obj = orm.Package.all_objects.filter(slug=slug).first()
            if obj is None:
                obj = orm.Package.objects.create(slug=slug, sort_order=order * 10, is_active=True)
                stats["packages"][0] += 1
            else:
                restore(obj)
                stats["packages"][1] += 1
            _upsert_translations(orm.PackageTranslation, "package", obj, {"uz": uz, "ru": ru, "en": en})
        for order, (slug, en, uz, ru, color) in enumerate(FLAVOURS, start=1):
            obj = orm.Flavour.all_objects.filter(slug=slug).first()
            if obj is None:
                obj = orm.Flavour.objects.create(slug=slug, color_hex=color, sort_order=order * 10, is_active=True)
                stats["flavours"][0] += 1
            else:
                restore(obj)
                stats["flavours"][1] += 1
            _upsert_translations(orm.FlavourTranslation, "flavour", obj, {"uz": uz, "ru": ru, "en": en})
        for code, uz, ru, en in TAGS:
            obj = orm.Tag.all_objects.filter(code=code).first()
            if obj is None:
                obj = orm.Tag.objects.create(code=code)
                stats["tags"][0] += 1
            else:
                restore(obj)
                stats["tags"][1] += 1
            _upsert_translations(orm.TagTranslation, "tag", obj, {"uz": uz, "ru": ru, "en": en})
    if stdout:
        for k, (c, e) in stats.items():
            stdout.write(f"{k}: {c} created, {e} already there")
    return stats
