"""Hide two bits per sample byte and flip its two lowest bits when it changes."""

from utils.stego_file import read_message, write_message

BITS_PER_BYTE = 2


def check_flip(data: int, a: int, b: int) -> int:
    """
    Flip the two lowest bits of a byte unless it already holds the message bits.

    :param data: The byte to check
    :param a: First bit of the secret message
    :param b: Second bit of the secret message
    :return: The potentially modified byte
    """
    if extract_bits(data) == (a, b):
        return data
    return data ^ 3


def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Flip if needed, then replace the fourth and third lowest bits of a sample byte."""
    flipped = check_flip(byte, bits[0], bits[1])
    return (flipped & 243) | (bits[0] << 3) | (bits[1] << 2)


def extract_bits(byte: int) -> tuple[int, ...]:
    """Read the fourth and third lowest bits, in that order."""
    return (byte >> 3) & 1, (byte >> 2) & 1


def encode(input_file_path: str, output_file_path: str, secret_message: str, overwrite: bool = False) -> None:
    """
    Encode a secret message into an audio file using enhanced LSB steganography with flipping.

    :param input_file_path: Path to the input audio file
    :param output_file_path: Path to the output encoded audio file
    :param secret_message: The message to be encoded
    :param overwrite: Whether an existing output file may be replaced
    """
    write_message(input_file_path, output_file_path, secret_message, BITS_PER_BYTE, embed_bits, overwrite)


def decode(input_file_path: str) -> str:
    """
    Decode a secret message from an audio file using enhanced LSB steganography with flipping.

    :param input_file_path: Path to the encoded audio file
    :return: The decoded secret message
    """
    return read_message(input_file_path, BITS_PER_BYTE, extract_bits)
