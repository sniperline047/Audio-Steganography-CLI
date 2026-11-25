"""Tests for audiosteg/core/signal_samples.py."""

import random

import pytest
from conftest import pack

from audiosteg.core.signal_samples import largest_number, mix_channels, sample_bytes, to_numbers, to_stored

pytestmark = pytest.mark.needs_signal


def limits(width: int) -> tuple[int, int]:
    return -(1 << 8 * width - 1), (1 << 8 * width - 1) - 1


def some_values(width: int) -> list[int]:
    smallest, largest = limits(width)
    chooser = random.Random(width)
    edges = [smallest, smallest + 1, -1, 0, 1, largest - 1, largest]
    return edges + [chooser.randint(smallest, largest) for _ in range(93)]


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2, 5])
def test_every_sample_becomes_its_number_and_back(width: int, channels: int) -> None:
    values = some_values(width)
    stored = pack(values, 8 * width)
    view = sample_bytes(stored, channels, width)
    assert view.shape == (len(values) // channels, channels, width)
    numbers = to_numbers(view)
    assert numbers.ravel().tolist() == values
    assert to_stored(numbers, width).tobytes() == stored


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_numbers_are_rounded_and_never_wrap_around(width: int) -> None:
    import numpy as np

    smallest, largest = limits(width)
    assert largest_number(width) == largest
    numbers = np.array([smallest - 1e9, smallest - 0.6, largest + 0.6, largest * 4.0, 0.4, -0.6, 1.5, 2.5])
    expected = [smallest, smallest, largest, largest, 0, -1, 2, 2]
    assert to_stored(numbers, width).tobytes() == pack(expected, 8 * width)


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_channels_are_added_without_a_limit(width: int) -> None:
    smallest, largest = limits(width)
    stored = pack([largest, largest, largest, smallest, smallest, smallest, 1, 2, -4], 8 * width)
    assert mix_channels(stored, 3, width).tolist() == [3 * largest, 3 * smallest, -1]


def test_a_view_changes_the_frames_themselves() -> None:
    frames = bytearray(8)
    sample_bytes(frames, 2, 2)[1, 0] = [7, 9]
    assert frames == bytes([0, 0, 0, 0, 7, 9, 0, 0])


def test_no_frames_at_all() -> None:
    assert mix_channels(b"", 2, 3).tolist() == []
