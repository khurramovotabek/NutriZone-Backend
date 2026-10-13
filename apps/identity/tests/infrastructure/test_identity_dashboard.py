"""
Dashboard → Identity: the premium lists render, the user card's panels and actions (block → sessions closed, revoke a
session, assign / remove a role) go through the services, the role editor saves its permission set, a role assignment
is added through AssignRole, the overview matrix, and the small User-Agent / permission-label helpers.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth.models import User as AuthUser
from django.test import Client
from django.utils import timezone

from apps.identity.infrastructure import admin_ui as ui
from apps.identity.infrastructure import models as m

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss():
    client = Client()
    client.force_login(AuthUser.objects.create_superuser(username=f"boss_{uuid.uuid4().hex[:6]}", password="test-pass-12345"))
    return client


def _user(name="Dilnoza Rahimova", status="active"):
    return m.User.objects.create(phone_number=f"+99893{uuid.uuid4().int % 10000000:07d}", full_name=name, status=status)


def _session(user, revoked=False, days_ago=0, ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"):
    now = timezone.now() - timedelta(days=days_ago)
    return m.UserSession.objects.create(user=user, device_type="web", refresh_token_hash=uuid.uuid4().hex, ip_address="188.113.1.2", user_agent=ua,
                                        last_activity=now, expires_at=timezone.now() + timedelta(days=20), revoked_at=timezone.now() if revoked else None)


def _role(code="store_manager", perms=()):
    role = m.Role.objects.create(code=f"{code}_{uuid.uuid4().hex[:4]}", name=code.replace("_", " ").title())
    for p in perms:
        m.RolePermission.objects.create(role=role, permission=m.Permission.objects.get_or_create(code=p, defaults={"description": ""})[0])
    return role


class TestLists:
    @pytest.mark.parametrize("url", ["/django-admin/identity/user/", "/django-admin/identity/usersession/", "/django-admin/identity/device/",
                                     "/django-admin/identity/role/", "/django-admin/identity/permission/", "/django-admin/identity/userrole/",
                                     "/django-admin/identity/userrole/add/", "/django-admin/roles-overview/"])
    def test_every_page_renders(self, boss, url):
        u = _user()
        _session(u)
        _role(perms=["cart.item.create"])
        assert boss.get(url).status_code == 200

    def test_users_list_shows_status_tabs_and_rows(self, boss):
        _user("Bekzod Tursunov", status="blocked")
        html = boss.get("/django-admin/identity/user/?status__exact=blocked").content.decode()
        assert "Bekzod Tursunov" in html and "Bloklangan" in html and "nzi-tr" in html

    def test_sessions_list_reads_the_browser_and_never_the_token(self, boss):
        s = _session(_user())
        html = boss.get("/django-admin/identity/usersession/?state=active").content.decode()
        assert "Chrome · Windows" in html
        assert s.refresh_token_hash not in html

    def test_session_and_device_pages_cannot_add(self, boss):
        assert boss.get("/django-admin/identity/usersession/add/").status_code == 403
        assert boss.get("/django-admin/identity/device/add/").status_code == 403


class TestUserCard:
    def test_card_shows_roles_sessions_and_orders_panels(self, boss):
        u = _user()
        _session(u)
        html = boss.get(f"/django-admin/identity/user/{u.pk}/change/").content.decode()
        assert "Xavfsizlik: sessiyalar va qurilmalar" in html and "Chrome · Windows" in html and "Rol biriktirish" in html

    def test_block_closes_every_session(self, boss):
        u = _user()
        a, b = _session(u), _session(u)
        r = boss.post(f"/django-admin/identity/user/{u.pk}/nz/status/blocked/")
        assert r.status_code == 302
        u.refresh_from_db()
        assert u.status == "blocked"
        assert m.UserSession.objects.filter(pk__in=[a.pk, b.pk], revoked_at__isnull=True).count() == 0

    def test_revoke_one_session(self, boss):
        u = _user()
        a, b = _session(u), _session(u)
        boss.post(f"/django-admin/identity/user/{u.pk}/nz/session/{a.pk}/revoke/")
        a.refresh_from_db(), b.refresh_from_db()
        assert a.revoked_at is not None and b.revoked_at is None
        assert m.RevokedTokenRecord.objects.filter(session_id=a.pk).exists()

    def test_actions_need_post(self, boss):
        u = _user()
        assert boss.get(f"/django-admin/identity/user/{u.pk}/nz/status/blocked/").status_code == 403

    def test_assign_and_remove_a_role_from_the_card(self, boss):
        u, role = _user(), _role()
        boss.post(f"/django-admin/identity/user/{u.pk}/nz/role/add/", {"nzi_role": role.code, "nzi_store": ""})
        ur = m.UserRole.objects.get(user=u, role=role)
        boss.post(f"/django-admin/identity/user/{u.pk}/nz/role/{ur.pk}/remove/")
        assert not m.UserRole.objects.filter(pk=ur.pk).exists()


class TestRoles:
    def test_role_editor_saves_exactly_the_ticked_permissions(self, boss):
        role = _role(perms=["cart.item.create", "cart.item.view"])
        m.Permission.objects.get_or_create(code="reviews.review.create", defaults={"description": ""})
        r = boss.post(f"/django-admin/identity/role/{role.pk}/change/", {"name": role.name, "code": role.code, "permissions": ["cart.item.view", "reviews.review.create"]})
        assert r.status_code == 302
        assert set(m.RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)) == {"cart.item.view", "reviews.review.create"}

    def test_a_held_or_system_role_cannot_be_deleted(self, boss):
        role = _role()
        m.UserRole.objects.create(user=_user(), role=role)
        assert boss.get(f"/django-admin/identity/role/{role.pk}/delete/").status_code == 403

    def test_assignment_page_goes_through_assign_role(self, boss):
        u, role = _user(), _role()
        r = boss.post("/django-admin/identity/userrole/add/", {"user": u.pk, "role": role.pk, "store": ""})
        assert r.status_code == 302
        assert m.UserRole.objects.filter(user=u, role=role, store_id__isnull=True).count() == 1
        boss.post("/django-admin/identity/userrole/add/", {"user": u.pk, "role": role.pk, "store": ""})  # a duplicate is refused, not doubled
        assert m.UserRole.objects.filter(user=u, role=role).count() == 1

    def test_overview_matrix_marks_what_each_role_grants(self, boss):
        _role(perms=["chat.message.send"])
        html = boss.get("/django-admin/roles-overview/").content.decode()
        assert "Xabar — yuborish" in html and "nzi-mx-yes" in html


class TestHelpers:
    @pytest.mark.parametrize("ua,label", [
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", "Safari · iOS"),
        ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36", "Chrome · Android"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36 Edg/129.0", "Edge · Windows"),
        ("node", "node (server)"), ("", "Noma'lum"),
    ])
    def test_parse_ua(self, ua, label):
        assert ui.parse_ua(ua)["label"] == label

    def test_permission_label(self):
        assert ui.permission_label("reviews.review.create") == "Sharh — qo'shish"
        assert ui.permission_label("x.y.z", "Custom text") == "Custom text"

    def test_session_state(self):
        u = _user()
        assert ui.session_state(_session(u)) == "active"
        assert ui.session_state(_session(u, days_ago=10)) == "idle"
        assert ui.session_state(_session(u, revoked=True)) == "revoked"
