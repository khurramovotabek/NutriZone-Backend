"""
Chart images for the Telegram rich reports, drawn with Pillow (already a dependency -- no plotting library needed).
One dark, branded look: deep navy card, indigo/cyan series, rounded bars, soft grid, tabular numbers. Rendered at
2x (1600 px wide) so they stay crisp on phones. Every function returns PNG bytes, or None when there is nothing to draw.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

W = 1600
BG = (11, 18, 32)
CARD = (17, 26, 46)
GRID = (36, 48, 72)
TEXT = (226, 232, 240)
MUTED = (139, 152, 176)
INDIGO = (99, 102, 241)
CYAN = (6, 182, 212)
AMBER = (245, 158, 11)
GREEN = (34, 197, 94)
ROSE = (244, 63, 94)
PALETTE = [INDIGO, CYAN, GREEN, AMBER, (236, 72, 153), (139, 92, 246), (20, 184, 166), (148, 163, 184)]


def _font(size: int):
    return ImageFont.load_default(size=size)


_GLYPHS = str.maketrans({"▲": "+", "▼": "-", "–": "-", "—": "-", "−": "-", "→": ">", "’": "'", "ʻ": "'", "ʼ": "'", "…": "..."})


def t(text) -> str:
    """The bundled font has no arrows / dashes -- map them to plain characters."""
    return str(text or "").translate(_GLYPHS)


def _fit(d, text: str, width: int, size: int, minimum: int = 28) -> tuple:
    while size > minimum and d.textlength(text, font=_font(size)) > width:
        size -= 2
    return _font(size)


def hex_rgb(value: str | None, default=INDIGO) -> tuple:
    try:
        v = (value or "").lstrip("#")
        return tuple(int(v[k:k + 2], 16) for k in (0, 2, 4))
    except ValueError:
        return default


def compact(n: float) -> str:
    a = abs(n)
    if a >= 1e9:
        return f"{n / 1e9:.1f} mlrd".replace(".0 ", " ").replace(".", ",")
    if a >= 1e6:
        return f"{n / 1e6:.1f} mln".replace(".0 ", " ").replace(".", ",")
    if a >= 1e3:
        return f"{round(n / 1e3)} ming"
    return str(int(round(n)))


def full(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _canvas(h: int, title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    title, subtitle = t(title), t(subtitle)
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, W - 16, h - 16), 36, fill=CARD)
    d.text((64, 52), title, font=_font(46), fill=TEXT, stroke_width=1, stroke_fill=TEXT)
    if subtitle:
        d.text((64, 112), subtitle, font=_font(30), fill=MUTED)
    return img, d, 170 if subtitle else 130


def _gradient(img: Image.Image, box, top, bottom) -> None:
    x0, y0, x1, y1 = box
    grad = Image.new("RGB", (1, max(1, y1 - y0)))
    for y in range(grad.height):
        t = y / max(1, grad.height - 1)
        grad.putpixel((0, y), tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3)))
    img.paste(grad.resize((max(1, x1 - x0), grad.height)), (x0, y0))


# ---------------------------------------------------------------- KPI banner


def kpi_banner(title: str, subtitle: str, tiles: list[tuple[str, str, str, tuple | None]]) -> bytes:
    """A hero image: brand gradient, title, up to 4 tiles of (label, value, note, accent)."""
    h = 620
    img = Image.new("RGB", (W, h), BG)
    _gradient(img, (0, 0, W, h), (49, 46, 129), (14, 116, 144))
    d = ImageDraw.Draw(img)
    for k in range(0, W, 36):  # faint dot pattern
        for y in range(0, h, 36):
            if (k + y) % 72 == 0:
                d.ellipse((k, y, k + 3, y + 3), fill=(92, 104, 190))
    d.text((64, 56), "NUTRIZONE · ANALYTICS", font=_font(28), fill=(199, 210, 254))
    title, subtitle = t(title), t(subtitle)
    d.text((64, 96), title, font=_font(64), fill=(255, 255, 255), stroke_width=2, stroke_fill=(255, 255, 255))
    d.text((64, 182), subtitle, font=_font(32), fill=(224, 231, 255))
    n = max(1, min(4, len(tiles)))
    gap, top = 24, 270
    tw = (W - 128 - gap * (n - 1)) // n
    for k, (label, value, note, accent) in enumerate(tiles[:4]):
        label, value, raw_note = t(label), t(value), note or ""
        note = t(note)
        x = 64 + k * (tw + gap)
        d.rounded_rectangle((x, top, x + tw, top + 290), 28, fill=(15, 23, 42))
        d.rounded_rectangle((x, top, x + 10, top + 290), 5, fill=accent or INDIGO)
        d.text((x + 36, top + 34), label.upper(), font=_font(26), fill=MUTED)
        d.text((x + 36, top + 86), value, font=_fit(d, value, tw - 72, 64), fill=TEXT, stroke_width=2, stroke_fill=TEXT)
        if note:
            color = GREEN if raw_note.startswith("▲") else ROSE if raw_note.startswith("▼") else MUTED
            d.text((x + 36, top + 200), note, font=_font(30), fill=color)
    return _png(img)


# ---------------------------------------------------------------- bars over time


def bar_chart(title: str, subtitle: str, labels: list[str], series: list[tuple[str, tuple, list[float]]], previous: list[float] | None = None, every: int = 0) -> bytes | None:
    """Stacked bars per label (store tills / online …) with an optional dashed "previous period" line."""
    totals = [sum(s[2][k] for s in series) for k in range(len(labels))]
    if not labels or max(totals + (previous or [0])) <= 0:
        return None
    h = 900
    img, d, top = _canvas(h, title, subtitle)
    left, right, bottom = 190, W - 70, h - 170
    peak = max(totals + (previous or [0])) * 1.12
    step = 10 ** max(0, int(math.log10(peak)) - 1)
    nice = math.ceil(peak / 4 / step) * step or 1
    for g in range(5):
        v = nice * g
        y = bottom - (bottom - top - 40) * v / (nice * 4)
        d.line((left, y, right, y), fill=GRID, width=2)
        d.text((left - 24, y), compact(v), font=_font(26), fill=MUTED, anchor="rm")
    n = len(labels)
    slot = (right - left) / n
    bw = max(6, min(70, slot * 0.62))
    scale = (bottom - top - 40) / (nice * 4)
    every = every or max(1, math.ceil(n / 12))
    for k in range(n):
        cx = left + slot * (k + 0.5)
        y = bottom
        for _name, color, values in series:
            v = values[k]
            if v <= 0:
                continue
            hgt = v * scale
            d.rounded_rectangle((cx - bw / 2, y - hgt, cx + bw / 2, y), radius=min(12, bw / 3), fill=color)
            y -= hgt
        if k % every == 0:
            d.text((cx, bottom + 34), labels[k], font=_font(26), fill=MUTED, anchor="mm")
    if previous and any(previous):
        pts = [(left + slot * (k + 0.5), bottom - previous[k] * scale) for k in range(n)]
        for k in range(len(pts) - 1):
            x0, y0 = pts[k]
            x1, y1 = pts[k + 1]
            seg = max(1, int(math.hypot(x1 - x0, y1 - y0) // 18))
            for s in range(0, seg, 2):
                a, c = s / seg, min(1, (s + 1) / seg)
                d.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * c, y0 + (y1 - y0) * c), fill=AMBER, width=5)
    # legend
    lx = left
    items = [(name, color) for name, color, _ in series] + ([("Oldingi davr", AMBER)] if previous and any(previous) else [])
    for name, color in items:
        d.rounded_rectangle((lx, h - 70, lx + 26, h - 44), 6, fill=color)
        d.text((lx + 38, h - 57), name, font=_font(28), fill=TEXT, anchor="lm")
        lx += 60 + d.textlength(name, font=_font(28))
    return _png(img)


# ---------------------------------------------------------------- horizontal ranking


def hbar(title: str, subtitle: str, rows: list[tuple[str, float, tuple, str]]) -> bytes | None:
    """Ranking bars: (label, value, colour, right-hand text)."""
    rows = [r for r in rows if r[1] > 0][:8]
    if not rows:
        return None
    row_h = 112
    h = 200 + row_h * len(rows) + 40
    img, d, top = _canvas(h, title, subtitle)
    peak = rows[0][1] or 1
    for k, (label, value, color, right) in enumerate(rows):
        y = top + 20 + k * row_h
        d.ellipse((64, y + 6, 112, y + 54), fill=color)
        d.text((88, y + 30), str(k + 1), font=_font(28), fill=(255, 255, 255), anchor="mm", stroke_width=1, stroke_fill=(255, 255, 255))
        label, right = t(label), t(right)
        d.text((136, y + 6), label[:42], font=_font(34), fill=TEXT, stroke_width=1, stroke_fill=TEXT)
        d.text((W - 64, y + 6), right, font=_font(32), fill=TEXT, anchor="ra")
        x0, x1 = 136, W - 64
        d.rounded_rectangle((x0, y + 60, x1, y + 78), 9, fill=GRID)
        d.rounded_rectangle((x0, y + 60, x0 + max(18, (x1 - x0) * value / peak), y + 78), 9, fill=color)
    return _png(img)


# ---------------------------------------------------------------- donut


def donut(title: str, subtitle: str, rows: list[tuple[str, float]], center: str, center_note: str = "") -> bytes | None:
    rows = [r for r in rows if r[1] > 0][:7]
    total = sum(v for _l, v in rows)
    if total <= 0:
        return None
    h = 820
    img, d, top = _canvas(h, title, subtitle)
    cx, cy, r = 400, top + 300, 270
    start = -90.0
    for k, (_label, v) in enumerate(rows):
        sweep = 360 * v / total
        d.pieslice((cx - r, cy - r, cx + r, cy + r), start, start + sweep, fill=PALETTE[k % len(PALETTE)])
        start += sweep
    d.ellipse((cx - r * 0.66, cy - r * 0.66, cx + r * 0.66, cy + r * 0.66), fill=CARD)
    d.text((cx, cy - 18), center, font=_font(56), fill=TEXT, anchor="mm", stroke_width=2, stroke_fill=TEXT)
    if center_note:
        d.text((cx, cy + 40), center_note, font=_font(28), fill=MUTED, anchor="mm")
    y = top + 40
    for k, (label, v) in enumerate(rows):
        d.rounded_rectangle((760, y + 8, 792, y + 40), 8, fill=PALETTE[k % len(PALETTE)])
        d.text((816, y + 24), t(label)[:22], font=_font(32), fill=TEXT, anchor="lm")
        d.text((W - 64, y + 24), f"{v / total * 100:.0f}%  ·  {compact(v)}", font=_font(30), fill=MUTED, anchor="rm")
        y += 78
    return _png(img)


# ---------------------------------------------------------------- receipt (POS sale / order) header


def receipt_banner(kind: str, number: str, branch: str, amount: str, note: str, accent: tuple = INDIGO) -> bytes:
    """A small header picture for an order / sale post: kind badge, number, branch, big amount."""
    h = 420
    kind, number, branch, amount, note = t(kind), t(number), t(branch), t(amount), t(note)
    img = Image.new("RGB", (W, h), BG)
    _gradient(img, (0, 0, W, h), tuple(int(c * 0.55) for c in accent), (15, 23, 42))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((64, 56, 64 + 40 + d.textlength(kind, font=_font(30)), 108), 26, fill=(255, 255, 255))
    d.text((84, 82), kind, font=_font(30), fill=accent, anchor="lm", stroke_width=1, stroke_fill=accent)
    d.text((64, 150), number, font=_font(70), fill=(255, 255, 255), stroke_width=2, stroke_fill=(255, 255, 255))
    d.text((64, 250), branch, font=_fit(d, branch, 900, 34), fill=(203, 213, 225))
    d.text((W - 64, 170), amount, font=_font(84), fill=(255, 255, 255), anchor="ra", stroke_width=2, stroke_fill=(255, 255, 255))
    d.text((W - 64, 290), note, font=_font(32), fill=(203, 213, 225), anchor="ra")
    return _png(img)
