"""Fills the three branches that had no map point, from the owner's Telegram channel @lifesportpit (each branch's
pinned location post, 2026-08/09) cross-checked against OpenStreetMap. Only empty fields are filled -- anything the
staff already typed in the dashboard is left alone, and running it twice changes nothing."""
from django.db import migrations

BRANCHES = {
    # slug: (latitude, longitude, address, city, district)
    "lifesport-olmazor": (41.351406, 69.213064, "Talabalar ko'chasi, 88/1", "Toshkent", "Olmazor"),
    "lifesport-chirchiq": (41.475724, 69.582992, "Madaniyat ko'chasi, 25", "Chirchiq", ""),
    "lifesport-termiz": (37.238322, 67.303457, "Alisher Navoiy ko'chasi, 7/7", "Termiz", ""),
    # these two already have their point; only the empty city is filled
    "lifesport-andijon": (None, None, "", "Andijon", ""),
    "lifesport-samarqand": (None, None, "", "Samarqand", ""),
}


def forwards(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    for slug, (lat, lng, address, city, district) in BRANCHES.items():
        store = Store.objects.filter(slug=slug).first()
        if store is None:
            continue
        changed = []
        if lat is not None and (store.latitude is None or store.longitude is None):
            store.latitude, store.longitude = lat, lng
            changed += ["latitude", "longitude"]
        for field, value in (("address", address), ("city", city), ("district", district)):
            if value and not getattr(store, field):
                setattr(store, field, value)
                changed.append(field)
        if changed:
            store.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("stores", "0022_store_map_listings")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
