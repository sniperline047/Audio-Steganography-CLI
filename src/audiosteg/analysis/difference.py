"""Make the difference between two WAV files loud enough to hear, and never too loud."""

from collections.abc import Iterator
from fractions import Fraction
from operator import sub
from typing import BinaryIO

from audiosteg.analysis.samples import Pair, Part, read_blocks, read_pairs, to_bytes, to_values, write_wav

SAFE_LEVEL_DBFS = -12


def safe_peak(full_scale: int) -> int:
    """Return the largest sample that a difference may have."""
    return int(full_scale * 10 ** (SAFE_LEVEL_DBFS / 20))


def choose_gain(largest_change: int, full_scale: int, wanted: Fraction | None = None) -> Fraction:
    """
    Return how much to amplify a difference, so that no sample passes the safe level.

    :param largest_change: The largest change of a sample
    :param full_scale: The largest possible sample
    :param wanted: The amplification that was asked for, or None for as much as is safe
    """
    highest = Fraction(safe_peak(full_scale), largest_change)
    if wanted is not None:
        return min(wanted, highest)
    return Fraction(int(highest)) if highest >= 1 else highest


def amplified_blocks(pair: Pair, part: Part, gain: Fraction) -> Iterator[bytes]:
    """Yield the amplified difference, rounded to whole numbers."""
    width = pair.format.sample_width
    up, down = 2 * gain.numerator, 2 * gain.denominator
    half = gain.denominator
    silence = to_bytes([0], width)
    for original, encoded in read_pairs(pair, part):
        if original == encoded:
            yield silence * (len(original) // width)
        else:
            changes = map(sub, to_values(encoded, width), to_values(original, width))
            yield to_bytes([(change * up + half) // down for change in changes], width)


def write_difference(destination: BinaryIO, pair: Pair, part: Part, gain: Fraction) -> None:
    """Write the amplified difference as a WAV file."""
    write_wav(destination, pair.format, part.frames, amplified_blocks(pair, part, gain))


def write_original(destination: BinaryIO, pair: Pair, part: Part) -> None:
    """Write a part of the original as a WAV file."""
    write_wav(destination, pair.format, part.frames, read_blocks(pair.original, part))


def write_encoded(destination: BinaryIO, pair: Pair, part: Part) -> None:
    """Write a part of the encoded file as a WAV file."""
    write_wav(destination, pair.format, part.frames, read_blocks(pair.encoded, part))
