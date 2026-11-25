"""Find the largest samples along a WAV file, so that a waveform can be drawn."""

import wave
from collections.abc import Iterable
from operator import sub

from audiosteg.analysis.samples import Pair, Part, read_blocks, read_format, read_pairs, to_values


def largest(values: Iterable[int], so_far: int) -> int:
    """Return the largest distance from silence."""
    numbers = list(values)
    return max(so_far, max(numbers), -min(numbers))


def columns_of(part: Part, columns: int) -> list[Part]:
    """Split a part into this many columns, or into fewer if it is shorter."""
    return part.split(min(columns, part.frames)) if part.frames else []


def peaks(audio: wave.Wave_read, part: Part, columns: int) -> list[int]:
    """Return the largest sample of each column."""
    sample_width = read_format(audio).sample_width
    result = []
    for column in columns_of(part, columns):
        peak = 0
        for block in read_blocks(audio, column):
            peak = largest(to_values(block, sample_width), peak)
        result.append(peak)
    return result


def difference_peaks(pair: Pair, part: Part, columns: int) -> list[int]:
    """Return the largest change of each column."""
    width = pair.format.sample_width
    result = []
    for column in columns_of(part, columns):
        peak = 0
        for original, encoded in read_pairs(pair, column):
            if original != encoded:
                peak = largest(map(sub, to_values(encoded, width), to_values(original, width)), peak)
        result.append(peak)
    return result
