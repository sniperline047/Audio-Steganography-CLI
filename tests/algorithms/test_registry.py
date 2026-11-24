"""Tests for audiosteg/algorithms/registry.py."""

import os
from collections.abc import Callable
from itertools import product
from pathlib import Path

import pytest

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.basic_lsb import BASIC_LSB
from audiosteg.algorithms.enhanced_lsb import ENHANCED_LSB
from audiosteg.algorithms.enhanced_lsb_flip import ENHANCED_LSB_FLIP
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.utils.output_path import check_windows_path

every_algorithm = pytest.mark.parametrize(
    "algorithm", ALGORITHMS.values(), ids=lambda algorithm: algorithm.name
)


def test_numbers_follow_the_order_of_the_menu() -> None:
    assert list(ALGORITHMS) == list(range(1, len(ALGORITHMS) + 1))


def test_the_documented_numbers_do_not_change() -> None:
    assert (ALGORITHMS[1], ALGORITHMS[2], ALGORITHMS[3]) == (BASIC_LSB, ENHANCED_LSB_FLIP, ENHANCED_LSB)


@pytest.mark.parametrize("field", ["name", "output_file_name"])
def test_no_two_algorithms_look_the_same(field: str) -> None:
    values = [getattr(algorithm, field).casefold() for algorithm in ALGORITHMS.values()]
    assert len(set(values)) == len(values)


@every_algorithm
def test_default_names_are_plain_wav_files_on_every_system(algorithm: Algorithm) -> None:
    name = algorithm.output_file_name
    check_windows_path(name)
    assert name.endswith(".wav") and name == os.path.basename(name) and "\\" not in name


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
    output = tmp_path / algorithm.output_file_name
    encode(str(make_wav()), str(output), "Hello 🎵", algorithm)
    assert decode(str(output), algorithm) == "Hello 🎵"
