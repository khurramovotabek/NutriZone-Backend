"""
Order Telegram message builder -- kept separate from the subscriber's
own orchestration logic, matching this phase's own explicit
"message builders separated from handlers" instruction, and so a
future Dashboard-managed template system has one clear place to plug
into.

Uses `Order.compute_total()` (the certified formula already proven in
Phase 10) for the total -- never a second, independent calculation.
Markdown special characters in free-text fields (recipient name,
address lines) are escaped, since `LiveTelegramGateway` sends with
`parse_mode: Markdown` and unescaped customer-supplied text could
otherwise break message formatting or inject unintended Markdown.
"""
from __future__ import annotations

import re

_MARKDOWN_SPECIAL_CHARS = re.compile(r"([_*\[\]`])")


def _escape_markdown(text: str) -> str:
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", text)


def _format_amount(amount) -> str:
    return f"{amount:,.0f}".replace(",", " ")


def build_new_order_channel_message(order) -> str:
    """`order` is a real, already-loaded `apps.ordering.domain.aggregates.Order`. Returns the full message text for the staff Orders Channel."""
    total = order.compute_total()
    lines_text = "\n".join(
        f"\u2022 {line.quantity} x {_format_amount(line.unit_price.amount)} {line.unit_price.currency}"
        for line in order.active_lines()
    )

    address = order.shipping_address
    address_text = _escape_markdown(f"{address.line1}, {address.city}") if address else "N/A"

    return (
        f"\U0001F195 *Yangi buyurtma*\n\n"
        f"\U0001F4E6 *{_escape_markdown(order.order_number.value)}*\n\n"
        f"\U0001F6CD Mahsulotlar:\n{lines_text}\n\n"
        f"\U0001F4B0 *Jami: {_format_amount(total.grand_total.amount)} {total.grand_total.currency}*\n\n"
        f"\U0001F4CD Manzil: {address_text}\n"
        f"\U0001F4B5 To'lov: Naqd"
    )
