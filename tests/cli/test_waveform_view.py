"""Tests for audiosteg/cli/waveform_view.py."""

import io

import pytest

from audiosteg.cli.waveform_view import blocks_for, draw_waveform

BLOCKS = " ▁▂▃▄▅▆▇█"


def test_a_waveform_with_every_level() -> None:
    lines = draw_waveform([0, 1, 3, 4, 8, 9, 31, 32], 32, BLOCKS)
    assert lines == ["      ▇█", "      ██", "     ▁██", " ▁▃▄████"]
    assert draw_waveform([0, 1, 2, 3, 4, 9, 11, 12], 12, " .:|") == [
        "      :|",
        "     |||",
        "    .|||",
        " .:|||||",
    ]


@pytest.mark.parametrize("blocks", [BLOCKS, " .:|"])
def test_the_smallest_number_is_visible_and_the_top_is_full(blocks: str) -> None:
    top = 2**31
    smallest, half, full = zip(*draw_waveform([1, top // 2, top], top, blocks), strict=True)
    assert "".join(smallest) == f"   {blocks[1]}"
    assert "".join(full) == blocks[-1] * 4
    assert "".join(draw_waveform([0], top, blocks)) == "    "
    assert "".join(half) == "  " + blocks[-1] * 2


def test_silence_and_no_columns() -> None:
    assert draw_waveform([0, 0], 0, BLOCKS) == ["  "] * 4
    assert draw_waveform([], 0, BLOCKS) == [""] * 4


@pytest.mark.parametrize(
    ("encoding", "drawn", "expected"),
    [
        ("utf-8", True, BLOCKS),
        ("utf-8", False, " .:|"),
        ("cp437", True, " .:|"),
        ("ascii", True, " .:|"),
    ],
)
def test_characters_that_the_output_can_show(encoding: str, drawn: bool, expected: str) -> None:
    assert blocks_for(io.TextIOWrapper(io.BytesIO(), encoding=encoding), drawn) == expected
