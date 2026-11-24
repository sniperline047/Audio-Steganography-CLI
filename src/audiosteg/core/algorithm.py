"""The description of one way to hide bits in sample bytes."""

from collections.abc import Callable
from dataclasses import dataclass

EmbedBits = Callable[[int, tuple[int, ...]], int]
ExtractBits = Callable[[int], tuple[int, ...]]


@dataclass(frozen=True)
class Algorithm:
    """
    One way to hide bits in sample bytes.

    :param name: The name shown in the menu
    :param bits_per_byte: How many bits each sample byte carries (1, 2, 4, or 8)
    :param embed_bits: Function that puts a group of bits into a sample byte
    :param extract_bits: Function that gets the hidden bits from a sample byte
    :param output_file_name: The default name of an encoded file
    """

    name: str
    bits_per_byte: int
    embed_bits: EmbedBits
    extract_bits: ExtractBits
    output_file_name: str

    def __post_init__(self) -> None:
        """Refuse a number of bits that does not divide a byte evenly."""
        if self.bits_per_byte not in (1, 2, 4, 8):
            raise ValueError(f"bits_per_byte must be 1, 2, 4, or 8, not {self.bits_per_byte}.")
