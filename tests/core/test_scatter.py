"""Tests for audiosteg/core/scatter.py."""

import hashlib
import tracemalloc
from itertools import islice

import pytest

from audiosteg.core.scatter import half_bits, scatter

KEY = bytes(range(32))
KNOWN_188_672 = [65175, 91969, 109515, 141293, 53387, 54907, 121805, 20008]
KNOWN_2_32 = [415234757, 3905294199, 3934890438, 3039728579]


def place(key: bytes, limit: int, number: int) -> int:
    """Return one place as the documentation says, without the package."""
    half = 1
    while 4**half < limit:
        half += 1
    while True:
        left, right = divmod(number, 2**half)
        for step in range(10):
            table = hashlib.shake_256(key + limit.to_bytes(8, "big") + bytes([step])).digest(2 * 2**half)
            value = int.from_bytes(table[2 * right : 2 * right + 2], "big") % 2**half
            left, right = right, left ^ value
        number = left * 2**half + right
        if number < limit:
            return number


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 15, 16, 17, 64, 65, 304, 1000, 1024, 1025, 4097])
def test_every_number_comes_exactly_once(limit: int) -> None:
    order = list(scatter(KEY, limit))
    assert sorted(order) == list(range(limit))
    assert limit < 64 or order != sorted(order)


@pytest.mark.parametrize("limit", [1, 2, 5, 304, 1025, 188_672, 2**30 - 128])
def test_known_answers_of_another_implementation(limit: int) -> None:
    count = min(limit, 12)
    assert list(islice(scatter(KEY, limit), count)) == [place(KEY, limit, index) for index in range(count)]


def test_known_answers_that_never_change() -> None:
    assert list(islice(scatter(KEY, 188_672), 8)) == KNOWN_188_672
    assert list(islice(scatter(KEY, 2**32), 4)) == KNOWN_2_32


def test_another_key_or_limit_gives_another_order() -> None:
    orders = {
        tuple(islice(scatter(key, limit), 20))
        for key in (KEY, bytes(32), KEY[:-1] + b"\0")
        for limit in (10_000, 10_001)
    }
    assert len(orders) == 6


def test_the_numbers_are_spread_evenly() -> None:
    limit = 100_000
    counts = [0] * 10
    for number in islice(scatter(KEY, limit), 10_000):
        counts[number * 10 // limit] += 1
    assert all(850 < count < 1150 for count in counts)


def test_memory_stays_small_for_the_largest_file() -> None:
    tracemalloc.start()
    try:
        assert len(set(islice(scatter(KEY, 2**32), 1000))) == 1000
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 8_000_000


@pytest.mark.parametrize(
    ("limit", "bits"),
    [(1, 1), (4, 1), (5, 2), (16, 2), (17, 3), (2**30, 15), (2**30 + 1, 16), (2**32, 16)],
)
def test_the_halves_are_as_small_as_possible(limit: int, bits: int) -> None:
    assert half_bits(limit) == bits


def test_too_many_numbers_are_refused() -> None:
    with pytest.raises(ValueError, match="too many samples"):
        next(scatter(KEY, 2**32 + 1))
