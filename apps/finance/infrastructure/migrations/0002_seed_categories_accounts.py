"""Starter expense/income categories and two accounts (cash + bank) -- the owner renames, adds or closes them on the dashboard."""
from django.db import migrations
from django.utils import timezone

CATEGORIES = [
    # name, kind, section, icon, color
    ("Ijara", "expense", "opex", "fa-house", "#7c3aed"),
    ("Kommunal xizmatlar", "expense", "opex", "fa-bolt", "#f59e0b"),
    ("Xodimlar ish haqi", "expense", "opex", "fa-users", "#0ea5e9"),
    ("Marketing va reklama", "expense", "opex", "fa-bullhorn", "#ec4899"),
    ("Yetkazib berish va logistika", "expense", "opex", "fa-truck", "#14b8a6"),
    ("Bank va to'lov komissiyalari", "expense", "opex", "fa-percent", "#64748b"),
    ("Internet, aloqa va dasturlar", "expense", "opex", "fa-wifi", "#6366f1"),
    ("Xo'jalik va ofis", "expense", "opex", "fa-broom", "#84cc16"),
    ("Ta'mirlash va jihozlar", "expense", "opex", "fa-screwdriver-wrench", "#f97316"),
    ("Boshqa xarajatlar", "expense", "opex", "fa-ellipsis", "#94a3b8"),
    ("Soliqlar", "expense", "tax", "fa-landmark", "#dc2626"),
    ("Egasiga to'lov (dividend)", "expense", "capital", "fa-hand-holding-dollar", "#a855f7"),
    ("Qarzni qaytarish", "expense", "capital", "fa-rotate-left", "#475569"),
    ("Boshqa daromad", "income", "other_income", "fa-circle-plus", "#16a34a"),
    ("Egasidan investitsiya", "income", "capital", "fa-piggy-bank", "#22c55e"),
    ("Qarz olindi", "income", "capital", "fa-handshake", "#0d9488"),
]


def seed(apps, schema_editor):
    Category = apps.get_model("finance", "Category")
    MoneyAccount = apps.get_model("finance", "MoneyAccount")
    for i, (name, kind, section, icon, color) in enumerate(CATEGORIES):
        Category.objects.get_or_create(name=name, kind=kind, defaults={"section": section, "icon": icon, "color": color, "sort_order": i * 10})
    if not MoneyAccount.objects.exists():
        today = timezone.localdate()
        MoneyAccount.objects.create(name="Naqd kassa", kind="cash", color="#16a34a", sort_order=10, opening_date=today,
                                    sources=["pos_cash", "web_cod", "supplier_cash", "payroll"], note="Do'kon kassalaridagi naqd pul")
        MoneyAccount.objects.create(name="Bank hisobi", kind="bank", color="#2563eb", sort_order=20, opening_date=today,
                                    sources=["pos_card", "pos_qr", "web_online", "supplier_bank", "supplier_card"], note="Terminal, Click/Payme/Uzum va bank o'tkazmalari")


class Migration(migrations.Migration):
    dependencies = [("finance", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
