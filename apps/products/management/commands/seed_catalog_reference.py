from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load package types, flavours (with swatch colours) and tags in uz/ru/en; idempotent -- never duplicates or overwrites edits."

    def handle(self, *args, **options):
        from apps.products.infrastructure.reference_catalog import seed_reference

        seed_reference(stdout=self.stdout)
