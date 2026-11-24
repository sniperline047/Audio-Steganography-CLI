"""Tests for audiosteg/algorithms/registry.py."""

import re
from collections.abc import Callable
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.legacy import BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS

every_algorithm = pytest.mark.parametrize(
    "algorithm", ALGORITHMS.values(), ids=lambda algorithm: algorithm.name
)


def test_the_documented_names_and_the_order_of_detection_do_not_change() -> None:
    assert list(ALGORITHMS.items())[:2] == [("lsb", LSB), ("lsb_2", LSB_2)]
    assert LEGACY_ALGORITHMS == {
        "basic": BASIC_LSB,
        "enhanced_flip": ENHANCED_LSB_FLIP,
        "enhanced": ENHANCED_LSB,
    }


@pytest.mark.parametrize("algorithms", [ALGORITHMS, LEGACY_ALGORITHMS])
def test_every_algorithm_has_a_usable_name_and_one_line_of_explanation(algorithms: Any) -> None:
    for key, algorithm in algorithms.items():
        assert re.fullmatch("[a-z][a-z0-9_]*", key)
        assert algorithm.explanation and algorithm.explanation.isprintable()


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
