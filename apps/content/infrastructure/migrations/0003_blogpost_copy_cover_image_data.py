from django.db import migrations


def copy_cover_image_data_forward(apps, schema_editor):
    """Media Asset architecture removal (BlogPost), step 2 of 3: for every BlogPost that currently has a real `cover_image` (ProductMediaAsset FK), copy its real storage_path/thumbnail_paths into the new direct fields. Real, existing production data is preserved -- nothing is regenerated or re-uploaded."""
    BlogPost = apps.get_model("content", "BlogPost")
    for post in BlogPost.objects.exclude(cover_image=None).select_related("cover_image"):
        post.cover_image_storage_path = post.cover_image.storage_path
        post.cover_image_thumbnail_paths = post.cover_image.thumbnail_paths
        post.save(update_fields=["cover_image_storage_path", "cover_image_thumbnail_paths"])


def copy_cover_image_data_backward(apps, schema_editor):
    """Reverse: best-effort only -- cannot recreate a ProductMediaAsset row with its original id/checksum, so this is a no-op."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0002_blogpost_direct_cover_fields"),
    ]

    operations = [
        migrations.RunPython(copy_cover_image_data_forward, copy_cover_image_data_backward),
    ]
