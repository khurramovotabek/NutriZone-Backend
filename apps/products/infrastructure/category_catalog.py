"""
NutriZone's category tree (owner-approved structure, 2026-10-17): 3 top sections → short sections → product types.

Intra-Workout is not a category of its own: BCAA / EAA live under Aminokislotalar, isotonic and electrolytes in the
Hydration section next to it, and HMB / Glutamine / Beef Amino / Carbohydrates under Recovery.

`seed_categories()` is idempotent: a category is found by its English name under the same parent, so re-running
never duplicates and never overwrites names, descriptions, images or order edited in the dashboard -- it only adds
what is missing (and restores a soft-deleted one from the list).
"""
from __future__ import annotations

# (uz, ru, en, (uz, ru, en) description or None, children)
Node = tuple

_SPORT = (
    "Sport ozuqalari", "Спортивное питание", "Sports Nutrition",
    (
        "Original sport ozuqalari: protein, kreatin, geyner, aminokislotalar, pre-workout va yog' yoquvchilar — natija, kuch va tiklanish uchun.",
        "Оригинальное спортивное питание: протеин, креатин, гейнеры, аминокислоты, предтренировочные комплексы и жиросжигатели — для результата, силы и восстановления.",
        "Genuine sports nutrition: protein, creatine, gainers, amino acids, pre-workouts and fat burners — for results, strength and recovery.",
    ),
    [
        ("Proteinlar", "Протеины", "Proteins",
         ("Mushak o'sishi va tiklanishi uchun protein: whey, izolyat, gidrolizat, kazein, mol go'shti va vegan proteinlari.",
          "Протеин для роста и восстановления мышц: сывороточный, изолят, гидролизат, казеин, говяжий и веганский.",
          "Protein for muscle growth and recovery: whey, isolate, hydrolyzed, casein, beef and vegan protein."),
         [("Whey protein", "Сывороточный протеин", "Whey Protein"), ("Izolyat", "Изолят", "Whey Isolate"),
          ("Gidrolizat", "Гидролизат", "Hydrolyzed Whey"), ("Kazein", "Казеин", "Casein"),
          ("Mol go'shti proteini", "Говяжий протеин", "Beef Protein"), ("Vegan protein", "Веганский протеин", "Vegan Protein")]),
        ("Kreatin", "Креатин", "Creatine",
         ("Kuch, chidamlilik va mushak hajmi uchun kreatin: monogidrat, HCL va Kre-Alkalyn.",
          "Креатин для силы, выносливости и объёма мышц: моногидрат, HCL и Kre-Alkalyn.",
          "Creatine for strength, endurance and muscle size: monohydrate, HCL and Kre-Alkalyn."),
         [("Kreatin monogidrat", "Креатин моногидрат", "Creatine Monohydrate"), ("Kreatin HCL", "Креатин HCL", "Creatine HCL"),
          ("Kre-Alkalyn", "Kre-Alkalyn", "Kre-Alkalyn")]),
        ("Geynerlar", "Гейнеры", "Gainers",
         ("Vazn va massa yig'ish uchun geynerlar: kaloriyali mass gainer va sifatli massa uchun lean gainer.",
          "Гейнеры для набора веса и массы: калорийные mass gainer и lean gainer для качественной массы.",
          "Gainers for gaining weight and mass: high-calorie mass gainers and lean gainers for quality mass."),
         [("Mass gainer", "Гейнер для массы", "Mass Gainer"), ("Lean gainer", "Lean-гейнер", "Lean Gainer")]),
        ("Aminokislotalar", "Аминокислоты", "Amino Acids",
         ("Mashg'ulot davomida va keyin: BCAA, EAA va aminokomplekslar — mushaklarni himoya qilish va tiklanish uchun.",
          "Во время и после тренировки: BCAA, EAA и аминокомплексы — для защиты мышц и восстановления.",
          "During and after training: BCAA, EAA and amino complexes — to protect muscle and recover."),
         [("BCAA", "BCAA", "BCAA"), ("EAA", "EAA", "EAA"), ("Aminokompleks", "Аминокомплекс", "Amino Complex")]),
        ("Hydration", "Гидратация", "Hydration",
         ("Mashg'ulot paytida suv-tuz balansi uchun izotoniklar va elektrolitlar.",
          "Изотоники и электролиты для водно-солевого баланса во время тренировки.",
          "Isotonic drinks and electrolytes to keep your fluid balance during training."),
         [("Izotonik", "Изотоники", "Isotonic"), ("Elektrolitlar", "Электролиты", "Electrolytes")]),
        ("Performance", "Спортивная производительность", "Performance",
         ("Chidamlilik va kuch uchun arginin, sitrullin va beta-alanin.",
          "Аргинин, цитруллин и бета-аланин для выносливости и силы.",
          "Arginine, citrulline and beta-alanine for endurance and power."),
         [("Arginin", "Аргинин", "Arginine"), ("Sitrullin", "Цитруллин", "Citrulline"), ("Beta-alanin", "Бета-аланин", "Beta-Alanine")]),
        ("Pre-Workout", "Предтренировочные комплексы", "Pre-Workout",
         ("Mashg'ulotdan oldin energiya va diqqat uchun: stimulyatorli, stimulyatorsiz va hardcore pre-workoutlar.",
          "Энергия и концентрация перед тренировкой: комплексы со стимуляторами, без стимуляторов и hardcore.",
          "Energy and focus before training: stim, stim-free and hardcore pre-workouts."),
         [("Stimulyatorli", "Со стимуляторами", "Stim"), ("Stimulyatorsiz", "Без стимуляторов", "Stim-Free"), ("Hardcore", "Hardcore", "Hardcore")]),
        ("Pump", "Пампинг", "Pump",
         ("Kuchli pump va qon aylanishi uchun: pump formulalar, azot oksidi va stimulyatorsiz pump.",
          "Для сильного пампа и кровотока: памп-формулы, оксид азота и памп без стимуляторов.",
          "For a strong pump and blood flow: pump formulas, nitric oxide and stim-free pump."),
         [("Pump formula", "Памп-формула", "Pump Formula"), ("Azot oksidi (NO)", "Оксид азота (NO)", "Nitric Oxide"),
          ("Stimulyatorsiz pump", "Памп без стимуляторов", "Stim-Free Pump")]),
        ("Tiklanish", "Восстановление", "Recovery",
         ("Mashg'ulotdan keyingi tiklanish: HMB, glutamin, mol go'shti aminokislotalari va uglevodlar.",
          "Восстановление после тренировки: HMB, глютамин, говяжьи аминокислоты и углеводы.",
          "Post-workout recovery: HMB, glutamine, beef amino and carbohydrates."),
         [("HMB", "HMB", "HMB"), ("Glutamin", "Глютамин", "Glutamine"), ("Beef Amino", "Говяжьи аминокислоты", "Beef Amino"),
          ("Uglevodlar", "Углеводы", "Carbohydrates")]),
        ("Yog' yoquvchilar", "Жиросжигатели", "Fat Burners",
         ("Ozish va relyef uchun termogeniklar va L-karnitin.",
          "Термогеники и L-карнитин для похудения и рельефа.",
          "Thermogenics and L-carnitine for fat loss and definition."),
         [("Termogeniklar", "Термогеники", "Thermogenics"), ("L-karnitin", "L-карнитин", "L-Carnitine")]),
    ],
)

_VITAMINS = (
    "Vitaminlar", "Витамины", "Vitamins",
    (
        "Sog'liq va energiya uchun vitaminlar, minerallar, omega-3, bo'g'imlar va uyqu uchun komplekslar.",
        "Витамины, минералы, омега-3, комплексы для суставов и сна — для здоровья и энергии.",
        "Vitamins, minerals, omega-3, joint and sleep support — for health and energy.",
    ),
    [
        ("Multivitaminlar", "Мультивитамины", "Multivitamins",
         ("Har kunlik, sportchilar, erkaklar va ayollar uchun multivitamin komplekslari.",
          "Мультивитаминные комплексы на каждый день, для спортсменов, мужчин и женщин.",
          "Multivitamin formulas for every day, for athletes, for men and for women."),
         [("Kundalik", "На каждый день", "Daily"), ("Sport uchun", "Для спортсменов", "Sport"),
          ("Erkaklar uchun", "Для мужчин", "Men's"), ("Ayollar uchun", "Для женщин", "Women's")]),
        ("Vitaminlar", "Витамины", "Single Vitamins",
         ("Alohida vitaminlar: D3, C, B-kompleks, E va K2.",
          "Отдельные витамины: D3, C, B-комплекс, E и K2.",
          "Single vitamins: D3, C, B-complex, E and K2."),
         [("Vitamin D3", "Витамин D3", "Vitamin D3"), ("Vitamin C", "Витамин C", "Vitamin C"), ("B-kompleks", "B-комплекс", "B-Complex"),
          ("Vitamin E", "Витамин E", "Vitamin E"), ("Vitamin K2", "Витамин K2", "Vitamin K2")]),
        ("Minerallar", "Минералы", "Minerals",
         ("Magniy, rux, kalsiy, temir va selen — organizm va mashg'ulot uchun zarur minerallar.",
          "Магний, цинк, кальций, железо и селен — минералы, нужные организму и для тренировок.",
          "Magnesium, zinc, calcium, iron and selenium — minerals your body and training need."),
         [("Magniy", "Магний", "Magnesium"), ("Rux", "Цинк", "Zinc"), ("Kalsiy", "Кальций", "Calcium"),
          ("Temir", "Железо", "Iron"), ("Selen", "Селен", "Selenium")]),
        ("Omega", "Омега", "Omega",
         ("Yurak, miya va bo'g'imlar uchun omega-3, baliq yog'i va krill yog'i.",
          "Омега-3, рыбий жир и масло криля для сердца, мозга и суставов.",
          "Omega-3, fish oil and krill oil for heart, brain and joints."),
         [("Omega-3", "Омега-3", "Omega-3"), ("Baliq yog'i", "Рыбий жир", "Fish Oil"), ("Krill yog'i", "Масло криля", "Krill Oil")]),
        ("Bo'g'imlar salomatligi", "Здоровье суставов", "Joint Support",
         ("Bo'g'im va paylar uchun kollagen, glyukozamin va xondroitin.",
          "Коллаген, глюкозамин и хондроитин для суставов и связок.",
          "Collagen, glucosamine and chondroitin for joints and ligaments."),
         [("Kollagen", "Коллаген", "Collagen"), ("Glyukozamin", "Глюкозамин", "Glucosamine"), ("Xondroitin", "Хондроитин", "Chondroitin")]),
        ("Sog'lom uyqu", "Здоровый сон", "Sleep Support",
         ("Sifatli uyqu va tiklanish uchun melatonin va uyqu komplekslari.",
          "Мелатонин и комплексы для качественного сна и восстановления.",
          "Melatonin and sleep formulas for quality sleep and recovery."),
         [("Melatonin", "Мелатонин", "Melatonin"), ("Uyqu kompleksi", "Комплекс для сна", "Sleep Complex")]),
    ],
)

_EXTRAS = (
    "Qo'shimchalar va aksessuarlar", "Аксессуары и товары для спорта", "Accessories & Extras",
    (
        "Sport ozuqasi yoki vitamin bo'lmagan, lekin sport bilan shug'ullanuvchilar uchun kerakli mahsulotlar: shakerlar, aksessuarlar, kiyim, protein sneklar va boshqalar.",
        "Товары для спорта, которые не являются питанием или витаминами: шейкеры, аксессуары, одежда, протеиновые снеки и другое.",
        "Gear for active people that isn't nutrition or vitamins: shakers, gym accessories, clothing, protein snacks and more.",
    ),
    [
        ("Shakerlar", "Шейкеры", "Shakers",
         ("Protein va ichimliklar uchun klassik, blender va smart shakerlar.",
          "Классические шейкеры, шейкеры-блендеры и смарт-шейкеры для протеина и напитков.",
          "Classic, blender and smart shakers for protein and drinks."),
         [("Klassik", "Классические", "Classic"), ("Blender shaker", "Шейкер-блендер", "Blender"), ("Smart shaker", "Смарт-шейкер", "Smart Shaker")]),
        ("Suv idishlari", "Бутылки для воды", "Water Bottles",
         ("Mashg'ulot va kundalik hayot uchun suv butilkalari va gallonlar.",
          "Бутылки для воды и галлоны для тренировок и каждого дня.",
          "Water bottles and gallon jugs for training and everyday life."),
         [("Butilkalar", "Бутылки", "Bottles"), ("Gallonlar", "Галлоны", "Gallon Jugs")]),
        ("Zal aksessuarlari", "Аксессуары для зала", "Gym Accessories",
         ("Qo'lqoplar, lyamkalar, kamarlar va bilak bintlari — xavfsiz va samarali mashg'ulot uchun.",
          "Перчатки, лямки, пояса и кистевые бинты — для безопасной и эффективной тренировки.",
          "Gloves, straps, belts and wrist wraps — for safe and effective training."),
         [("Qo'lqoplar", "Перчатки", "Gloves"), ("Lyamkalar", "Лямки", "Straps"), ("Atletik kamarlar", "Атлетические пояса", "Belts"),
          ("Bilak bintlari", "Кистевые бинты", "Wrist Wraps")]),
        ("Sport kiyimlari", "Спортивная одежда", "Sportswear",
         ("Mashg'ulot uchun futbolkalar, shortilar, xudilar va paypoqlar.",
          "Футболки, шорты, худи и носки для тренировок.",
          "T-shirts, shorts, hoodies and socks for training."),
         [("Futbolkalar", "Футболки", "T-Shirts"), ("Shortilar", "Шорты", "Shorts"), ("Xudilar", "Худи", "Hoodies"), ("Paypoqlar", "Носки", "Socks")]),
        ("Protein sneklar", "Протеиновые снеки", "Protein Snacks",
         ("Protein batonchiklar, pechenyelar va chipslar — foydali va mazali gazak.",
          "Протеиновые батончики, печенье и чипсы — полезный и вкусный перекус.",
          "Protein bars, cookies and chips — a healthy, tasty snack."),
         [("Protein batonchiklar", "Протеиновые батончики", "Protein Bars"), ("Protein pechenyelar", "Протеиновое печенье", "Protein Cookies"),
          ("Protein chipslar", "Протеиновые чипсы", "Protein Chips")]),
        ("Sog'lom ovqat", "Здоровое питание", "Healthy Food",
         ("Yeryong'oq pastasi, protein pankeyklar va shakarsiz souslar — to'g'ri ovqatlanish uchun.",
          "Арахисовая паста, протеиновые панкейки и соусы без сахара — для правильного питания.",
          "Peanut butter, protein pancakes and sugar-free sauces — for clean eating."),
         [("Yeryong'oq pastasi", "Арахисовая паста", "Peanut Butter"), ("Protein pankeyklar", "Протеиновые панкейки", "Protein Pancakes"),
          ("Shakarsiz souslar", "Соусы без сахара", "Sugar-Free Sauces")]),
        ("Sport sumkalari", "Спортивные сумки", "Sports Bags",
         ("Zal uchun sumkalar va ryukzaklar.",
          "Сумки и рюкзаки для зала.",
          "Gym bags and backpacks."),
         [("Zal sumkalari", "Сумки для зала", "Gym Bags"), ("Ryukzaklar", "Рюкзаки", "Backpacks")]),
        ("Sport elektronikasi", "Спортивная электроника", "Sports Electronics",
         ("Fitnes-trekerlar va aqlli tarozilar — natijani kuzatish uchun.",
          "Фитнес-трекеры и умные весы — чтобы следить за результатом.",
          "Fitness trackers and smart scales — to track your progress."),
         [("Fitnes-trekerlar", "Фитнес-трекеры", "Fitness Trackers"), ("Aqlli tarozilar", "Умные весы", "Smart Scales")]),
    ],
)

TREE = [_SPORT, _VITAMINS, _EXTRAS]


def _leaf_description(name: tuple[str, str, str], parent: tuple[str, str, str]) -> tuple[str, str, str]:
    return (
        f"{name[0]} — «{parent[0]}» bo'limidagi original mahsulotlar: narxlar, ta'mlar va mavjudlik.",
        f"{name[1]} — оригинальная продукция в разделе «{parent[1]}»: цены, вкусы и наличие.",
        f"{name[2]} — genuine products in the {parent[2]} section: prices, flavours and availability.",
    )


def count_nodes() -> int:
    return sum(1 + sum(1 + len(c[4]) for c in top[4]) for top in TREE)


def seed_categories(stdout=None) -> dict:
    from django.db import transaction
    from django.db.models.functions import Lower

    from apps.geo.infrastructure.reference_data import slugify_uz
    from apps.products.infrastructure import models as orm

    stats = {"created": 0, "existing": 0}

    def slug_for(locale: str, base: str, parent_slug: str | None) -> str:
        slug = slugify_uz(base)[:200] or "kategoriya"
        if orm.CategoryTranslation.objects.filter(locale_code=locale, slug=slug).exists() and parent_slug:
            slug = f"{parent_slug}-{slug}"[:200]
        n = 2
        candidate = slug
        while orm.CategoryTranslation.objects.filter(locale_code=locale, slug=candidate).exists():
            candidate = f"{slug}-{n}"
            n += 1
        return candidate

    def upsert(names: tuple[str, str, str], description: tuple[str, str, str], parent, order: int):
        uz, ru, en = names
        found = orm.Category.all_objects.filter(parent=parent).annotate(n=Lower("translations__name")).filter(
            translations__locale_code="en", n=en.lower()).first()
        if found is not None:
            if found.is_deleted:
                found.is_deleted, found.deleted_at = False, None
                found.save()
            stats["existing"] += 1
            category = found
        else:
            category = orm.Category.objects.create(parent=parent, sort_order=order, is_active=True)
            stats["created"] += 1
        parent_slugs = {t.locale_code: t.slug for t in parent.translations.all()} if parent else {}
        # Latin URLs in every language (the Russian name is the page text, not the address).
        for locale, name, text, slug_base in (("uz", uz, description[0], uz), ("ru", ru, description[1], en), ("en", en, description[2], en)):
            row = orm.CategoryTranslation.objects.filter(category=category, locale_code=locale).first()
            if row is None:
                orm.CategoryTranslation.objects.create(category=category, locale_code=locale, name=name, description=text,
                                                       slug=slug_for(locale, slug_base, parent_slugs.get(locale)))
            elif not row.description:
                row.description = text
                row.save(update_fields=["description", "updated_at"])
        return category

    with transaction.atomic():
        for i, (uz, ru, en, desc, sections) in enumerate(TREE, start=1):
            top = upsert((uz, ru, en), desc, None, i * 10)
            for j, (suz, sru, sen, sdesc, leaves) in enumerate(sections, start=1):
                section = upsert((suz, sru, sen), sdesc, top, j * 10)
                for k, leaf in enumerate(leaves, start=1):
                    upsert(leaf, _leaf_description(leaf, (suz, sru, sen)), section, k * 10)
    if stdout:
        stdout.write(f"Categories: {stats['created']} created, {stats['existing']} already there ({count_nodes()} in the tree)")
    return stats
