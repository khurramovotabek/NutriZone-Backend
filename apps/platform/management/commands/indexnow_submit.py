"""python manage.py indexnow_submit [--all | --days N] -- push storefront pages to IndexNow (Bing, Yandex, ...)."""
from django.core.management.base import BaseCommand

from apps.platform.infrastructure import indexnow


class Command(BaseCommand):
    help = "Submit storefront sitemap pages to IndexNow (Bing, Yandex, Seznam, Naver)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Every page in the sitemap, not only recently changed ones.")
        parser.add_argument("--days", type=float, default=2, help="Pages changed in the last N days (default 2).")

    def handle(self, *args, **opts):
        result = indexnow.submit_changed(None if opts["all"] else opts["days"])
        self.stdout.write(self.style.SUCCESS(f"IndexNow: {result['submitted']} URL, javob: {result['statuses']}"))
