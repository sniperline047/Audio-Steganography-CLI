"""Hide a message in a WAV file and read it back, one sample byte at a time."""

from collections.abc import Callable, Iterator
from itertools import islice

from utils.errors import CapacityError, NoMessageError
from utils.message_codec import (
    HEADER_BITS,
    MAX_MESSAGE_BITS,
    add_length_header,
    bits_to_bytes,
    bytes_to_bits,
    bytes_to_message,
    message_to_bytes,
    read_length_header,
)
from utils.output_path import check_output_path, normalize_output_path
from utils.wav_io import (
    check_regular_file,
    count_sample_bytes,
    open_pcm_wav,
    read_audio,
    read_first_bytes,
    write_audio,
)

EmbedBits = Callable[[int, tuple[int, ...]], int]
ExtractBits = Callable[[int], tuple[int, ...]]


def check_capacity(message_length: int, sample_bytes: int, bits_per_byte: int) -> None:
    """Make sure the message and its length header fit in the audio."""
    available = max(sample_bytes * bits_per_byte - HEADER_BITS, 0)
    available = min(available, MAX_MESSAGE_BITS) // 8
    if sample_bytes * bits_per_byte < HEADER_BITS or message_length > available:
        raise CapacityError(
            f"The message is too large: it needs {message_length} bytes "
            f"and the audio file can hold {available} bytes."
        )


def write_message(
    input_path: str,
    output_path: str,
    message: str,
    bits_per_byte: int,
    embed_bits: EmbedBits,
    overwrite: bool,
) -> None:
    """
    Hide a message in a copy of a WAV file.

    :param input_path: Path to the original audio file
    :param output_path: Path to the new audio file
    :param message: The message to hide
    :param bits_per_byte: How many bits each sample byte carries
    :param embed_bits: Function that puts a group of bits into a sample byte
    :param overwrite: Whether an existing output file may be replaced
    """
    message_bytes = message_to_bytes(message)
    check_regular_file(input_path)
    output_path = normalize_output_path(output_path)
    check_output_path(input_path, output_path, overwrite)
    audio = read_audio(input_path)
    check_capacity(len(message_bytes), len(audio.frames), bits_per_byte)

    bits = bytes_to_bits(add_length_header(message_bytes))
    position = 0
    while group := tuple(islice(bits, bits_per_byte)):
        audio.frames[position] = embed_bits(audio.frames[position], group)
        position += 1

    write_audio(input_path, output_path, audio, overwrite)


def extract_all(sample_bytes: bytes, extract_bits: ExtractBits) -> Iterator[int]:
    """Yield the hidden bits of every sample byte."""
    for byte in sample_bytes:
        yield from extract_bits(byte)


def read_message(path: str, bits_per_byte: int, extract_bits: ExtractBits) -> str:
    """
    Read a hidden message from a WAV file.

    :param path: Path to the encoded audio file
    :param bits_per_byte: How many bits each sample byte carries
    :param extract_bits: Function that gets the hidden bits from a sample byte
    :return: The hidden message
    """
    header_size = HEADER_BITS // bits_per_byte
    with open_pcm_wav(path) as audio:
        header = read_first_bytes(audio, header_size)
        available = count_sample_bytes(audio, path) * bits_per_byte - HEADER_BITS
        length = read_length_header(list(extract_all(header, extract_bits)), available)
        sample_bytes = read_first_bytes(audio, header_size + length // bits_per_byte)

    message_bits = extract_all(sample_bytes[header_size:], extract_bits)
    message_bytes = bits_to_bytes(message_bits)
    if len(message_bytes) * 8 != length:
        raise NoMessageError("The audio file ends before the hidden message does.")
    return bytes_to_message(message_bytes)
