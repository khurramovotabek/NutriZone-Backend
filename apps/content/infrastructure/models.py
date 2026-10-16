"""
apps/content/infrastructure/models.py

Real implementation: BlogCategory/BlogPost for the storefront's
homepage Blog section, confirmed missing entirely from the project
before this phase (this module was a 13-line placeholder with no
models at all).

Deliberately simple, single-language (Uzbek) fields rather than a
Category/Product-style i18n translation table: a blog post is
authored content, not a catalog entity that needs the same name in
every locale simultaneously -- matching this build's own established
convention of choosing the simplest correct model for low-business-
rule, CRUD-heavy content (see Wishlist/Banner).
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import AllObjectsManager, BaseModel


class BlogCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    i18n = models.JSONField(default=dict, blank=True)  # {"ru": {"name": ...}, "en": {...}}; Uzbek lives in `name`

    objects = AllObjectsManager()

    def localized_name(self, locale: str) -> str:
        return ((self.i18n or {}).get(locale) or {}).get("name") or self.name

    class Meta:
        db_table = "content_blog_categories"
        verbose_name = _("Blog Category")
        verbose_name_plural = _("Blog Categories")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class BlogPostStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")


class BlogPost(BaseModel):
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    excerpt = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField()
    # Media Asset architecture removed per explicit product decision --
    # direct file storage fields (same pattern as Brand/Category/Banner).
    cover_image_storage_path = models.CharField(max_length=500, blank=True, default="")
    cover_image_thumbnail_paths = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=BlogPostStatus.choices, default=BlogPostStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    view_count = models.PositiveIntegerField(default=0)
    # Russian / English versions: {"ru": {"title", "excerpt", "body"}, "en": {...}}. Uzbek is the base fields above;
    # a missing translation (or a missing field of one) falls back to Uzbek.
    i18n = models.JSONField(default=dict, blank=True)

    objects = AllObjectsManager()

    def localized(self, field: str, locale: str) -> str:
        return ((self.i18n or {}).get(locale) or {}).get(field) or getattr(self, field)

    def translated_locales(self) -> list[str]:
        return ["uz"] + [code for code in ("ru", "en") if ((self.i18n or {}).get(code) or {}).get("title")]

    class Meta:
        db_table = "content_blog_posts"
        verbose_name = _("Blog Post")
        verbose_name_plural = _("Blog Posts")
        ordering = ["-published_at"]
        indexes = [models.Index(fields=["status", "published_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.title
