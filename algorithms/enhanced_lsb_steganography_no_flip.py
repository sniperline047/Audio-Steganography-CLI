"""Hide two bits in the fourth and third lowest bits of each sample byte."""

from utils.stego_file import read_message, write_message

BITS_PER_BYTE = 2


def embed_bits(byte: int, bits: tuple[int, ...]) -> int:
    """Replace the fourth and third lowest bits of a sample byte."""
    return (byte & 243) | (bits[0] << 3) | (bits[1] << 2)


def extract_bits(byte: int) -> tuple[int, ...]:
    """Read the fourth and third lowest bits, in that order."""
    return (byte >> 3) & 1, (byte >> 2) & 1


def encode(input_file_path: str, output_file_path: str, secret_message: str, overwrite: bool = False) -> None:
    """
    Encode a secret message into an audio file using enhanced LSB steganography (no flip).

    :param input_file_path: Path to the input audio file
    :param output_file_path: Path to the output encoded audio file
    :param secret_message: The message to be encoded
    :param overwrite: Whether an existing output file may be replaced
    """
    write_message(input_file_path, output_file_path, secret_message, BITS_PER_BYTE, embed_bits, overwrite)


def decode(input_file_path: str) -> str:
    """
    Decode a secret message from an audio file using enhanced LSB steganography (no flip).

    :param input_file_path: Path to the encoded audio file
    :return: The decoded secret message
    """
    return read_message(input_file_path, BITS_PER_BYTE, extract_bits)
