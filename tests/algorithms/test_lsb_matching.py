"""Tests for audiosteg/algorithms/lsb_matching.py."""

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from audiosteg import CapacityError, decode, encode
from audiosteg.algorithms.lsb import LSB
from audiosteg.algorithms.lsb_matching import LSB_MATCHING

CONTAINER = bytes.fromhex("4153544701000000000348c3a9a411cc3b")
DOWN = replace(LSB_MATCHING, choose=lambda limit: 0)
UP = replace(LSB_MATCHING, choose=lambda limit: 1)


def to_numbers(frames: bytes, width: int) -> list[int]:
    return [
        int.from_bytes(frames[start : start + width], "little", signed=width > 1)
        for start in range(0, len(frames), width)
    ]


def to_frames(numbers: list[int], width: int) -> bytes:
    return b"".join(number.to_bytes(width, "little", signed=width > 1) for number in numbers)


def limits(width: int) -> tuple[int, int]:
    return (0, 255) if width == 1 else (-(256**width) // 2, 256**width // 2 - 1)


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize(("algorithm", "step"), [(DOWN, -1), (UP, 1)])
def test_known_answer_samples(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    tmp_path: Path,
    width: int,
    channels: int,
    algorithm: Any,
    step: int,
) -> None:
    smallest, largest = limits(width)
    numbers = [
        smallest,
        largest,
        smallest + 1,
        largest - 1,
        0,
        1,
        *([] if width == 1 else [-1, 255, 256, -256]),
    ]
    numbers = (numbers * 200)[: 200 * channels]
    digits = "".join(f"{byte:08b}" for byte in CONTAINER)
    expected = list(numbers)
    for index, digit in enumerate(digits):
        if numbers[index] % 2 != int(digit):
            safe = {smallest: 1, largest: -1}.get(numbers[index], step)
            expected[index] += safe
    source = make_wav(frames=to_frames(numbers, width), sample_width=width, channels=channels)
    output = tmp_path / "output.wav"
    encode(str(source), str(output), "Hé", algorithm)
    assert to_numbers(read_frames(output), width) == expected
    assert decode(str(output)) == decode(str(output), LSB) == decode(str(output), algorithm) == "Hé"


@pytest.mark.parametrize(
    ("before", "bit", "step", "after"),
    [
        ("ff", 0, 1, "fe"),
        ("00", 1, 0, "01"),
        ("7f", 0, 1, "80"),
        ("80", 1, 0, "7f"),
        ("ff00", 0, 1, "0001"),
        ("0001", 1, 0, "ff00"),
        ("ffff", 0, 1, "0000"),
        ("0000", 1, 0, "ffff"),
        ("ff7f", 0, 1, "fe7f"),
        ("0080", 1, 0, "0180"),
        ("ffff00", 0, 1, "000001"),
        ("000080", 1, 0, "010080"),
        ("ffff7f", 0, 1, "feff7f"),
        ("ffffffff", 0, 1, "00000000"),
        ("ffffff7f", 0, 1, "feffff7f"),
        ("00000080", 1, 0, "01000080"),
    ],
)
def test_carries_and_the_limits_of_a_sample(before: str, bit: int, step: int, after: str) -> None:
    sample = bytes.fromhex(before)
    algorithm = replace(LSB_MATCHING, choose=lambda limit: step)
    assert algorithm.embed_group(sample, len(sample), (bit,)).hex() == after
    assert algorithm.embed_group(sample, len(sample), (1 - bit,)) == sample


def test_both_directions_are_really_used(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path
) -> None:
    numbers = [random.Random(2).randrange(-30000, 30000) for _ in range(8000)]
    source = make_wav(frames=to_frames(numbers, 2), sample_width=2)
    encode(str(source), str(tmp_path / "output.wav"), "x" * 900, LSB_MATCHING)
    changed = to_numbers(read_frames(tmp_path / "output.wav"), 2)
    steps = Counter(new - old for old, new in zip(numbers, changed, strict=True))
    assert set(steps) == {-1, 0, 1}
    assert min(steps[1], steps[-1]) > 1000


@pytest.mark.parametrize(("samples", "capacity"), [(112, 0), (119, 0), (120, 1), (800, 86)])
def test_the_exact_capacity(
    make_wav: Callable[..., Path], tmp_path: Path, samples: int, capacity: int
) -> None:
    source, output = make_wav(frames=bytes(samples)), tmp_path / "output.wav"
    with pytest.raises(CapacityError, match=f"can hold {capacity} bytes"):
        encode(str(source), str(output), "x" * (capacity + 1), LSB_MATCHING)
    encode(str(source), str(output), "x" * capacity, LSB_MATCHING)
    assert decode(str(output)) == "x" * capacity


@pytest.mark.needs_crypto
def test_an_encrypted_message(make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_wav()), output, "hidden 🎵", LSB_MATCHING, passphrase="key")
    assert decode(output, passphrase="key") == "hidden 🎵"
