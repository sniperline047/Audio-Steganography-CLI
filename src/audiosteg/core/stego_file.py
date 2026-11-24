"""Hide a message in a WAV file and read it back, one sample at a time."""

import wave
from itertools import islice

from audiosteg.core import crypto
from audiosteg.core.algorithm import Algorithm, LegacyAlgorithm
from audiosteg.core.header import (
    HEADER_SIZE,
    Header,
    build_container,
    check_passphrase_use,
    container_overhead,
    open_container,
    parse_header,
)
from audiosteg.core.message_codec import (
    bits_to_bytes,
    bytes_to_bits,
    bytes_to_message,
    extract_all,
    message_to_bytes,
)
from audiosteg.core.wav_io import (
    count_sample_bytes,
    open_pcm_wav,
    read_audio,
    read_first_bytes,
    write_audio,
)
from audiosteg.errors import (
    CapacityError,
    DamagedMessageError,
    NoMessageError,
    UnsupportedAlgorithmError,
)
from audiosteg.utils.output_path import check_output_path, normalize_output_path


def check_algorithm(algorithm: object) -> None:
    """Refuse anything that is not an algorithm, such as its name."""
    if not isinstance(algorithm, Algorithm):
        raise TypeError(f"The algorithm must be an Algorithm, not {type(algorithm).__name__}.")


def check_capacity(message_length: int, samples: int, bits_per_byte: int, encrypted: bool) -> None:
    """Make sure the message and its container fit in the audio."""
    available = samples * bits_per_byte // 8 - container_overhead(encrypted)
    if message_length > available:
        raise CapacityError(
            f"The message is too large: it needs {message_length} bytes "
            f"and the audio file can hold {max(available, 0)} bytes."
        )


def encode(
    input_path: str,
    output_path: str,
    message: str,
    algorithm: Algorithm,
    *,
    passphrase: str | None = None,
    overwrite: bool = False,
) -> None:
    """
    Hide a message in a copy of a WAV file.

    :param input_path: Path to the original audio file
    :param output_path: Path to the new audio file
    :param message: The message to hide
    :param algorithm: The algorithm that hides the bits
    :param passphrase: The passphrase that encrypts the message, or None for no encryption
    :param overwrite: Whether an existing output file may be replaced
    """
    if isinstance(algorithm, LegacyAlgorithm):
        raise UnsupportedAlgorithmError("This algorithm can only read old files, not hide messages.")
    check_algorithm(algorithm)
    passphrase_bytes = None
    if passphrase is not None:
        passphrase_bytes = crypto.passphrase_to_bytes(passphrase)
        crypto.check_available()
    message_bytes = message_to_bytes(message)
    output_path = normalize_output_path(output_path)
    check_output_path(input_path, output_path, overwrite)
    audio = read_audio(input_path)
    samples = len(audio.frames) // audio.sample_width
    check_capacity(len(message_bytes), samples, algorithm.bits_per_byte, passphrase is not None)

    bits = bytes_to_bits(build_container(message_bytes, passphrase_bytes))
    position = 0
    while group := tuple(islice(bits, algorithm.bits_per_byte)):
        audio.frames[position] = algorithm.embed_bits(audio.frames[position], group)
        position += audio.sample_width

    write_audio(input_path, output_path, audio, overwrite)


def read_hidden_bytes(audio: wave.Wave_read, algorithm: Algorithm, count: int) -> bytes:
    """Read the first hidden bytes from the lowest byte of each sample."""
    samples = count * 8 // algorithm.bits_per_byte
    sample_width = audio.getsampwidth()
    sample_bytes = read_first_bytes(audio, samples * sample_width)
    return bits_to_bytes(extract_all(sample_bytes[::sample_width], algorithm.extract_bits))


def find_header(audio: wave.Wave_read, path: str, algorithm: Algorithm) -> Header | None:
    """Read the container header, and refuse a length that does not fit in the audio."""
    header = parse_header(read_hidden_bytes(audio, algorithm, HEADER_SIZE))
    if header is None:
        return None
    samples = count_sample_bytes(audio, path) // audio.getsampwidth()
    if header.container_size > samples * algorithm.bits_per_byte // 8:
        raise DamagedMessageError("The hidden message is damaged: it is longer than the audio file.")
    return header


def read_header(path: str, algorithm: Algorithm) -> Header | None:
    """Return the header of a hidden message, or None if this algorithm finds no message."""
    with open_pcm_wav(path) as audio:
        return find_header(audio, path, algorithm)


def decode(path: str, algorithm: Algorithm, *, passphrase: str | None = None) -> str:
    """
    Read a hidden message from a WAV file.

    :param path: Path to the encoded audio file
    :param algorithm: The algorithm that was used to hide the message
    :param passphrase: The passphrase of an encrypted message
    :return: The hidden message
    """
    check_algorithm(algorithm)
    passphrase_bytes = None if passphrase is None else crypto.passphrase_to_bytes(passphrase)
    with open_pcm_wav(path) as audio:
        header = find_header(audio, path, algorithm)
        if header is None:
            raise NoMessageError("No hidden message was found. Check the file and the algorithm.")
        check_passphrase_use(header, passphrase)
        container = read_hidden_bytes(audio, algorithm, header.container_size)

    if len(container) < header.container_size:
        raise DamagedMessageError("The audio file ends before the hidden message does.")
    return bytes_to_message(open_container(container, passphrase_bytes))
