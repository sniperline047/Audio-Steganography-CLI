"""Tests for audiosteg/algorithms/legacy.py."""

from collections.abc import Callable
from pathlib import Path

import pytest

from audiosteg import decode, encode
from audiosteg.algorithms.legacy import (
    BASIC_LSB,
    ENHANCED_LSB,
    ENHANCED_LSB_FLIP,
    bytes_to_old_message,
    read_length_header,
)
from audiosteg.core.algorithm import LegacyAlgorithm
from audiosteg.errors import NoMessageError, UnsupportedAlgorithmError

BASIC_UTF8_CARRIER = bytes.fromhex(
    "0a30547a9ec4e80e32587ca2c6ec10365a80a4caee14385e82a8ccf3173c6086aad1f41a3f6488ae"
    "d3f91c42668cb1d7fb20456a8fb4d8ff23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
BASIC_OLD_ASCII_CARRIER = bytes.fromhex(
    "0a30547a9ec4e80e32587ca2c6ec10365a80a4caee14385e82a8ccf3173c6086aad1f41a3f6589af"
    "d2f91d42678db0d6fa21456a8eb5d8fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
BASIC_OLD_LATIN_1_CARRIER = bytes.fromhex(
    "0a30547a9ec4e80e32587ca2c6ec10365a80a4caee14385e82a8cdf2163c6086aad1f51a3e6489af"
    "d2f91d42668cb0d7fa21456a8eb5d9fe23496d92b7dc00274b7095badf04294e7398bde2072c5176"
)
FLIP_UTF8_CARRIER = bytes.fromhex(
    "0030527190c3e201335372a2c0e71a315480aac1ef13325e88a8caf5173c6186abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
FLIP_OLD_ASCII_CARRIER = bytes.fromhex(
    "0030527190c3e201335372a2c0e71a315480aecde41b3e5184a8c6f2173c6186abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
FLIP_OLD_LATIN_1_CARRIER = bytes.fromhex(
    "0030527190c3e201335372a2c0eb1131548ba2cde41b325584a8c6f91c3b6a86abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
NO_FLIP_UTF8_CARRIER = bytes.fromhex(
    "0330517293c0e102335071a2c3e419325780a9c2ef10315e8ba8c9f6173c6186abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
NO_FLIP_OLD_ASCII_CARRIER = bytes.fromhex(
    "0330517293c0e102335071a2c3e419325780adcee7183d5287a8c5f2173c6186abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
NO_FLIP_OLD_LATIN_1_CARRIER = bytes.fromhex(
    "0330517293c0e102335071a2c3e811325788a1cee718315687a8c5fa1f386986abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)


def header(value: int) -> list[int]:
    return [int(digit) for digit in f"{value:032b}"]


def carrier(value: int, message: bytes = b"") -> bytes:
    digits = f"{value:032b}" + "".join(f"{byte:08b}" for byte in message)
    return bytes(int(digit) for digit in digits)


@pytest.mark.parametrize(
    ("algorithm", "carrier", "message"),
    [
        (BASIC_LSB, BASIC_UTF8_CARRIER, "Hé"),
        (BASIC_LSB, BASIC_OLD_ASCII_CARRIER, "Old"),
        (BASIC_LSB, BASIC_OLD_LATIN_1_CARRIER, "café"),
        (ENHANCED_LSB_FLIP, FLIP_UTF8_CARRIER, "Hé"),
        (ENHANCED_LSB_FLIP, FLIP_OLD_ASCII_CARRIER, "Old"),
        (ENHANCED_LSB_FLIP, FLIP_OLD_LATIN_1_CARRIER, "café"),
        (ENHANCED_LSB, NO_FLIP_UTF8_CARRIER, "Hé"),
        (ENHANCED_LSB, NO_FLIP_OLD_ASCII_CARRIER, "Old"),
        (ENHANCED_LSB, NO_FLIP_OLD_LATIN_1_CARRIER, "café"),
    ],
)
def test_known_answer_bytes_for_decode(
    make_wav: Callable[..., Path], algorithm: LegacyAlgorithm, carrier: bytes, message: str
) -> None:
    assert decode(str(make_wav(frames=carrier)), algorithm) == message


@pytest.mark.parametrize(
    ("other", "carrier"),
    [
        (ENHANCED_LSB, BASIC_UTF8_CARRIER),
        (ENHANCED_LSB_FLIP, BASIC_UTF8_CARRIER),
        (BASIC_LSB, FLIP_UTF8_CARRIER),
        (BASIC_LSB, NO_FLIP_UTF8_CARRIER),
    ],
)
def test_decoding_with_another_kind_of_algorithm_does_not_reveal_the_message(
    make_wav: Callable[..., Path], other: LegacyAlgorithm, carrier: bytes
) -> None:
    with pytest.raises(NoMessageError):
        decode(str(make_wav(frames=carrier)), other)


@pytest.mark.parametrize("algorithm", [BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP])
def test_audio_too_short_for_a_header_holds_no_message(
    make_wav: Callable[..., Path], algorithm: LegacyAlgorithm
) -> None:
    with pytest.raises(NoMessageError):
        decode(str(make_wav(frames=bytes(32 // algorithm.bits_per_byte - 1))), algorithm)


@pytest.mark.parametrize("algorithm", [BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP])
def test_old_algorithms_cannot_hide_a_new_message(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: LegacyAlgorithm
) -> None:
    output = tmp_path / "output.wav"
    with pytest.raises(UnsupportedAlgorithmError, match="only read old files"):
        encode(str(make_wav()), str(output), "hidden", algorithm)  # type: ignore[arg-type]
    assert not output.exists()


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
    assert bytes_to_old_message(data) == message


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


@pytest.mark.parametrize(
    "frames",
    [carrier(48, b"hello"), carrier(41, b"hello!"), carrier(2**32 - 8, b"hello"), carrier(0)[:-1], b""],
    ids=["one_byte_short", "not_whole_bytes", "huge", "half_header", "no_audio"],
)
def test_a_damaged_message_is_refused(make_wav: Callable[..., Path], frames: bytes) -> None:
    with pytest.raises(NoMessageError, match="No hidden message was found|too short"):
        decode(str(make_wav(frames=frames)), BASIC_LSB)


def test_a_message_that_fills_the_file_is_read(make_wav: Callable[..., Path]) -> None:
    assert decode(str(make_wav(frames=carrier(40, b"hello"))), BASIC_LSB) == "hello"


def test_a_message_cut_off_by_a_truncated_file_is_refused(make_wav: Callable[..., Path]) -> None:
    source = make_wav(frames=carrier(40, b"hello") + bytes(500))
    content = source.read_bytes()
    source.write_bytes(content[: 44 + 32 + 39])
    with pytest.raises(NoMessageError, match="ends before"):
        decode(str(source), BASIC_LSB)


def test_a_message_is_still_readable_when_only_audio_after_it_is_cut(make_wav: Callable[..., Path]) -> None:
    source = make_wav(frames=carrier(40, b"hello") + bytes(500))
    source.write_bytes(source.read_bytes()[: 44 + 72])
    assert decode(str(source), BASIC_LSB) == "hello"
