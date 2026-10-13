from django.db import migrations

PALETTE = [
    "#2D8CFF", "#22C55E", "#FF9800", "#E91E63", "#7E35C1", "#4338CA", "#FF8057", "#F45B5B", "#38BDF8", "#E879F9",
    "#818CF8", "#C9DC45", "#607D8B", "#14B8A6", "#F59E0B", "#A855F7", "#EF4444", "#10B981", "#0EA5E9", "#D946EF",
]


def colours(apps, schema_editor):
    """Every existing store gets its own lifelong chart colour (oldest store first)."""
    Store = apps.get_model("stores", "Store")
    used = set(Store.objects.exclude(color="").values_list("color", flat=True))
    free = [c for c in PALETTE if c not in used]
    for i, store in enumerate(Store.objects.filter(color="").order_by("created_at")):
        colour = free[i] if i < len(free) else PALETTE[i % len(PALETTE)]
        Store.objects.filter(pk=store.pk).update(color=colour)


class Migration(migrations.Migration):
    dependencies = [("stores", "0005_store_color")]
    operations = [migrations.RunPython(colours, migrations.RunPython.noop)]
