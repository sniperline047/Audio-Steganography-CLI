"""Tests for audiosteg/core/protection.py."""

import random
import zlib
from collections.abc import Callable

import pytest

from audiosteg.core.protection import (
    LARGEST_DATA,
    largest_container,
    protect,
    protected_size,
    restore_body,
    restore_header,
)
from audiosteg.errors import DamagedMessageError

HEADER = b"ASTG\x01\x00\x00\x00\x00\x05"
HELLO = HEADER + b"Hello" + zlib.crc32(HEADER + b"Hello").to_bytes(4, "big")
PROTECTED_HELLO = bytes.fromhex(
    "415354470100000000052f62f33cb0a837373d4e8cdc690539e948656c6c6fd2c17e40f5be349adcfd6ad68eabfb3ef92fab8a"
)


def slow_multiply(first: int, second: int) -> int:
    product = 0
    while second:
        if second & 1:
            product ^= first
        first = first << 1 ^ (0x11D if first & 128 else 0)
        second >>= 1
    return product


def independent_parity(data: bytes, size: int) -> bytes:
    """Make parity bytes as the documentation says, without the package."""
    generator, point = [1], 1
    for _ in range(size):
        shifted = [*generator, 0]
        generator = [
            value ^ (slow_multiply(point, generator[index - 1]) if index else 0)
            for index, value in enumerate(shifted)
        ]
        point = slow_multiply(point, 2)
    rest = [*data, *[0] * size]
    for index in range(len(data)):
        factor = rest[index]
        for offset, value in enumerate(generator):
            rest[index + offset] ^= slow_multiply(factor, value)
    return bytes(rest[-size:])


def independent_protect(container: bytes) -> bytes:
    """Protect a container as the documentation says, without the package."""
    header, body = container[:10], container[10:]
    count = (len(body) + 119) // 120
    size = max(16, (len(body) + count - 1) // count)
    parities = [independent_parity(body[number::count], size) for number in range(count)]
    mixed = [parity[index] for index in range(size) for parity in parities]
    return header + independent_parity(header, 16) + body + bytes(mixed)


@pytest.mark.parametrize("size", [1, 4, 16, 17, 44, 120, 121, 240, 241, 500])
def test_the_layout_is_the_documented_one(size: int) -> None:
    container = HEADER + random.Random(size).randbytes(size)
    protected = protect(container)
    assert protected == independent_protect(container)
    assert len(protected) == protected_size(len(container))
    assert restore_header(protected[:26]) == (HEADER, 0)
    assert restore_body(protected[26:], size) == (container[10:], 0)


def test_a_known_answer() -> None:
    assert protect(HELLO) == PROTECTED_HELLO
    assert PROTECTED_HELLO.startswith(HEADER)


def flip(protected: bytes, positions: list[int]) -> bytes:
    damaged = bytearray(protected)
    for position in positions:
        damaged[position] ^= 0x5A
    return bytes(damaged)


@pytest.mark.parametrize("size", [9, 44, 120, 300])
def test_a_quarter_of_the_body_in_one_place_is_corrected(size: int) -> None:
    body = random.Random(3).randbytes(size)
    protected = protect(HEADER + body)[26:]
    burst = len(protected) // 4 - 3
    for start in (0, size // 2, len(protected) - burst):
        restored = restore_body(flip(protected, list(range(start, start + burst))), size)
        assert restored.data == body
        assert 0 < restored.strain <= 1


def test_the_strain_is_the_share_of_the_bound_of_the_worst_codeword() -> None:
    body = random.Random(4).randbytes(240)
    protected = protect(HEADER + body)[26:]
    assert restore_body(flip(protected, [0, 2, 1]), 240).strain == 2 / 60
    assert restore_body(flip(protected, list(range(0, 120, 2))), 240).strain == 1
    with pytest.raises(DamagedMessageError, match="too much of it"):
        restore_body(flip(protected, list(range(0, 122, 2))), 240)


def test_a_header_is_corrected_up_to_its_bound() -> None:
    protected = protect(HELLO)[:26]
    assert restore_header(flip(protected, list(range(8)))) == (HEADER, 1)
    assert restore_header(flip(protected, list(range(9)))) is None
    assert restore_header(protected[:25]) is None
    assert restore_header(b"") is None


def test_noise_is_never_a_header() -> None:
    chooser = random.Random(5)
    for _ in range(300):
        assert restore_header(chooser.randbytes(26)) is None


@pytest.mark.parametrize("check", [protected_size])
def test_the_largest_container_is_the_largest_that_fits(check: Callable[[int], int]) -> None:
    sizes = [check(size) for size in range(11, 1200)]
    assert sizes == sorted(sizes)
    for size in range(2000):
        largest = largest_container(size)
        assert largest == 0 or check(largest) <= size
        assert check(max(largest, 10) + 1) > size
    assert largest_container(-5) == 0
    assert LARGEST_DATA == 120
