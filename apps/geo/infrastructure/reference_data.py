"""
Reference data for the Dashboard: supplement-producing countries, Uzbekistan's 14 regions with their main cities,
and product package types -- each in uz / ru / en. Loaded (idempotently, by code/slug) by
`python manage.py seed_reference_data`; re-running only fills gaps and fixes names, it never duplicates.
"""
from __future__ import annotations

# (ISO code, uz, ru, en, IANA timezone) -- the countries sports-nutrition / vitamin brands manufacture in, plus Uzbekistan's neighbours
COUNTRIES = [
    ("UZ", "O'zbekiston", "Узбекистан", "Uzbekistan", "Asia/Tashkent"),
    ("US", "AQSH", "США", "United States", "America/New_York"),
    ("GB", "Buyuk Britaniya", "Великобритания", "United Kingdom", "Europe/London"),
    ("DE", "Germaniya", "Германия", "Germany", "Europe/Berlin"),
    ("NL", "Niderlandiya", "Нидерланды", "Netherlands", "Europe/Amsterdam"),
    ("IE", "Irlandiya", "Ирландия", "Ireland", "Europe/Dublin"),
    ("IT", "Italiya", "Италия", "Italy", "Europe/Rome"),
    ("ES", "Ispaniya", "Испания", "Spain", "Europe/Madrid"),
    ("FR", "Fransiya", "Франция", "France", "Europe/Paris"),
    ("PL", "Polsha", "Польша", "Poland", "Europe/Warsaw"),
    ("BE", "Belgiya", "Бельгия", "Belgium", "Europe/Brussels"),
    ("DK", "Daniya", "Дания", "Denmark", "Europe/Copenhagen"),
    ("SE", "Shvetsiya", "Швеция", "Sweden", "Europe/Stockholm"),
    ("CH", "Shveytsariya", "Швейцария", "Switzerland", "Europe/Zurich"),
    ("CA", "Kanada", "Канада", "Canada", "America/Toronto"),
    ("AU", "Avstraliya", "Австралия", "Australia", "Australia/Sydney"),
    ("NZ", "Yangi Zelandiya", "Новая Зеландия", "New Zealand", "Pacific/Auckland"),
    ("JP", "Yaponiya", "Япония", "Japan", "Asia/Tokyo"),
    ("KR", "Janubiy Koreya", "Южная Корея", "South Korea", "Asia/Seoul"),
    ("CN", "Xitoy", "Китай", "China", "Asia/Shanghai"),
    ("IN", "Hindiston", "Индия", "India", "Asia/Kolkata"),
    ("TR", "Turkiya", "Турция", "Türkiye", "Europe/Istanbul"),
    ("RU", "Rossiya", "Россия", "Russia", "Europe/Moscow"),
    # more sports-nutrition / vitamin makers (BioTechUSA & Scitec -- Hungary, Max Titanium -- Brazil, ...)
    ("HU", "Vengriya", "Венгрия", "Hungary", "Europe/Budapest"),
    ("LT", "Litva", "Литва", "Lithuania", "Europe/Vilnius"),
    ("LV", "Latviya", "Латвия", "Latvia", "Europe/Riga"),
    ("CZ", "Chexiya", "Чехия", "Czechia", "Europe/Prague"),
    ("AT", "Avstriya", "Австрия", "Austria", "Europe/Vienna"),
    ("PT", "Portugaliya", "Португалия", "Portugal", "Europe/Lisbon"),
    ("GR", "Gretsiya", "Греция", "Greece", "Europe/Athens"),
    ("FI", "Finlandiya", "Финляндия", "Finland", "Europe/Helsinki"),
    ("NO", "Norvegiya", "Норвегия", "Norway", "Europe/Oslo"),
    ("UA", "Ukraina", "Украина", "Ukraine", "Europe/Kyiv"),
    ("BY", "Belarus", "Беларусь", "Belarus", "Europe/Minsk"),
    ("BR", "Braziliya", "Бразилия", "Brazil", "America/Sao_Paulo"),
    ("AE", "BAA", "ОАЭ", "United Arab Emirates", "Asia/Dubai"),
    # Uzbekistan's neighbours
    ("KZ", "Qozog'iston", "Казахстан", "Kazakhstan", "Asia/Almaty"),
    ("KG", "Qirg'iziston", "Кыргызстан", "Kyrgyzstan", "Asia/Bishkek"),
    ("TJ", "Tojikiston", "Таджикистан", "Tajikistan", "Asia/Dushanbe"),
    ("TM", "Turkmaniston", "Туркменистан", "Turkmenistan", "Asia/Ashgabat"),
    ("AF", "Afg'oniston", "Афганистан", "Afghanistan", "Asia/Kabul"),
]

# Region code (ISO 3166-2 where possible) -> (uz, ru, en, [(city code, uz, ru, en, lat, lon), ...]).
# "TGCITYR"/"TGCITY1" are kept for Tashkent city: the Telegram checkout looks them up by these codes.
LEGACY_REGION_CODES = {"TC": "TGCITYR", "TA": "UZ-TO", "AN": "UZ-AN", "BU": "UZ-BU", "FA": "UZ-FA", "JI": "UZ-JI", "NA": "UZ-NG", "NV": "UZ-NW",
                       "KA": "UZ-QA", "KP": "UZ-QR", "SA": "UZ-SA", "SY": "UZ-SI", "SU": "UZ-SU", "KH": "UZ-XO"}

UZ_REGIONS = {
    "TGCITYR": ("Toshkent shahri", "город Ташкент", "Tashkent City", [
        ("TGCITY1", "Toshkent", "Ташкент", "Tashkent", 41.2995, 69.2401),
    ]),
    "UZ-TO": ("Toshkent viloyati", "Ташкентская область", "Tashkent Region", [
        ("TO-NURAF", "Nurafshon", "Нурафшан", "Nurafshon", 41.0406, 69.3486),
        ("TO-CHIRC", "Chirchiq", "Чирчик", "Chirchiq", 41.4689, 69.5822),
        ("TO-OLMAL", "Olmaliq", "Алмалык", "Almalyk", 40.8447, 69.5983),
        ("TO-ANGRE", "Angren", "Ангрен", "Angren", 41.0167, 70.1436),
        ("TO-BEKOB", "Bekobod", "Бекабад", "Bekabad", 40.2208, 69.2697),
        ("TO-OHANG", "Ohangaron", "Ахангаран", "Akhangaran", 40.9064, 69.6383),
        ("TO-YANGI", "Yangiyo'l", "Янгиюль", "Yangiyul", 41.1122, 69.0472),
        ("TO-GAZAL", "G'azalkent", "Газалкент", "Gazalkent", 41.5586, 69.7708),
        ("TO-PARKE", "Parkent", "Паркент", "Parkent", 41.2944, 69.6764),
        ("TO-BOKA", "Bo'ka", "Бука", "Buka", 40.8108, 69.1986),
    ]),
    "UZ-AN": ("Andijon viloyati", "Андижанская область", "Andijan Region", [
        ("AN-ANDIJ", "Andijon", "Андижан", "Andijan", 40.7821, 72.3442),
        ("AN-ASAKA", "Asaka", "Асака", "Asaka", 40.6415, 72.2387),
        ("AN-XONOB", "Xonobod", "Ханабад", "Khanabad", 40.8036, 73.0036),
        ("AN-SHAHR", "Shahrixon", "Шахрихан", "Shahrikhan", 40.7133, 72.0572),
        ("AN-QORAS", "Qorasuv", "Карасу", "Karasu", 40.7247, 72.8847),
        ("AN-MARHA", "Marhamat", "Мархамат", "Markhamat", 40.4914, 72.3239),
    ]),
    "UZ-BU": ("Buxoro viloyati", "Бухарская область", "Bukhara Region", [
        ("BU-BUXOR", "Buxoro", "Бухара", "Bukhara", 39.7747, 64.4286),
        ("BU-KOGON", "Kogon", "Каган", "Kagan", 39.7228, 64.5517),
        ("BU-GIJDU", "G'ijduvon", "Гиждуван", "Gijduvan", 40.1003, 64.6822),
        ("BU-QORAK", "Qorako'l", "Каракуль", "Karakul", 39.4989, 63.8536),
        ("BU-ROMIT", "Romitan", "Ромитан", "Romitan", 39.9261, 64.3806),
        ("BU-OLOT", "Olot", "Алат", "Alat", 39.4151, 63.8035),
    ]),
    "UZ-FA": ("Farg'ona viloyati", "Ферганская область", "Fergana Region", [
        ("FA-FARGO", "Farg'ona", "Фергана", "Fergana", 40.3864, 71.7864),
        ("FA-QOQON", "Qo'qon", "Коканд", "Kokand", 40.5286, 70.9425),
        ("FA-MARGI", "Marg'ilon", "Маргилан", "Margilan", 40.4711, 71.7247),
        ("FA-QUVAS", "Quvasoy", "Кувасай", "Kuvasay", 40.2972, 71.9803),
        ("FA-RISHT", "Rishton", "Риштан", "Rishtan", 40.3567, 71.2847),
        ("FA-BESHA", "Beshariq", "Бешарык", "Besharik", 40.4358, 70.6103),
        ("FA-QUVA", "Quva", "Кува", "Kuva", 40.5222, 72.0639),
    ]),
    "UZ-JI": ("Jizzax viloyati", "Джизакская область", "Jizzakh Region", [
        ("JI-JIZZA", "Jizzax", "Джизак", "Jizzakh", 40.1158, 67.8422),
        ("JI-GALLA", "G'allaorol", "Галляарал", "Gallaorol", 40.0217, 67.5953),
        ("JI-DOSTL", "Do'stlik", "Дустлик", "Dustlik", 40.5247, 68.0358),
        ("JI-PAXTA", "Paxtakor", "Пахтакор", "Pakhtakor", 40.3153, 67.9544),
        ("JI-ZOMIN", "Zomin", "Зомин", "Zaamin", 39.9606, 68.3958),
    ]),
    "UZ-NG": ("Namangan viloyati", "Наманганская область", "Namangan Region", [
        ("NG-NAMAN", "Namangan", "Наманган", "Namangan", 40.9983, 71.6726),
        ("NG-CHUST", "Chust", "Чуст", "Chust", 41.0033, 71.2372),
        ("NG-CHORT", "Chortoq", "Чартак", "Chartak", 41.0692, 71.8233),
        ("NG-KOSON", "Kosonsoy", "Касансай", "Kasansay", 41.2556, 71.5494),
        ("NG-POP", "Pop", "Пап", "Pap", 40.8736, 71.1089),
        ("NG-UCHQO", "Uchqo'rg'on", "Учкурган", "Uchkurgan", 41.1136, 72.0792),
    ]),
    "UZ-NW": ("Navoiy viloyati", "Навоийская область", "Navoiy Region", [
        ("NW-NAVOI", "Navoiy", "Навои", "Navoiy", 40.0844, 65.3792),
        ("NW-ZARAF", "Zarafshon", "Зарафшан", "Zarafshan", 41.5747, 64.2014),
        ("NW-UCHQU", "Uchquduq", "Учкудук", "Uchkuduk", 42.1567, 63.5556),
        ("NW-NUROT", "Nurota", "Нурата", "Nurata", 40.5614, 65.6886),
        ("NW-KARMA", "Karmana", "Кармана", "Karmana", 40.1353, 65.3617),
        ("NW-QIZIL", "Qiziltepa", "Кызылтепа", "Kyzyltepa", 40.0331, 64.8506),
    ]),
    "UZ-QA": ("Qashqadaryo viloyati", "Кашкадарьинская область", "Kashkadarya Region", [
        ("QA-QARSH", "Qarshi", "Карши", "Karshi", 38.8606, 65.7892),
        ("QA-SHAHR", "Shahrisabz", "Шахрисабз", "Shahrisabz", 39.0578, 66.8342),
        ("QA-KITOB", "Kitob", "Китаб", "Kitab", 39.1219, 66.8816),
        ("QA-GUZOR", "G'uzor", "Гузар", "Guzar", 38.6208, 66.2481),
        ("QA-KOSON", "Koson", "Касан", "Kasan", 39.0375, 65.5850),
        ("QA-MUBOR", "Muborak", "Мубарек", "Mubarek", 39.2553, 65.1528),
        ("QA-YAKKA", "Yakkabog'", "Яккабаг", "Yakkabag", 38.9767, 66.6831),
    ]),
    "UZ-QR": ("Qoraqalpog'iston Respublikasi", "Республика Каракалпакстан", "Republic of Karakalpakstan", [
        ("QR-NUKUS", "Nukus", "Нукус", "Nukus", 42.4600, 59.6100),
        ("QR-XOJAY", "Xo'jayli", "Ходжейли", "Khojeyli", 42.4047, 59.4517),
        ("QR-BERUN", "Beruniy", "Беруни", "Beruniy", 41.6911, 60.7525),
        ("QR-TORTK", "To'rtko'l", "Турткуль", "Turtkul", 41.5500, 61.0000),
        ("QR-QONGI", "Qo'ng'irot", "Кунград", "Kungrad", 43.0758, 58.9003),
        ("QR-CHIMB", "Chimboy", "Чимбай", "Chimbay", 42.9311, 59.7708),
        ("QR-MOYNO", "Mo'ynoq", "Муйнак", "Muynak", 43.7683, 59.0214),
    ]),
    "UZ-SA": ("Samarqand viloyati", "Самаркандская область", "Samarkand Region", [
        ("SA-SAMAR", "Samarqand", "Самарканд", "Samarkand", 39.6542, 66.9597),
        ("SA-KATTA", "Kattaqo'rg'on", "Каттакурган", "Kattakurgan", 39.8989, 66.2561),
        ("SA-URGUT", "Urgut", "Ургут", "Urgut", 39.4022, 67.2431),
        ("SA-BULUN", "Bulung'ur", "Булунгур", "Bulungur", 39.7614, 67.2714),
        ("SA-ISHTI", "Ishtixon", "Иштыхан", "Ishtikhan", 39.9667, 66.4833),
        ("SA-PAYAR", "Payariq", "Пайарык", "Payariq", 39.9892, 66.8903),
        ("SA-JOMBO", "Jomboy", "Джамбай", "Jambay", 39.6983, 67.0933),
    ]),
    "UZ-SI": ("Sirdaryo viloyati", "Сырдарьинская область", "Syrdarya Region", [
        ("SI-GULIS", "Guliston", "Гулистан", "Gulistan", 40.4897, 68.7842),
        ("SI-YANGI", "Yangiyer", "Янгиер", "Yangiyer", 40.2750, 68.8225),
        ("SI-SHIRI", "Shirin", "Ширин", "Shirin", 40.2244, 69.1386),
        ("SI-SIRDA", "Sirdaryo", "Сырдарья", "Syrdarya", 40.8436, 68.6617),
        ("SI-BOYOV", "Boyovut", "Баяут", "Bayaut", 40.3383, 69.0072),
    ]),
    "UZ-SU": ("Surxondaryo viloyati", "Сурхандарьинская область", "Surkhandarya Region", [
        ("SU-TERMI", "Termiz", "Термез", "Termez", 37.2242, 67.2783),
        ("SU-DENOV", "Denov", "Денау", "Denau", 38.2667, 67.8944),
        ("SU-SHERO", "Sherobod", "Шерабад", "Sherabad", 37.6667, 67.0333),
        ("SU-SHORC", "Sho'rchi", "Шурчи", "Shurchi", 38.0000, 67.7833),
        ("SU-BOYSU", "Boysun", "Байсун", "Baysun", 38.2056, 67.2022),
        ("SU-QUMQO", "Qumqo'rg'on", "Кумкурган", "Kumkurgan", 37.8317, 67.5817),
        ("SU-JARQO", "Jarqo'rg'on", "Джаркурган", "Jarkurgan", 37.5044, 67.4094),
    ]),
    "UZ-XO": ("Xorazm viloyati", "Хорезмская область", "Khorezm Region", [
        ("XO-URGAN", "Urganch", "Ургенч", "Urgench", 41.5500, 60.6333),
        ("XO-XIVA", "Xiva", "Хива", "Khiva", 41.3783, 60.3639),
        ("XO-XONQA", "Xonqa", "Ханка", "Khanka", 41.4736, 60.7747),
        ("XO-HAZOR", "Hazorasp", "Хазарасп", "Hazarasp", 41.3194, 61.0742),
        ("XO-GURLA", "Gurlan", "Гурлен", "Gurlen", 41.8447, 60.3919),
        ("XO-SHOVO", "Shovot", "Шават", "Shavat", 41.6556, 60.3025),
        ("XO-BOGOT", "Bog'ot", "Багат", "Bagat", 41.3500, 60.8667),
    ]),
}

# (slug, uz, ru, en) -- how sports nutrition is actually packed, most common first
PACKAGES = [
    ("jar", "Banka", "Банка", "Jar"),
    ("tub", "Katta idish (tub)", "Туба (большая банка)", "Tub"),
    ("bottle", "Butilka", "Бутылка", "Bottle"),
    ("pouch", "Zip-paket (doy-pak)", "Дой-пак (zip-lock)", "Pouch (zip-lock)"),
    ("bag", "Paket", "Пакет", "Bag"),
    ("box", "Quti", "Коробка", "Box"),
    ("sachet", "Porsiyali paketcha (sashe)", "Саше (порционный пакетик)", "Sachet"),
    ("stick-pack", "Stik", "Стик", "Stick pack"),
    ("blister", "Blister", "Блистер", "Blister"),
    ("capsule-bottle", "Kapsula idishi", "Флакон для капсул", "Capsule bottle"),
    ("can", "Ichimlik bankasi (tayyor ichimlik)", "Жестяная банка (напиток)", "Can (ready-to-drink)"),
    ("shot", "Ampula / shot", "Ампула / шот", "Shot / ampoule"),
    ("gel-pack", "Energetik gel (tubik)", "Энергетический гель", "Gel pack"),
    ("bar-wrapper", "Batonchik o'rami", "Обёртка батончика", "Bar wrapper"),
    ("multipack", "Blok (multipak)", "Блок (мультипак)", "Multipack"),
    ("dropper-bottle", "Tomizg'ichli flakon", "Флакон с пипеткой", "Dropper bottle"),
]


def slugify_uz(text: str) -> str:
    from django.utils.text import slugify

    return slugify(text.replace("'", "").replace("ʻ", "").replace("’", ""))


def flag_emoji(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code.upper())


def _set_translations(model, fk: str, obj, names: dict, *, slugs: dict | None = None) -> None:
    """Upserts the uz/ru/en rows. A slug already taken by another object gets the object's code appended."""
    for locale, name in names.items():
        fields = {"name": name}
        if slugs is not None:
            slug = slugs[locale]
            taken = model.objects.filter(locale_code=locale, slug=slug).exclude(**{fk: obj}).exists()
            fields["slug"] = f"{slug}-{obj.code.lower()}"[:140] if taken else slug
        model.objects.update_or_create(**{fk: obj, "locale_code": locale}, defaults=fields)


def seed_countries(stdout=None) -> int:
    from apps.geo.infrastructure import models as geo

    for code, uz, ru, en, tz in COUNTRIES:
        country = geo.Country.all_objects.filter(code=code).first() or geo.Country(code=code)
        country.status, country.timezone, country.icon, country.is_deleted = "active", tz, flag_emoji(code), False
        country.save()
        en_slug = slugify_uz(en)
        _set_translations(geo.CountryTranslation, "country", country, {"uz": uz, "ru": ru, "en": en}, slugs={"uz": slugify_uz(uz), "ru": en_slug, "en": en_slug})
    return len(COUNTRIES)


def _cleanup_legacy_uz_test_rows(uz_country) -> list[str]:
    """Early test rows: region "75" (Surxondaryo) carrying a "Mustaqillik/Velikiy" district and a duplicate "Toshkent"
    city. The region becomes UZ-SU; the duplicate city's addresses move to the real Tashkent (TGCITY1), then it goes."""
    from apps.geo.infrastructure import models as geo

    notes = []
    # Regions first created with short codes (AN, TC, KA...) become the ISO / seed codes, so seeding never duplicates them.
    for short, target in LEGACY_REGION_CODES.items():
        old = geo.Region.all_objects.filter(code=short, country=uz_country).first()
        if old is not None and not geo.Region.all_objects.filter(code=target).exists():
            old.code = target
            old.save(update_fields=["code", "updated_at"])
            notes.append(f"region {short} -> {target}")
    legacy = geo.Region.objects.filter(code="75", country=uz_country).first()
    if legacy is not None and not geo.Region.objects.filter(code="UZ-SU").exists():
        legacy.code = "UZ-SU"
        legacy.save(update_fields=["code", "updated_at"])
        notes.append("region 75 -> UZ-SU")
    dup = geo.City.objects.filter(code="TASH").first()
    tashkent = geo.City.objects.filter(code="TGCITY1").first()
    if dup is not None and tashkent is not None:
        moved = geo.Address.all_objects.filter(city=dup).update(city=tashkent, region=tashkent.region)
        geo.CityTranslation.objects.filter(city=dup).delete()
        geo.City.objects.filter(pk=dup.pk)._raw_delete(geo.City.objects.db)
        notes.append(f"duplicate city TASH removed ({moved} address(es) -> Tashkent)")
    for d in geo.District.all_objects.filter(code="12", translations__name="Mustaqillik").distinct():
        geo.Address.all_objects.filter(district=d).update(district=None)  # a placeholder district, not a real one
        if not geo.City.all_objects.filter(district=d).exists():
            geo.DistrictTranslation.objects.filter(district=d).delete()
            geo.District.objects.filter(pk=d.pk)._raw_delete(geo.District.objects.db)
            notes.append("test district 12 removed")
    return notes


def _fix_district_cities() -> list[str]:
    """A Tashkent district saved as a "city" (e.g. MB = Mirobod) → its addresses move to Tashkent with that district set."""
    from apps.geo.infrastructure import models as geo

    notes = []
    tashkent = geo.City.objects.filter(code="TGCITY1").first()
    if tashkent is None:
        return notes
    for city in geo.City.objects.exclude(code="TGCITY1").filter(region__code__in=("TGCITYR", "UZ-TO")).prefetch_related("translations"):
        names = {t.name.lower() for t in city.translations.all()}
        district = None
        for d in geo.District.objects.filter(region=tashkent.region).prefetch_related("translations"):
            if any(t.name.lower().replace(" tumani", "").replace(" district", "") in names for t in d.translations.all()):
                district = d
                break
        if district is None:
            continue
        moved = geo.Address.all_objects.filter(city=city).update(city=tashkent, region=tashkent.region, district=district)
        city.status = "inactive"
        city.save(update_fields=["status", "updated_at"])
        notes.append(f"city {city.code} is the {district.code} district of Tashkent ({moved} address(es) moved)")
    return notes


def seed_districts() -> int:
    """The tumanlar of every region (the list in migration 0009) for regions that have none yet."""
    import importlib
    import re
    import uuid

    from apps.geo.infrastructure import models as geo

    districts = importlib.import_module("apps.geo.infrastructure.migrations.0009_region_districts").DISTRICTS
    made = 0
    for region_code, names in districts.items():
        region = geo.Region.objects.filter(code=region_code).first()
        if region is None or geo.District.objects.filter(region=region).exists():
            continue
        prefix = region_code.split("-")[1]
        for i, name in enumerate(names, 1):
            code = f"{prefix}-{re.sub(r'[^A-Z]', '', name.replace(chr(39), '').upper())[:5]}{i:02d}"[:10]
            if geo.District.all_objects.filter(code=code).exists():
                continue
            d = geo.District.objects.create(id=uuid.uuid4(), region=region, code=code, status="active")
            latin = name.replace("'", "")
            _set_translations(geo.DistrictTranslation, "district", d, {"uz": f"{name} tumani", "en": f"{latin} District"},
                              slugs={"uz": f"{slugify_uz(name)}-tumani-{prefix.lower()}", "en": f"{slugify_uz(latin)}-district-{prefix.lower()}"})
            made += 1
    return made


def seed_uzbekistan(stdout=None) -> dict:
    from apps.geo.infrastructure import models as geo

    uz = geo.Country.objects.get(code="UZ")
    notes = _cleanup_legacy_uz_test_rows(uz)
    regions = cities = 0
    for code, (r_uz, r_ru, r_en, city_rows) in UZ_REGIONS.items():
        region = geo.Region.all_objects.filter(code=code).first() or geo.Region(code=code)
        region.country, region.status, region.is_deleted = uz, "active", False
        region.save()
        en_slug = slugify_uz(r_en)
        _set_translations(geo.RegionTranslation, "region", region, {"uz": r_uz, "ru": r_ru, "en": r_en}, slugs={"uz": slugify_uz(r_uz), "ru": en_slug, "en": en_slug})
        regions += 1
        for c_code, c_uz, c_ru, c_en, lat, lon in city_rows:
            city = geo.City.all_objects.filter(code=c_code).first() or geo.City(code=c_code)
            city.region, city.status, city.is_deleted = region, "active", False
            city.center_latitude, city.center_longitude = lat, lon
            city.timezone = "Asia/Tashkent"
            city.save()
            c_slug = slugify_uz(c_en)
            _set_translations(geo.CityTranslation, "city", city, {"uz": c_uz, "ru": c_ru, "en": c_en}, slugs={"uz": slugify_uz(c_uz), "ru": c_slug, "en": c_slug})
            cities += 1
    notes += _fix_district_cities()
    districts = seed_districts()
    if districts:
        notes.append(f"{districts} district(s) added")
    return {"regions": regions, "cities": cities, "notes": notes}


def seed_packages(stdout=None) -> int:
    from apps.products.infrastructure import models as products

    for order, (slug, uz, ru, en) in enumerate(PACKAGES, start=1):
        package = products.Package.all_objects.filter(slug=slug).first() or products.Package(slug=slug)
        package.sort_order, package.is_active, package.is_deleted = order, True, False
        package.save()
        for locale, name in (("uz", uz), ("ru", ru), ("en", en)):
            products.PackageTranslation.objects.update_or_create(package=package, locale_code=locale, defaults={"name": name})
    return len(PACKAGES)
