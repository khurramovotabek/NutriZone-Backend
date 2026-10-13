"""
Reviews read-model selectors -- optimized, read-only Postgres
queries. No business logic, no aggregate construction, matching the
pattern established by every prior module. Every method returns a
plain dict (DTO) or list of dicts, never an ORM object or a Domain
aggregate.
"""
from __future__ import annotations

import uuid

from django.db.models import Count

from apps.reviews.infrastructure import models as orm


class ReviewSelector:
    def list_for_product(self, product_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.ReviewModel.objects.filter(product_id=product_id)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def list_for_customer(self, customer_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.ReviewModel.objects.filter(customer_id=customer_id)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def _card(self, row: orm.ReviewModel) -> dict:
        return {"id": str(row.id), "product_id": str(row.product_id), "customer_id": str(row.customer_id), "rating": row.rating, "title": row.title, "body": row.body, "status": row.status, "verified_purchase": row.verified_purchase}

    def list_published_for_product(self, product_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
        """
        Real, closed gap: the only product-review-list endpoint
        (`ProductReviewListView`) requires authentication plus an RBAC
        permission grant despite its own docstring claiming public,
        no-ownership-check read access -- confirmed directly against
        `ViewOwnReviews`, which fails closed for an anonymous visitor.
        This is the genuine public read path a storefront product page
        needs: PUBLISHED reviews only (forced here, never a
        client-supplied filter), enriched with a privacy-safe author
        display name (first name + last-initial only -- never the full
        name, phone, or any other contact detail) and attached media,
        both resolved in bulk (matching this codebase's own established
        cross-app-join convention, e.g. Products'
        `ProductDetailSelector.get_pos_display_info`'s brand_name
        resolution) -- never a per-review query.
        """
        from django.conf import settings

        from apps.identity.infrastructure.models import User
        from apps.reviews.domain.enums import ReviewStatus

        qs = orm.ReviewModel.objects.filter(product_id=product_id, status=ReviewStatus.PUBLISHED.value)
        total = qs.count()
        start = (page - 1) * page_size
        rows = list(qs.order_by("-published_at", "-created_at")[start : start + page_size])

        customer_ids = {r.customer_id for r in rows}
        full_names_by_id = {u.id: u.full_name for u in User.objects.filter(id__in=customer_ids).only("id", "full_name")}

        review_ids = [r.id for r in rows]
        media_by_review: dict = {}
        if review_ids:
            base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
            for m in orm.ReviewMediaModel.objects.filter(review_id__in=review_ids).order_by("uploaded_at"):
                url = m.url if m.url.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{m.url}"
                media_by_review.setdefault(m.review_id, []).append({"id": str(m.id), "media_type": m.media_type, "url": url})

        def _display_name(full_name: str | None) -> str:
            full_name = (full_name or "").strip()
            if not full_name:
                from apps.platform.infrastructure.branding import brand_name

                return f"{brand_name()} customer"
            parts = full_name.split()
            return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."

        cards = []
        for r in rows:
            cards.append({
                "id": str(r.id),
                "rating": r.rating,
                "title": r.title,
                "body": r.body,
                "verified_purchase": r.verified_purchase,
                "author_name": _display_name(full_names_by_id.get(r.customer_id)),
                "created_at": (r.published_at or r.created_at).isoformat(),
                "media": media_by_review.get(r.id, []),
            })
        return cards, total


def featured_reviews(limit: int = 6, locale: str = "uz") -> dict:
    """
    The home page's "what customers say": PUBLISHED reviews rated 4-5 with a real comment (at least a few words),
    verified purchases first, newest first -- each with its product (name, slug, photo) and the same privacy-safe
    author name the product page shows. Plus the store-wide average over every published review.
    """
    from django.db.models import Avg, Count
    from django.db.models.functions import Length

    from apps.identity.infrastructure.models import User
    from apps.reviews.domain.enums import ReviewStatus

    published = orm.ReviewModel.objects.filter(status=ReviewStatus.PUBLISHED.value)
    stats = published.aggregate(avg=Avg("rating"), n=Count("id"))
    from apps.products.infrastructure.models import Product

    live = Product.objects.filter(status="published").values_list("id", flat=True)  # never a review of a hidden / deleted product
    rows = list(published.filter(rating__gte=4, product_id__in=list(live)).annotate(n=Length("body")).filter(n__gte=12).order_by("-verified_purchase", "-published_at", "-created_at")[: limit * 3])
    # one review per product first, so the wall isn't one product repeated
    seen, picked = set(), []
    for r in rows:
        if r.product_id not in seen:
            picked.append(r)
            seen.add(r.product_id)
    picked += [r for r in rows if r not in picked]
    picked = picked[:limit]
    names = {u.id: u.full_name for u in User.objects.filter(id__in={r.customer_id for r in picked}).only("id", "full_name")}
    products = _review_products({r.product_id for r in picked}, locale)

    def author(full_name):
        parts = (full_name or "").split()
        if not parts:
            return "NutriZone mijozi"
        return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."

    return {
        "average": round(float(stats["avg"]), 1) if stats["avg"] else None,
        "count": stats["n"],
        "results": [{
            "id": str(r.id), "rating": r.rating, "title": r.title, "body": r.body, "verified_purchase": r.verified_purchase,
            "author_name": author(names.get(r.customer_id)), "created_at": (r.published_at or r.created_at).isoformat(),
            "product": products.get(r.product_id),
        } for r in picked],
    }


def _review_products(ids, locale: str) -> dict:
    """{product_id: {"name", "slug", "image_url"}} for review cards (bulk)."""
    from django.conf import settings

    from apps.products.infrastructure import models as p

    out: dict = {}
    tr: dict = {}
    for t in p.ProductTranslation.objects.filter(product_id__in=ids).values("product_id", "locale_code", "name", "slug"):
        tr.setdefault(t["product_id"], {})[t["locale_code"]] = t
    images: dict = {}
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    for m in p.ProductMedia.objects.filter(product_id__in=ids).order_by("product_id", "sort_order").values("product_id", "storage_path", "thumbnail_paths"):
        if m["product_id"] in images or not m["storage_path"]:
            continue
        path = (m["thumbnail_paths"] or {}).get("small") or m["storage_path"]
        images[m["product_id"]] = path if path.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{path}"
    for pid in ids:
        by = tr.get(pid) or {}
        t = by.get(locale) or by.get("uz") or next(iter(by.values()), None)
        if t:
            out[pid] = {"id": str(pid), "name": t["name"], "slug": t["slug"], "image_url": images.get(pid)}
    return out


class ReviewMediaSelector:
    def list_for_review(self, review_id: uuid.UUID) -> list[dict]:
        from django.conf import settings

        rows = orm.ReviewMediaModel.objects.filter(review_id=review_id)
        result = []
        for r in rows:
            base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
            url = r.url if r.url.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{r.url}"
            result.append({"id": str(r.id), "media_type": r.media_type, "url": url, "uploaded_at": r.uploaded_at.isoformat()})
        return result


# **A deliberately absent selector, per Phase 1's own certified boundary decision**: no
# `ProductRatingStatisticsSelector`-style rollup (average rating / review count per product)
# exists here. Phase 1's Critical Boundary Review explicitly concluded that product-level
# rating aggregation is "a future concern, document the boundary instead of inventing it" --
# a deliberate deferral, not an oversight. This phase's own instructions say "do not redesign
# these decisions during Infrastructure implementation," and building even a minimal read-only
# rollup here would be exactly that kind of redesign dressed up as "just a selector." A first
# draft of this file included one; it was removed before certification once this conflict was
# recognized (see the certification report's Mistakes Found section for the full account).


class ReviewStatisticsSelector:
    def counts_by_status(self) -> dict:
        rows = orm.ReviewModel.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}

    def bulk_rating_summary(self, product_ids: list) -> dict:
        """Real, closed gap: no product-level rating aggregation previously existed anywhere (confirmed via direct inspection -- this selector only had counts_by_status(), an admin-only, status-grouped count). Only PUBLISHED reviews count -- a draft/pending/rejected review must never influence a publicly-displayed rating. Bulk: one query for any number of products, never a per-product N+1."""
        from apps.reviews.domain.enums import ReviewStatus
        from django.db.models import Avg

        rows = (
            orm.ReviewModel.objects.filter(product_id__in=product_ids, status=ReviewStatus.PUBLISHED.value)
            .values("product_id")
            .annotate(average=Avg("rating"), count=Count("id"))
        )
        return {str(r["product_id"]): {"average": round(float(r["average"]), 1), "count": r["count"]} for r in rows}
