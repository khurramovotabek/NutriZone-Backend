from django.db import migrations


def copy_document_data_forward(apps, schema_editor):
    """Media Asset architecture removal (Certificate), step 2 of 4: for every Certificate that currently has a real `document_media_asset`, copy its real storage_path/thumbnail_paths into the new direct fields. Real, existing production data is preserved -- nothing is regenerated or re-uploaded."""
    Certificate = apps.get_model("products", "Certificate")
    for cert in Certificate.objects.exclude(document_media_asset=None).select_related("document_media_asset"):
        cert.document_storage_path = cert.document_media_asset.storage_path
        cert.document_thumbnail_paths = cert.document_media_asset.thumbnail_paths
        cert.save(update_fields=["document_storage_path", "document_thumbnail_paths"])


def copy_document_data_backward(apps, schema_editor):
    """Reverse: best-effort only -- cannot recreate a ProductMediaAsset row with its original id/checksum, so this is a no-op."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0015_certificate_direct_document_fields"),
    ]

    operations = [
        migrations.RunPython(copy_document_data_forward, copy_document_data_backward),
    ]
