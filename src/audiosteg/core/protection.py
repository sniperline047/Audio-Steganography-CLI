"""Protect a container with error correction, so that some of its bytes may be read wrong."""

from bisect import bisect_right
from typing import NamedTuple

from audiosteg.core.header import HEADER_SIZE
from audiosteg.core.reed_solomon import TooManyErrorsError, correct, make_parity
from audiosteg.errors import DamagedMessageError

FEWEST_PARITY = 16
LARGEST_DATA = 120
PROTECTED_HEADER_SIZE = HEADER_SIZE + FEWEST_PARITY


class Restored(NamedTuple):
    """
    Bytes that were corrected.

    :param strain: The largest share of its correctable errors that a codeword had, from 0 to 1
    """

    data: bytes
    strain: float


class Layout(NamedTuple):
    """How the bytes after the header are divided into codewords."""

    codewords: int
    parity_size: int

    @property
    def total_parity(self) -> int:
        """Return how many parity bytes all codewords have together."""
        return self.codewords * self.parity_size


def body_layout(size: int) -> Layout:
    """Return the fewest codewords for this many bytes, with about as much parity as data in each."""
    codewords = -(-size // LARGEST_DATA)
    return Layout(codewords, max(-(-size // codewords), FEWEST_PARITY))


def protected_size(container_size: int) -> int:
    """Return the size of a container and everything that protects it."""
    body = container_size - HEADER_SIZE
    return PROTECTED_HEADER_SIZE + body + body_layout(body).total_parity


def largest_container(size: int) -> int:
    """Return the size of the largest container that fits in this many bytes, or 0 if none does."""
    sizes = range(HEADER_SIZE + 1, max(size, HEADER_SIZE) + 1)
    fitting = bisect_right(sizes, size, key=protected_size)
    return sizes[fitting - 1] if fitting else 0


def protect(container: bytes) -> bytes:
    """Add parity bytes. Neighbouring bytes belong to different codewords, so that damage is spread."""
    header, body = container[:HEADER_SIZE], container[HEADER_SIZE:]
    codewords, parity_size = body_layout(len(body))
    parities = [make_parity(body[first::codewords], parity_size) for first in range(codewords)]
    mixed = bytes(parity[index] for index in range(parity_size) for parity in parities)
    return header + make_parity(header, FEWEST_PARITY) + body + mixed


def restore(codeword: bytes, parity_size: int) -> Restored | None:
    """Correct one codeword, or return None if too many bytes are wrong."""
    try:
        data, errors = correct(codeword, parity_size)
    except TooManyErrorsError:
        return None
    return Restored(data, errors / (parity_size // 2))


def restore_header(protected: bytes) -> Restored | None:
    """Correct a header, or return None if there is none that can be corrected."""
    if len(protected) < PROTECTED_HEADER_SIZE:
        return None
    return restore(protected, FEWEST_PARITY)


def restore_body(protected: bytes, size: int) -> Restored:
    """
    Correct everything after the header.

    :param protected: The bytes after the protected header
    :param size: How many of them are not parity bytes
    """
    codewords, parity_size = body_layout(size)
    body, mixed = protected[:size], protected[size:]
    restored = bytearray(size)
    strain = 0.0
    for first in range(codewords):
        found = restore(body[first::codewords] + mixed[first::codewords], parity_size)
        if found is None:
            raise DamagedMessageError("The hidden message is damaged: too much of it cannot be read.")
        restored[first::codewords] = found.data
        strain = max(strain, found.strain)
    return Restored(bytes(restored), strain)
