"""Tests for audiosteg/core/algorithm.py."""

from dataclasses import FrozenInstanceError

import pytest

from audiosteg import Algorithm


def make_algorithm(bits_per_byte: int) -> Algorithm:
    return Algorithm("Test", bits_per_byte, lambda byte, bits: byte, lambda byte: ())


@pytest.mark.parametrize("bits_per_byte", [1, 2, 4, 8])
def test_bits_that_divide_a_byte_evenly_are_accepted(bits_per_byte: int) -> None:
    assert make_algorithm(bits_per_byte).bits_per_byte == bits_per_byte


@pytest.mark.parametrize("bits_per_byte", [-1, 0, 3, 5, 6, 7, 9, 16, 32])
def test_other_numbers_of_bits_are_refused(bits_per_byte: int) -> None:
    with pytest.raises(ValueError, match=f"must be 1, 2, 4, or 8, not {bits_per_byte}"):
        make_algorithm(bits_per_byte)


@pytest.mark.parametrize("samples", [-1, 0])
def test_a_group_without_samples_is_refused(samples: int) -> None:
    with pytest.raises(ValueError, match=f"must be 1 or more, not {samples}"):
        Algorithm("Test", 1, lambda byte, bits: byte, lambda byte: (), samples_per_group=samples)


def test_a_keyed_algorithm_uses_single_samples() -> None:
    with pytest.raises(ValueError, match="one sample at a time"):
        Algorithm("Test", 1, lambda byte, bits: byte, lambda byte: (), samples_per_group=2, keyed=True)


def test_an_algorithm_for_bytes_uses_only_the_lowest_byte() -> None:
    algorithm = Algorithm("Test", 2, lambda byte, bits: byte ^ bits[0] ^ bits[1], lambda byte: (byte, 7))
    assert algorithm.embed_group(b"\x10\x20\x30", 3, (1, 0)) == b"\x11\x20\x30"
    assert algorithm.extract_group(b"\x05") == (5, 7)
    assert [algorithm.count_bytes(samples) for samples in (0, 3, 4, 9)] == [0, 0, 1, 2]
    assert algorithm.detectable


def test_what_cannot_be_detected() -> None:
    reader = make_algorithm(1)
    assert not Algorithm("Test", 1, reader.embed_bits, reader.extract_bits, reads_like=reader).detectable
    assert not Algorithm("Test", 1, reader.embed_bits, reader.extract_bits, keyed=True).detectable


def test_an_algorithm_cannot_be_changed_after_it_is_checked() -> None:
    algorithm = make_algorithm(1)
    with pytest.raises(FrozenInstanceError):
        algorithm.bits_per_byte = 3  # type: ignore[misc]
