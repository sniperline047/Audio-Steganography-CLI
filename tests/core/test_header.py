"""Tests for audiosteg/core/header.py."""

from typing import Any

import pytest

from audiosteg.core.header import (
    Header,
    build_container,
    check_passphrase_use,
    open_container,
    parse_header,
)
from audiosteg.errors import (
    DamagedMessageError,
    NotEncryptedError,
    PassphraseRequiredError,
    UnsupportedFormatError,
    WrongPassphraseError,
)

PLAIN = bytes.fromhex("4153544701000000000348c3a9a411cc3b")


@pytest.mark.parametrize(
    ("data", "header"),
    [
        ("41535447010000000000", Header(False, 0)),
        ("41535447010100000008", Header(True, 8)),
        ("41535447010001020304", Header(False, 0x01020304)),
        ("415354470101ffffffff", Header(True, 2**32 - 1)),
    ],
)
def test_known_answer_headers(data: str, header: Header) -> None:
    assert header.to_bytes() == bytes.fromhex(data)
    assert parse_header(bytes.fromhex(data)) == header
    assert parse_header(bytes.fromhex(data) + b"more") == header


@pytest.mark.parametrize(("encrypted", "size"), [(False, 114), (True, 154)])
def test_the_size_of_a_container(encrypted: bool, size: int) -> None:
    assert Header(encrypted, 100).container_size == size


@pytest.mark.parametrize(
    "data", [b"", b"ASTG", PLAIN[:9], b"astg" + PLAIN[4:], b"\0" + PLAIN, b"ASTF" + PLAIN[4:]]
)
def test_other_data_has_no_header(data: bytes) -> None:
    assert parse_header(data) is None


@pytest.mark.parametrize("version", [0, 2, 129, 255])
def test_another_version_is_refused(version: int) -> None:
    with pytest.raises(UnsupportedFormatError, match=f"version {version}[ ,]"):
        parse_header(b"ASTG" + bytes([version]) + PLAIN[5:])


def test_unknown_flags_are_refused() -> None:
    for flags in range(2, 256):
        with pytest.raises(UnsupportedFormatError, match=rf"flags \({flags}\)"):
            parse_header(b"ASTG\x01" + bytes([flags]) + PLAIN[6:])


def test_a_passphrase_must_be_used_exactly_when_the_message_is_encrypted() -> None:
    check_passphrase_use(Header(False, 1), None)
    check_passphrase_use(Header(True, 1), "key")
    with pytest.raises(PassphraseRequiredError):
        check_passphrase_use(Header(True, 1), None)
    for passphrase in ("key", ""):
        with pytest.raises(NotEncryptedError, match="may not be the message you expect"):
            check_passphrase_use(Header(False, 1), passphrase)


def test_known_answer_plain_container() -> None:
    assert build_container("Hé".encode(), None) == PLAIN
    assert open_container(PLAIN, None) == "Hé".encode()


def test_the_checksum_covers_every_bit() -> None:
    for position in range(len(PLAIN) * 8):
        changed = bytearray(PLAIN)
        changed[position // 8] ^= 1 << position % 8
        with pytest.raises(DamagedMessageError, match="damaged"):
            open_container(bytes(changed), None)


@pytest.mark.needs_crypto
def test_known_answer_encrypted_container(known_answer: Any, known_randomness: None) -> None:
    passphrase = known_answer.passphrase.encode()
    message = known_answer.message.encode()
    assert build_container(message, passphrase) == known_answer.container
    assert open_container(known_answer.container, passphrase) == message


@pytest.mark.needs_crypto
def test_encryption_covers_every_bit_of_the_header(fast_scrypt: None) -> None:
    container = build_container(b"message", b"key")
    assert open_container(container, b"key") == b"message"
    for position in range(80):
        changed = bytearray(container)
        changed[position // 8] ^= 1 << position % 8
        with pytest.raises(WrongPassphraseError):
            open_container(bytes(changed), b"key")
