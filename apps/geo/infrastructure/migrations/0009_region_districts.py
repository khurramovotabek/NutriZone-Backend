"""
The districts (tumanlar) of every other region, in Uzbek and English -- a GPS point anywhere in Uzbekistan now gets its
district from the OpenStreetMap name (geocoder._match_district compares the Uzbek names). Russian names are left for
the team to add from the dashboard (Geo → Tumanlar shows a red RU badge); until then Russian pages show the Uzbek name.
Only added to a region that has no districts yet, so names edited on the dashboard are never touched.
"""
from __future__ import annotations

import re
import uuid

from django.db import migrations

DISTRICTS = {
    "UZ-AN": ["Andijon", "Asaka", "Baliqchi", "Bo'ston", "Buloqboshi", "Izboskan", "Jalaquduq", "Xo'jaobod", "Qo'rg'ontepa", "Marhamat", "Oltinko'l", "Paxtaobod", "Shahrixon", "Ulug'nor"],
    "UZ-BU": ["Olot", "Buxoro", "G'ijduvon", "Jondor", "Kogon", "Qorako'l", "Qorovulbozor", "Peshku", "Romitan", "Shofirkon", "Vobkent"],
    "UZ-FA": ["Oltiariq", "Bag'dod", "Beshariq", "Buvayda", "Dang'ara", "Farg'ona", "Furqat", "Qo'shtepa", "Quva", "Rishton", "So'x", "Toshloq", "Uchko'prik", "O'zbekiston", "Yozyovon"],
    "UZ-JI": ["Arnasoy", "Baxmal", "Do'stlik", "Forish", "G'allaorol", "Sharof Rashidov", "Mirzacho'l", "Paxtakor", "Yangiobod", "Zomin", "Zafarobod", "Zarbdor"],
    "UZ-NG": ["Chortoq", "Chust", "Kosonsoy", "Mingbuloq", "Namangan", "Norin", "Pop", "To'raqo'rg'on", "Uchqo'rg'on", "Uychi", "Yangiqo'rg'on"],
    "UZ-NW": ["Karmana", "Konimex", "Qiziltepa", "Navbahor", "Nurota", "Tomdi", "Uchquduq", "Xatirchi"],
    "UZ-QA": ["Chiroqchi", "Dehqonobod", "G'uzor", "Qamashi", "Qarshi", "Kasbi", "Kitob", "Koson", "Ko'kdala", "Mirishkor", "Muborak", "Nishon", "Shahrisabz", "Yakkabog'"],
    "UZ-QR": ["Amudaryo", "Beruniy", "Bo'zatov", "Chimboy", "Ellikqal'a", "Kegeyli", "Mo'ynoq", "Nukus", "Qanliko'l", "Qo'ng'irot", "Qorao'zak", "Shumanay", "Taxtako'pir", "Taxiatosh", "To'rtko'l", "Xo'jayli"],
    "UZ-SA": ["Bulung'ur", "Ishtixon", "Jomboy", "Kattaqo'rg'on", "Qo'shrabot", "Narpay", "Nurobod", "Oqdaryo", "Paxtachi", "Payariq", "Pastdarg'om", "Samarqand", "Toyloq", "Urgut"],
    "UZ-SI": ["Oqoltin", "Boyovut", "Guliston", "Xovos", "Mirzaobod", "Sayxunobod", "Sardoba", "Sirdaryo"],
    "UZ-SU": ["Angor", "Bandixon", "Boysun", "Denov", "Jarqo'rg'on", "Qiziriq", "Qumqo'rg'on", "Muzrabot", "Oltinsoy", "Sariosiyo", "Sherobod", "Sho'rchi", "Termiz", "Uzun"],
    "UZ-TO": ["Bekobod", "Bo'stonliq", "Bo'ka", "Chinoz", "Qibray", "Ohangaron", "Oqqo'rg'on", "Parkent", "Piskent", "Quyi Chirchiq", "O'rta Chirchiq", "Yangiyo'l", "Yuqori Chirchiq", "Zangiota", "Toshkent"],
    "UZ-XO": ["Bog'ot", "Gurlan", "Xonqa", "Hazorasp", "Xiva", "Qo'shko'pir", "Shovot", "Urganch", "Yangiariq", "Yangibozor", "Tuproqqal'a"],
}


def _latin(name: str) -> str:
    return name.replace("'", "").replace("ʻ", "")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _latin(text).lower()).strip("-")


def forwards(apps, schema_editor):
    Region = apps.get_model("geo", "Region")
    District = apps.get_model("geo", "District")
    Translation = apps.get_model("geo", "DistrictTranslation")
    for region_code, names in DISTRICTS.items():
        region = Region.objects.filter(code=region_code).first()
        if region is None or District.objects.filter(region=region).exists():
            continue
        prefix = region_code.split("-")[1]
        for i, name in enumerate(names, 1):
            code = f"{prefix}-{re.sub(r'[^A-Z]', '', _latin(name).upper())[:5]}{i:02d}"[:10]
            d = District.objects.create(id=uuid.uuid4(), region=region, code=code, status="active")
            for locale, label in (("uz", f"{name} tumani"), ("en", f"{_latin(name)} District")):
                slug = f"{_slug(label)}-{prefix.lower()}"
                if Translation.objects.filter(locale_code=locale, slug=slug).exists():
                    slug = f"{slug}-{i}"
                Translation.objects.create(id=uuid.uuid4(), district=d, locale_code=locale, name=label, slug=slug)


def backwards(apps, schema_editor):
    District = apps.get_model("geo", "District")
    prefixes = [c.split("-")[1] + "-" for c in DISTRICTS]
    for p in prefixes:
        District.objects.filter(code__startswith=p, addresses__isnull=True, cities__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("geo", "0008_tashkent_districts_and_address_regions")]
    operations = [migrations.RunPython(forwards, backwards)]
