"""The descriptions of the ways to hide bits in samples."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

EmbedBits = Callable[[int, tuple[int, ...]], int]
ExtractBits = Callable[[int], tuple[int, ...]]


@dataclass(frozen=True)
class Algorithm:
    """
    One way to hide bits in samples. Without a subclass, it uses the lowest byte of each sample.

    :param name: The full name
    :param bits_per_byte: How many bits the lowest byte of a sample carries (1, 2, 4, or 8)
    :param embed_bits: Function that puts a group of bits into a byte
    :param extract_bits: Function that gets the hidden bits from a byte
    :param explanation: One line that explains the algorithm to a beginner
    :param strengths: What the algorithm is good at, one sentence each
    :param weaknesses: What the algorithm is bad at, one sentence each
    :param how: One line that explains what it does to the samples, if their bits do not show it
    :param samples_per_group: How many samples carry one group of bits together
    :param reads_like: The algorithm that reads its messages, if it only hides them in another way
    :param keyed: Whether a passphrase decides the order of the samples. Such messages are always
        encrypted and are never detected without the passphrase.
    """

    name: str
    bits_per_byte: int
    embed_bits: EmbedBits
    extract_bits: ExtractBits
    explanation: str = ""
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    how: str = ""
    samples_per_group: int = 1
    reads_like: Algorithm | None = None
    keyed: bool = False

    def __post_init__(self) -> None:
        """Refuse a number of bits that does not divide a byte evenly, and groups that cannot be used."""
        if self.bits_per_byte not in (1, 2, 4, 8):
            raise ValueError(f"bits_per_byte must be 1, 2, 4, or 8, not {self.bits_per_byte}.")
        if self.samples_per_group < 1:
            raise ValueError(f"samples_per_group must be 1 or more, not {self.samples_per_group}.")
        if self.keyed and self.samples_per_group != 1:
            raise ValueError("A keyed algorithm must use one sample at a time.")

    @property
    def detectable(self) -> bool:
        """Say whether its messages can be told apart from others without a passphrase."""
        return self.reads_like is None and not self.keyed

    def count_bytes(self, samples: int) -> int:
        """Return how many bytes this many samples carry."""
        return samples // self.samples_per_group * self.bits_per_byte // 8

    def embed_group(self, samples: bytes, sample_width: int, bits: tuple[int, ...]) -> bytes:
        """
        Put a group of bits into a group of samples.

        :param samples: The samples as they are stored
        :param sample_width: The size of one sample in bytes
        :param bits: As many bits as bits_per_byte
        :return: The changed samples, with the same size
        """
        return bytes((self.embed_bits(samples[0], bits),)) + samples[1:]

    def extract_group(self, low_bytes: bytes) -> tuple[int, ...]:
        """Get the hidden bits from the lowest bytes of a group of samples."""
        return self.extract_bits(low_bytes[0])


@dataclass(frozen=True)
class LegacyAlgorithm:
    """
    One way older versions hid bits, using every sample byte in order.

    :param name: The full name
    :param bits_per_byte: How many bits each sample byte carries
    :param extract_bits: Function that gets the hidden bits from a sample byte
    :param explanation: One line that explains the algorithm to a beginner
    :param replaced_because: Why it was replaced, one sentence each
    """

    name: str
    bits_per_byte: int
    extract_bits: ExtractBits
    explanation: str = ""
    replaced_because: tuple[str, ...] = ()
