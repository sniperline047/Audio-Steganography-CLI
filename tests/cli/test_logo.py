"""Tests for audiosteg/cli/logo.py."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL

from audiosteg.cli.logo import COLOURS, PIXELS, draw_logo

MENU = ("What would you like to do?", "\x03")
TRUECOLOUR = {"COLORTERM": "truecolor", "columns": 80}


def rgb(colour: str) -> str:
    return ";".join(str(int(colour[start : start + 2], 16)) for start in (1, 3, 5))


def cell(upper: str, lower: str) -> str:
    """Return how a terminal draws two pixels, one above the other."""
    if upper == lower == ".":
        return " "
    if upper == ".":
        return f"\x1b[38;2;{rgb(COLOURS[lower])}m▄\x1b[0m"
    background = "" if lower == "." else f";48;2;{rgb(COLOURS[lower])}"
    return f"\x1b[38;2;{rgb(COLOURS[upper])}{background}m▀\x1b[0m"


def test_the_approved_pixels() -> None:
    assert len(PIXELS) == 20
    assert {len(row) for row in PIXELS} == {30}
    colours = ",".join(COLOURS.get(pixel, "") for row in PIXELS for pixel in row)
    assert (
        hashlib.sha256(colours.encode()).hexdigest()
        == "661b8f2a8bfede0af612eca405c9541f212028506d1ba409a227376392b52f09"
    )
    assert max(len(line) for line in draw_logo().plain.split("\n")) < 80


def test_a_terminal_draws_every_pixel(run: Any) -> None:
    result = run(prompts=(MENU,), terminals=ALL, **TRUECOLOUR)
    lines = result.seen.split("\n")
    assert lines[0] == ""
    texts = {3: "Audio Steganography CLI", 4: "Hide messages in sound, and see how it works"}
    for number in range(10):
        pairs = zip(PIXELS[number * 2], PIXELS[number * 2 + 1], strict=True)
        drawn = "".join(cell(upper, lower) for upper, lower in pairs)
        assert lines[number + 1].rstrip() == f"  {drawn}   {texts.get(number, '')}".rstrip()


@pytest.mark.parametrize(
    "changes",
    [
        {"columns": 79},
        {"COLORTERM": ""},
        {"NO_COLOR": "1"},
        {"TERM": "xterm", "COLORTERM": ""},
        {"encoding": "ascii"},
        {"encoding": "cp1252"},
    ],
)
def test_the_logo_is_replaced_by_text_where_it_cannot_be_drawn(run: Any, changes: dict[str, Any]) -> None:
    result = run(prompts=(MENU,), terminals=ALL, **{**TRUECOLOUR, **changes})
    assert result.code == 130
    assert "▀" not in result.seen
    assert "Audio Steganography CLI\nHide messages in sound, and see how it works\n" in result.text


def test_plain_has_no_logo(run: Any) -> None:
    result = run("--plain", prompts=(MENU,), terminals=ALL, **TRUECOLOUR)
    assert "▀" not in result.seen
    assert result.seen.startswith("Audio Steganography CLI\n")


def test_commands_have_no_logo(run: Any, make_wav: Callable[..., Path]) -> None:
    make_wav()
    for words in (["algorithms"], ["hide", "input.wav", "-m", "x"], ["--version"], ["--help"], ["hide"]):
        result = run(*words, terminals=ALL, **TRUECOLOUR)
        assert "▀" not in result.seen
        assert "Audio Steganography CLI" not in result.seen
