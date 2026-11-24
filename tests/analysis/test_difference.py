"""Tests for audiosteg/analysis/difference.py."""

import io
import wave
from collections.abc import Callable
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from conftest import pack

from audiosteg.analysis import samples
from audiosteg.analysis.difference import (
    choose_gain,
    safe_peak,
    write_difference,
    write_encoded,
    write_original,
)
from audiosteg.analysis.samples import Part, open_pair, to_values
from audiosteg.errors import UnsupportedFormatError

PEAKS = {8: 32, 16: 8230, 24: 2107123, 32: 539423503}


def amplified(paths: tuple[str, str], gain: Fraction, first: int = 0, frames: int | None = None) -> list[int]:
    target = io.BytesIO()
    with open_pair(*paths) as pair:
        part = Part(first, pair.frames if frames is None else frames)
        write_difference(target, pair, part, gain)
    with wave.open(io.BytesIO(target.getvalue())) as audio:
        assert audio.getparams()[:4] == (*pair.format, part.frames)
        return to_values(audio.readframes(part.frames), pair.format.sample_width)


@pytest.mark.parametrize("bits", PEAKS)
def test_the_safe_level_is_the_largest_whole_number_12_db_below_the_maximum(bits: int) -> None:
    full = 2 ** (bits - 1)
    assert safe_peak(full) == PEAKS[bits]
    with localcontext(prec=40):
        limit = Decimal(full) * Decimal(10) ** (Decimal(-12) / 20)
    assert PEAKS[bits] <= limit < PEAKS[bits] + 1


@pytest.mark.parametrize("bits", PEAKS)
@pytest.mark.parametrize("wanted", [None, Fraction(1), Fraction(10**9)])
def test_no_sample_ever_passes_the_safe_level(
    make_pair: Callable[..., tuple[str, str]], bits: int, wanted: Fraction | None
) -> None:
    full = 2 ** (bits - 1)
    for largest in (1, 2, 3, full // 4, PEAKS[bits], PEAKS[bits] + 1, full, 2 * full - 1):
        low = -full if largest > full // 2 else -largest // 2
        paths = make_pair([low, low + largest, 0], [low + largest, low, 0], bits)
        gain = choose_gain(largest, full, wanted)
        values = amplified(paths, gain)
        assert values[0] == -values[1] > 0
        assert values[0] <= PEAKS[bits]
        if wanted is None and largest > 1:
            assert values[0] > PEAKS[bits] - largest
        if wanted == 10**9:
            assert values[0] == PEAKS[bits]
        if wanted == 1 and largest <= PEAKS[bits]:
            assert values[0] == largest


@pytest.mark.parametrize(
    ("largest", "wanted", "gain"),
    [
        (1, None, Fraction(8230)),
        (3, None, Fraction(2743)),
        (8230, None, Fraction(1)),
        (8231, None, Fraction(8230, 8231)),
        (65535, None, Fraction(8230, 65535)),
        (3, Fraction(5, 2), Fraction(5, 2)),
        (3, Fraction(2744), Fraction(8230, 3)),
        (8230, Fraction(1), Fraction(1)),
        (8231, Fraction(1), Fraction(8230, 8231)),
    ],
)
def test_the_gain(largest: int, wanted: Fraction | None, gain: Fraction) -> None:
    assert choose_gain(largest, 32768, wanted) == gain


@pytest.mark.parametrize(
    ("change", "gain", "expected"),
    [
        (1, Fraction(3, 2), 2),
        (-1, Fraction(3, 2), -1),
        (3, Fraction(3, 2), 5),
        (-3, Fraction(3, 2), -4),
        (1, Fraction(149, 100), 1),
        (-1, Fraction(151, 100), -2),
        (5, Fraction(1, 2), 3),
        (4, Fraction(1, 10), 0),
        (7, Fraction(1, 3), 2),
        (8, Fraction(1, 3), 3),
    ],
)
def test_rounding_to_the_nearest_whole_number(
    make_pair: Callable[..., tuple[str, str]], change: int, gain: Fraction, expected: int
) -> None:
    assert amplified(make_pair([10], [10 + change]), gain) == [expected]


@pytest.mark.parametrize("bits", PEAKS)
@pytest.mark.parametrize("block_bytes", [1, 1 << 18])
def test_the_difference_is_the_encoded_file_minus_the_original(
    make_pair: Callable[..., tuple[str, str]], monkeypatch: pytest.MonkeyPatch, bits: int, block_bytes: int
) -> None:
    monkeypatch.setattr(samples, "BLOCK_BYTES", block_bytes)
    paths = make_pair([1, 2, 3, 4, -5, -6], [1, 2, 4, 2, -5, -3], bits, channels=2)
    assert amplified(paths, Fraction(2)) == [0, 0, 2, -4, 0, 6]
    assert amplified(paths, Fraction(2), 1, 1) == [2, -4]


def test_a_file_that_changes_while_it_is_read_is_never_too_loud(
    make_pair: Callable[..., tuple[str, str]],
) -> None:
    for encoded in ([0, 4, 0], [0, -4, 0]):
        paths = make_pair([0, 0, 0], encoded)
        with pytest.raises(UnsupportedFormatError, match="changed while it was being read"):
            amplified(paths, Fraction(8230, 3))


@pytest.mark.parametrize("bits", PEAKS)
def test_both_files_are_copied_exactly(make_pair: Callable[..., tuple[str, str]], bits: int) -> None:
    full = 2 ** (bits - 1)
    original, encoded = [-full, full - 1, 0, 1, 2, 3], [0, 0, -1, full - 1, 5, 6]
    with open_pair(*make_pair(original, encoded, bits, channels=3, frame_rate=44100)) as pair:
        for write, values in ((write_original, original), (write_encoded, encoded)):
            for part in (Part(0, 2), Part(1, 1)):
                target = io.BytesIO()
                write(target, pair, part)
                with wave.open(io.BytesIO(target.getvalue())) as audio:
                    assert audio.getparams()[:4] == (3, bits // 8, 44100, part.frames)
                    assert audio.readframes(9) == pack(values[3 * part.first : 6], bits)


def test_copies_have_nothing_but_the_audio(make_pair: Callable[..., tuple[str, str]]) -> None:
    paths = make_pair([1], [2])
    plain = Path(paths[0]).read_bytes()
    Path(paths[0]).write_bytes(plain + b"LIST\x04\x00\x00\x00note")
    target = io.BytesIO()
    with open_pair(*paths) as pair:
        write_original(target, pair, Part(0, 1))
    assert target.getvalue() == plain
