from apps.telegram_bot.infrastructure.telegram_html import sanitize, to_plain, visible_length


class TestSanitize:
    def test_plain_text_is_escaped(self):
        assert sanitize("2 < 3 & 5 > 4") == "2 &lt; 3 &amp; 5 &gt; 4"

    def test_editor_blocks_become_newlines(self):
        assert sanitize("<div>Salom</div><div>Dunyo</div>") == "Salom\nDunyo"
        assert sanitize("<p>A</p><p><br></p><p>B</p>") == "A\n\nB"
        assert sanitize("A<br>B") == "A\nB"

    def test_inline_tags_are_mapped(self):
        assert sanitize("<strong>x</strong> <em>y</em> <ins>z</ins> <del>w</del>") == "<b>x</b> <i>y</i> <u>z</u> <s>w</s>"

    def test_spoiler_quote_and_code(self):
        assert sanitize('<span class="tg-spoiler">sir</span>') == "<tg-spoiler>sir</tg-spoiler>"
        assert sanitize("<blockquote>iqtibos</blockquote>") == "<blockquote>iqtibos</blockquote>"
        assert sanitize('<blockquote class="expandable">uzun</blockquote>') == "<blockquote expandable>uzun</blockquote>"
        assert sanitize("<code>NZ-10</code>") == "<code>NZ-10</code>"

    def test_lists(self):
        assert sanitize("<ul><li>Bir</li><li>Ikki</li></ul>") == "• Bir\n• Ikki"
        assert sanitize("<ol><li>Bir</li><li>Ikki</li></ol>") == "1. Bir\n2. Ikki"

    def test_links_only_safe_schemes(self):
        assert sanitize('<a href="https://nutrizone.uz/p?a=1&b=2">Sayt</a>') == '<a href="https://nutrizone.uz/p?a=1&amp;b=2">Sayt</a>'
        assert sanitize('<a href="javascript:alert(1)">x</a>') == "x"

    def test_unknown_tags_and_scripts_are_dropped(self):
        assert sanitize('<span style="color:red">qizil</span><script>alert(1)</script><font>f</font>') == "qizilf"

    def test_misnested_and_unclosed_tags_are_balanced(self):
        assert sanitize("<b>qalin <i>ikkalasi</b> kursiv</i>") == "<b>qalin <i>ikkalasi</i></b><i> kursiv</i>"
        assert sanitize("<b>ochiq qoldi") == "<b>ochiq qoldi</b>"

    def test_empty_formatting_removed(self):
        assert sanitize("<b></b>Matn<i> </i>") == "Matn"


def test_to_plain_and_length():
    html = sanitize('<b>Aksiya</b> -20% <a href="https://nutrizone.uz">sayt</a>')
    assert to_plain(html) == "Aksiya -20% sayt (https://nutrizone.uz)"
    assert visible_length("<b>a&amp;b</b>") == 3
