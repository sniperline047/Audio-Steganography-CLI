"""Hide four bits in the lowest byte of each sample, so a sample moves by at most 15."""

from audiosteg.core.algorithm import Algorithm


def embed_four_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Replace the four lowest bits of a byte."""
    return (byte & 240) | (bits[0] << 3) | (bits[1] << 2) | (bits[2] << 1) | bits[3]


def extract_four_bits(byte: int) -> tuple[int, ...]:
    """Read the four lowest bits of a byte, the highest of them first."""
    return (byte >> 3) & 1, (byte >> 2) & 1, (byte >> 1) & 1, byte & 1


LSB_4 = Algorithm(
    name="Enhanced LSB (4 bit)",
    bits_per_byte=4,
    embed_bits=embed_four_bits,
    extract_bits=extract_four_bits,
    explanation="Hides 4 bits in each sample. The most room, and the most noise.",
    strengths=(
        "It uses a quarter of the samples that LSB uses for the same message.",
        "No other algorithm here holds more.",
    ),
    weaknesses=(
        "A sample can move by 15, which can be heard in quiet or 8-bit audio.",
        "Editing, compressing, or converting the audio destroys the message.",
        "Anyone who looks at the lowest bits can find the message.",
    ),
)
