"""Hide one or two bits in the lowest byte of each sample, so a sample moves by at most 1 or 3."""

from audiosteg.core.algorithm import Algorithm


def embed_one_bit(byte: int, bits: tuple[int, ...]) -> int:
    """Replace the lowest bit of a byte."""
    return (byte & 254) | bits[0]


def extract_one_bit(byte: int) -> tuple[int, ...]:
    """Read the lowest bit of a byte."""
    return (byte & 1,)


def embed_two_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Replace the two lowest bits of a byte."""
    return (byte & 252) | (bits[0] << 1) | bits[1]


def extract_two_bits(byte: int) -> tuple[int, ...]:
    """Read the second lowest and the lowest bit of a byte, in that order."""
    return (byte >> 1) & 1, byte & 1


LSB = Algorithm(
    name="LSB (1 bit per sample)",
    bits_per_byte=1,
    embed_bits=embed_one_bit,
    extract_bits=extract_one_bit,
    explanation="Hides 1 bit in each sample. Best sound quality.",
    strengths=(
        "The change is the smallest that a sample can have.",
        "The idea is easy to understand and fast.",
    ),
    weaknesses=(
        "It holds less than LSB_2.",
        "Editing, compressing, or converting the audio destroys the message.",
        "Anyone who looks at the lowest bits can find the message.",
    ),
)

LSB_2 = Algorithm(
    name="LSB_2 (2 bits per sample)",
    bits_per_byte=2,
    embed_bits=embed_two_bits,
    extract_bits=extract_two_bits,
    explanation="Hides 2 bits in each sample. Double the capacity, a little more noise.",
    strengths=(
        "It uses half as many samples as LSB for the same message.",
        "The change is still small in 16-bit audio.",
    ),
    weaknesses=(
        "A sample can change more than with LSB, so it adds more noise.",
        "Editing, compressing, or converting the audio destroys the message.",
        "Anyone who looks at the lowest bits can find the message.",
    ),
)
