"""Tests for audiosteg/core/reed_solomon.py."""

import random

import pytest

from audiosteg.core.reed_solomon import TooManyErrorsError, correct, divide, make_parity, multiply


def slow_multiply(first: int, second: int) -> int:
    """Multiply in the field as the documentation says, without tables and without the package."""
    product = 0
    for shift in range(8):
        if second >> shift & 1:
            product ^= first << shift
    for shift in reversed(range(8, 16)):
        if product >> shift & 1:
            product ^= 0x11D << shift - 8
    return product


def slow_value(codeword: bytes, exponent: int) -> int:
    """Return the value of a codeword at a power of 2, as the documentation says."""
    point = 1
    for _ in range(exponent):
        point = slow_multiply(point, 2)
    value = 0
    for byte in codeword:
        value = slow_multiply(value, point) ^ byte
    return value


def damage(codeword: bytes, errors: int, chooser: random.Random) -> bytes:
    damaged = bytearray(codeword)
    for position in chooser.sample(range(len(codeword)), errors):
        damaged[position] ^= chooser.randrange(1, 256)
    return bytes(damaged)


def test_the_field_is_the_documented_one() -> None:
    for first in range(256):
        for second in range(0, 256, 5):
            product = multiply(first, second)
            assert product == slow_multiply(first, second)
            if second:
                assert divide(product, second) == first


def test_a_known_answer_of_another_standard() -> None:
    """The parity bytes of the QR code HELLO WORLD (1-M), which uses the same field and points."""
    data = bytes([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17])
    assert make_parity(data, 10) == bytes([196, 35, 39, 119, 235, 215, 231, 226, 93, 23])


@pytest.mark.parametrize(
    ("size", "parity_size"), [(1, 2), (10, 16), (4, 16), (44, 44), (120, 120), (135, 120)]
)
def test_up_to_half_of_the_parity_is_corrected(size: int, parity_size: int) -> None:
    chooser = random.Random(size)
    data = chooser.randbytes(size)
    codeword = data + make_parity(data, parity_size)
    assert [slow_value(codeword, exponent) for exponent in range(parity_size)] == [0] * parity_size
    for errors in sorted({0, 1, parity_size // 4, parity_size // 2 - 1, parity_size // 2}):
        for _ in range(2):
            assert correct(damage(codeword, errors, chooser), parity_size) == (data, errors)


@pytest.mark.parametrize("position", range(26))
def test_one_error_anywhere_is_corrected(position: int) -> None:
    codeword = bytearray(b"ASTG\x01\x00\x00\x00\x00\x05" + make_parity(b"ASTG\x01\x00\x00\x00\x00\x05", 16))
    codeword[position] ^= 255
    assert correct(bytes(codeword), 16) == (b"ASTG\x01\x00\x00\x00\x00\x05", 1)


@pytest.mark.parametrize(("size", "parity_size"), [(10, 16), (44, 44), (120, 120)])
def test_more_errors_are_reported_and_never_become_another_message_unnoticed(
    size: int, parity_size: int
) -> None:
    chooser = random.Random(1)
    data = chooser.randbytes(size)
    codeword = data + make_parity(data, parity_size)
    for errors in range(parity_size // 2 + 1, size + parity_size + 1, max(size // 10, 1)):
        for _ in range(5):
            with pytest.raises(TooManyErrorsError):
                correct(damage(codeword, errors, chooser), parity_size)


def test_whatever_is_returned_is_a_codeword_near_the_input() -> None:
    chooser = random.Random(2)
    corrected = 0
    for _ in range(3000):
        noise = chooser.randbytes(12)
        try:
            data, errors = correct(noise, 4)
        except TooManyErrorsError:
            continue
        codeword = data + make_parity(data, 4)
        assert sum(a != b for a, b in zip(noise, codeword, strict=True)) == errors <= 2
        assert not any(slow_value(codeword, exponent) for exponent in range(4))
        corrected += 1
    assert corrected


def test_a_codeword_that_is_too_long_is_refused() -> None:
    assert len(make_parity(bytes(239), 16)) == 16
    with pytest.raises(ValueError, match="at most 255"):
        make_parity(bytes(240), 16)
