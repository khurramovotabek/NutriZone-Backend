"""
BTS Express Cargo public tariff card, in force from 2026-09-01 (bts.uz -> Hujjatlar -> "BTS xizmatlarining tarif
kartasi", order No. 75 of 2026-08-13). Prices include VAT. Every parcel leaves from Tashkent (the NutriZone warehouse
hands it in at a BTS office in Tashkent, so the sender pays no pick-up courier).

The bts.uz calculator itself sits behind a captcha, so the card is encoded here instead:

* zone: Tashkent MVO -> destination MVO (table 1.3, the "Toshkent" row). Every city of one region shares its MVO's zone.
* "Ekspress pochta" office to office (2.1.1) for parcels up to 20 kg; "Yig'ma yuk" (2.2.1) above that.
* billable weight: max(actual, volumetric = L x W x H cm / 6000), rounded UP to whole kilograms (General terms).
* remote office (2.3): an office in a district away from the regional centre adds 3 000 / 7 000 / 11 000 / 18 000.
* door delivery (3.1, optional on the dashboard): the courier fee of the destination's courier zone (3.5) instead.
* winter fuel surcharge (1.1, "up to 30 % in Dec-Mar"): a dashboard percentage, 0 by default.

When BTS publishes a new card, update the tables below (and the date in this docstring).
"""
from __future__ import annotations

import math
from decimal import Decimal

VOLUMETRIC_DIVISOR = 6000  # domestic parcels (international uses 5000)

# Table 1.3, row "Toshkent": the zone of each destination region (geo.Region.code) -- its MVO city in the comment.
ZONE_BY_REGION = {
    "UZ-TO": 0,  # Toshkent viloyati -> Toshkent MVO
    "UZ-SA": 1, "UZ-JI": 1, "UZ-SI": 1,  # Samarqand, Jizzax, Guliston
    "UZ-FA": 1, "UZ-NG": 1, "UZ-AN": 1,  # Farg'ona / Qo'qon, Namangan, Andijon
    "UZ-BU": 2, "UZ-NW": 2, "UZ-QA": 2,  # Buxoro, Navoiy, Qarshi
    "UZ-SU": 3,  # Termiz
    "UZ-XO": 4,  # Urganch
    "UZ-QR": 5,  # Nukus
}
DEFAULT_ZONE = 3  # an unknown region: a middle zone rather than the cheapest

# 2.1.1 Ekspress pochta, office -> office, so'm per parcel; index = kg - 1 (1..20 kg), one list per zone 0..5.
EXPRESS = [
    [29000, 33000, 36000, 40000, 43000, 46000, 49000, 52000, 55000, 59000, 62000, 65000, 68000, 71000, 74000, 76000, 79000, 82000, 85000, 88000],
    [34000, 43000, 52000, 60000, 69000, 76000, 84000, 93000, 101000, 110000, 118000, 125000, 133000, 141000, 149000, 156000, 164000, 172000, 179000, 187000],
    [36000, 46000, 55000, 65000, 74000, 81000, 90000, 99000, 108000, 117000, 125000, 134000, 142000, 150000, 159000, 167000, 175000, 183000, 192000, 200000],
    [40000, 50000, 60000, 70000, 80000, 88000, 97000, 107000, 116000, 126000, 135000, 143000, 152000, 161000, 170000, 178000, 187000, 196000, 204000, 213000],
    [42000, 53000, 64000, 74000, 85000, 93000, 103000, 113000, 123000, 133000, 142000, 151000, 161000, 170000, 179000, 188000, 197000, 207000, 216000, 225000],
    [46000, 58000, 69000, 81000, 92000, 100000, 111000, 122000, 132000, 143000, 153000, 162000, 172000, 182000, 192000, 201000, 211000, 221000, 230000, 240000],
]
# 2.2.1 Yig'ma yuk (21 kg and heavier), office -> office: (price at 21 kg, per kg 22-100, per kg 101-500, per kg 501+)
LTL = [
    (130000, 2500, 2500, 2500),
    (250000, 6000, 5500, 5000),
    (275000, 6800, 6300, 6000),
    (295000, 7500, 7000, 6500),
    (310000, 8500, 8000, 7500),
    (330000, 9000, 8500, 8000),
]

CITY, A, B, C, D = "city", "A", "B", "C", "D"
# 2.3: remote office logistics fee per parcel (not applied inside zone 0)
REMOTE_OFFICE_FEE = {CITY: 0, A: 3000, B: 7000, C: 11000, D: 18000}
# 3.1 courier (door) fee by billable weight band: (up to kg, {zone: so'm}); above 100 kg the heavy-goods rows apply
COURIER = [
    (10, {CITY: 35000, A: 65000, B: 95000, C: 145000, D: 190000}),
    (20, {CITY: 47000, A: 85000, B: 120000, C: 175000, D: 230000}),
    (30, {CITY: 60000, A: 105000, B: 145000, C: 205000, D: 270000}),
    (50, {CITY: 80000, A: 125000, B: 180000, C: 255000, D: 335000}),
    (100, {CITY: 110000, A: 170000, B: 235000, C: 320000, D: 415000}),
]
COURIER_PER_50KG_OVER_100 = {CITY: 30000, A: 45000, B: 55000, C: 65000, D: 80000}

# 3.5: courier zone of each city we have in geo (geo.City.code). "Shahar" = a city with its own BTS office.
_Z = {1: A, 2: B, 3: C, 4: D}
COURIER_ZONE_BY_CITY = {
    "AN-ANDIJ": CITY, "AN-ASAKA": CITY, "AN-SHAHR": CITY, "AN-XONOB": B, "AN-QORAS": B, "AN-MARHA": A,
    "BU-BUXOR": CITY, "BU-KOGON": CITY, "BU-ROMIT": A, "BU-GIJDU": A, "BU-QORAK": B, "BU-OLOT": B,
    "FA-FARGO": CITY, "FA-QOQON": CITY, "FA-QUVAS": CITY, "FA-BESHA": CITY, "FA-QUVA": A, "FA-MARGI": A, "FA-RISHT": A,
    "JI-JIZZA": CITY, "JI-PAXTA": A, "JI-ZOMIN": B, "JI-GALLA": B, "JI-DOSTL": B,
    "NG-NAMAN": CITY, "NG-CHUST": CITY, "NG-KOSON": CITY, "NG-CHORT": A, "NG-POP": B, "NG-UCHQO": B,
    "NW-NAVOI": CITY, "NW-KARMA": A, "NW-ZARAF": A, "NW-QIZIL": B, "NW-NUROT": B, "NW-UCHQU": D,
    "QA-QARSH": CITY, "QA-SHAHR": CITY, "QA-KOSON": A, "QA-YAKKA": B, "QA-MUBOR": B, "QA-GUZOR": B, "QA-KITOB": C,
    "QR-NUKUS": CITY, "QR-BERUN": A, "QR-XOJAY": A, "QR-TORTK": B, "QR-CHIMB": B, "QR-QONGI": C, "QR-MOYNO": D,
    "SA-SAMAR": CITY, "SA-KATTA": CITY, "SA-URGUT": CITY, "SA-JOMBO": CITY, "SA-PAYAR": CITY, "SA-BULUN": CITY, "SA-ISHTI": A,
    "SI-GULIS": CITY, "SI-SIRDA": A, "SI-YANGI": A, "SI-BOYOV": A, "SI-SHIRI": B,
    "SU-TERMI": CITY, "SU-DENOV": CITY, "SU-JARQO": A, "SU-SHORC": B, "SU-SHERO": B, "SU-QUMQO": B, "SU-BOYSU": C,
    "TO-OLMAL": CITY, "TO-CHIRC": CITY, "TO-ANGRE": CITY, "TO-NURAF": A, "TO-PARKE": A, "TO-OHANG": A, "TO-YANGI": A,
    "TO-GAZAL": B, "TO-BOKA": B, "TO-BEKOB": C,
    "XO-URGAN": CITY, "XO-XIVA": CITY, "XO-XONQA": A, "XO-BOGOT": B, "XO-SHOVO": B, "XO-HAZOR": B, "XO-GURLA": B,
}


def zone_for(region_code: str | None) -> int:
    return ZONE_BY_REGION.get((region_code or "").upper(), DEFAULT_ZONE)


def courier_zone_for(city_code: str | None) -> str:
    """An unknown city is treated as a nearby district (A, up to 50 km from the office) -- never as the cheapest case."""
    return COURIER_ZONE_BY_CITY.get((city_code or "").upper(), A)


def billable_kg(actual_kg: float, volume_cm3: float = 0.0) -> int:
    volumetric = (volume_cm3 or 0) / VOLUMETRIC_DIVISOR
    return max(1, math.ceil(round(max(actual_kg or 0, volumetric), 3)))


def transport_fee(kg: int, zone: int) -> int:
    zone = min(max(zone, 0), 5)
    if kg <= 20:
        return EXPRESS[zone][kg - 1]
    base, per_100, per_500, per_more = LTL[zone]
    fee = base + per_100 * (min(kg, 100) - 21)
    if kg > 100:
        fee += per_500 * (min(kg, 500) - 100)
    if kg > 500:
        fee += per_more * (kg - 500)
    return fee


def courier_fee(kg: int, courier_zone: str) -> int:
    for up_to, prices in COURIER:
        if kg <= up_to:
            return prices[courier_zone]
    return COURIER[-1][1][courier_zone] + COURIER_PER_50KG_OVER_100[courier_zone] * math.ceil((kg - 100) / 50)


def price(actual_kg: float, region_code: str | None, city_code: str | None, *, volume_cm3: float = 0.0, door: bool = False,
          fuel_surcharge_percent: Decimal | int | float = 0) -> Decimal:
    """What BTS charges to send this parcel from Tashkent to the address (so'm, before NutriZone's own rounding)."""
    kg = billable_kg(actual_kg, volume_cm3)
    zone = zone_for(region_code)
    cz = courier_zone_for(city_code)
    fee = transport_fee(kg, zone)
    if door:
        fee += courier_fee(kg, cz)
    elif zone != 0:
        fee += REMOTE_OFFICE_FEE[cz]
    surcharge = Decimal(str(fuel_surcharge_percent or 0))
    return Decimal(fee) * (Decimal(100) + surcharge) / Decimal(100)
