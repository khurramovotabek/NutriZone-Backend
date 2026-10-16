from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load NutriZone's brand list (country + uz/ru/en description); idempotent -- never duplicates or overwrites edits."

    def handle(self, *args, **options):
        from apps.products.infrastructure.brand_catalog import seed_brands

        seed_brands(stdout=self.stdout)
