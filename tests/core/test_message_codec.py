"""Tests for audiosteg/core/message_codec.py."""

import pytest

from audiosteg.core.message_codec import (
    add_length_header,
    bits_to_bytes,
    bytes_to_bits,
    bytes_to_message,
    message_to_bytes,
    read_length_header,
)
from audiosteg.errors import InvalidMessageError, NoMessageError


def header(value: int) -> list[int]:
    return [int(digit) for digit in f"{value:032b}"]


def test_messages_are_stored_as_utf_8() -> None:
    assert message_to_bytes("Aé🎵\0") == b"A\xc3\xa9\xf0\x9f\x8e\xb5\0"


def test_a_lone_surrogate_is_refused_without_showing_the_message() -> None:
    with pytest.raises(InvalidMessageError) as caught:
        message_to_bytes("my secret \udcff")
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"A\xc3\xa9", "Aé"),
        (b"caf\xe9", "café"),
        (bytes(range(128, 256)), "".join(map(chr, range(128, 256)))),
    ],
    ids=["utf_8", "latin_1", "every_high_latin_1_byte"],
)
def test_bytes_that_are_not_utf_8_are_read_as_latin_1(data: bytes, message: str) -> None:
    assert bytes_to_message(data) == message


def test_bits_are_ordered_from_most_significant() -> None:
    assert list(bytes_to_bits(b"\x80\x01")) == [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
    assert bits_to_bytes([1, 0, 1, 0, 0, 0, 1, 0]) == b"\xa2"


def test_an_incomplete_last_byte_is_dropped() -> None:
    assert bits_to_bytes([0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1]) == b"A"


def test_the_header_is_the_length_in_bits_as_four_big_endian_bytes() -> None:
    assert add_length_header(b"x" * 33)[:4] == b"\x00\x00\x01\x08"


def test_a_length_that_exactly_fills_the_audio_is_accepted() -> None:
    assert read_length_header(header(800), 800) == 800


@pytest.mark.parametrize(
    ("header_bits", "available"),
    [(header(808), 807), (header(2**32 - 8), 1000), (header(9), 1000), (header(8)[:31], 1000), ([], 0)],
    ids=["one_too_long", "huge", "not_whole_bytes", "short_header", "empty"],
)
def test_impossible_headers_hold_no_message(header_bits: list[int], available: int) -> None:
    with pytest.raises(NoMessageError):
        read_length_header(header_bits, available)
