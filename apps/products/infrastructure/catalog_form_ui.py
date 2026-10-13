"""
Premium add/change pages for the catalog (Mahsulotlar, Variantlar, Brendlar, Kategoriyalar, Ta'mlar, Qadoqlar,
Teglar): a hero card (image / colour / icon, name, status, live numbers, storefront link) above the form, a sticky
section bar, uz/ru/en translation tabs, a drag-and-drop image picker and switch-style booleans
(templates/admin/products/premium_change_form.html + nutrizone-catalog-form.css/js).

Translation inlines always offer all three languages: missing locales come as pre-filled extra rows, which Django
skips on save while their name stays empty (an untouched extra form is not "changed").
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin

from apps.products.infrastructure import catalog_analytics as ca

LOCALES = ("uz", "ru", "en")


def media_url(storage_path: str, thumbnail_paths: dict | None = None, size: str = "medium") -> str:
    if not storage_path:
        return ""
    paths = thumbnail_paths or {}
    path = paths.get(size) or paths.get("small") or storage_path
    return path if path.startswith(("http://", "https://")) else f"{settings.MEDIA_URL}{path}"


def storefront_url(path: str) -> str:
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else ""


def stat(label: str, value, tone: str, sub: str = "", icon: str = "") -> dict:
    return {"label": label, "value": value, "tone": tone, "sub": sub, "icon": icon}


def sales_stat(n: ca.Numbers | None) -> dict:
    if n is None or (not n.units and not n.revenue):
        return stat("30 kunlik savdo", "—", "#64748b", "savdo bo'lmagan", "fa-chart-line")
    trend = f" · {'+' if n.change_pct >= 0 else ''}{n.change_pct}%" if n.change_pct is not None else ""
    return stat("30 kunlik savdo", f"{ca.compact(n.revenue)} so'm", "#10b981", f"{n.units} dona{trend}", "fa-chart-line")


class TranslationInlineMixin:
    """uz / ru / en rows always present (missing ones as blank extras) -- rendered as language tabs by the page JS."""

    extra = 0
    classes = ("nzp-translations",)

    LABELS = {
        "name": ("Nomi", ""),
        "slug": ("Slug (URL manzil)", "Nomdan avtomatik yasaladi; faqat lotin harflari, raqam va chiziqcha."),
        "description": ("Tavsif", "Saytdagi sahifada ko'rinadi. Emoji va yangi qatorlar saqlanadi."),
        "locale_code": ("Til", ""),
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        meta = self.LABELS.get(db_field.name)
        if field is not None and meta:
            field.label = meta[0]
            if meta[1]:
                field.help_text = meta[1]
            if db_field.name == "description":
                field.widget.attrs.update({"rows": 9, "placeholder": "Qisqa va aniq: nima, kim uchun, nimasi bilan ajralib turadi…"})
            if db_field.name == "name":
                field.widget.attrs.update({"placeholder": "Shu tildagi nomini kiriting", "autocomplete": "off"})
        return field

    def get_extra(self, request, obj=None, **kwargs):
        if obj is None:
            return len(LOCALES)
        have = set(self.model.objects.filter(**{self.fk_name or self._fk_name(): obj}).values_list("locale_code", flat=True))
        return len([c for c in LOCALES if c not in have])

    def _fk_name(self) -> str:
        parent = self.parent_model
        return next(f.name for f in self.model._meta.fields if getattr(f.remote_field, "model", None) is parent)

    def missing_locales(self, obj) -> list[dict]:
        if obj is None:
            return [{"locale_code": c} for c in LOCALES]
        have = set(self.model.objects.filter(**{self.fk_name or self._fk_name(): obj}).values_list("locale_code", flat=True))
        return [{"locale_code": c} for c in LOCALES if c not in have]


class CatalogFormMixin:
    """Hero + premium form chrome for a catalog ModelAdmin. Override `form_hero(request, obj)`."""

    change_form_template = "admin/products/premium_change_form.html"
    hero_icon = "fa-box"
    hero_tone = "#10b981"
    hero_noun = ""  # "brend", "kategoriya" ... -- the add page reads "Yangi {noun}"

    def form_hero(self, request, obj) -> dict:  # pragma: no cover - overridden
        return {}

    def get_formset_kwargs(self, request, obj, inline, prefix):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if isinstance(inline, TranslationInlineMixin):
            kwargs["initial"] = inline.missing_locales(obj)
        return kwargs

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        hero = {}
        try:
            hero = self.form_hero(request, obj) or {}
        except Exception:  # noqa: BLE001 - the numbers never block the form itself
            hero = {}
        hero.setdefault("icon", self.hero_icon)
        hero.setdefault("tone", self.hero_tone)
        if obj is None:
            hero.setdefault("title", f"Yangi {self.hero_noun}".strip())
            hero.setdefault("subtitle", "Ma'lumotlarni to'ldiring — nom kiritilishi bilan bu yerda ko'rinadi")
        context["nzp"] = hero
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)
