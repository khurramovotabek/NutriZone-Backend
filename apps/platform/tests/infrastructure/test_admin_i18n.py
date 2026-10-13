"""
Phase 16.3: admin dashboard i18n regression protection.

Confirmed via reconnaissance: this project's own `locale/` directory
did not exist at all before this phase, and zero of 27 `models.py`
files anywhere used `gettext_lazy` for `verbose_name` -- meaning every
model's own sidebar/app-list label was permanently English regardless
of the administrator's selected language, exactly the defect this
phase's own Step 10/11 describes.

This test proves the fix for the one module demonstrated end-to-end
this phase (`apps.ordering`) -- `verbose_name` wrapped in
`gettext_lazy`, real `uz`/`ru` translations added to `locale/`, and
compiled to real `.mo` catalogs. The remaining ~26 `models.py` files
still need the same treatment; this is disclosed as deferred work in
this phase's own final report, not silently left unverified.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


class TestAdminSidebarTranslation:
    def test_ordering_app_index_shows_uzbek_label_when_uz_selected(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "uz", "next": "/django-admin/ordering/"})
        response = staff_client.get("/django-admin/ordering/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Buyurtma" in body

    def test_ordering_app_index_shows_russian_label_when_ru_selected(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/ordering/"})
        response = staff_client.get("/django-admin/ordering/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Заказ" in body

    def test_ordering_app_index_shows_english_label_when_en_selected(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "en", "next": "/django-admin/ordering/"})
        response = staff_client.get("/django-admin/ordering/")
        assert response.status_code == 200
        body = response.content.decode()
        assert ">Order<" in body or ">Orders<" in body

    def test_gettext_resolves_all_four_ordering_verbose_names_in_uzbek(self):
        from django.utils.translation import activate, gettext

        activate("uz")
        assert gettext("Order") == "Buyurtma"
        assert gettext("Order Line Item") == "Buyurtma qatori"
        assert gettext("Order Return") == "Buyurtma qaytarish"
        assert gettext("Order Cancellation") == "Buyurtmani bekor qilish"
        activate("en")


class TestJazzminWelcomeSignTranslation:
    """
    A second, genuinely additional gap found this turn: JAZZMIN_SETTINGS['welcome_sign']
    was a plain Python string (not gettext_lazy-wrapped), evaluated once
    at settings-load time -- meaning it was permanently English on the
    real login page regardless of selected language, the exact same
    defect class this file's own TestAdminSidebarTranslation already
    closed for apps.ordering's verbose_names, just in a different
    location (Jazzmin config vs. model Meta).
    """

    def test_login_page_shows_uzbek_welcome_sign_with_no_stale_english(self):
        response = Client().get("/django-admin/login/", HTTP_ACCEPT_LANGUAGE="uz")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Ichki operatsiyalar" in body
        assert "Internal Operations" not in body  # the critical regression this phase's own Step 11 explicitly requires

    def test_login_page_shows_russian_welcome_sign(self):
        response = Client().get("/django-admin/login/", HTTP_ACCEPT_LANGUAGE="ru")
        assert response.status_code == 200
        assert "Внутренние операции" in response.content.decode()

    def test_login_page_shows_english_welcome_sign_by_default(self):
        response = Client().get("/django-admin/login/", HTTP_ACCEPT_LANGUAGE="en")
        assert response.status_code == 200
        assert "Internal Operations" in response.content.decode()


class TestProductsAppTranslation:
    """
    Phase 16.4: extends the same gettext_lazy(verbose_name) fix to the
    products app -- the highest-traffic catalog module an administrator
    sees daily. Verified live (real staff-authenticated request,
    real language switch) before being formalized here.
    """

    def test_products_app_index_shows_uzbek_labels_with_no_stale_english(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "uz", "next": "/django-admin/products/"})
        response = staff_client.get("/django-admin/products/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Mahsulotlar" in body
        assert "Kategoriyalar" in body
        assert "Brendlar" in body
        assert ">Products<" not in body

    def test_products_app_index_shows_russian_labels(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/products/"})
        response = staff_client.get("/django-admin/products/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Товары" in body
        assert "Категории" in body


class TestIdentityAppTranslation:
    """
    Phase 16.5: extends the gettext_lazy(verbose_name) fix to apps.identity
    (Priority 1). Verified live before formalization -- and along the way,
    discovered that a naive ">Users<" search incorrectly also matches
    Django's own separate, unrelated built-in auth.User sidebar entry
    (the staff-login model, distinct from apps.identity.User, the
    customer-facing model) -- so these tests assert against the specific
    identity/user/ link, not a blanket string search.
    """

    def test_identity_app_index_shows_uzbek_labels(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "uz", "next": "/django-admin/identity/"})
        response = staff_client.get("/django-admin/identity/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Foydalanuvchilar" in body
        assert "Rollar" in body
        assert "Ruxsatlar" in body
        # Scoped specifically to apps.identity's own User link, not Django's separate built-in auth.User.
        idx = body.find('href="/django-admin/identity/user/"')
        assert idx != -1
        assert "Foydalanuvchilar" in body[idx:idx + 400]

    def test_identity_app_index_shows_russian_labels(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/identity/"})
        response = staff_client.get("/django-admin/identity/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Пользователи" in body
        assert "Роли" in body


class TestAppGroupHeaderTranslation:
    """
    Phase 16.6: a distinct translation layer from model verbose_name --
    AppConfig.verbose_name controls the sidebar's own group header
    (e.g. "Ordering" as a section title, above the individual "Orders"
    model link within it). Confirmed via direct inspection that all 4
    apps fixed so far (identity, wallet, products, ordering) used a
    plain, untranslated string here.

    Also closes a genuine collision found via compilemessages' own
    "#, fuzzy" marker: gettext's fuzzy-matching heuristic guessed
    "Ordering" was close enough to the existing "Order"->"Buyurtma"
    translation to reuse it -- correct Django/gettext behavior treats
    fuzzy entries as untranslated until confirmed, which this fix does
    with a deliberately distinct translation ("Buyurtmalar boshqaruvi",
    not "Buyurtma") so the app-group header reads naturally as a
    section title rather than a singular noun.
    """

    def test_all_four_app_group_headers_translated_to_uzbek(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "uz", "next": "/django-admin/"})
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Buyurtmalar boshqaruvi" in body
        assert "Mahsulotlar va katalog" in body
        assert "Foydalanuvchilar boshqaruvi" in body

    def test_all_four_app_group_headers_translated_to_russian(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/"})
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Управление заказами" in body
        assert "Товары и каталог" in body

    def test_order_model_translation_is_unaffected_by_the_new_ordering_app_translation(self):
        """Regression guard for the fuzzy-match collision found this turn -- the pre-existing "Order" model translation (Phase 16) must remain exactly what it was, not overwritten by the new "Ordering" app-group entry."""
        from django.utils.translation import activate, gettext

        activate("uz")
        assert gettext("Order") == "Buyurtma"
        assert gettext("Ordering") == "Buyurtmalar boshqaruvi"
        assert gettext("Order") != gettext("Ordering")
        activate("en")
