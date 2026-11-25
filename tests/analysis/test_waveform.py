"""Tests for audiosteg/analysis/waveform.py."""

from collections.abc import Callable

import pytest

from audiosteg.analysis import samples
from audiosteg.analysis.samples import Part, open_pair
from audiosteg.analysis.waveform import columns_of, difference_peaks, peaks


@pytest.mark.parametrize("block_bytes", [1, 1 << 18])
@pytest.mark.parametrize("bits", [8, 16, 24, 32])
def test_every_column_has_its_largest_sample_and_change(
    make_pair: Callable[..., tuple[str, str]], monkeypatch: pytest.MonkeyPatch, bits: int, block_bytes: int
) -> None:
    monkeypatch.setattr(samples, "BLOCK_BYTES", block_bytes)
    full = 2 ** (bits - 1)
    original = [1, -7, 0, 0, 3, 2, -full, 0, full - 1, 0, 0, 0]
    encoded = [1, -9, 0, 1, 3, 2, full - 1, 0, full - 2, 0, 0, 0]
    with open_pair(*make_pair(original, encoded, bits, channels=2)) as pair:
        assert peaks(pair.original, Part(0, 6), 6) == [7, 0, 3, full, full - 1, 0]
        assert peaks(pair.original, Part(0, 6), 2) == [7, full]
        assert peaks(pair.encoded, Part(0, 6), 4) == [9, 3, full - 1, full - 2]
        assert difference_peaks(pair, Part(0, 6), 6) == [2, 1, 0, 2 * full - 1, 1, 0]
        assert difference_peaks(pair, Part(0, 6), 4) == [2, 1, 2 * full - 1, 1]
        assert peaks(pair.original, Part(2, 1), 80) == [3]
        assert difference_peaks(pair, Part(4, 2), 500) == [1, 0]


@pytest.mark.parametrize(
    ("frames", "columns", "expected"),
    [(0, 5, 0), (1, 80, 1), (79, 80, 79), (80, 80, 80), (81, 80, 80), (1000, 80, 80)],
)
def test_there_are_never_more_columns_than_frames(frames: int, columns: int, expected: int) -> None:
    parts = columns_of(Part(7, frames), columns)
    assert len(parts) == expected
    assert sum(part.frames for part in parts) == frames
    assert all(part.frames for part in parts)
