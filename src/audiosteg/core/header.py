"""The container that surrounds a hidden message."""

import struct
import zlib
from typing import NamedTuple

from audiosteg.core import crypto
from audiosteg.errors import (
    DamagedMessageError,
    NotEncryptedError,
    PassphraseRequiredError,
    UnsupportedFormatError,
)

MARKER = b"ASTG"
VERSION = 1
ENCRYPTED_FLAG = 1
HEADER_FORMAT = struct.Struct(">4sBBI")
HEADER_SIZE = HEADER_FORMAT.size
CHECKSUM_SIZE = 4


class Header(NamedTuple):
    """The first bytes of a container."""

    encrypted: bool
    message_length: int

    def to_bytes(self) -> bytes:
        """Return the header as it is stored."""
        flags = ENCRYPTED_FLAG if self.encrypted else 0
        return HEADER_FORMAT.pack(MARKER, VERSION, flags, self.message_length)

    @property
    def container_size(self) -> int:
        """Return the size of the whole container in bytes."""
        return container_overhead(self.encrypted) + self.message_length


def container_overhead(encrypted: bool) -> int:
    """Return how many bytes a container adds to a message."""
    return HEADER_SIZE + (crypto.OVERHEAD if encrypted else CHECKSUM_SIZE)


def parse_header(data: bytes) -> Header | None:
    """Read a header, or return None if the data does not start with one."""
    if len(data) < HEADER_SIZE or not data.startswith(MARKER):
        return None
    _, version, flags, message_length = HEADER_FORMAT.unpack_from(data)
    if version != VERSION:
        raise UnsupportedFormatError(
            f"The hidden message uses format version {version}, which this program cannot read, "
            "or it is damaged."
        )
    if flags & ~ENCRYPTED_FLAG:
        raise UnsupportedFormatError(
            f"The hidden message uses unknown flags ({flags}), which this program cannot read, "
            "or it is damaged."
        )
    return Header(bool(flags & ENCRYPTED_FLAG), message_length)


def check_passphrase_use(header: Header, passphrase: str | None) -> None:
    """Refuse a missing passphrase, and a passphrase for a message that is not encrypted."""
    if header.encrypted and passphrase is None:
        raise PassphraseRequiredError("The hidden message is encrypted. A passphrase is needed.")
    if not header.encrypted and passphrase is not None:
        raise NotEncryptedError(
            "The hidden message is not encrypted, so the passphrase cannot protect it. "
            "It may not be the message you expect."
        )


def checksum(data: bytes) -> bytes:
    """Return the CRC-32 of the data as 4 big-endian bytes."""
    return zlib.crc32(data).to_bytes(CHECKSUM_SIZE, "big")


def build_container(message: bytes, passphrase: bytes | None) -> bytes:
    """Put a message into a container, and encrypt it if there is a passphrase."""
    header = Header(passphrase is not None, len(message)).to_bytes()
    if passphrase is not None:
        return header + crypto.encrypt(message, header, passphrase)
    return header + message + checksum(header + message)


def open_container(container: bytes, passphrase: bytes | None) -> bytes:
    """Check a whole container and return its message. A passphrase means that it is encrypted."""
    header, body = container[:HEADER_SIZE], container[HEADER_SIZE:]
    if passphrase is not None:
        return crypto.decrypt(body, header, passphrase)
    message, stored_checksum = body[:-CHECKSUM_SIZE], body[-CHECKSUM_SIZE:]
    if checksum(header + message) != stored_checksum:
        raise DamagedMessageError("The hidden message is damaged.")
    return message
