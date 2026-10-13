from django.db import migrations


class Migration(migrations.Migration):
    """Media Asset architecture removal, step 3 of 3: remove the old `logo` FK now that every real Brand's logo data is safely copied into logo_storage_path/logo_thumbnail_paths (step 2)."""

    dependencies = [
        ("products", "0006_brand_copy_logo_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="brand",
            name="logo",
        ),
    ]
