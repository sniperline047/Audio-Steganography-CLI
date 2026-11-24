"""Tests for audiosteg/core/algorithm.py."""

import pytest

from audiosteg import Algorithm


def make_algorithm(bits_per_byte: int) -> Algorithm:
    return Algorithm("Test", bits_per_byte, lambda byte, bits: byte, lambda byte: (), "test.wav")


@pytest.mark.parametrize("bits_per_byte", [1, 2, 4, 8])
def test_bits_that_divide_a_byte_evenly_are_accepted(bits_per_byte: int) -> None:
    assert make_algorithm(bits_per_byte).bits_per_byte == bits_per_byte


@pytest.mark.parametrize("bits_per_byte", [-1, 0, 3, 5, 6, 7, 9, 16, 32])
def test_other_numbers_of_bits_are_refused(bits_per_byte: int) -> None:
    with pytest.raises(ValueError, match=f"must be 1, 2, 4, or 8, not {bits_per_byte}"):
        make_algorithm(bits_per_byte)
