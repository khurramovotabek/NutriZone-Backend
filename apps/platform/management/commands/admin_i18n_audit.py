"""
Finds dashboard text that is not in the chosen language (apps/platform/infrastructure/admin_i18n.py).

    python manage.py admin_i18n_audit --lang en          # Uzbek phrases left on English pages
    python manage.py admin_i18n_audit --lang ru --top 50

Opens every admin list, add, first-change and custom page as the first superuser (read-only GETs) and prints
the Uzbek-looking phrases with a page where each appears. Add the missing ones to
locale/<lang>/LC_MESSAGES/admin_phrases.po. Names, addresses and other data are expected in the output.
"""
from __future__ import annotations

import collections
import re
from html.parser import HTMLParser

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import NoReverseMatch, get_resolver, reverse

UZBEK = re.compile(r"[a-z][og]['‘’ʻ][a-z]|\b(va|yoki|uchun|bilan|yo'q|barcha|hali|kerak|bo'yicha)\b|\w(lar|larni|larga|ning|dagi|ilgan|moqda|ladi|ingiz)\b", re.I)
SKIP = ("logout/", "delete/", "export/", ".json", "csv/", "xlsx/")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "textarea"):
            self.skip += 1
        for k, v in attrs:
            if k in ("placeholder", "title", "aria-label") and v:
                self.out.append(v.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style", "textarea") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.out.append(re.sub(r"\s+", " ", data.strip()))


class Command(BaseCommand):
    help = "Lists dashboard phrases still in Uzbek on the English or Russian dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--lang", default="en", choices=["en", "ru"])
        parser.add_argument("--top", type=int, default=200)

    def _urls(self) -> list[str]:
        urls = ["/django-admin/"]
        for model in admin.site._registry:
            o = model._meta
            for name in ("changelist", "add"):
                try:
                    urls.append(reverse(f"admin:{o.app_label}_{o.model_name}_{name}"))
                except NoReverseMatch:
                    pass
            obj = model._default_manager.order_by("-pk").first() if model._default_manager.exists() else None
            if obj is not None:
                try:
                    urls.append(reverse(f"admin:{o.app_label}_{o.model_name}_change", args=[obj.pk]))
                except NoReverseMatch:
                    pass

        def walk(patterns, prefix=""):
            for p in patterns:
                if hasattr(p, "url_patterns"):
                    walk(p.url_patterns, prefix + str(p.pattern))
                else:
                    s = prefix + str(p.pattern)
                    if s.startswith("django-admin/") and "<" not in s and "(?P" not in s and not s.endswith(SKIP):
                        urls.append("/" + s.replace("^", "").replace("$", ""))

        walk(get_resolver().url_patterns)
        return list(dict.fromkeys(urls))

    def handle(self, *args, lang, top, **options):
        user = get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
        if user is None:
            self.stderr.write("No superuser to browse the dashboard as.")
            return
        client = Client(HTTP_X_FORWARDED_PROTO="https")
        client.force_login(user)
        client.cookies["django_language"] = lang
        found: collections.Counter[str] = collections.Counter()
        where: dict[str, str] = {}
        pages = 0
        for url in self._urls():
            try:
                resp = client.get(url, HTTP_ACCEPT_LANGUAGE=lang, secure=True, follow=True)
            except Exception:  # noqa: BLE001 -- one broken page must not stop the audit
                continue
            if resp.status_code != 200 or "html" not in resp.get("Content-Type", ""):
                continue
            pages += 1
            parser = _Text()
            parser.feed(resp.content.decode("utf-8", "replace"))
            for text in parser.out:
                if 2 < len(text) < 300 and UZBEK.search(text):
                    found[text] += 1
                    where.setdefault(text, url)
        self.stdout.write(f"{pages} pages, {len(found)} Uzbek-looking phrases on the '{lang}' dashboard")
        for text, n in found.most_common(top):
            self.stdout.write(f"{n:>4} | {text[:120]} | {where[text]}")
