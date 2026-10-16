"""
Real, live-verified regression test for the Blog feature -- confirmed
missing entirely from the project before this phase (apps/content was
a 13-line placeholder module with no models, admin, views, or urls at
all).
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client
from django.utils import timezone

from apps.content.infrastructure.models import BlogCategory, BlogPost, BlogPostStatus

pytestmark = pytest.mark.django_db


def _published_post(title: str = "Published Post", category: BlogCategory | None = None) -> BlogPost:
    return BlogPost.objects.create(
        id=uuid.uuid4(), category=category, title=title, slug=f"slug-{uuid.uuid4().hex[:8]}",
        excerpt="Excerpt", body="Full body text", status=BlogPostStatus.PUBLISHED, published_at=timezone.now(),
    )


class TestBlogPostListView:
    def test_only_published_posts_are_listed(self):
        _published_post("Published Post")
        BlogPost.objects.create(id=uuid.uuid4(), title="Draft Post", slug=f"draft-{uuid.uuid4().hex[:8]}", body="Draft body", status=BlogPostStatus.DRAFT)

        client = Client()
        response = client.get("/api/v1/content/posts")
        assert response.status_code == 200
        titles = [p["title"] for p in response.json()["data"]]
        assert "Published Post" in titles
        assert "Draft Post" not in titles

    def test_category_name_is_included_when_present(self):
        category = BlogCategory.objects.create(id=uuid.uuid4(), name="Sport ozuqasi", slug=f"cat-{uuid.uuid4().hex[:8]}")
        _published_post("Categorized Post", category=category)

        client = Client()
        response = client.get("/api/v1/content/posts")
        matching = next(p for p in response.json()["data"] if p["title"] == "Categorized Post")
        assert matching["category"] == "Sport ozuqasi"


class TestBlogPostDetailView:
    def test_published_post_is_reachable_and_increments_view_count(self):
        post = _published_post()
        client = Client()

        response = client.get(f"/api/v1/content/posts/{post.slug}")
        assert response.status_code == 200
        assert response.json()["data"]["body"] == "Full body text"

        post.refresh_from_db()
        assert post.view_count == 1

        client.get(f"/api/v1/content/posts/{post.slug}")
        post.refresh_from_db()
        assert post.view_count == 2

    def test_draft_post_is_not_reachable_by_slug(self):
        draft = BlogPost.objects.create(id=uuid.uuid4(), title="Draft", slug=f"draft-{uuid.uuid4().hex[:8]}", body="Draft body", status=BlogPostStatus.DRAFT)
        client = Client()
        response = client.get(f"/api/v1/content/posts/{draft.slug}")
        assert response.status_code == 404


class TestBlogPostAdminRealUpload:
    def test_real_cover_image_upload_and_auto_publish_timestamp(self):
        import io

        from django.contrib.auth.models import User as AuthUser
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        admin_user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)

        buf = io.BytesIO()
        Image.new("RGB", (800, 500), color="blue").save(buf, format="JPEG")

        response = client.post("/django-admin/content/blogpost/add/", data={
            "title": "Test Admin Post", "slug": "test-admin-post", "excerpt": "", "body": "Body text", "status": "published",
            "cover_image_upload": SimpleUploadedFile("cover.jpg", buf.getvalue(), content_type="image/jpeg"),
        }, follow=True)
        assert response.status_code == 200

        post = BlogPost.objects.filter(slug="test-admin-post").first()
        assert post is not None
        assert post.cover_image_storage_path
        assert post.published_at is not None


class TestBlogTranslations:
    def _translated(self):
        category = BlogCategory.objects.create(id=uuid.uuid4(), name="Qo'llanmalar", slug=f"cat-{uuid.uuid4().hex[:8]}", i18n={"ru": {"name": "Руководства"}})
        post = _published_post("Kreatin qo'llanmasi", category)
        post.i18n = {"ru": {"title": "Гид по креатину", "excerpt": "Коротко", "body": "Текст на русском"}}
        post.save()
        return post

    def test_russian_translation_is_served_with_locale(self):
        post = self._translated()
        card = next(p for p in Client().get("/api/v1/content/posts?locale=ru").json()["data"] if p["id"] == str(post.id))
        assert (card["title"], card["excerpt"], card["category"], card["locale"]) == ("Гид по креатину", "Коротко", "Руководства", "ru")
        detail = Client().get(f"/api/v1/content/posts/{post.slug}", HTTP_ACCEPT_LANGUAGE="ru").json()["data"]
        assert detail["body"] == "Текст на русском"

    def test_missing_translation_falls_back_to_uzbek(self):
        post = self._translated()
        card = next(p for p in Client().get("/api/v1/content/posts?locale=en").json()["data"] if p["id"] == str(post.id))
        assert (card["title"], card["excerpt"], card["category"], card["locale"]) == ("Kreatin qo'llanmasi", "Excerpt", "Qo'llanmalar", "uz")

    def test_admin_form_stores_translations(self, admin_client):
        from apps.content.infrastructure.admin import BlogPostAdminForm

        form = BlogPostAdminForm(data={"title": "Sarlavha", "slug": f"s-{uuid.uuid4().hex[:6]}", "body": "Matn", "status": "draft",
                                       "title_en": "Title", "body_en": "Text", "title_ru": "", "body_ru": ""})
        assert form.is_valid(), form.errors
        post = form.save()
        assert post.i18n == {"en": {"title": "Title", "body": "Text"}}
        assert BlogPostAdminForm(data={"title": "S", "slug": "s-x", "body": "M", "status": "draft", "body_ru": "Текст"}).is_valid() is False
        assert admin_client.get(f"/django-admin/content/blogpost/{post.pk}/change/").status_code == 200
