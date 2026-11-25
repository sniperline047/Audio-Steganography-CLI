"""Read files made by older versions. These algorithms cannot hide new messages."""

from collections.abc import Sequence

from audiosteg.core.algorithm import LegacyAlgorithm
from audiosteg.core.message_codec import bits_to_bytes, extract_all
from audiosteg.core.wav_io import count_sample_bytes, open_pcm_wav, read_first_bytes
from audiosteg.errors import NoMessageError

HEADER_BITS = 32
EVERY_BYTE = (
    "It used every byte of a sample. The highest byte decides how loud a sample is, "
    "so the start of the file could have audible noise."
)
NO_MARKER = "It had no marker and no checksum, so a message could not be detected and damage went unnoticed."
NO_ENCRYPTION = "It could not encrypt messages."
MIDDLE_BITS = "It changed middle bits, which adds more noise than changing the lowest bits."


def extract_lowest_bit(byte: int) -> tuple[int, ...]:
    """Read the lowest bit of a sample byte."""
    return (byte & 1,)


def extract_middle_bits(byte: int) -> tuple[int, ...]:
    """Read the fourth and third lowest bits of a sample byte, in that order."""
    return (byte >> 3) & 1, (byte >> 2) & 1


BASIC_LSB = LegacyAlgorithm(
    name="Basic LSB Steganography",
    bits_per_byte=1,
    extract_bits=extract_lowest_bit,
    explanation="Reads 1 bit from every byte.",
    replaced_because=(EVERY_BYTE, NO_MARKER, NO_ENCRYPTION),
)

ENHANCED_LSB_FLIP = LegacyAlgorithm(
    name="Enhanced LSB Steganography with Bit Flipping",
    bits_per_byte=2,
    extract_bits=extract_middle_bits,
    explanation="Reads 2 middle bits of every byte (bit flipping).",
    replaced_because=(EVERY_BYTE, MIDDLE_BITS, NO_MARKER, NO_ENCRYPTION),
)

ENHANCED_LSB = LegacyAlgorithm(
    name="Enhanced LSB Steganography without Bit Flipping",
    bits_per_byte=2,
    extract_bits=extract_middle_bits,
    explanation="Reads 2 middle bits from every byte.",
    replaced_because=(EVERY_BYTE, MIDDLE_BITS, NO_MARKER, NO_ENCRYPTION),
)


def bytes_to_old_message(data: bytes) -> str:
    """Decode UTF-8 bytes, falling back to Latin-1 for the oldest files."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


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


def decode_legacy(path: str, algorithm: LegacyAlgorithm) -> str:
    """
    Read a message that an older version hid.

    :param path: Path to the encoded audio file
    :param algorithm: The algorithm that was used to hide the message
    :return: The hidden message
    """
    header_size = HEADER_BITS // algorithm.bits_per_byte
    with open_pcm_wav(path) as audio:
        header = read_first_bytes(audio, header_size)
        available = count_sample_bytes(audio, path) * algorithm.bits_per_byte - HEADER_BITS
        length = read_length_header(list(extract_all(header, algorithm.extract_bits)), available)
        sample_bytes = read_first_bytes(audio, header_size + length // algorithm.bits_per_byte)

    message_bytes = bits_to_bytes(extract_all(sample_bytes[header_size:], algorithm.extract_bits))
    if len(message_bytes) * 8 != length:
        raise NoMessageError("The audio file ends before the hidden message does.")
    return bytes_to_old_message(message_bytes)
