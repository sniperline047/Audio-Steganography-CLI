"""Tests for audiosteg/cli/change_view.py."""

import pytest

from audiosteg.cli.change_view import bit_spans, mark_changed


@pytest.mark.parametrize(
    ("byte", "other", "groups"),
    [
        (0b00000000, 0b00000000, [("00000000", False)]),
        (0b10110100, 0b10110101, [("1011010", False), ("0", True)]),
        (0b10110111, 0b10110100, [("101101", False), ("11", True)]),
        (0b11111111, 0b01111110, [("1", True), ("111111", False), ("1", True)]),
        (0b11111111, 0b00000000, [("11111111", True)]),
    ],
)
def test_changed_bits_are_marked(byte: int, other: int, groups: list[tuple[str, bool]]) -> None:
    assert mark_changed(byte, other) == groups
    shown = "".join(text for text, _ in bit_spans(byte, other))
    assert shown == "".join(f"[{bits}]" if changed else bits for bits, changed in groups)
