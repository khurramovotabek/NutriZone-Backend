"""
Dashboard text in the staff member's language -- the safety net under gettext.

Much of the dashboard was written with Uzbek text straight in Python (f-strings, dict labels, `title=`),
templates and JS. With Uzbek as the default language that reads fine, but in English / Russian those
strings stayed Uzbek and the pages came out mixed. Wrapping every literal in gettext would touch hundreds
of files; instead the *rendered* dashboard is translated phrase by phrase:

* `AdminTextTranslationMiddleware` rewrites the text nodes and the user-visible attributes (placeholder,
  title, aria-label, alt, button values) of every /django-admin/ HTML response.
* `phrases_js_view` serves the same catalog to the browser, where `nutrizone-i18n.js` translates text that
  dashboard scripts render later (charts, the WMS desk, the chat desk...).

The catalog is `locale/<lang>/LC_MESSAGES/admin_phrases.po` (msgid = the text as shown, msgstr = its
translation). A text node is looked up whole; failing that with its numbers as {0}, {1}... (so
"4 kun oldin" matches "{0} kun oldin"); failing that it is split on separators (" | ", " · ", " — ", ...)
and the parts are looked up; leading/trailing emoji, arrows and punctuation are kept as they are. The
regular Django catalog (django.po) is consulted too, so gettext msgids rendered without gettext work.

Only whole phrases are replaced -- never words inside a phrase -- so customer data (names, addresses,
product text) is left alone unless it is literally one of the dashboard's own phrases.
Text inside <script>, <style>, <textarea>, <pre>, <code> and elements marked `translate="no"` /
`class="notranslate"` is never touched.
"""
from __future__ import annotations

import ast
import html
import json
import pathlib
import re
from functools import lru_cache

from django.conf import settings
from django.http import HttpResponse
from django.utils import translation

ADMIN_PREFIX = "/django-admin/"
PHRASES_DOMAIN = "admin_phrases"
_LOCALE_DIR = pathlib.Path(settings.BASE_DIR) / "locale"

# ---------------------------------------------------------------------------------------------- catalog


def _unquote(chunks: list[str]) -> str:
    return "".join(ast.literal_eval(c.strip()) for c in chunks if c.strip())


def parse_po(path: pathlib.Path) -> dict[str, str]:
    """msgid -> msgstr of a .po file (empty and fuzzy entries skipped). Enough of the format for our catalogs."""
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    cur: dict[str, list[str]] = {}
    key = None
    fuzzy = False

    def flush():
        nonlocal cur, fuzzy
        if "msgid" in cur and "msgstr" in cur and not fuzzy:
            mid, mstr = _unquote(cur["msgid"]), _unquote(cur["msgstr"])
            if mid and mstr:
                entries[mid] = mstr
        cur, fuzzy = {}, False

    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            flush()
            key = None
            continue
        if s.startswith("#,") and "fuzzy" in s:
            fuzzy = True
            continue
        if s.startswith("#"):
            continue
        if s.startswith("msgid "):
            if "msgid" in cur:
                flush()
            key = "msgid"
            cur[key] = [s[6:]]
        elif s.startswith("msgstr "):
            key = "msgstr"
            cur[key] = [s[7:]]
        elif s.startswith('"') and key:
            cur[key].append(s)
    flush()
    return entries


def _catalog_path(lang: str) -> pathlib.Path:
    return _LOCALE_DIR / lang / "LC_MESSAGES" / f"{PHRASES_DOMAIN}.po"


@lru_cache(maxsize=8)
def _load(lang: str, mtime: float) -> tuple[dict[str, str], str]:
    entries = parse_po(_catalog_path(lang))
    # Matching ignores the kind of apostrophe (o' / o‘ / oʻ / o’ are all written in Uzbek text).
    normalized = {_norm(k): v for k, v in entries.items()}
    version = f"{int(mtime)}-{len(entries)}"
    return normalized, version


def catalog(lang: str) -> tuple[dict[str, str], str]:
    path = _catalog_path(lang)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}, "0"
    return _load(lang, mtime)


# ---------------------------------------------------------------------------------------------- phrases

_APOS = re.compile(r"[‘’ʻʼ`´]")
_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d+(?:[  .,:]\d+)*")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
# Leading / trailing decoration kept as is: emoji, arrows, bullets, dashes, punctuation, spaces.
_EDGE = re.compile(r"^([\W_]*)(.*?)([^\w)\]»”\"']*)$", re.S | re.U)  # closing brackets/quotes stay with the phrase
_SEPARATORS = (" | ", " · ", " • ", " — ", " – ", " - ", " → ", " ← ", ": ", " / ")
# Django / Jazzmin wrap a model name into "Change %s", "Изменить %s"...: the model name is translated on its own.
_PREFIXES = ("Change ", "Add ", "View ", "Delete ", "Select ", "Edit ", "Изменить ", "Добавить ", "Просмотреть ", "Удалить ",
             "Выбрать ", "Выберите ", "O'zgartirish ", "Qo'shish ", "Ko'rish ", "O'chirish ", "Tanlash ")


def _norm(s: str) -> str:
    return _WS.sub(" ", _APOS.sub("'", s)).strip()


def _django_gettext(lang: str, s: str) -> str | None:
    try:
        t = translation.trans_real.translation(lang)
    except Exception:  # pragma: no cover - a broken catalog must never break a page
        return None
    out = t.gettext(s)
    return out if out != s else None


def _lookup(s: str, lang: str, table: dict[str, str]) -> str | None:
    n = _norm(s)
    if n in table:
        return table[n]
    hit = _django_gettext(lang, s)
    if hit is not None:
        return hit
    if _NUM.search(n):
        nums: list[str] = []

        def take(m):
            nums.append(m.group(0))
            return "{%d}" % (len(nums) - 1)

        templ = _NUM.sub(take, n)
        if templ in table:
            out = table[templ]
            for i, v in enumerate(nums):
                out = out.replace("{%d}" % i, v)
            return out
    return None


def translate_text(text: str, lang: str, table: dict[str, str] | None = None, _depth: int = 0) -> str | None:
    """The translation of one visible phrase, or None when there is nothing to change."""
    if table is None:
        table = catalog(lang)[0]
    core = text.strip()
    if not core or not _LETTER.search(core) or len(core) > 600:
        return None
    hit = _lookup(core, lang, table)
    m = _EDGE.match(core)
    decorated = bool(m and (m.group(1) or m.group(3)) and m.group(2) and _LETTER.search(m.group(2)))
    if hit is None and decorated:
        # "☠️ Phrase 🧠", "Phrase:" -- the bare phrase, matched whole.
        inner = _lookup(m.group(2), lang, table)
        if inner is not None:
            hit = m.group(1) + inner + m.group(3)
    if hit is None:
        for prefix in _PREFIXES:
            if core.startswith(prefix) and len(core) > len(prefix):
                rest = _lookup(core[len(prefix):], lang, table)
                if rest is not None:
                    head = _lookup(prefix.strip(), lang, table) or prefix.strip()
                    hit = f"{head} {rest}"
                break
    if hit is None and _depth < 3:
        for sep in _SEPARATORS:
            if sep in core:
                parts = core.split(sep)
                done = [translate_text(p, lang, table, _depth + 1) for p in parts]
                if any(d is not None for d in done):
                    hit = sep.join(d if d is not None else p for p, d in zip(parts, done))
                    break
    if hit is None and decorated and _depth < 3:
        inner = translate_text(m.group(2), lang, table, _depth + 1)
        if inner is not None:
            hit = m.group(1) + inner + m.group(3)
    if hit is None:
        return None
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return lead + hit + trail


# ---------------------------------------------------------------------------------------------- HTML

_SKIP_BLOCK = re.compile(r"<(script|style|textarea|pre|code)\b[^>]*>.*?</\1\s*>|<!--.*?-->", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_ATTR = re.compile(r"""(\s(?:placeholder|title|aria-label|alt|data-label|data-title|data-confirm)=)(["'])(.*?)\2""", re.S | re.I)
_BTN_VALUE = re.compile(r"""(\svalue=)(["'])(.*?)\2""", re.S | re.I)
_NO_TRANSLATE_OPEN = re.compile(r"""<(\w+)\b[^>]*(?:\stranslate=["']no["']|class=["'][^"']*\bnotranslate\b)[^>]*>""", re.I)


def _translate_tag(tag: str, lang: str, table: dict[str, str]) -> str:
    def attr(m):
        raw = html.unescape(m.group(3))
        t = translate_text(raw, lang, table)
        return m.group(0) if t is None else f"{m.group(1)}{m.group(2)}{html.escape(t, quote=True)}{m.group(2)}"

    out = _ATTR.sub(attr, tag)
    low = out[:60].lower()
    if low.startswith("<input") and re.search(r"""type=["']?(submit|button|reset)""", out, re.I):
        out = _BTN_VALUE.sub(attr, out)
    return out


def _translate_fragment(fragment: str, lang: str, table: dict[str, str]) -> str:
    pieces: list[str] = []
    pos = 0
    skip_until: str | None = None  # closing tag name of a translate="no" element (no nesting support needed)
    for m in _TAG.finditer(fragment):
        text = fragment[pos:m.start()]
        if text and skip_until is None:
            raw = html.unescape(text)
            t = translate_text(raw, lang, table)
            pieces.append(text if t is None else html.escape(t, quote=False))
        else:
            pieces.append(text)
        tag = m.group(0)
        if skip_until is not None:
            if tag.lower().startswith(f"</{skip_until}"):
                skip_until = None
            pieces.append(tag)
        else:
            nt = _NO_TRANSLATE_OPEN.match(tag)
            if nt and not tag.endswith("/>"):
                skip_until = nt.group(1).lower()
                pieces.append(tag)
            else:
                pieces.append(_translate_tag(tag, lang, table))
        pos = m.end()
    tail = fragment[pos:]
    if tail and skip_until is None:
        t = translate_text(html.unescape(tail), lang, table)
        pieces.append(tail if t is None else html.escape(t, quote=False))
    else:
        pieces.append(tail)
    return "".join(pieces)


def translate_html(markup: str, lang: str) -> str:
    table = catalog(lang)[0]
    out: list[str] = []
    pos = 0
    for m in _SKIP_BLOCK.finditer(markup):
        out.append(_translate_fragment(markup[pos:m.start()], lang, table))
        block = m.group(0)
        if block[:9].lower() == "<textarea":
            # The typed text stays untouched; the opening tag's placeholder/title are dashboard text.
            open_end = block.index(">") + 1
            block = _translate_tag(block[:open_end], lang, table) + block[open_end:]
        out.append(block)
        pos = m.end()
    out.append(_translate_fragment(markup[pos:], lang, table))
    return "".join(out)


class AdminTextTranslationMiddleware:
    """Translates the dashboard's rendered HTML (see the module docstring). Placed after LocaleMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(settings, "ADMIN_PHRASES_ENABLED", True) or not request.path.startswith(ADMIN_PREFIX):
            return response
        if getattr(response, "streaming", False) or response.status_code not in (200, 400, 403, 404):
            return response
        if not response.get("Content-Type", "").startswith("text/html") or response.get("Content-Encoding"):
            return response
        lang = (getattr(request, "LANGUAGE_CODE", None) or translation.get_language() or settings.LANGUAGE_CODE)[:2]
        if lang not in {code for code, _ in settings.LANGUAGES}:
            return response
        try:
            body = response.content.decode(response.charset or "utf-8")
            response.content = translate_html(body, lang).encode(response.charset or "utf-8")
        except Exception:  # pragma: no cover - never lose a page over a translation problem
            return response
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response


def phrases_js_view(request, lang: str):
    """The phrase catalog for nutrizone-i18n.js (dynamic dashboard text). Cached by the browser per version."""
    if lang not in {code for code, _ in settings.LANGUAGES}:
        lang = settings.LANGUAGE_CODE
    table, version = catalog(lang)
    body = "window.NZ_PHRASES=" + json.dumps({"lang": lang, "v": version, "t": table}, ensure_ascii=False, separators=(",", ":")) + ";"
    resp = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "public, max-age=31536000, immutable" if request.GET.get("v") == version else "no-cache"
    return resp


def phrases_version(lang: str) -> str:
    return catalog(lang)[1]
