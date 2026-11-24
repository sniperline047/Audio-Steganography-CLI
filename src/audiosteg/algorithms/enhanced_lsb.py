"""Hide two bits in the fourth and third lowest bits of each sample byte."""

from audiosteg.core.algorithm import Algorithm


def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Replace the fourth and third lowest bits of a sample byte."""
    return (byte & 243) | (bits[0] << 3) | (bits[1] << 2)


def extract_bits(byte: int) -> tuple[int, ...]:
    """Read the fourth and third lowest bits, in that order."""
    return (byte >> 3) & 1, (byte >> 2) & 1


ENHANCED_LSB = Algorithm(
    name="Enhanced LSB Steganography without Bit Flipping",
    bits_per_byte=2,
    embed_bits=embed_bits,
    extract_bits=extract_bits,
    output_file_name="enhanced_lsb_encoded_no_flip.wav",
)
