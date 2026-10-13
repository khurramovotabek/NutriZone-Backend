"""
Search analytics: one row per normalized search term (what shoppers asked the catalog for).

Feeds the storefront's "popular searches" and the dashboard's Qidiruv tahlili page -- above all the terms that
found nothing, which are demand the store does not yet meet. Rows are upserted with F() increments (one cheap
write per submitted search; typing-ahead previews are not recorded).
"""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class SearchTerm(models.Model):
    term = models.CharField(max_length=120, unique=True, verbose_name=_("Qidiruv"))  # smart_search.normalize()d
    display = models.CharField(max_length=120, verbose_name=_("Ko'rinishi"))  # the latest spelling a shopper typed
    searches = models.PositiveIntegerField(default=0, verbose_name=_("Qidirilgan"))
    zero_results = models.PositiveIntegerField(default=0, verbose_name=_("Natijasiz"))
    last_results = models.PositiveIntegerField(default=0, verbose_name=_("Oxirgi natija"))
    last_locale = models.CharField(max_length=8, blank=True, default="")
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(db_index=True)

    class Meta:
        app_label = "search"
        db_table = "search_terms"
        verbose_name = _("Qidiruv so'rovi")
        verbose_name_plural = _("Qidiruv tahlili")
        indexes = [models.Index(fields=["-searches"], name="search_terms_searches_idx")]

    def __str__(self) -> str:  # pragma: no cover
        return self.display
