"""Hide two bits per sample byte and flip its two lowest bits when it changes."""

from audiosteg.algorithms import enhanced_lsb
from audiosteg.core.algorithm import Algorithm


def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Flip the two lowest bits unless the byte already holds the message bits, then store those bits."""
    if enhanced_lsb.extract_bits(byte) != bits:
        byte ^= 3
    return enhanced_lsb.embed_bits(byte, bits)


ENHANCED_LSB_FLIP = Algorithm(
    name="Enhanced LSB Steganography with Bit Flipping",
    bits_per_byte=2,
    embed_bits=embed_bits,
    extract_bits=enhanced_lsb.extract_bits,
    output_file_name="enhanced_lsb_encoded_flip.wav",
)
