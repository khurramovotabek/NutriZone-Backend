"""Template helpers for the shared premium admin list (templates/admin/premium/list.html)."""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def nzi_choices(spec, cl) -> list[dict]:
    """A list filter's choices as plain dicts (an empty list hides a filter with nothing to choose)."""
    choices = list(spec.choices(cl))
    return choices if len(choices) > 1 else []


@register.simple_tag
def nz_phrases_version(lang: str) -> str:
    """Cache-busting version of the dashboard phrase catalog (apps/platform/infrastructure/admin_i18n.py)."""
    from apps.platform.infrastructure.admin_i18n import phrases_version

    return phrases_version((lang or "uz")[:2])
