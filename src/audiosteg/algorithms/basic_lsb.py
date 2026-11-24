"""Hide one bit in the lowest bit of each sample byte."""

from audiosteg.core.algorithm import Algorithm


def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Replace the lowest bit of a sample byte."""
    return (byte & 254) | bits[0]


def extract_bits(byte: int) -> tuple[int, ...]:
    """Read the lowest bit of a sample byte."""
    return (byte & 1,)


BASIC_LSB = Algorithm(
    name="Basic LSB Steganography",
    bits_per_byte=1,
    embed_bits=embed_bits,
    extract_bits=extract_bits,
    output_file_name="basic_lsb_encoded.wav",
)
