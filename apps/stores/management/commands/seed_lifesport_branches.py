"""
LifeSport branches (do'konlar) with phones and map pins taken from the official @lifesportpit channel posts.

    python manage.py seed_lifesport_branches            # create missing branches, fill empty fields of existing ones
    python manage.py seed_lifesport_branches --dry-run

A branch is matched by name (any of its spellings, case-insensitive), so a row renamed or edited in the dashboard
is never duplicated, and fields someone already filled in are left alone.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

# name, other spellings, city, district, phone, (lat, lon) or None, channel post id
BRANCHES = [
    ("LifeSport Toshkent Siti", ["LifeSport Tashkent City"], "Toshkent", "Shayxontohur", "+998555169916", (41.316836, 69.241513), 3686),
    ("LifeSport Chilonzor", [], "Toshkent", "Chilonzor", "+998998931554", (41.286254, 69.227378), 2359),
    ("LifeSport Olmazor", ["LifeSport Olamazor", "LifeSport Almazar"], "Toshkent", "Olmazor", "+998995260298", None, 4207),
    ("LifeSport Mirzo Ulug'bek", ["LifeSport Mirzo Ulugbek"], "Toshkent", "Mirzo Ulug'bek", "+998950059916", (41.321358, 69.320595), 3174),
    ("LifeSport Yunusobod", ["LifeSport Yunusabad"], "Toshkent", "Yunusobod", "+998935661101", (41.366964, 69.289023), 2972),
    ("LifeSport NEXT", ["LifeSport TRC NEXT", "LifeSport Next"], "Toshkent", "Yakkasaroy", "+998771189916", (41.296079, 69.250209), 3386),
    ("LifeSport Uchtepa", [], "Toshkent", "Uchtepa", "+998901289916", (41.291814, 69.193646), 3815),
    ("LifeSport Sergeli", [], "Toshkent", "Sergeli", "+998770779916", (41.222530, 69.224027), 3861),
    ("LifeSport Qadeshva", ["LifeSport Kadeshva"], "Toshkent", "Mirzo Ulug'bek", "+998958149916", (41.296368, 69.341890), 4017),
    ("LifeSport Chirchiq", ["LifeSport Chirchik"], "Chirchiq", "", "+998771159916", None, 4131),
    ("LifeSport Samarqand", ["LifeSport Samarkand"], "Samarqand", "", "+998932430773", (39.658992, 66.935990), 3940),
    ("LifeSport Andijon", ["LifeSport Andijan"], "Andijon", "", "+998942060629", (40.771893, 72.359882), 4103),
    ("LifeSport Qo'yliq", ["LifeSport Kuyluk", "LifeSport Quyliq"], "Toshkent", "Bektemir", "+998505159916", (41.246785, 69.321867), 4161),
    ("LifeSport Termiz", ["LifeSport Termez"], "Termiz", "", "+998501789916", None, 4168),
]


class Command(BaseCommand):
    help = "Creates / completes the LifeSport branch list (phones, districts, map pins)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        from apps.stores.infrastructure.models import Store

        created = updated = 0
        with transaction.atomic():
            for name, aliases, city, district, phone, pin, post in BRANCHES:
                names = [name, *aliases]
                store = next((s for s in Store.objects.filter(kind="store") if s.name.strip().lower() in {n.lower() for n in names}), None)
                if store is None:
                    store = Store(name=name, kind="store")
                    created += 1
                changes = []
                for field, value in (("city", city), ("district", district), ("tagline", f"LifeSport · {district or city}"),
                                     ("telegram_username", "lifesportpit"), ("description", f"LifeSport sport ozuqalari do'koni — {district or city}. https://t.me/lifesportpit/{post}")):
                    if value and not getattr(store, field):
                        setattr(store, field, value)
                        changes.append(field)
                if phone not in (store.phone_numbers or []):
                    store.phone_numbers = [phone, *(store.phone_numbers or [])]
                    changes.append("phone_numbers")
                # a pin from the channel is authoritative; a missing one never clears what the dashboard has
                if pin and (store.latitude, store.longitude) != pin:
                    store.latitude, store.longitude = pin
                    changes.append("location")
                if store.name in aliases:
                    store.name = name
                    changes.append("name")
                if store._state.adding or changes:
                    if store._state.adding is False:
                        updated += 1
                    self.stdout.write(f"  {'+' if store._state.adding else '~'} {name}: {', '.join(changes) or 'new'}")
                    if not dry_run:
                        store.save()
            if dry_run:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f"LifeSport: {created} created, {updated} updated"))
