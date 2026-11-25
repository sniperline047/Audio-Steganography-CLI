"""Convert messages to bits and back."""

from collections.abc import Iterable, Iterator
from contextlib import suppress

from audiosteg.core.algorithm import Algorithm, ExtractBits
from audiosteg.errors import DamagedMessageError, InvalidMessageError


def message_to_bytes(message: str) -> bytes:
    """Encode a message as UTF-8 bytes."""
    with suppress(UnicodeEncodeError):
        return message.encode("utf-8")
    raise InvalidMessageError("The message contains characters that are not valid text.")


def bytes_to_message(data: bytes) -> str:
    """Decode UTF-8 bytes."""
    with suppress(UnicodeDecodeError):
        return data.decode("utf-8")
    raise DamagedMessageError("The hidden message is not valid text.")


def bytes_to_bits(data: bytes) -> Iterator[int]:
    """Yield the bits of each byte, most significant bit first."""
    for byte in data:
        for shift in range(7, -1, -1):
            yield (byte >> shift) & 1


def bits_to_bytes(bits: Iterable[int]) -> bytes:
    """Join bits into bytes, most significant bit first. Incomplete bytes are dropped."""
    result = bytearray()
    value = 0
    count = 0
    for bit in bits:
        value = (value << 1) | bit
        count += 1
        if count == 8:
            result.append(value)
            value = 0
            count = 0
    return bytes(result)


def extract_all(sample_bytes: bytes, extract_bits: ExtractBits) -> Iterator[int]:
    """Yield the hidden bits of every given byte."""
    for byte in sample_bytes:
        yield from extract_bits(byte)


def extract_groups(low_bytes: bytes, algorithm: Algorithm) -> Iterator[int]:
    """Yield the hidden bits of every complete group of samples, given their lowest bytes."""
    size = algorithm.samples_per_group
    for start in range(0, len(low_bytes) - size + 1, size):
        yield from algorithm.extract_group(low_bytes[start : start + size])
