"""'Find this product for me': customer API, validation, staff answer → notification, dashboard page."""
import io
import uuid
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.support.infrastructure import product_requests as svc
from apps.support.infrastructure.models import ProductRequest

pytestmark = pytest.mark.django_db


def _user(phone="+998901112233"):
    from apps.identity.infrastructure.models import User

    return User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Aziz", status="active")


def _client(monkeypatch, user):
    fake = SimpleNamespace(id=user.id, is_authenticated=True, store_ids=set(), permissions=frozenset())
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake, None))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake")
    return client


def _png(name="p.png"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_requires_login():
    assert APIClient().get("/api/v1/product-requests").status_code in (401, 403)


def test_create_with_photo_and_link_then_list(monkeypatch, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    user = _user()
    client = _client(monkeypatch, user)
    res = client.post("/api/v1/product-requests", {"product_name": "Mutant Mass 6.8 kg", "brand": "Mutant", "description": "Shokoladli",
                                                    "url": "iherb.com/pr/mutant", "quantity": "2", "image": _png()}, format="multipart")
    assert res.status_code == 201, res.content
    data = res.json()["data"]
    assert data["number"] == "PR-000001" and data["status"] == "new" and data["quantity"] == 2
    assert data["url"] == "https://iherb.com/pr/mutant" and data["image_url"].startswith("/media/product-requests/")
    listed = client.get("/api/v1/product-requests").json()["data"]
    assert [r["number"] for r in listed] == ["PR-000001"] and listed[0]["can_cancel"] is True


def test_validation(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client = _client(monkeypatch, _user())
    assert client.post("/api/v1/product-requests", {"product_name": " "}, format="multipart").json()["error"]["code"] == "NAME_REQUIRED"
    assert client.post("/api/v1/product-requests", {"product_name": "X1", "url": "not a url"}, format="multipart").json()["error"]["code"] == "URL_INVALID"
    fake = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    assert client.post("/api/v1/product-requests", {"product_name": "X1", "image": fake}, format="multipart").json()["error"]["code"] == "IMAGE_INVALID"
    pdf = SimpleUploadedFile("x.pdf", b"%PDF", content_type="application/pdf")
    assert client.post("/api/v1/product-requests", {"product_name": "X1", "image": pdf}, format="multipart").json()["error"]["code"] == "IMAGE_TYPE"
    assert ProductRequest.objects.count() == 0


def test_cancel_only_own_open_request(monkeypatch):
    owner, other = _user(), _user("+998909998877")
    row = svc.create(owner.id, product_name="BCAA")
    assert _client(monkeypatch, other).post(f"/api/v1/product-requests/{row.id}/cancel").status_code == 404
    res = _client(monkeypatch, owner).post(f"/api/v1/product-requests/{row.id}/cancel")
    assert res.status_code == 200 and res.json()["data"]["status"] == "cancelled"
    assert _client(monkeypatch, owner).post(f"/api/v1/product-requests/{row.id}/cancel").status_code == 409


def test_open_requests_are_capped():
    user = _user()
    for i in range(svc.MAX_OPEN_PER_CUSTOMER):
        svc.create(user.id, product_name=f"P{i}")
    with pytest.raises(svc.ProductRequestError) as exc:
        svc.create(user.id, product_name="One more")
    assert exc.value.code == "TOO_MANY_OPEN"


def test_staff_answer_notifies_customer_once(django_capture_on_commit_callbacks):
    from apps.notifications.infrastructure.models import NotificationModel

    user = _user()
    row = svc.create(user.id, product_name="Kreatin Kre-Alkalyn")
    row.status, row.staff_reply = "found", "5 kunda keladi"
    row.save()
    with django_capture_on_commit_callbacks(execute=True):
        svc.answer(row, previous_status="new", previous_reply="", staff="Operator")
    with django_capture_on_commit_callbacks(execute=True):
        svc.answer(row, previous_status="new", previous_reply="", staff="Operator")  # same answer again: deduped
    rows = NotificationModel.objects.filter(recipient_id=user.id, kind="product_request_found")
    assert rows.count() == 1 and "5 kunda keladi" in rows.first().i18n["uz"]["body"]
    row.refresh_from_db()
    assert row.handled_by == "Operator" and row.answered_at is not None


def test_dashboard_pages_render(admin_client):
    user = _user()
    row = svc.create(user.id, product_name="Omega 3", url="https://example.com/o3")
    assert admin_client.get("/django-admin/support/productrequest/").status_code == 200
    page = admin_client.get(f"/django-admin/support/productrequest/{row.pk}/change/")
    assert page.status_code == 200 and "Omega 3" in page.content.decode()
    assert admin_client.get("/django-admin/support/productrequest/add/").status_code == 403
