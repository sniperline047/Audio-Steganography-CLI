"""Convert messages to bits and back."""

from collections.abc import Iterable, Iterator, Sequence

from utils.errors import InvalidMessageError, NoMessageError

HEADER_BITS = 32
MAX_MESSAGE_BITS = 2**HEADER_BITS - 1


def message_to_bytes(message: str) -> bytes:
    """Encode a message as UTF-8 bytes."""
    try:
        return message.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InvalidMessageError("The message contains characters that are not valid text.") from error


def bytes_to_message(data: bytes) -> str:
    """Decode UTF-8 bytes, falling back to Latin-1 for files made by older versions."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


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


def add_length_header(message_bytes: bytes) -> bytes:
    """Put the message length, in bits, in front of the message as 4 big-endian bytes."""
    return (len(message_bytes) * 8).to_bytes(HEADER_BITS // 8, "big") + message_bytes


def read_length_header(header_bits: Sequence[int], available_bits: int) -> int:
    """
    Read and check the message length.

    :param header_bits: The first 32 hidden bits
    :param available_bits: How many hidden bits can follow the header
    :return: The message length in bits
    """
    if len(header_bits) < HEADER_BITS:
        raise NoMessageError("The audio file is too short to hold a hidden message.")
    length = int.from_bytes(bits_to_bytes(header_bits), "big")
    if length > available_bits or length % 8 != 0:
        raise NoMessageError("No hidden message was found. Check the file and the algorithm.")
    return length
