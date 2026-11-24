"""Tests for audiosteg/cli/logo.py."""

import hashlib
from typing import Any

import pytest

from audiosteg.cli.logo import COLOURS, PIXELS, draw_logo


def test_the_approved_pixels() -> None:
    assert len(PIXELS) == 20
    assert {len(row) for row in PIXELS} == {30}
    colours = ",".join(COLOURS.get(pixel, "") for row in PIXELS for pixel in row)
    assert (
        hashlib.sha256(colours.encode()).hexdigest()
        == "661b8f2a8bfede0af612eca405c9541f212028506d1ba409a227376392b52f09"
    )
    assert max(len(line) for line in draw_logo().plain.split("\n")) < 80


@pytest.mark.parametrize(
    ("columns", "changes", "drawn"),
    [
        (80, {"COLORTERM": "truecolor"}, True),
        (79, {"COLORTERM": "truecolor"}, False),
        (80, {}, False),
        (80, {"COLORTERM": "truecolor", "NO_COLOR": "1"}, False),
        (80, {"COLORTERM": "truecolor", "PYTHONIOENCODING": "ascii"}, False),
        (80, {"COLORTERM": "truecolor", "PYTHONIOENCODING": "cp1252"}, False),
    ],
)
def test_the_logo_is_replaced_by_text_where_it_cannot_be_drawn(
    terminal: Any, columns: int, changes: dict[str, str], drawn: bool
) -> None:
    program = terminal(columns=columns, **changes)
    program.answer("What would you like to do?", "\x03")
    assert program.finish() == 130
    assert ("▀" in program.seen) is drawn
    assert "Audio Steganography CLI" in program.seen
