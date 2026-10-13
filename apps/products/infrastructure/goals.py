"""
Training goals a product serves -- the storefront's "shop by goal" cards and the catalog's goal filter.

A product can serve several goals (whey protein: muscle and recovery...). The list is fixed so the storefront can
show a curated card (icon, colour, copy) for each; staff tick the goals on the product page.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

GOALS: dict[str, dict] = {
    "muscle": {"label": _("Muscle gain"), "uz": "Mushak o'stirish", "ru": "Набор мышц", "en": "Muscle gain"},
    "weight_loss": {"label": _("Weight loss"), "uz": "Ozish", "ru": "Похудение", "en": "Weight loss"},
    "endurance": {"label": _("Endurance & energy"), "uz": "Chidamlilik va energiya", "ru": "Выносливость и энергия", "en": "Endurance & energy"},
    "health": {"label": _("Health & immunity"), "uz": "Salomatlik va immunitet", "ru": "Здоровье и иммунитет", "en": "Health & immunity"},
}
CHOICES = [(code, g["label"]) for code, g in GOALS.items()]


def clean(values) -> list[str]:
    """Known goal codes only, in the canonical order, without duplicates."""
    wanted = set(values or [])
    return [code for code in GOALS if code in wanted]


def label(code: str, locale: str) -> str:
    g = GOALS.get(code) or {}
    return g.get(locale) or g.get("uz") or code
