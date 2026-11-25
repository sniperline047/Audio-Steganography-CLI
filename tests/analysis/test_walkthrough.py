"""Tests for audiosteg/analysis/walkthrough.py."""

import hashlib
import hmac
from collections.abc import Callable
from dataclasses import replace
from itertools import islice
from pathlib import Path

import pytest
from conftest import pack

from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_4 import LSB_4
from audiosteg.algorithms.lsb_keyed import LSB_KEYED
from audiosteg.algorithms.lsb_matching import LSB_MATCHING
from audiosteg.algorithms.lsb_parity import LSB_PARITY
from audiosteg.analysis import walkthrough
from audiosteg.analysis.walkthrough import largest_possible_change, walk_through
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.scatter import scatter
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
@pytest.mark.parametrize(("algorithm", "size"), [(LSB, 1), (LSB_2, 2), (LSB_4, 4)])
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
        (2, 1, "h", LSB_4, True),
        (1, 1, "h", LSB_4, False),
        (64, 1, "h", LSB_PARITY, True),
        (63, 1, "h", LSB_PARITY, False),
        (66, 3, "h", LSB_PARITY, True),
        (432, 1, "h", LSB_KEYED, True),
        (431, 1, "h", LSB_KEYED, False),
        (430, 2, "h", LSB_KEYED, False),
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
    assert [largest_possible_change(known) for known in (LSB, LSB_2, LSB_4)] == [1, 3, 15]
    assert [largest_possible_change(known) for known in (LSB_MATCHING, LSB_PARITY, LSB_KEYED)] == [1, 1, 1]
    flip = Algorithm("", 1, lambda byte, bits: byte ^ (128 * bits[0]), lambda byte: (byte >> 7,))
    assert largest_possible_change(flip) == 128
    down = Algorithm("", 1, lambda byte, bits: byte if bits[0] else max(byte - 5, 0), lambda byte: (0,))
    assert largest_possible_change(down) == 5
    last = Algorithm("", 1, lambda byte, bits: 0 if byte == 255 else byte, lambda byte: (0,))
    assert largest_possible_change(last) == 255


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


@pytest.mark.parametrize("bits", [8, 16, 24, 32])
@pytest.mark.parametrize(("choice", "step"), [(0, -1), (1, 1)])
def test_matching_moves_whole_samples(
    make_samples: Callable[..., Path], bits: int, choice: int, step: int
) -> None:
    smallest, largest = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
    values = [smallest, largest, 63, 64, -1, 0, 1, -64]
    algorithm = replace(LSB_MATCHING, choose=lambda limit: choice)
    steps = walk_through(str(make_samples("a.wav", values, bits)), "\x55", algorithm)
    for index, change in enumerate(steps.changes):
        wrong = values[index] % 2 != index % 2
        safe = {smallest: 1, largest: -1}.get(values[index], step)
        assert change.change == (safe if wrong else 0)
        assert change.byte_after == pack([values[index] + change.change], bits)[0]
    assert steps.read_back == "\x55"


@pytest.mark.parametrize("bits", [8, 16, 24, 32])
@pytest.mark.parametrize("channels", [1, 3])
def test_parity_changes_the_chosen_sample_of_a_group(
    make_samples: Callable[..., Path], bits: int, channels: int
) -> None:
    values = [100] + [(index * 7) % 50 - 25 for index in range(66 * channels - 1)]
    algorithm = replace(LSB_PARITY, choose=lambda limit: 5)
    steps = walk_through(str(make_samples("a.wav", values, bits, channels)), "h", algorithm)
    assert (len(steps.changes), len(steps.groups), steps.read_back) == (64, 8, "h")
    for index, (group, digit) in enumerate(zip(steps.groups, "01101000", strict=True)):
        before = values[index * 8 : index * 8 + 8]
        assert [sample.value_before for sample in group.samples] == before
        assert [sample.position for sample in group.samples] == list(range(index * 8, index * 8 + 8))
        assert group.number == index + 1
        wrong = sum(value % 2 for value in before) % 2 != int(digit)
        assert (group.changed is group.samples[5]) is wrong
        assert (group.changed is None) is not wrong
        assert sum(sample.value_after % 2 for sample in group.samples) % 2 == int(digit)


@pytest.mark.parametrize(("bits", "channels"), [(8, 1), (16, 2), (24, 1), (32, 3)])
def test_the_places_of_a_keyed_message_are_those_of_the_demo_seed(
    make_samples: Callable[..., Path], bits: int, channels: int
) -> None:
    values = [index % 100 - 50 for index in range(600)]
    path = make_samples("a.wav", values, bits, channels)
    before = path.read_bytes()
    steps = walk_through(str(path), "h", LSB_KEYED)
    key = hashlib.sha256(b"audiosteg demo").digest()
    order_key = hmac.new(key, b"audiosteg keyed 1: order\x01", hashlib.sha256).digest()
    places = [128 + number for number in islice(scatter(order_key, 472), 8)]
    assert [change.position for change in steps.changes] == places
    assert [change.value_before for change in steps.changes] == [values[place] for place in places]
    assert [change.value_after % 2 for change in steps.changes] == [0, 1, 1, 0, 1, 0, 0, 0]
    assert (steps.first_frame, steps.read_back) == (min(places) // channels, "h")
    assert path.read_bytes() == before


def test_no_passphrase_library_is_needed_to_explain(
    make_samples: Callable[..., Path], no_library: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(hashlib, "scrypt", raising=False)
    path = str(make_samples("a.wav", [100] * 500))
    assert walk_through(path, "h", LSB_KEYED).read_back == "h"
