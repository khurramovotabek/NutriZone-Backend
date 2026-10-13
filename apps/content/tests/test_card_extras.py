"""Blog cards carry an estimated reading time and, when no excerpt was written, an automatic one from the text."""
from apps.content.interfaces.api.v1.views import auto_excerpt, reading_minutes


def test_reading_minutes_counts_words_without_tags():
    assert reading_minutes("") == 1
    assert reading_minutes("<p>" + "so'z " * 610 + "</p>") == 4


def test_auto_excerpt_strips_markup_and_cuts_at_a_word():
    assert auto_excerpt("## Kreatin\n**eng** kerakli [ozuqa](https://x.uz)") == "Kreatin eng kerakli ozuqa"
    long = auto_excerpt("kreatin " * 60)
    assert long.endswith("…") and len(long) <= 172 and not long[:-1].endswith(" ")
