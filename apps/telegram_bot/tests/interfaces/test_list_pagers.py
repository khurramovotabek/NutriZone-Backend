"""Bot list pagers: brands / categories / my orders page in place, the product card jumps ten or to either end."""
from __future__ import annotations

from apps.telegram_bot.interfaces import callback_router as cr


def _cbs(keyboard):
    return [b.get("callback_data") for row in keyboard for b in row]


def test_pager_row_ends_and_middle():
    assert cr._pager_row("menu:brands", 1, 1) == []
    first = cr._pager_row("menu:brands", 1, 3)[0]
    assert [b["callback_data"] for b in first] == ["pc:noop", "pc:noop", "menu:brands:2"] and first[1]["text"] == "1 / 3"
    mid = cr._pager_row("menu:orders", 2, 3)[0]
    assert [b["callback_data"] for b in mid] == ["menu:orders:1", "pc:noop", "menu:orders:3"]


def test_brands_are_paged_two_per_row_and_a_pager_tap_edits_in_place(monkeypatch):
    from apps.telegram_bot.application.services import shopping

    brands = [{"id": f"b{i}", "name": f"Brand {i:02d}"} for i in range(40)]
    monkeypatch.setattr(shopping.TelegramCatalogService, "list_brands", lambda self, locale="uz": brands)
    sent = []
    monkeypatch.setattr(cr, "_send_or_edit", lambda chat_id, edit_id, text, kb: sent.append((edit_id, text, kb)))

    cr._handle_menu(None, 1, "brands", None, "uz", {"message_id": 7})
    edit_id, text, kb = sent[-1]
    assert edit_id == "" and "40 · 1/3" in text
    assert all(len(row) == 2 for row in kb if row[0]["callback_data"].startswith("catalog:")) and "catalog:brand:b15" in _cbs(kb) and "catalog:brand:b16" not in _cbs(kb)
    assert "menu:brands:2" in _cbs(kb)

    cr._handle_menu(None, 1, "brands", "3", "uz", {"message_id": 7})
    edit_id, text, kb = sent[-1]
    assert edit_id == "7" and "catalog:brand:b39" in _cbs(kb) and "menu:brands:2" in _cbs(kb)
    cr._handle_menu(None, 1, "brands", "99", "uz", {"message_id": 7})  # past the end: the last page
    assert "catalog:brand:b39" in _cbs(sent[-1][2])


def test_product_card_has_fast_jumps_only_for_long_lists():
    product = {"default_variant_id": None}
    assert "pc:p10" not in _cbs(cr._product_card_keyboard(product, 1, 8, "uz", False))
    kb = cr._product_card_keyboard(product, 1, 40, "uz", False)
    assert {"pc:first", "pc:m10", "pc:p10", "pc:last"} <= set(_cbs(kb))
    assert "pc:prev" not in _cbs(kb)  # nothing before the first product


def test_jumps_clamp_and_skip_needless_edits(monkeypatch):
    from apps.telegram_bot.interfaces import catalog_state

    moved = []
    monkeypatch.setattr(cr, "_resolve_current_product", lambda state, lang: ({}, 40))
    monkeypatch.setattr(catalog_state, "set_page", lambda chat_id, page: moved.append(page) or {"page": page})
    monkeypatch.setattr(cr, "_render_browse", lambda *a, **k: None)
    for action, page, want in (("p10", 35, 40), ("m10", 5, 1), ("last", 3, 40), ("first", 9, 1), ("next", 1, 2)):
        cr._pc_paginate(None, 1, "uz", "5", {"page": page}, action)
        assert moved[-1] == want
    n = len(moved)
    cr._pc_paginate(None, 1, "uz", "5", {"page": 40}, "last")
    assert len(moved) == n  # already on the last product
