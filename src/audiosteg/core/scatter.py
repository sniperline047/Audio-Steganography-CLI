"""Visit every number below a limit exactly once, in an order that a key decides."""

from __future__ import annotations

import hashlib
import struct
from array import array
from collections.abc import Iterator

ROUNDS = 10
LARGEST_LIMIT = 2**32


def half_bits(limit: int) -> int:
    """Return the fewest bits, at least 1, so that a number with twice as many bits can reach the limit."""
    return max((max(limit - 1, 1).bit_length() + 1) // 2, 1)


def make_tables(key: bytes, limit: int) -> list[array[int]]:
    """Make the random table of every round."""
    size = 1 << half_bits(limit)
    tables = []
    for number in range(ROUNDS):
        seed = key + limit.to_bytes(8, "big") + bytes([number])
        data = hashlib.shake_256(seed).digest(2 * size)
        tables.append(array("H", (value & size - 1 for value in struct.unpack(f">{size}H", data))))
    return tables


def scatter(key: bytes, limit: int) -> Iterator[int]:
    """
    Yield every number below the limit exactly once. The numbers are made one at a time.

    This is a Feistel network. A result that is too large goes through it again.

    :param key: The 32 bytes that decide the order
    :param limit: How many numbers there are, at most 2**32
    """
    if limit > LARGEST_LIMIT:
        raise ValueError("There are too many samples to scatter.")
    tables = make_tables(key, limit)
    shift = half_bits(limit)
    mask = (1 << shift) - 1
    for start in range(limit):
        number = start
        while True:
            left, right = number >> shift, number & mask
            for table in tables:
                left, right = right, left ^ table[right]
            number = left << shift | right
            if number < limit:
                break
        yield number
