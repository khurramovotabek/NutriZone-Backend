"""
The brands NutriZone sells (2026-10-16 list from the owner) with their home country and a short uz / ru / en description.
Loaded by `python manage.py seed_brands` -- idempotent: a brand is matched by any of its names (case-insensitive), so
re-running fills gaps (country, empty descriptions) and never duplicates or overwrites what was edited on the dashboard.
"""
from __future__ import annotations

# (official name, ISO country, uz, ru, en, aliases)
BRANDS = [
    ("Optimum Nutrition", "US", "1986-yildan beri ishlab kelayotgan AQSh brendi. Gold Standard 100% Whey proteini bilan dunyoga mashhur.",
     "Американский бренд, работающий с 1986 года. Всемирно известен протеином Gold Standard 100% Whey.",
     "US brand since 1986, world-famous for Gold Standard 100% Whey.", ("ON",)),
    ("Dymatize", "US", "1994-yilda Dallasda (AQSh) tashkil topgan. ISO100 gidrolizlangan izolyati bilan tanilgan.",
     "Основан в 1994 году в Далласе (США). Известен гидролизованным изолятом ISO100.",
     "Founded in Dallas, USA in 1994; known for ISO100 hydrolyzed whey isolate.", ()),
    ("ALLMAX Nutrition", "CA", "Kanada brendi. Toza tarkibli izolyat proteini va kreatini bilan tanilgan.",
     "Канадский бренд, известный изолятом протеина и креатином с чистым составом.",
     "Canadian brand known for clean-label whey isolate and creatine.", ("Allmax",)),
    ("BSN", "US", "AQSh brendi. Syntha-6 proteini va N.O.-Xplode pre-workout kompleksi bilan mashhur.",
     "Американский бренд. Известен протеином Syntha-6 и предтренировочным комплексом N.O.-Xplode.",
     "US brand known for Syntha-6 protein and N.O.-Xplode pre-workout.", ()),
    ("MuscleTech", "CA", "1995-yildan beri ishlab kelayotgan brend. Nitro-Tech proteini va Cell-Tech kreatini bilan tanilgan.",
     "Бренд, работающий с 1995 года. Известен протеином Nitro-Tech и креатином Cell-Tech.",
     "Brand since 1995, known for Nitro-Tech protein and Cell-Tech creatine.", ()),
    ("CBUM", "US", "Olti karra Classic Physique Mister Olimpiya chempioni Kris Bamsted va Raw Nutrition hamkorlikdagi seriyasi.",
     "Линейка Raw Nutrition, созданная с шестикратным чемпионом Classic Physique Mr. Olympia Крисом Бамстедом.",
     "Raw Nutrition line created with six-time Classic Physique Mr. Olympia Chris Bumstead.", ("Raw CBUM",)),
    ("Mutant", "CA", "Kanada brendi. Mutant Mass geyneri va Mutant Whey proteini bilan tanilgan.",
     "Канадский бренд. Известен гейнером Mutant Mass и протеином Mutant Whey.",
     "Canadian brand known for Mutant Mass gainer and Mutant Whey.", ()),
    ("Olimp Sport Nutrition", "PL", "1990-yildan beri ishlab kelayotgan Polshaning yirik sport ozuqa va vitamin ishlab chiqaruvchisi.",
     "Крупный польский производитель спортивного питания и витаминов, работающий с 1990 года.",
     "Major Polish maker of sports nutrition and vitamins since 1990.", ("Olimp",)),
    ("Applied Nutrition", "GB", "Liverpul (Buyuk Britaniya) brendi. ISO-XP izolyati va ABE pre-workout bilan tanilgan.",
     "Бренд из Ливерпуля (Великобритания). Известен изолятом ISO-XP и предтреником ABE.",
     "Liverpool, UK brand known for ISO-XP isolate and ABE pre-workout.", ()),
    ("DY Nutrition", "GB", "Olti karra Mister Olimpiya Dorian Yeyts asos solgan Buyuk Britaniya brendi.",
     "Британский бренд, основанный шестикратным Мистером Олимпия Дорианом Ятсом.",
     "UK brand founded by six-time Mr. Olympia Dorian Yates.", ("Dorian Yates",)),
    ("Myprotein", "GB", "Yevropaning eng yirik onlayn sport ozuqa brendlaridan biri (Buyuk Britaniya). Impact Whey proteini bilan tanilgan.",
     "Один из крупнейших онлайн-брендов спортивного питания в Европе (Великобритания). Известен протеином Impact Whey.",
     "One of Europe's largest online sports-nutrition brands (UK), known for Impact Whey.", ("MyProtein",)),
    ("California Gold Nutrition", "US", "iHerb kompaniyasining o'z brendi: vitaminlar, minerallar va ozuqaviy qo'shimchalar.",
     "Собственный бренд iHerb: витамины, минералы и пищевые добавки.",
     "iHerb's own brand of vitamins, minerals and supplements.", ()),
    ("Rule 1", "US", "AQSh brendi (Rule One Proteins). R1 Protein izolyati bilan tanilgan.",
     "Американский бренд (Rule One Proteins). Известен изолятом R1 Protein.",
     "US brand (Rule One Proteins) known for R1 Protein isolate.", ("Rule One", "R1")),
    ("USPLabs", "US", "AQSh brendi. Modern BCAA+ aminokislotalari va pre-workout komplekslari bilan tanilgan.",
     "Американский бренд. Известен аминокислотами Modern BCAA+ и предтренировочными комплексами.",
     "US brand known for Modern BCAA+ and pre-workout formulas.", ("Usblabs", "USP Labs")),
    ("MuscleMeds", "US", "AQSh brendi. Carnivor mol go'shti proteini bilan mashhur.",
     "Американский бренд. Известен говяжьим протеином Carnivor.",
     "US brand famous for Carnivor beef protein.", ()),
    ("Kevin Levrone Signature Series", "PL", "Mashhur bodibilder Kevin Levron nomidagi seriya. Polshada ishlab chiqariladi.",
     "Линейка имени известного бодибилдера Кевина Леврона. Производится в Польше.",
     "Line named after bodybuilding legend Kevin Levrone, made in Poland.", ("Kevin Levrone", "Levrone")),
    ("Hi-Tech Pharmaceuticals", "US", "AQShning Jorjiya shtatidagi ishlab chiqaruvchi. Yog' yoqish va kuch uchun vositalar.",
     "Производитель из штата Джорджия (США): жиросжигатели и средства для силы.",
     "Georgia, USA maker of fat burners and performance supplements.", ("HTP Hi-Tech", "Hi-Tech", "HTP")),
    ("GAT Sport", "US", "Nyu-Jersi (AQSh) brendi. Nitraflex pre-workout kompleksi bilan tanilgan.",
     "Бренд из Нью-Джерси (США). Известен предтреником Nitraflex.",
     "New Jersey, USA brand known for Nitraflex pre-workout.", ("Gat sport", "GAT")),
    ("Fitness Authority", "PL", "Polsha ishlab chiqaruvchisi (FA Nutrition). Keng assortimentdagi sport ozuqalari.",
     "Польский производитель (FA Nutrition) с широким ассортиментом спортивного питания.",
     "Polish manufacturer (FA Nutrition) with a wide sports-nutrition range.", ("FA", "FA Nutrition")),
    ("Nutrex Research", "US", "AQSh brendi. Lipo-6 yog' yoqish vositalari bilan mashhur.",
     "Американский бренд. Известен жиросжигателями Lipo-6.",
     "US brand famous for the Lipo-6 fat-burner line.", ("Nutrex",)),
    ("OstroVit", "PL", "Polsha brendi. Qulay narxdagi sport ozuqalari va vitaminlar.",
     "Польский бренд доступного спортивного питания и витаминов.",
     "Polish brand of affordable sports nutrition and vitamins.", ()),
    ("Quamtrax", "ES", "Ispaniya brendi. Protein, aminokislotalar va vitaminlar.",
     "Испанский бренд: протеины, аминокислоты и витамины.",
     "Spanish brand of proteins, amino acids and vitamins.", ()),
    ("APS Nutrition", "US", "AQSh brendi. Mesomorph pre-workout kompleksi bilan tanilgan.",
     "Американский бренд. Известен предтреником Mesomorph.",
     "US brand known for Mesomorph pre-workout.", ("APS",)),
    ("CON-CRET", "US", "AQSh brendi (ProMera Sports). Konsentrlangan kreatin HCl bilan tanilgan.",
     "Американский бренд (ProMera Sports). Известен концентрированным креатином HCl.",
     "US brand (ProMera Sports) known for concentrated creatine HCl.", ("Con-Cret", "ConCret")),
    ("BioTechUSA", "HU", "1999-yilda asos solingan Vengriya brendi. Yevropaning yirik sport ozuqa ishlab chiqaruvchilaridan biri.",
     "Венгерский бренд, основанный в 1999 году. Один из крупнейших производителей спортивного питания в Европе.",
     "Hungarian brand founded in 1999, one of Europe's largest sports-nutrition makers.", ("Biotech", "BioTech USA")),
    ("Ultimate Nutrition", "US", "1979-yildan beri ishlab kelayotgan AQSh brendi. Prostar Whey proteini bilan tanilgan.",
     "Американский бренд, работающий с 1979 года. Известен протеином Prostar Whey.",
     "US brand since 1979, known for Prostar Whey.", ()),
    ("NOW Foods", "US", "1968-yildan beri AQShda vitaminlar, minerallar va tabiiy qo'shimchalar ishlab chiqaradi.",
     "С 1968 года производит в США витамины, минералы и натуральные добавки.",
     "Making vitamins, minerals and natural supplements in the USA since 1968.", ("Now Foods", "NOW")),
    ("Solgar", "US", "1947-yildan beri vitamin va mineral qo'shimchalar ishlab chiqaruvchi AQSh brendi.",
     "Американский производитель витаминов и минералов с 1947 года.",
     "US vitamin and mineral maker since 1947.", ()),
    ("Sports Research", "US", "Kaliforniya (AQSh) brendi. Omega-3, kollagen va vitaminlar.",
     "Бренд из Калифорнии (США): омега-3, коллаген и витамины.",
     "California, USA brand of omega-3, collagen and vitamins.", ("Sport Research",)),
    ("KAL", "US", "AQSh vitamin brendi. Vitaminlar, minerallar va ozuqaviy qo'shimchalar.",
     "Американский бренд витаминов, минералов и пищевых добавок.",
     "US brand of vitamins, minerals and supplements.", ("Kal",)),
    ("Solaray", "US", "AQSh brendi. O'simlik ekstraktlari, vitaminlar va minerallar.",
     "Американский бренд: растительные экстракты, витамины и минералы.",
     "US brand of herbal extracts, vitamins and minerals.", ()),
    ("Carlson Labs", "US", "1965-yildan beri faoliyat yuritayotgan oilaviy AQSh kompaniyasi. Baliq yog'i va vitamin D bilan tanilgan.",
     "Семейная американская компания с 1965 года. Известна рыбьим жиром и витамином D.",
     "US family company since 1965, known for fish oil and vitamin D.", ("Carlson",)),
    ("Maxler", "DE", "Germaniya brendi. Sport ozuqalari va vitaminlar.",
     "Немецкий бренд спортивного питания и витаминов.",
     "German brand of sports nutrition and vitamins.", ()),
    ("Source Naturals", "US", "1982-yildan beri AQShda ozuqaviy qo'shimchalar ishlab chiqaradi.",
     "С 1982 года производит пищевые добавки в США.",
     "Making dietary supplements in the USA since 1982.", ()),
    ("Nutricost", "US", "Yuta (AQSh) brendi. Oddiy va toza tarkibli qo'shimchalar.",
     "Бренд из Юты (США): добавки с простым и чистым составом.",
     "Utah, USA brand of simple, clean-label supplements.", ()),
    ("USN", "ZA", "Janubiy Afrika brendi (Ultimate Sports Nutrition). Protein, geyner va sport ozuqalari.",
     "Бренд из ЮАР (Ultimate Sports Nutrition): протеины, гейнеры и спортивное питание.",
     "South African brand (Ultimate Sports Nutrition) of proteins, gainers and sports nutrition.", ("Ultimate Sports Nutrition",)),
    ("Nutriversum", "HU", "Vengriya brendi. Sport ozuqalari va vitaminlar.",
     "Венгерский бренд спортивного питания и витаминов.",
     "Hungarian brand of sports nutrition and vitamins.", ()),
]


def seed_brands(stdout=None) -> dict:
    from django.db import transaction
    from django.db.models.functions import Lower

    from apps.geo.infrastructure.models import Country
    from apps.geo.infrastructure.reference_data import slugify_uz
    from apps.products.infrastructure import models as orm

    countries = {c.code: c for c in Country.objects.all()}
    created = updated = 0
    with transaction.atomic():
        for name, code, uz, ru, en, aliases in BRANDS:
            wanted = {n.lower() for n in (name, *aliases)}
            brand = orm.Brand.all_objects.filter(translations__name__in=[n for n in (name, *aliases)]).first() or next(
                (b for b in orm.Brand.all_objects.annotate(n=Lower("translations__name")).filter(n__in=wanted)), None)
            if brand is None:
                brand = orm.Brand.objects.create(is_active=True, country=countries.get(code))
                created += 1
            else:
                if brand.is_deleted:
                    brand.is_deleted, brand.deleted_at = False, None
                if not brand.country_id and code in countries:
                    brand.country = countries[code]
                brand.save()
                updated += 1
            slug = slugify_uz(name)
            for locale, text in (("uz", uz), ("ru", ru), ("en", en)):
                row = orm.BrandTranslation.objects.filter(brand=brand, locale_code=locale).first()
                if row is None:
                    taken = orm.BrandTranslation.objects.filter(locale_code=locale, slug=slug).exists()
                    orm.BrandTranslation.objects.create(brand=brand, locale_code=locale, name=name, description=text,
                                                        slug=f"{slug}-{str(brand.id)[:4]}" if taken else slug)
                elif not row.description:
                    row.description = text
                    row.save(update_fields=["description", "updated_at"])
    if stdout:
        stdout.write(f"Brands: {created} created, {updated} already there ({len(BRANDS)} in the list)")
    return {"created": created, "updated": updated}
