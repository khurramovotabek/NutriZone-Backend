"""
Dashboard RichText field for anything that ends up in Telegram (posts, broadcasts, bot texts).

The widget is a small WYSIWYG editor (bold, italic, underline, strike, spoiler, code, link, quote, lists, emoji)
with a live Telegram-style preview and a character counter against Telegram's limit; the field cleans the posted
HTML down to Telegram's tag set (telegram_html.sanitize), so what the editor shows is exactly what gets sent.
Without JavaScript it degrades to a plain textarea (the value is still sanitized).
"""
from __future__ import annotations

from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.telegram_bot.infrastructure.telegram_html import CAPTION_LIMIT, TEXT_LIMIT, sanitize, visible_length


class TelegramRichTextWidget(forms.Textarea):
    template_name = "django/forms/widgets/textarea.html"

    class Media:
        css = {"all": ("admin/css/nutrizone-tg-editor.css",)}
        js = ("admin/js/nutrizone-tg-editor.js",)

    def __init__(self, attrs=None, limit: int = TEXT_LIMIT, placeholder: str = "", preview: bool = True):
        self.limit = limit
        self.preview = preview
        base = {"rows": 8, "data-nztg": "1", "data-limit": str(limit)}
        if placeholder:
            base["placeholder"] = placeholder
        if not preview:
            base["data-no-preview"] = "1"
        super().__init__({**base, **(attrs or {})})

    def render(self, name, value, attrs=None, renderer=None):
        textarea = super().render(name, value, attrs, renderer)
        return format_html('<div class="nztg" data-nztg-root>{}</div>', mark_safe(textarea))


class TelegramRichTextField(forms.CharField):
    """CharField whose value is Telegram-safe HTML; `max_length` counts visible characters, as Telegram does."""

    def __init__(self, *args, caption: bool = False, placeholder: str = "", preview: bool = True, **kwargs):
        self.visible_limit = CAPTION_LIMIT if caption else TEXT_LIMIT
        kwargs.setdefault("widget", TelegramRichTextWidget(limit=self.visible_limit, placeholder=placeholder, preview=preview))
        kwargs.pop("max_length", None)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        return sanitize(super().to_python(value))

    def validate(self, value):
        super().validate(value)
        n = visible_length(value)
        if n > self.visible_limit:
            raise forms.ValidationError(f"Matn juda uzun: {n} belgi (Telegram chegarasi — {self.visible_limit}).")
