"""Dashboard → Guruhlar: premium list, permission matrix, members on the form, duplicate."""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client

from apps.platform.infrastructure.group_admin import level_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    user = get_user_model().objects.create_superuser(f"boss{uuid.uuid4().hex[:6]}", "b@example.com", "x")
    c = Client()
    c.force_login(user)
    return c


def test_level_of():
    assert level_of([])[0] == "Ruxsatsiz"
    assert level_of(["view_store"])[0] == "Faqat ko'rish"
    assert level_of(["view_store", "change_store"])[0] == "Tahrirlash"
    assert level_of(["delete_store"])[0].startswith("To'liq")


def test_list_and_matrix_render(admin_client):
    g = Group.objects.create(name="Kassir")
    g.permissions.set(Permission.objects.filter(codename__in=["view_store", "change_store"]))
    html = admin_client.get("/django-admin/auth/group/").content.decode()
    assert "Guruhlar (xodim rollari)" in html and "Kassir" in html and "Tahrirlash" in html
    form = admin_client.get(f"/django-admin/auth/group/{g.pk}/change/").content.decode()
    assert 'class="nzpm"' in form and form.count("checked") >= 2 and "Faqat ko&#x27;rish" in form


def test_save_sets_permissions_and_members(admin_client):
    User = get_user_model()
    worker = User.objects.create_user("kassir1", password="x", is_staff=True)
    perms = list(Permission.objects.filter(codename__in=["view_store", "view_order"] if Permission.objects.filter(codename="view_order").exists() else ["view_store"]))
    r = admin_client.post("/django-admin/auth/group/add/", {"name": "Kassa", "permissions": [p.pk for p in perms], "members": [worker.pk]})
    assert r.status_code == 302, r.content.decode()[:2000]
    g = Group.objects.get(name="Kassa")
    assert set(g.permissions.all()) == set(perms)
    assert list(g.user_set.all()) == [worker]


def test_duplicate_copies_permissions_without_members(admin_client):
    User = get_user_model()
    g = Group.objects.create(name="Sklad")
    g.permissions.set(Permission.objects.filter(codename="view_store"))
    g.user_set.add(User.objects.create_user("w1", password="x", is_staff=True))
    admin_client.post("/django-admin/auth/group/", {"action": "duplicate", "_selected_action": [g.pk]})
    copy = Group.objects.get(name="Sklad (nusxa)")
    assert list(copy.permissions.values_list("codename", flat=True)) == ["view_store"]
    assert copy.user_set.count() == 0


def test_staff_form_uses_the_matrix(admin_client):
    other = get_user_model().objects.create_user("w2", password="x", is_staff=True)
    html = admin_client.get(f"/django-admin/auth/user/{other.pk}/change/").content.decode()
    assert 'class="nzpm" data-name="user_permissions"' in html
