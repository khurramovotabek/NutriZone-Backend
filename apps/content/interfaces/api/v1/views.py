"""
apps/content/interfaces/api/v1/views.py

Real implementation: public (AllowAny), read-only Blog endpoints for
the storefront's homepage Blog section and a full article page.
"""
from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.content.infrastructure.models import BlogCategory, BlogPost, BlogPostStatus
from common.exceptions import ResourceNotFound
from common.responses import paginated_response, success_response


def _image_url(storage_path: str, thumbnail_paths: dict) -> str | None:
    if not storage_path:
        return None
    path = thumbnail_paths.get("large") or storage_path
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return path if path.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{path}"


def _post_card(post: BlogPost) -> dict:
    return {
        "id": str(post.id),
        "title": post.title,
        "slug": post.slug,
        "excerpt": post.excerpt or auto_excerpt(post.body),
        "category": post.category.name if post.category else None,
        "cover_image_url": _image_url(post.cover_image_storage_path, post.cover_image_thumbnail_paths),
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "view_count": post.view_count,
        "reading_minutes": reading_minutes(post.body),
    }


def auto_excerpt(text: str | None, limit: int = 170) -> str:
    """A post with no written excerpt gets the start of its text (tags/markdown marks stripped, cut at a word)."""
    import re

    plain = re.sub(r"\s+", " ", re.sub(r"[#*_>`]|<[^>]+>|!?\[([^\]]*)\]\([^)]*\)", r"\1", text or "")).strip()
    if len(plain) <= limit:
        return plain
    return plain[:limit].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def reading_minutes(text: str | None) -> int:
    """Estimated reading time (~200 words a minute, rounded up, HTML tags ignored), at least 1."""
    import re

    import math

    words = len(re.sub(r"<[^>]+>", " ", text or "").split())
    return max(1, math.ceil(words / 200))


class BlogCategoryListView(APIView):
    """`GET /content/categories` -- real, public (AllowAny), read-only. Only categories with at least one real PUBLISHED post (an empty category is never worth offering as a filter tab with zero results behind it), sorted the same way BlogCategoryAdmin's own `sort_order` field is meant to be used."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Content"], summary="List blog categories with published posts", responses={200: OpenApiResponse(description="Blog categories")})
    def get(self, request):
        categories = (
            BlogCategory.objects.filter(posts__status=BlogPostStatus.PUBLISHED).distinct().order_by("sort_order", "name")
        )
        return success_response(data=[{"id": str(c.id), "name": c.name, "slug": c.slug} for c in categories])


class BlogPostListView(APIView):
    """`GET /content/posts` -- real, public (AllowAny), read-only. Only PUBLISHED posts, newest first, for the storefront's homepage Blog section and the full /blog listing. Optional `?category=<slug>` narrows to one real BlogCategory (matches BlogCategoryListView's own slug), never a free-text/name match that could silently return the wrong category on a name collision."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Content"], summary="List published blog posts", responses={200: OpenApiResponse(description="Published blog posts")})
    def get(self, request):
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 10)), 50)
        qs = BlogPost.objects.filter(status=BlogPostStatus.PUBLISHED).select_related("category").order_by("-published_at")
        category_slug = request.query_params.get("category")
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        total = qs.count()
        start = (page - 1) * page_size
        rows = list(qs[start : start + page_size])
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return paginated_response(data=[_post_card(p) for p in rows], pagination={"strategy": "page", "page": page, "page_size": page_size, "total_pages": total_pages, "total_count": total})


class BlogPostDetailView(APIView):
    """`GET /content/posts/<slug>` -- real, public (AllowAny). Increments view_count on each real view (best-effort, not exactly-once -- matches this build's own established convention for non-financial, low-stakes counters)."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Content"], summary="Get a published blog post by slug", responses={200: OpenApiResponse(description="Blog post detail"), 404: OpenApiResponse(description="Not found")})
    def get(self, request, slug: str):
        post = BlogPost.objects.filter(slug=slug, status=BlogPostStatus.PUBLISHED).select_related("category").first()
        if post is None:
            raise ResourceNotFound("Blog post not found.")
        BlogPost.objects.filter(id=post.id).update(view_count=post.view_count + 1)
        return success_response(data={**_post_card(post), "body": post.body})
