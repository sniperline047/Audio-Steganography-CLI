"""Hide one bit in each group of 8 samples, as the parity of their lowest bits."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from audiosteg.algorithms.lsb import embed_one_bit, extract_one_bit
from audiosteg.core.algorithm import Algorithm

GROUP_SIZE = 8


@dataclass(frozen=True)
class LsbParity(Algorithm):
    """
    Flip the lowest bit of one sample if the parity of its group is wrong.

    :param choose: Function that returns a random number below a limit
    """

    choose: Callable[[int], int] = secrets.randbelow

    def embed_group(self, samples: bytes, sample_width: int, bits: tuple[int, ...]) -> bytes:
        """Leave a group that already has the parity, and change one random sample of any other."""
        if self.extract_group(samples[::sample_width]) == bits:
            return samples
        changed = bytearray(samples)
        changed[self.choose(self.samples_per_group) * sample_width] ^= 1
        return bytes(changed)

    def extract_group(self, low_bytes: bytes) -> tuple[int, ...]:
        """Return 1 if an odd number of the lowest bits is 1, and 0 if not."""
        return (sum(byte & 1 for byte in low_bytes) & 1,)


LSB_PARITY = LsbParity(
    name="LSB parity (1 bit per 8 samples)",
    bits_per_byte=1,
    embed_bits=embed_one_bit,
    extract_bits=extract_one_bit,
    explanation="Hides 1 bit in each group of 8 samples. Spreads the changes out, but has little room.",
    strengths=(
        "At most 1 of 8 samples changes, and on average about 1 of 16.",
        "Any sample of a group can carry the change, so a random one is chosen.",
    ),
    weaknesses=(
        "It holds an eighth of what LSB holds.",
        "Editing, compressing, or converting the audio destroys the message.",
        "Anyone who knows the groups can find the message.",
    ),
    how="Parity says whether the number of ones among the lowest bits of a group is even (0) or odd (1).",
    samples_per_group=GROUP_SIZE,
    parity=True,
)
