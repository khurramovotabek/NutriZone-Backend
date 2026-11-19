"""Blog: a post published with a future time stays hidden until then; readiness checks."""
import uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.content.infrastructure.admin import readiness
from apps.content.infrastructure.models import BlogPost

pytestmark = pytest.mark.django_db


def _post(**kw):
    return BlogPost.objects.create(id=uuid.uuid4(), title=kw.pop("title", "Post"), slug=f"p-{uuid.uuid4().hex[:6]}", body="x", status="published", **kw)


def test_future_post_is_hidden_until_its_time():
    now = timezone.now()
    live, later, legacy = _post(published_at=now - timedelta(hours=1)), _post(published_at=now + timedelta(days=1)), _post(published_at=None)
    slugs = [p["slug"] for p in Client().get("/api/v1/content/posts").json()["data"]]
    assert live.slug in slugs and legacy.slug in slugs and later.slug not in slugs
    assert Client().get(f"/api/v1/content/posts/{later.slug}").status_code == 404
    assert Client().get(f"/api/v1/content/posts/{live.slug}").status_code == 200


def test_readiness_names_what_to_fix():
    p = _post(title="Qisqa", published_at=timezone.now())
    bad = [label for ok, label in readiness(p) if not ok]
    assert any("Sarlavha" in b for b in bad) and any("300 so'z" in b for b in bad) and any("Muqova" in b for b in bad)
