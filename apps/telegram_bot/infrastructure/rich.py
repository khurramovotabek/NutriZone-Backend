"""
Telegram Rich Messages (Bot API 10.1+, `sendRichMessage`) for the NutriZone bots: headings, bordered/striped tables,
collapsible <details>, figures with uploaded chart images, maps, button rows -- one document per message (up to
32 768 characters / 500 blocks / 50 media / 20 table columns). https://core.telegram.org/bots/api#rich-messages

Every helper escapes its text. `send()` uploads images in the same request (multipart, `tg://photo?id=` links) and,
should Telegram refuse the rich message, falls back to a classic HTML message so a report is never lost.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from html import escape

import requests
from django.conf import settings

logger = logging.getLogger("nutrizone.telegram_bot.rich")

MAX_CHARS = 32000


def e(text) -> str:
    return escape(str(text if text is not None else ""), quote=True)


# ---------------------------------------------------------------- building blocks (all return HTML strings)


def h(level: int, text: str) -> str:
    return f"<h{level}>{text}</h{level}>"


def p(text: str) -> str:
    return f"<p>{text}</p>"


def b(text) -> str:
    return f"<b>{e(text)}</b>"


def i(text) -> str:
    return f"<i>{e(text)}</i>"


def code(text) -> str:
    return f"<code>{e(text)}</code>"


def mark(text) -> str:
    return f"<mark>{e(text)}</mark>"


def link(text, url: str) -> str:
    return f'<a href="{e(url)}">{e(text)}</a>'


def phone(number: str) -> str:
    n = "".join(ch for ch in str(number or "") if ch.isdigit() or ch == "+")
    return f'<a href="tel:{e(n)}">{e(number)}</a>' if n else ""


def time_tag(dt, fmt: str = "wDT", text: str = "") -> str:
    """Telegram renders it in each reader's own locale/time zone ("tg-time")."""
    return f'<tg-time unix="{int(dt.timestamp())}" format="{fmt}">{e(text or dt.strftime("%d.%m.%Y %H:%M"))}</tg-time>'


def hr() -> str:
    return "<hr/>"


def footer(text: str) -> str:
    return f"<footer>{text}</footer>"


def quote(text: str, expandable: bool = False, cite: str = "") -> str:
    return f"<blockquote{' expandable' if expandable else ''}>{text}{f'<cite>{cite}</cite>' if cite else ''}</blockquote>"


def aside(text: str, cite: str = "") -> str:
    return f"<aside>{text}{f'<cite>{cite}</cite>' if cite else ''}</aside>"


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def ol(items: list[str]) -> str:
    return "<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>"


def checklist(items: list[tuple[str, bool]]) -> str:
    return "<ul>" + "".join(f'<li><input type="checkbox"{" checked" if done else ""}>{text}</li>' for text, done in items) + "</ul>"


def details(summary: str, body: str, open_: bool = False) -> str:
    return f"<details{' open' if open_ else ''}><summary>{summary}</summary>{body}</details>"


def table(header: list[str], rows: list[list[str]], align: list[str] | None = None, caption: str = "", compact: bool = True) -> str:
    """Cells are HTML (escape your text with e()/b()); `align` per column: left/center/right."""
    align = align or ["left"] * len(header)

    def cells(row, tag):
        return "".join(f'<{tag} align="{align[k] if k < len(align) else "left"}">{c}</{tag}>' for k, c in enumerate(row))

    head = f"<tr>{cells(header, 'th')}</tr>" if header else ""
    body = "".join(f"<tr>{cells(r, 'td')}</tr>" for r in rows)
    return f"<table bordered striped{' compact' if compact else ''}>{f'<caption>{caption}</caption>' if caption else ''}{head}{body}</table>"


def figure(image_id: str, caption: str = "", credit: str = "") -> str:
    cap = f"<figcaption>{caption}{f'<cite>{credit}</cite>' if credit else ''}</figcaption>" if caption else ""
    return f'<figure><img src="tg://photo?id={image_id}"/>{cap}</figure>'


def image_url(url: str, caption: str = "") -> str:
    return f'<figure><img src="{e(url)}"/><figcaption>{caption}</figcaption></figure>' if caption else f'<img src="{e(url)}"/>'


def collage(image_ids: list[str], caption: str = "") -> str:
    imgs = "".join(f'<img src="tg://photo?id={x}"/>' for x in image_ids)
    return f"<tg-collage>{imgs}{f'<figcaption>{caption}</figcaption>' if caption else ''}</tg-collage>"


def map_block(lat: float, lng: float, zoom: int = 16, caption: str = "") -> str:
    m = f'<tg-map lat="{lat:.6f}" long="{lng:.6f}" zoom="{zoom}"/>'
    return f"<figure>{m}<figcaption>{caption}</figcaption></figure>" if caption else m


def button(text: str, *, url: str | None = None, callback: str | None = None, web_app: str | None = None, style: str | None = None, copy: str | None = None) -> str:
    st = f' style="{style}"' if style else ""
    if url:
        return f'<tg-button type="url"{st} url="{e(url)}">{e(text)}</tg-button>'
    if web_app:
        return f'<tg-button type="web_app"{st} url="{e(web_app)}">{e(text)}</tg-button>'
    if copy is not None:
        return f'<tg-button type="copy_text"{st} text="{e(copy)}">{e(text)}</tg-button>'
    return f'<tg-button type="callback_data"{st} data="{e(callback or "noop")}">{e(text)}</tg-button>'


def buttons(*items: str, align: str = "center") -> str:
    return f'<tg-button-row align="{align}">' + "".join(x for x in items if x) + "</tg-button-row>"


# ---------------------------------------------------------------- the message


@dataclass
class RichDoc:
    """A rich message under construction: HTML parts + uploaded images + a classic-HTML fallback text."""

    parts: list[str] = field(default_factory=list)
    images: dict[str, bytes] = field(default_factory=dict)
    fallback: str = ""

    def add(self, *html_parts: str) -> RichDoc:
        self.parts += [x for x in html_parts if x]
        return self

    def image(self, image_id: str, png: bytes | None) -> bool:
        if png:
            self.images[image_id] = png
            return True
        return False

    @property
    def html(self) -> str:
        return "".join(self.parts)


class RichSendError(Exception):
    pass


def _api(token: str, method: str, *, data=None, json_body=None, files=None) -> dict:
    base = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
    try:
        r = requests.post(f"{base}/bot{token}/{method}", data=data, json=json_body, files=files, timeout=float(getattr(settings, "TELEGRAM_TIMEOUT_SECONDS", 10) or 10) + 20)
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise RichSendError(f"{method}: {exc.__class__.__name__}") from exc
    if not body.get("ok"):
        raise RichSendError(f"{method}: {body.get('description', r.status_code)}")
    return body.get("result") or {}


def _payload(doc: RichDoc) -> tuple[dict, dict]:
    html = doc.html
    if len(html) > MAX_CHARS:
        html = html[:MAX_CHARS]  # (callers keep documents far below the limit; this is a last guard)
    rich = {"html": html}
    files = {}
    if doc.images:
        rich["media"] = [{"id": k, "media": {"type": "photo", "media": f"attach://{k}"}} for k in doc.images]
        files = {k: (f"{k}.png", v, "image/png") for k, v in doc.images.items()}
    return rich, files


def send(token: str, chat_id, doc: RichDoc, keyboard: list | None = None, silent: bool = False) -> int:
    """sendRichMessage; on refusal, the classic HTML fallback (if the doc has one). Returns the message id."""
    rich, files = _payload(doc)
    data = {"chat_id": str(chat_id), "rich_message": json.dumps(rich, ensure_ascii=False)}
    if keyboard:
        data["reply_markup"] = json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False)
    if silent:
        data["disable_notification"] = "true"
    try:
        return int(_api(token, "sendRichMessage", data=data, files=files or None).get("message_id") or 0)
    except RichSendError as exc:
        if not doc.fallback or "blocked" in str(exc) or "chat not found" in str(exc):
            raise
        logger.warning("rich message refused (%s) -- sending the classic fallback", exc)
        body = {"chat_id": chat_id, "text": doc.fallback[:4096], "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
        if keyboard:
            body["reply_markup"] = {"inline_keyboard": keyboard}
        return int(_api(token, "sendMessage", json_body=body).get("message_id") or 0)


def edit(token: str, chat_id, message_id, doc: RichDoc, keyboard: list | None = None) -> None:
    """editMessageText with `rich_message` (a rich post is edited in place, images included)."""
    rich, files = _payload(doc)
    data = {"chat_id": str(chat_id), "message_id": str(message_id), "rich_message": json.dumps(rich, ensure_ascii=False),
            "reply_markup": json.dumps({"inline_keyboard": keyboard or []}, ensure_ascii=False)}
    _api(token, "editMessageText", data=data, files=files or None)


def is_blocked(exc: Exception) -> bool:
    text = str(exc).lower()
    return "blocked" in text or "deactivated" in text or "chat not found" in text or "forbidden" in text
