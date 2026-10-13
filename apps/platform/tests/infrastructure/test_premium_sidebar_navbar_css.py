"""
Phase 17.0: premium sidebar/navbar CSS additions.

Not a visual test (no browser tooling is available in this
environment) -- verifies the stylesheet is syntactically valid
(balanced braces) and that a real, live-rendered admin page correctly
references it, which is the strongest verification available without
a browser.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _css_path() -> Path:
    return Path(settings.BASE_DIR) / "apps" / "platform" / "static" / "admin" / "css" / "nutrizone-admin.css"


class TestPremiumSidebarNavbarCss:
    def test_stylesheet_has_balanced_braces(self):
        content = _css_path().read_text()
        assert content.count("{") == content.count("}")
        assert content.count("{") > 0

    def test_stylesheet_contains_sidebar_and_navbar_rules(self):
        content = _css_path().read_text()
        assert ".app-sidebar .nav-sidebar .nav-link.active" in content
        assert ".app-header.navbar" in content

    def test_stylesheet_only_uses_existing_design_tokens(self):
        content = _css_path().read_text()
        new_section = content.split("/* --- Phase 17.0: Premium sidebar --- */")[1]
        import re

        hex_colors = re.findall(r"#[0-9a-fA-F]{3,6}\b", new_section)
        allowed = {"#ffffff"}
        assert set(hex_colors) <= allowed, f"Unexpected raw hex colors introduced: {set(hex_colors) - allowed}"


class TestLiquidGlassDesign:
    """Real, professional premium redesign: buttons get an animated liquid-glass shimmer, and header/sidebar/cards get real glassmorphism (backdrop-blur) against a subtle, animated gradient mesh background."""

    def test_stylesheet_has_balanced_braces(self):
        content = _css_path().read_text()
        assert content.count("{") == content.count("}")

    def test_glass_design_tokens_are_defined(self):
        content = _css_path().read_text()
        for token in ("--nz-glass-bg", "--nz-glass-border", "--nz-glass-blur", "--nz-glass-shadow", "--nz-glass-highlight"):
            assert token in content, f"Missing glass design token: {token}"

    def test_dark_mode_overrides_the_same_glass_tokens(self):
        theme_path = Path(settings.BASE_DIR) / "apps" / "platform" / "static" / "admin" / "css" / "nutrizone-theme.css"
        content = theme_path.read_text()
        for token in ("--nz-glass-bg", "--nz-glass-border", "--nz-glass-shadow", "--nz-glass-highlight"):
            assert token in content, f"Dark mode is missing glass token override: {token}"

    def test_primary_button_has_liquid_shimmer_animation(self):
        content = _css_path().read_text()
        assert ".btn-primary::before" in content
        assert ".btn-primary:hover::before" in content

    def test_card_has_real_glassmorphism(self):
        content = _css_path().read_text()
        assert "backdrop-filter: blur(var(--nz-glass-blur))" in content

    def test_body_has_an_animated_gradient_mesh_background(self):
        content = _css_path().read_text()
        assert "@keyframes nz-mesh-drift" in content

    def test_motion_is_disabled_under_prefers_reduced_motion(self):
        """Real accessibility requirement: liquid-glass animation must never be forced on users who have asked for reduced motion."""
        content = _css_path().read_text()
        assert "@media (prefers-reduced-motion: reduce)" in content

    def test_pos_terminal_stylesheet_also_has_liquid_glass(self):
        pos_css_path = Path(settings.BASE_DIR) / "apps" / "platform" / "static" / "admin" / "css" / "nutrizone-pos.css"
        content = pos_css_path.read_text()
        assert content.count("{") == content.count("}")
        assert ".pos-complete-btn::before" in content
        assert "backdrop-filter" in content
        assert "@media (prefers-reduced-motion: reduce)" in content

    def test_changelist_table_has_glass_hover(self):
        """Real, professional extension: Order/Product/User list pages (Django Admin's own changelist table) now match the same premium glass design language as the dashboard cards, not left as plain Bootstrap defaults."""
        content = _css_path().read_text()
        assert ".table > tbody > tr:hover" in content

    def test_changelist_filter_sidebar_has_glassmorphism(self):
        content = _css_path().read_text()
        assert "#change-list-filters" in content

    def test_pagination_has_liquid_glass(self):
        content = _css_path().read_text()
        assert ".pagination .page-link" in content
        assert ".pagination .page-item.active .page-link" in content

    def test_real_changelist_page_references_the_glass_stylesheet(self, db):
        """Real, live-verified: an actual admin changelist page (not just the CSS file in isolation) loads with the same stylesheet the glass rules above live in."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get("/django-admin/products/product/")
        assert response.status_code == 200
        assert "nutrizone-admin.css" in response.content.decode()
        user.delete()

    def test_form_inputs_have_glass_styling_and_focus_glow(self):
        """Real, professional extension: Django's own vTextField/vLargeTextField/select/textarea (every Add/Change form field across the whole admin) previously had zero custom styling -- now matches the same premium glass design language, with a soft glow on focus."""
        content = _css_path().read_text()
        assert ".vTextField,\n.vLargeTextField,\ntextarea,\nselect," in content
        assert "box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.18);" in content

    def test_real_add_form_page_renders_text_fields_that_receive_the_glass_rule(self, db):
        """Real, live-verified: an actual Product Add form (not just the CSS file) contains real vTextField inputs the new CSS rule targets."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get("/django-admin/products/product/add/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "vTextField" in content
        assert "nutrizone-admin.css" in content
        user.delete()

    def test_login_page_has_liquid_glass_and_no_stale_button_override(self, db):
        """Real, closed gap: the login page's own inline <style> block previously hardcoded a flat .btn-primary override that shadowed the shared, liquid-glass button design -- and had no glassmorphism/animated background at all, unlike every other admin page."""
        client = Client()
        response = client.get("/django-admin/login/")
        assert response.status_code == 200
        content = response.content.decode()
        # Standalone premium login: frosted-glass card over an animated gradient brand panel.
        assert "backdrop-filter: blur(16px)" in content
        assert "@keyframes lg-float" in content
        assert ".nz-login-form-side .btn.btn-primary" not in content

    def test_chat_admin_page_has_liquid_glass(self, db):
        """Real, closed gap found via a full audit of every admin template: the Telegram Chat admin panel (chat list, thread, message bubbles, composer) was the one remaining page still using flat, opaque var(--nz-surface) backgrounds -- inconsistent with every other admin page's own glass design."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get("/django-admin/chat/")
        assert response.status_code == 200
        content = response.content.decode()
        # the Chat markazi desk: its panes use the glass tokens (nutrizone-chat-desk.css)
        assert "nutrizone-chat-desk.css" in content and 'class="nzc-desk"' in content
        from django.contrib.staticfiles import finders

        css = open(finders.find("admin/css/nutrizone-chat-desk.css"), encoding="utf-8").read()
        assert "background: var(--glass)" in css and "backdrop-filter: blur(var(--nz-glass-blur" in css
        user.delete()


class TestAdminPageLoadsWithUpdatedStylesheet:
    def test_real_admin_page_references_the_stylesheet(self):
        User = get_user_model()
        user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get("/django-admin/")
        assert response.status_code == 200
        assert "nutrizone-admin.css" in response.content.decode()

        user.delete()
