"""Read files made by older versions. These algorithms cannot hide new messages."""

from collections.abc import Sequence
from dataclasses import dataclass

from audiosteg.core.algorithm import ExtractBits
from audiosteg.core.message_codec import bits_to_bytes, extract_all
from audiosteg.core.wav_io import count_sample_bytes, open_pcm_wav, read_first_bytes
from audiosteg.errors import NoMessageError

HEADER_BITS = 32


@dataclass(frozen=True)
class LegacyAlgorithm:
    """
    One way older versions hid bits, using every sample byte in order.

    :param name: The name shown in the menu
    :param bits_per_byte: How many bits each sample byte carries
    :param extract_bits: Function that gets the hidden bits from a sample byte
    """

    name: str
    bits_per_byte: int
    extract_bits: ExtractBits


def extract_lowest_bit(byte: int) -> tuple[int, ...]:
    """Read the lowest bit of a sample byte."""
    return (byte & 1,)


def extract_middle_bits(byte: int) -> tuple[int, ...]:
    """Read the fourth and third lowest bits of a sample byte, in that order."""
    return (byte >> 3) & 1, (byte >> 2) & 1


BASIC_LSB = LegacyAlgorithm("Basic LSB Steganography", 1, extract_lowest_bit)
ENHANCED_LSB_FLIP = LegacyAlgorithm("Enhanced LSB Steganography with Bit Flipping", 2, extract_middle_bits)
ENHANCED_LSB = LegacyAlgorithm("Enhanced LSB Steganography without Bit Flipping", 2, extract_middle_bits)


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
