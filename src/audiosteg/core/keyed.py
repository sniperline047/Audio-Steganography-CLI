"""Scatter an encrypted container over the samples, so that nothing can be found without the passphrase."""

import wave
from collections.abc import Iterator
from itertools import chain, islice
from typing import NamedTuple

from audiosteg.core import crypto
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.header import HEADER_SIZE, Header, container_overhead, parse_header
from audiosteg.core.message_codec import bits_to_bytes
from audiosteg.core.scatter import scatter
from audiosteg.core.wav_io import read_low_bytes
from audiosteg.errors import DamagedMessageError, NoMessageError, WrongPassphraseError

ORDER_PURPOSE = b"audiosteg keyed 1: order"
ENCRYPTION_PURPOSE = b"audiosteg keyed 1: encryption"
NOT_FOUND = (
    "No hidden message was found with this passphrase. "
    "The passphrase is wrong, there is no message, or the file was edited. The file does not show which."
)
DAMAGED = "The hidden message is damaged or was changed."


class Keys(NamedTuple):
    """The two keys that come from one passphrase and one salt."""

    order: bytes
    encryption: bytes


def split_key(key: bytes) -> Keys:
    """Make a key for the order of the samples and an independent one for the encryption."""
    return Keys(crypto.derive_subkey(key, ORDER_PURPOSE), crypto.derive_subkey(key, ENCRYPTION_PURPOSE))


def count_groups(size: int, algorithm: Algorithm) -> int:
    """Return how many samples carry this many bytes."""
    return size * 8 // algorithm.bits_per_byte


def scattered_samples(order_key: bytes, samples: int, algorithm: Algorithm) -> Iterator[int]:
    """Yield every sample after those of the salt, in the order that the key decides."""
    first = count_groups(crypto.SALT_SIZE, algorithm)
    for number in scatter(order_key, samples - first):
        yield first + number


def build_container(
    message: bytes, passphrase: bytes, algorithm: Algorithm, samples: int
) -> tuple[bytes, Iterator[int]]:
    """Encrypt a message. Return its container, and the order of the samples that carry it."""
    salt = crypto.new_salt()
    keys = split_key(crypto.derive_key(passphrase, salt))
    header = Header(True, len(message)).to_bytes()
    container = header + salt + crypto.seal(message, header, keys.encryption)
    return container, container_order(scattered_samples(keys.order, samples, algorithm), algorithm)


def container_order(scattered: Iterator[int], algorithm: Algorithm) -> Iterator[int]:
    """Yield the samples of a container: the salt is in the first samples, everything else is scattered."""
    yield from islice(scattered, count_groups(HEADER_SIZE, algorithm))
    yield from range(count_groups(crypto.SALT_SIZE, algorithm))
    yield from scattered


def read_bytes(audio: wave.Wave_read, order: Iterator[int], size: int, algorithm: Algorithm) -> bytes:
    """Read hidden bytes from the next samples of the order."""
    low_bytes = read_low_bytes(audio, islice(order, count_groups(size, algorithm)))
    return bits_to_bytes(chain.from_iterable(algorithm.extract_group(bytes((byte,))) for byte in low_bytes))


def read_message(audio: wave.Wave_read, samples: int, passphrase: bytes, algorithm: Algorithm) -> bytes:
    """
    Find and decrypt a message. Until the passphrase proves right, only the salt and the header are read.

    :param audio: The open WAV file
    :param samples: How many samples it holds
    :param passphrase: The bytes from passphrase_to_bytes
    :param algorithm: The keyed algorithm
    :return: The message bytes
    """
    if algorithm.count_bytes(samples) < container_overhead(encrypted=True):
        raise NoMessageError(NOT_FOUND)
    crypto.load_aes_gcm()
    salt = read_bytes(audio, iter(range(samples)), crypto.SALT_SIZE, algorithm)
    keys = split_key(crypto.derive_key(passphrase, salt))
    order = scattered_samples(keys.order, samples, algorithm)
    header_bytes = read_bytes(audio, order, HEADER_SIZE, algorithm)
    header = parse_header(header_bytes)
    if header is None:
        raise NoMessageError(NOT_FOUND)
    if not header.encrypted or header.container_size > algorithm.count_bytes(samples):
        raise DamagedMessageError(DAMAGED)
    size = header.container_size - HEADER_SIZE - crypto.SALT_SIZE
    sealed = read_bytes(audio, order, size, algorithm)
    if len(sealed) < size:
        raise DamagedMessageError("The audio file ends before the hidden message does.")
    try:
        return crypto.unseal(sealed, header_bytes, keys.encryption)
    except WrongPassphraseError as error:
        raise DamagedMessageError(DAMAGED) from error
