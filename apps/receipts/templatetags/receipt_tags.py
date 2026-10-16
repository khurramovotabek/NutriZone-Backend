from django import template

register = template.Library()


@register.filter
def som(value) -> str:
    """28851000 -> "28 851 000" (Uzbek grouping with a thin no-break space), whatever the UI language."""
    try:
        return f"{round(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"
