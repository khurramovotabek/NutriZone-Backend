"""
Rich text for Telegram: the dashboard editor's HTML -> Telegram Bot API "HTML" parse mode.

Telegram accepts only a small tag set (b, i, u, s, a, code, pre, blockquote, tg-spoiler) and no block tags --
line breaks are literal newlines. `sanitize()` turns whatever a contenteditable editor produced (div/p/br, strong/em,
lists, pasted Word/Google Docs markup) into that subset, escapes every text node and always returns balanced tags,
so a post can never be refused with "can't parse entities". `to_plain()` gives the same content without markup
for the in-app inbox, SMS and previews.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

TEXT_LIMIT = 4096  # sendMessage
CAPTION_LIMIT = 1024  # sendPhoto caption

# editor tag -> Telegram tag
_INLINE = {
    "b": "b", "strong": "b",
    "i": "i", "em": "i",
    "u": "u", "ins": "u",
    "s": "s", "strike": "s", "del": "s",
    "code": "code",
    "tg-spoiler": "tg-spoiler",
}
_BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer", "table", "tr"}
_DROP_CONTENT = {"script", "style", "head", "title", "template", "noscript", "iframe", "object"}
_SAFE_SCHEMES = {"http", "https", "tg", "mailto", "tel"}


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []  # open Telegram tags, in order
        self.skip = 0
        self.lists: list[list] = []  # [kind, counter]
        self.in_pre = 0

    # -- helpers
    def _newline(self) -> None:
        text = "".join(self.out)
        if text and not text.endswith("\n"):
            self.out.append("\n")

    def _open(self, tag: str, attrs: str = "") -> None:
        if tag in self.stack and tag != "blockquote":
            self.stack.append("")  # nested duplicate: keep the stack aligned, emit nothing
            return
        self.out.append(f"<{tag}{attrs}>")
        self.stack.append(tag)

    def _close(self, tag: str) -> None:
        # close up to the nearest matching open tag (repairs mis-nesting)
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx] == tag or (self.stack[idx] == "" and tag in _INLINE.values()):
                for t in reversed(self.stack[idx:]):
                    if t:
                        self.out.append(f"</{t}>")
                reopen = [t for t in self.stack[idx + 1:] if t]
                del self.stack[idx:]
                for t in reopen:
                    self._open(t)
                return

    # -- parser callbacks
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_CONTENT:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "br":
            self.out.append("\n")
        elif tag in _BLOCK:
            self._newline()
        elif tag in ("ul", "ol"):
            self._newline()
            self.lists.append([tag, 0])
        elif tag == "li":
            self._newline()
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.out.append(f"{self.lists[-1][1]}. ")
            else:
                self.out.append("• ")
        elif tag == "blockquote":
            self._newline()
            self._open("blockquote", " expandable" if "expandable" in a or "expandable" in cls else "")
        elif tag == "pre":
            self._newline()
            self.in_pre += 1
            self._open("pre")
        elif tag == "a":
            href = (a.get("href") or "").strip()
            scheme = urlparse(href).scheme.lower()
            if href and scheme in _SAFE_SCHEMES:
                self._open("a", f' href="{escape(href, quote=True)}"')
            else:
                self.stack.append("")
        elif tag == "span" and ("tg-spoiler" in cls or "spoiler" in cls):
            self._open("tg-spoiler")
        elif tag in _INLINE:
            self._open(_INLINE[tag])
        elif tag == "span":
            self.stack.append("")  # styling-only span

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _BLOCK or tag == "li":
            self._newline()
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self._newline()
        elif tag == "blockquote":
            self._close("blockquote")
            self._newline()
        elif tag == "pre":
            self._close("pre")
            self.in_pre = max(0, self.in_pre - 1)
            self._newline()
        elif tag == "a":
            if self.stack and self.stack[-1] == "":
                self.stack.pop()
            else:
                self._close("a")
        elif tag == "span":
            if self.stack and self.stack[-1] == "":
                self.stack.pop()
            elif self.stack and self.stack[-1] == "tg-spoiler":
                self._close("tg-spoiler")
        elif tag in _INLINE:
            self._close(_INLINE[tag])

    def handle_data(self, data):
        if self.skip:
            return
        if not self.in_pre:
            data = re.sub(r"[ \t\r\f\v]*\n[ \t\r\f\v]*", "\n", data.replace("\xa0", " "))
        self.out.append(escape(data, quote=False))

    def result(self) -> str:
        for t in reversed(self.stack):
            if t:
                self.out.append(f"</{t}>")
        self.stack.clear()
        text = "".join(self.out)
        text = re.sub(r"<(b|i|u|s|code|tg-spoiler)>(\s*)</\1>", r"\2", text)  # empty formatting
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def sanitize(html: str | None) -> str:
    """Editor / pasted HTML (or plain text) -> Telegram-safe HTML with balanced tags."""
    if not html:
        return ""
    if "<" not in html:
        return escape(html.strip(), quote=False)
    conv = _Converter()
    conv.feed(html)
    conv.close()
    return conv.result()


def to_plain(html: str | None) -> str:
    """Telegram HTML -> plain text (inbox, SMS, previews). Links keep their address in brackets."""
    if not html:
        return ""
    text = re.sub(r'<a\s+href="([^"]*)"\s*>(.*?)</a>', lambda m: m.group(2) if m.group(2) == m.group(1) else f"{m.group(2)} ({m.group(1)})", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    from html import unescape

    return unescape(text).strip()


def visible_length(html: str | None) -> int:
    """Characters Telegram counts against the 4096 / 1024 limits (entities are not counted)."""
    return len(re.sub(r"<[^>]+>", "", html or "").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"'))
