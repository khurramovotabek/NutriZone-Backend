"""The dashboard brand colour moves from the old green to the storefront's blue; a colour the owner picked themselves is left alone."""
from django.db import migrations

OLD_GREEN = "#1f7a4d"
BLUE = "#1d4ed8"


def to_blue(apps, schema_editor):
    SiteSettings = apps.get_model("platform", "SiteSettings")
    SiteSettings.objects.filter(primary_color__iexact=OLD_GREEN).update(primary_color=BLUE)


def to_green(apps, schema_editor):
    SiteSettings = apps.get_model("platform", "SiteSettings")
    SiteSettings.objects.filter(primary_color__iexact=BLUE).update(primary_color=OLD_GREEN)


class Migration(migrations.Migration):
    dependencies = [("platform", "0015_alter_sitesettings_primary_color")]
    operations = [migrations.RunPython(to_blue, to_green)]
