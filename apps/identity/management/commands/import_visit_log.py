"""
Backfill the visitor-device statistics from nginx access logs (combined format, plain or .gz):

    python manage.py import_visit_log /logs/access.log /logs/access.log.2.gz ... [--until 2026-11-22] [--dry-run]

Counts only document page loads of the storefront (GET, 200, no /_next, /api, admin, files, RSC prefetches) from real
browsers (bots and server calls dropped). A visitor = sha256(IP + User-Agent). Idempotent: re-running adds no extra
days or hits -- each device's days/hits are recomputed from its day rows. `--until` stops at the day the storefront beacon
went live so the same visitors are not counted twice under two different keys.

Many crawlers pose as desktop Chrome / Safari (Apple, Bing, OpenAI ranges); they fetch the HTML but run no client code.
So a visitor only counts when the same IP + User-Agent also loaded a JS chunk or made a client-side navigation (RSC)
in the imported logs -- the same evidence a real phone or computer leaves.
"""
from __future__ import annotations

import gzip
import re
from collections import defaultdict
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Max, Min, Sum
from django.utils import timezone

from apps.identity.infrastructure.models import VisitorDay, VisitorDevice
from apps.identity.infrastructure.visitors import classify, visitor_key

LINE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d{3}) \S+ "[^"]*" "([^"]*)"')
SKIP = re.compile(r"^/(_next|api|django-admin|admin|static|media|feeds|og-image|r/|auto-login|__nextjs|\.well-known|cdn-cgi|wp-|xmlrpc)|"
                  r"\.(js|css|png|jpe?g|webp|avif|gif|svg|ico|txt|xml|json|map|woff2?|ttf|php|env|webmanifest|mp4)(\?|$)|[?&]_rsc=", re.I)


class Command(BaseCommand):
    help = "Import storefront visits (device statistics) from nginx access logs."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+")
        parser.add_argument("--until", help="last day to import (YYYY-MM-DD, Tashkent), exclusive", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *paths, **opts):  # noqa: C901
        until = date.fromisoformat(opts["until"]) if opts["until"] else None
        seen: dict = {}
        days: dict = defaultdict(int)
        human: set = set()  # visitor keys that ran the storefront's JS
        lines = pages = bots = 0
        for path in opts["paths"]:
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
                for raw in fh:
                    lines += 1
                    m = LINE.match(raw)
                    if not m:
                        continue
                    ip, ts, meth, url, status, ua = m.groups()
                    if url.startswith("/_next/static/chunks") or "_rsc=" in url:
                        human.add(visitor_key(f"log:{ip}|{ua}"))
                        continue
                    if meth != "GET" or status != "200" or SKIP.search(url):
                        continue
                    info = classify(ua)
                    if info["is_bot"]:
                        bots += 1
                        continue
                    when = datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z")
                    day = timezone.localtime(when).date()
                    if until and day >= until:
                        continue
                    pages += 1
                    key = visitor_key(f"log:{ip}|{ua}")
                    if key not in seen:
                        seen[key] = {**info, "first": when, "last": when}
                    else:
                        s = seen[key]
                        s["first"], s["last"] = min(s["first"], when), max(s["last"], when)
                    days[(key, day)] += 1
        dropped = len(seen)
        seen = {k: v for k, v in seen.items() if k in human}
        days = {kd: n for kd, n in days.items() if kd[0] in seen}
        pages = sum(days.values())
        self.stdout.write(f"{dropped - len(seen)} script-less visitors (crawlers) dropped")
        self.stdout.write(f"{lines} lines, {pages} page loads, {bots} bot hits skipped, {len(seen)} devices, {len(days)} device-days")
        if opts["dry_run"]:
            from collections import Counter

            self.stdout.write(str(Counter(v["os"] for v in seen.values()).most_common()))
            self.stdout.write(str(Counter(v["device_class"] for v in seen.values()).most_common()))
            return
        with transaction.atomic():
            existing = dict(VisitorDevice.objects.filter(key__in=list(seen)).values_list("key", "id"))
            VisitorDevice.objects.bulk_create([
                VisitorDevice(key=k, source="log", first_seen=v["first"], last_seen=v["last"],
                              **{f: v[f] for f in ("device_class", "os", "os_version", "browser", "in_app", "brand", "model", "screen", "user_agent", "is_bot")})
                for k, v in seen.items() if k not in existing], batch_size=1000)
            ids = dict(VisitorDevice.objects.filter(key__in=list(seen)).values_list("key", "id"))
            VisitorDay.objects.bulk_create([VisitorDay(device_id=ids[k], day=d, hits=n) for (k, d), n in days.items()], batch_size=2000, ignore_conflicts=True)
            for row in (VisitorDay.objects.filter(device_id__in=ids.values()).values("device_id")
                        .annotate(n=Count("id"), h=Sum("hits"), d0=Min("day"), d1=Max("day"))):
                VisitorDevice.objects.filter(pk=row["device_id"]).update(days=row["n"], hits=row["h"])
        self.stdout.write(self.style.SUCCESS(f"imported: {len(seen) - len(existing)} new devices"))
