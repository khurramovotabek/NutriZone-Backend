"""Formatting for the Analitika page (templates/admin/analytics.html): so'm amounts, counts, percentages and ▲/▼ chips."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()


def _num(value) -> str:
    try:
        return f"{int(round(Decimal(str(value or 0)))):,}".replace(",", " ")
    except (InvalidOperation, ValueError):
        return "—"


@register.filter
def num(value) -> str:
    return _num(value)


@register.filter
def som(value) -> str:
    return "—" if value is None else f"{_num(value)} so'm"


@register.filter
def compact(value) -> str:
    """12 450 000 → 12,5 mln (headline numbers); below a million the full number."""
    if value is None:
        return "—"
    v = Decimal(str(value or 0))
    a = abs(v)
    if a >= 1_000_000_000:
        text = f"{v / 1_000_000_000:.1f} mlrd"
    elif a >= 1_000_000:
        text = f"{v / 1_000_000:.1f} mln"
    else:
        return _num(v)
    return text.replace(".0 ", " ").replace(".", ",")


@register.filter
def pct(value) -> str:
    if value is None:
        return "—"
    text = f"{float(value):.1f}".replace(".", ",")
    return (text[:-2] if text.endswith(",0") else text) + "%"


@register.filter
def trend(ch, unit: str = "pct"):
    """A ▲/▼ chip for a business_analytics.change() dict; nothing when there's no honest baseline."""
    if not ch or ch.get("dir") is None:
        return ""
    if ch["dir"] == "flat":
        return format_html('<span class="nza-trend is-flat">▬ {}</span>', "0%")
    if unit == "pct":
        if ch.get("pct") is None:
            return format_html('<span class="nza-trend is-new">{}</span>', "yangi")
        body = pct(abs(ch["pct"]))
    else:
        body = f"{_num(abs(ch['diff']))} {unit}"
    arrow = "▲" if ch["dir"] == "up" else "▼"
    return format_html('<span class="nza-trend is-{}">{} {}</span>', ch["dir"], arrow, body)
