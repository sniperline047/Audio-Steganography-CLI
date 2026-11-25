"""Tests for audiosteg/core/message_codec.py."""

import pytest

from audiosteg.core.algorithm import Algorithm
from audiosteg.core.message_codec import (
    bits_to_bytes,
    bytes_to_bits,
    bytes_to_message,
    extract_groups,
    message_to_bytes,
)
from audiosteg.errors import DamagedMessageError, InvalidMessageError


def test_messages_are_stored_as_utf_8() -> None:
    assert message_to_bytes("Aé🎵\0") == b"A\xc3\xa9\xf0\x9f\x8e\xb5\0"


def test_a_lone_surrogate_is_refused_without_showing_the_message() -> None:
    with pytest.raises(InvalidMessageError) as caught:
        message_to_bytes("my secret \udcff")
    assert "secret" not in str(caught.value)


def test_bits_are_ordered_from_most_significant() -> None:
    assert list(bytes_to_bits(b"\x80\x01")) == [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
    assert bits_to_bytes([1, 0, 1, 0, 0, 0, 1, 0]) == b"\xa2"


def test_an_incomplete_last_byte_is_dropped() -> None:
    assert bits_to_bytes([0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1]) == b"A"


def test_bytes_that_are_not_utf_8_are_damaged() -> None:
    assert bytes_to_message(b"A\xc3\xa9") == "Aé"
    with pytest.raises(DamagedMessageError):
        bytes_to_message(b"caf\xe9")


def test_only_complete_groups_are_read() -> None:
    class Sum(Algorithm):
        def extract_group(self, low_bytes: bytes) -> tuple[int, ...]:
            return (sum(low_bytes), len(low_bytes))

    algorithm = Sum("Sum", 1, lambda byte, bits: byte, lambda byte: (), samples_per_group=3)
    assert list(extract_groups(bytes(range(8)), algorithm)) == [3, 3, 12, 3]
    assert list(extract_groups(b"", algorithm)) == []
