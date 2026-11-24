"""Tests for utils/text.py."""

import unicodedata

import pytest

from utils.text import escape_text


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("\x1b[2J", "\\x1b[2J"),
        ("a\r\nb\t\0\x07\x7f", "a\\r\\nb\\t\\x00\\x07\\x7f"),
        ("\x85\x9b31m", "\\x85\\x9b31m"),
        ("\u202egpj\u2066\u061c", "\\u202egpj\\u2066\\u061c"),
        ("\u2028\u2029\u200d\ufeff", "\\u2028\\u2029\\u200d\\ufeff"),
        ("\U000e0041", "\\U000e0041"),
        ("\udcff", "\\udcff"),
    ],
    ids=["esc", "c0", "c1", "bidi", "separators", "tags", "surrogate"],
)
def test_unsafe_characters_become_visible_codes(text: str, shown: str) -> None:
    assert escape_text(text) == shown


def test_ordinary_text_is_unchanged() -> None:
    text = "Plain text, café, 日本語, العربية, 🎵 ~ C:\\folder"
    assert escape_text(text) == text


def test_no_control_or_format_character_survives() -> None:
    every_character = "".join(map(chr, range(0x110000)))
    shown = escape_text(every_character)
    assert {unicodedata.category(character) for character in set(shown)}.isdisjoint(
        {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
    )
