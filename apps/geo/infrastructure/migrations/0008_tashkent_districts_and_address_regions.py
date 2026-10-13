"""
* Saved addresses learn their region from their city (the storefront only ever sent city_id, so region was empty).
* Toshkent shahri gets its 12 districts (tumanlar) in uz / ru / en -- the address form and the courier see
  "Chilonzor tumani", and a GPS point inside Tashkent is matched to its district. Only added when the region has
  no districts yet; other regions' districts are added from the dashboard as delivery grows there.
"""
from __future__ import annotations

import uuid

from django.db import migrations

TASHKENT_REGION = "TGCITYR"
DISTRICTS = [  # code, uz, ru, en
    ("TSH-BEK", "Bektemir tumani", "Бектемирский район", "Bektemir District"),
    ("TSH-CHI", "Chilonzor tumani", "Чиланзарский район", "Chilanzar District"),
    ("TSH-MIR", "Mirobod tumani", "Мирабадский район", "Mirabad District"),
    ("TSH-MUL", "Mirzo Ulug'bek tumani", "Мирзо-Улугбекский район", "Mirzo Ulugbek District"),
    ("TSH-OLM", "Olmazor tumani", "Алмазарский район", "Almazar District"),
    ("TSH-SER", "Sergeli tumani", "Сергелийский район", "Sergeli District"),
    ("TSH-SHA", "Shayxontohur tumani", "Шайхантахурский район", "Shaykhantakhur District"),
    ("TSH-UCH", "Uchtepa tumani", "Учтепинский район", "Uchtepa District"),
    ("TSH-YAK", "Yakkasaroy tumani", "Яккасарайский район", "Yakkasaray District"),
    ("TSH-YAS", "Yashnobod tumani", "Яшнабадский район", "Yashnabad District"),
    ("TSH-YUN", "Yunusobod tumani", "Юнусабадский район", "Yunusabad District"),
    ("TSH-YAN", "Yangihayot tumani", "Янгихаётский район", "Yangihayot District"),
]


def _slug(text: str) -> str:
    table = str.maketrans({"'": "", "ʻ": "", "’": "", " ": "-"})
    ru = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
    out = "".join(ru.get(ch, ch) for ch in text.lower().translate(table))
    return "".join(ch for ch in out if ch.isalnum() or ch == "-").strip("-")


def forwards(apps, schema_editor):
    Address = apps.get_model("geo", "Address")
    City = apps.get_model("geo", "City")
    for city in City.objects.all():
        Address.objects.filter(city_id=city.id, region__isnull=True).update(region_id=city.region_id)

    Region = apps.get_model("geo", "Region")
    District = apps.get_model("geo", "District")
    Translation = apps.get_model("geo", "DistrictTranslation")
    region = Region.objects.filter(code=TASHKENT_REGION).first()
    if region is None or District.objects.filter(region=region).exists():
        return
    for code, uz, ru, en in DISTRICTS:
        if District.objects.filter(code=code).exists():
            continue
        d = District.objects.create(id=uuid.uuid4(), region=region, code=code, status="active")
        for locale, name in (("uz", uz), ("ru", ru), ("en", en)):
            slug = _slug(name)
            if Translation.objects.filter(locale_code=locale, slug=slug).exists():
                slug = f"{slug}-{code.lower()}"
            Translation.objects.create(id=uuid.uuid4(), district=d, locale_code=locale, name=name, slug=slug)


def backwards(apps, schema_editor):
    District = apps.get_model("geo", "District")
    District.objects.filter(code__in=[c for c, *_ in DISTRICTS], addresses__isnull=True, cities__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("geo", "0007_address_entrance")]
    operations = [migrations.RunPython(forwards, backwards)]
