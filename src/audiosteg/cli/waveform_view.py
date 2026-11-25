"""Draw waveforms with characters."""

from collections.abc import Sequence
from typing import TextIO

HEIGHT = 4
BLOCKS = " ▁▂▃▄▅▆▇█"
ASCII_BLOCKS = " .:|"


def blocks_for(stream: TextIO, drawn: bool) -> str:
    """Return the characters for a cell, from empty to full, that the stream can show."""
    if not drawn:
        return ASCII_BLOCKS
    try:
        BLOCKS.encode(stream.encoding)
    except UnicodeEncodeError:
        return ASCII_BLOCKS
    return BLOCKS


def draw_waveform(peaks: Sequence[int], top: int, blocks: str) -> list[str]:
    """
    Draw one column for each number, from the bottom up.

    :param peaks: Numbers from 0 to the top
    :param top: The number that fills the whole height
    :param blocks: The characters for a cell, from empty to full
    :return: The lines, the highest first. Every number above 0 is visible.
    """
    full = len(blocks) - 1
    levels = [-(-peak * HEIGHT * full // top) if top else 0 for peak in peaks]
    return [
        "".join(blocks[min(max(level - row * full, 0), full)] for level in levels)
        for row in reversed(range(HEIGHT))
    ]
