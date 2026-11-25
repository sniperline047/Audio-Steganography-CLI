"""Hide one bit in each sample by moving the whole sample up or down by 1."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from audiosteg.algorithms.lsb import LSB, embed_one_bit, extract_one_bit
from audiosteg.core.algorithm import Algorithm


def sample_range(sample_width: int) -> tuple[int, int]:
    """Return the smallest and the largest number that a sample can store. 8-bit samples have no sign."""
    if sample_width == 1:
        return 0, 255
    limit = 1 << (8 * sample_width - 1)
    return -limit, limit - 1


@dataclass(frozen=True)
class LsbMatching(Algorithm):
    """
    Move a sample by 1 if its lowest bit is wrong.

    :param choose: Function that returns a random number below a limit
    """

    choose: Callable[[int], int] = secrets.randbelow

    def embed_group(self, samples: bytes, sample_width: int, bits: tuple[int, ...]) -> bytes:
        """Leave a sample that already has the bit, and move any other up or down, but never too far."""
        if samples[0] & 1 == bits[0]:
            return samples
        signed = sample_width > 1
        value = int.from_bytes(samples, "little", signed=signed)
        smallest, largest = sample_range(sample_width)
        if value == smallest:
            step = 1
        elif value == largest:
            step = -1
        else:
            step = 1 if self.choose(2) else -1
        return (value + step).to_bytes(sample_width, "little", signed=signed)


LSB_MATCHING = LsbMatching(
    name="LSB matching (1 bit per sample)",
    bits_per_byte=1,
    embed_bits=embed_one_bit,
    extract_bits=extract_one_bit,
    explanation="Adds or subtracts 1 to hide 1 bit in a sample. Read as lsb.",
    strengths=(
        "The change is the smallest that a sample can have.",
        "It avoids the pattern that replacing the lowest bit leaves in the values of the samples.",
    ),
    weaknesses=(
        "The file does not show that it was used: inspect and reveal call it lsb.",
        "Editing, compressing, or converting the audio destroys the message.",
        "Anyone who looks at the lowest bits can find the message.",
    ),
    how="If the lowest bit is wrong, the whole sample moves by +1 or -1 at random, so more bits can change.",
    reads_like=LSB,
)
