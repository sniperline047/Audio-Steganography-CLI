"""The descriptions of the ways to hide bits in samples."""

from collections.abc import Callable
from dataclasses import dataclass

EmbedBits = Callable[[int, tuple[int, ...]], int]
ExtractBits = Callable[[int], tuple[int, ...]]


@dataclass(frozen=True)
class Algorithm:
    """
    One way to hide bits in the lowest byte of each sample.

    :param name: The full name
    :param bits_per_byte: How many bits the lowest byte of a sample carries (1, 2, 4, or 8)
    :param embed_bits: Function that puts a group of bits into a byte
    :param extract_bits: Function that gets the hidden bits from a byte
    :param explanation: One line that explains the algorithm to a beginner
    """

    name: str
    bits_per_byte: int
    embed_bits: EmbedBits
    extract_bits: ExtractBits
    explanation: str = ""

    def __post_init__(self) -> None:
        """Refuse a number of bits that does not divide a byte evenly."""
        if self.bits_per_byte not in (1, 2, 4, 8):
            raise ValueError(f"bits_per_byte must be 1, 2, 4, or 8, not {self.bits_per_byte}.")


@dataclass(frozen=True)
class LegacyAlgorithm:
    """
    One way older versions hid bits, using every sample byte in order.

    :param name: The full name
    :param bits_per_byte: How many bits each sample byte carries
    :param extract_bits: Function that gets the hidden bits from a sample byte
    :param explanation: One line that explains the algorithm to a beginner
    """

    name: str
    bits_per_byte: int
    extract_bits: ExtractBits
    explanation: str = ""
