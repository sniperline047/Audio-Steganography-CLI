"""Hide a message in a WAV file and read it back, one sample byte at a time."""

from collections.abc import Iterator
from itertools import islice

from audiosteg.core.algorithm import Algorithm
from audiosteg.core.message_codec import (
    HEADER_BITS,
    MAX_MESSAGE_BITS,
    add_length_header,
    bits_to_bytes,
    bytes_to_bits,
    bytes_to_message,
    message_to_bytes,
    read_length_header,
)
from audiosteg.core.wav_io import (
    count_sample_bytes,
    open_pcm_wav,
    read_audio,
    read_first_bytes,
    write_audio,
)
from audiosteg.errors import CapacityError, NoMessageError
from audiosteg.utils.output_path import check_output_path, normalize_output_path


def check_capacity(message_length: int, sample_bytes: int, bits_per_byte: int) -> None:
    """Make sure the message and its length header fit in the audio."""
    available = max(sample_bytes * bits_per_byte - HEADER_BITS, 0)
    available = min(available, MAX_MESSAGE_BITS) // 8
    if sample_bytes * bits_per_byte < HEADER_BITS or message_length > available:
        raise CapacityError(
            f"The message is too large: it needs {message_length} bytes "
            f"and the audio file can hold {available} bytes."
        )


def encode(
    input_path: str, output_path: str, message: str, algorithm: Algorithm, *, overwrite: bool = False
) -> None:
    """
    Hide a message in a copy of a WAV file.

    :param input_path: Path to the original audio file
    :param output_path: Path to the new audio file
    :param message: The message to hide
    :param algorithm: The algorithm that hides the bits
    :param overwrite: Whether an existing output file may be replaced
    """
    message_bytes = message_to_bytes(message)
    output_path = normalize_output_path(output_path)
    check_output_path(input_path, output_path, overwrite)
    audio = read_audio(input_path)
    check_capacity(len(message_bytes), len(audio.frames), algorithm.bits_per_byte)

    bits = bytes_to_bits(add_length_header(message_bytes))
    position = 0
    while group := tuple(islice(bits, algorithm.bits_per_byte)):
        audio.frames[position] = algorithm.embed_bits(audio.frames[position], group)
        position += 1

    write_audio(input_path, output_path, audio, overwrite)


def extract_all(sample_bytes: bytes, algorithm: Algorithm) -> Iterator[int]:
    """Yield the hidden bits of every sample byte."""
    for byte in sample_bytes:
        yield from algorithm.extract_bits(byte)


def decode(path: str, algorithm: Algorithm) -> str:
    """
    Read a hidden message from a WAV file.

    :param path: Path to the encoded audio file
    :param algorithm: The algorithm that was used to hide the message
    :return: The hidden message
    """
    header_size = HEADER_BITS // algorithm.bits_per_byte
    with open_pcm_wav(path) as audio:
        header = read_first_bytes(audio, header_size)
        available = count_sample_bytes(audio, path) * algorithm.bits_per_byte - HEADER_BITS
        length = read_length_header(list(extract_all(header, algorithm)), available)
        sample_bytes = read_first_bytes(audio, header_size + length // algorithm.bits_per_byte)

    message_bits = extract_all(sample_bytes[header_size:], algorithm)
    message_bytes = bits_to_bytes(message_bits)
    if len(message_bytes) * 8 != length:
        raise NoMessageError("The audio file ends before the hidden message does.")
    return bytes_to_message(message_bytes)
