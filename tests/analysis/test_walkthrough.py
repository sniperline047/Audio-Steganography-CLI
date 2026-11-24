"""Tests for audiosteg/analysis/walkthrough.py."""

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import pack

from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.analysis import walkthrough
from audiosteg.analysis.walkthrough import largest_possible_change, walk_through
from audiosteg.core.algorithm import Algorithm
from audiosteg.errors import CapacityError, InvalidMessageError

LOUD = [20000, -20000, 19999, -19999, 12345, -12345, 1, -1]


@pytest.mark.parametrize(
    ("letter", "stored"),
    [
        ("h", "68"),
        ("\0", "00"),
        ("é", "c3a9"),
        ("☕", "e29895"),
        ("🎵", "f09f8eb5"),
        ("\U0010ffff", "f48fbfbf"),
    ],
)
@pytest.mark.parametrize(("algorithm", "size"), [(LSB, 1), (LSB_2, 2)])
@pytest.mark.parametrize("bits", [8, 16, 24, 32])
@pytest.mark.parametrize("channels", [1, 3])
def test_every_step_as_calculated_by_hand(
    make_samples: Callable[..., Path],
    letter: str,
    stored: str,
    algorithm: Algorithm,
    size: int,
    bits: int,
    channels: int,
) -> None:
    values = [(value * 3) % 2**bits - 2 ** (bits - 1) for value in range(17, 17 + 36 * channels)]
    values[0] = -(2 ** (bits - 1))
    path = make_samples("a.wav", values, bits, channels)
    before = path.read_bytes()
    steps = walk_through(str(path), letter, algorithm)
    digits = "".join(f"{byte:08b}" for byte in bytes.fromhex(stored))
    assert (steps.letter, steps.data.hex(), steps.read_back) == (letter, stored, letter)
    assert (steps.first_frame, steps.silent, len(steps.changes)) == (0, False, len(digits) // size)
    for index, change in enumerate(steps.changes):
        group = digits[index * size : (index + 1) * size]
        value = values[index]
        expected = value - value % 2**size + int(group, 2)
        assert (change.number, change.hidden_bits) == (index + 1, tuple(map(int, group)))
        assert (change.value_before, change.value_after) == (value, expected)
        assert change.change == expected - value
        assert change.byte_before == pack([value], bits)[0]
        assert change.byte_after == pack([expected], bits)[0]
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("values", "channels", "frame", "silent"),
    [
        ([0] * 30, 1, 0, True),
        ([0] * 10 + [5] + [0] * 19, 1, 10, False),
        ([0] * 10 + [-5] + [0] * 19, 1, 10, False),
        ([0] * 10 + [5, 6, -7, 7] + [0] * 16, 1, 12, False),
        ([0] * 29 + [9], 1, 22, False),
        ([0] * 22 + [9] + [0] * 7, 1, 22, False),
        ([0] * 21 + [9, 1] + [0] * 7, 2, 10, False),
        ([0] * 29 + [9], 2, 11, False),
        ([0] * 8, 1, 0, True),
        ([9] * 8, 1, 0, False),
    ],
)
def test_the_loudest_place_that_leaves_room_is_used(
    make_samples: Callable[..., Path], values: list[int], channels: int, frame: int, silent: bool
) -> None:
    steps = walk_through(str(make_samples("a.wav", values, channels=channels)), "h", LSB)
    assert (steps.first_frame, steps.silent) == (frame, silent)
    assert steps.changes[0].value_before == values[frame * channels]


@pytest.mark.parametrize(("quiet", "frame"), [(2048, 1), (2047, 5)])
def test_the_search_ends_at_the_first_place_that_is_not_quiet(
    make_samples: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, quiet: int, frame: int
) -> None:
    monkeypatch.setattr(walkthrough, "SCAN_FRAMES", 4)
    values = [0, quiet, 0, 0, 0, 30000] + [0] * 20
    assert walk_through(str(make_samples("a.wav", values)), "h", LSB).first_frame == frame


def test_a_later_place_must_be_louder(
    make_samples: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(walkthrough, "SCAN_FRAMES", 4)
    values = [0, 0, 7, 0, 7, 0, 0, 0, 6] + [0] * 20
    assert walk_through(str(make_samples("a.wav", values)), "h", LSB).first_frame == 2


@pytest.mark.parametrize(
    ("samples", "channels", "letter", "algorithm", "fits"),
    [
        (8, 1, "h", LSB, True),
        (7, 1, "h", LSB, False),
        (4, 1, "h", LSB_2, True),
        (3, 1, "h", LSB_2, False),
        (32, 1, "🎵", LSB, True),
        (31, 1, "🎵", LSB, False),
        (9, 3, "h", LSB, True),
        (6, 3, "h", LSB, False),
        (255, 255, "🎵", LSB, True),
        (0, 1, "h", LSB, False),
    ],
)
def test_a_file_that_is_almost_too_short(
    make_samples: Callable[..., Path],
    samples: int,
    channels: int,
    letter: str,
    algorithm: Algorithm,
    fits: bool,
) -> None:
    path = str(make_samples("a.wav", [100] * samples, channels=channels))
    if fits:
        assert walk_through(path, letter, algorithm).read_back == letter
    else:
        with pytest.raises(CapacityError, match="too short to hide one character"):
            walk_through(path, letter, algorithm)


def test_half_of_a_character_is_not_text(make_samples: Callable[..., Path]) -> None:
    with pytest.raises(InvalidMessageError):
        walk_through(str(make_samples("a.wav", LOUD * 4)), "\ud83c", LSB)


def test_the_largest_change_is_computed_from_the_algorithm() -> None:
    assert (largest_possible_change(LSB), largest_possible_change(LSB_2)) == (1, 3)
    flip = Algorithm("", 1, lambda byte, bits: byte ^ (128 * bits[0]), lambda byte: (byte >> 7,))
    assert largest_possible_change(flip) == 128
    down = Algorithm("", 1, lambda byte, bits: byte if bits[0] else max(byte - 5, 0), lambda byte: (0,))
    assert largest_possible_change(down) == 5


def test_a_new_algorithm_is_explained_with_its_own_functions(make_samples: Callable[..., Path]) -> None:
    whole = Algorithm(
        "",
        8,
        lambda byte, bits: int("".join(map(str, bits)), 2),
        lambda byte: tuple(int(bit) for bit in f"{byte:08b}"),
    )
    steps = walk_through(str(make_samples("a.wav", [0x1234] * 3)), "é", whole)
    assert [change.value_after for change in steps.changes] == [0x12C3, 0x12A9]
    assert steps.read_back == "é"
