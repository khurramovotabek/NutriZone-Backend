"""Short in-process memos that keep assistant answers fast; tests run with CATALOG_CANDIDATES_TTL=0 (no memo)."""
import uuid
from unittest import mock

from apps.assistant.infrastructure import knowledge, tools


def test_product_detail_is_memoised_for_the_catalogue_ttl_and_handed_out_as_a_copy(settings):
    settings.CATALOG_CANDIDATES_TTL = 30
    pid = uuid.uuid4()
    tools._DETAILS.clear()
    with mock.patch("apps.products.infrastructure.selectors.ProductDetailSelector.get_by_id", return_value={"name": "X", "variants": []}) as get:
        first = tools._product_detail(pid, "uz")
        first["name"] = "changed by a caller"
        second = tools._product_detail(pid, "uz")
        tools._product_detail(pid, "ru")
    assert get.call_count == 2  # uz once, ru once
    assert second["name"] == "X"
    tools._DETAILS.clear()


def test_no_memo_when_the_ttl_is_zero(settings):
    settings.CATALOG_CANDIDATES_TTL = 0
    with mock.patch("apps.products.infrastructure.selectors.ProductDetailSelector.get_by_id", return_value={"name": "X"}) as get:
        tools._product_detail(uuid.uuid4(), "uz")
        tools._product_detail(uuid.uuid4(), "uz")
    assert get.call_count == 2


def test_knowledge_entry_stems_are_redone_when_its_text_changes():
    entry = mock.Mock(pk="k1", questions="kreatin qanday ichiladi", keywords="kreatin", title="Kreatin", answer_uz="a", answer_ru="", answer_en="")
    first = knowledge._prepared(entry)
    assert knowledge._prepared(entry) is first
    entry.keywords = "kreatin, protein"
    assert "prote" in knowledge._prepared(entry)[2]
    knowledge._PREPARED.pop("k1", None)
