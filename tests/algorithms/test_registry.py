"""Tests for audiosteg/algorithms/registry.py."""

from collections.abc import Callable
from itertools import product
from pathlib import Path

import pytest

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.legacy import BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS

every_algorithm = pytest.mark.parametrize(
    "algorithm", ALGORITHMS.values(), ids=lambda algorithm: algorithm.name
)


def test_numbers_follow_the_order_of_the_menu() -> None:
    assert list(ALGORITHMS) == list(range(1, len(ALGORITHMS) + 1))


def test_the_documented_numbers_do_not_change() -> None:
    assert (ALGORITHMS[1], ALGORITHMS[2]) == (LSB, LSB_2)
    assert LEGACY_ALGORITHMS == {1: BASIC_LSB, 2: ENHANCED_LSB_FLIP, 3: ENHANCED_LSB}


def test_no_two_algorithms_look_the_same() -> None:
    algorithms = [*ALGORITHMS.values(), *LEGACY_ALGORITHMS.values()]
    names = [algorithm.name.casefold() for algorithm in algorithms]
    assert len(set(names)) == len(names)


@every_algorithm
def test_every_byte_carries_every_group_of_bits(algorithm: Algorithm) -> None:
    for byte, bits in product(range(256), product(range(2), repeat=algorithm.bits_per_byte)):
        changed = algorithm.embed_bits(byte, bits)
        assert 0 <= changed <= 255
        assert tuple(algorithm.extract_bits(changed)) == bits


@every_algorithm
def test_every_algorithm_hides_and_reveals_a_message(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "Hello 🎵", algorithm)
    assert decode(str(output), algorithm) == "Hello 🎵"
    assert decode(str(output)) == "Hello 🎵"
