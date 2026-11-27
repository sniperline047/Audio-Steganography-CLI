"""Hide a message in a WAV file and read it back, one group of samples at a time."""

import wave
from collections.abc import Iterable
from itertools import count

from audiosteg.core import crypto, keyed, signal_file
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
    extract_groups,
    message_to_bytes,
)
from audiosteg.core.signal_algorithm import SignalAlgorithm, check_library
from audiosteg.core.wav_io import (
    AudioData,
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
    PassphraseRequiredError,
    UnsupportedAlgorithmError,
)
from audiosteg.utils.output_path import check_output_path, normalize_output_path


def check_algorithm(algorithm: object) -> None:
    """Refuse anything that is not an algorithm, such as its name."""
    if not isinstance(algorithm, (Algorithm, SignalAlgorithm)):
        raise TypeError(f"The algorithm must be an Algorithm, not {type(algorithm).__name__}.")


def is_encrypted(algorithm: Algorithm | SignalAlgorithm, encrypted: bool) -> bool:
    """Say whether a message is encrypted, which an algorithm can demand."""
    return encrypted or algorithm.keyed


def count_container_bytes(samples: int, algorithm: Algorithm | SignalAlgorithm, channels: int) -> int:
    """Return the size of the largest container that fits in this many samples."""
    if isinstance(algorithm, SignalAlgorithm):
        return algorithm.largest_container(samples // channels)
    return algorithm.count_bytes(samples)


def count_message_bytes(
    samples: int, algorithm: Algorithm | SignalAlgorithm, encrypted: bool, channels: int = 1
) -> int:
    """Return the size of the largest message that fits in this many samples, counting every channel."""
    overhead = container_overhead(is_encrypted(algorithm, encrypted))
    return max(count_container_bytes(samples, algorithm, channels) - overhead, 0)


def message_fits(
    message_length: int,
    samples: int,
    algorithm: Algorithm | SignalAlgorithm,
    encrypted: bool,
    channels: int = 1,
) -> bool:
    """Say whether a message and its container fit in this many samples, counting every channel."""
    overhead = container_overhead(is_encrypted(algorithm, encrypted))
    return message_length + overhead <= count_container_bytes(samples, algorithm, channels)


def check_capacity(
    message_length: int,
    samples: int,
    algorithm: Algorithm | SignalAlgorithm,
    encrypted: bool,
    channels: int = 1,
) -> None:
    """Make sure the message and its container fit in the audio."""
    if not message_fits(message_length, samples, algorithm, encrypted, channels):
        if isinstance(algorithm, SignalAlgorithm) and not message_fits(
            0, samples, algorithm, encrypted, channels
        ):
            kind = "empty encrypted message" if encrypted else "empty message"
            raise CapacityError(f"The audio file is too short for this algorithm, even for an {kind}.")
        raise CapacityError(
            f"The message is too large: it needs {message_length} bytes and the audio file "
            f"can hold {count_message_bytes(samples, algorithm, encrypted, channels)} bytes."
        )


def check_key(algorithm: Algorithm | SignalAlgorithm, passphrase: str | None) -> None:
    """Make sure that a keyed algorithm gets a passphrase."""
    if algorithm.keyed and passphrase is None:
        raise PassphraseRequiredError("This algorithm always encrypts the message. A passphrase is needed.")


def embed_container(audio: AudioData, container: bytes, algorithm: Algorithm, order: Iterable[int]) -> None:
    """Put a container into groups of samples, in the given order."""
    bits = bytes_to_bits(container)
    groups = zip(*[bits] * algorithm.bits_per_byte, strict=True)
    size = algorithm.samples_per_group * audio.sample_width
    with memoryview(audio.frames) as frames:
        for group, number in zip(groups, order, strict=False):
            part = slice(number * size, (number + 1) * size)
            frames[part] = algorithm.embed_group(bytes(frames[part]), audio.sample_width, group)


def encode(
    input_path: str,
    output_path: str,
    message: str,
    algorithm: Algorithm | SignalAlgorithm,
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
    hide_message(input_path, output_path, message, algorithm, passphrase, overwrite)


def hide_message(
    input_path: str,
    output_path: str,
    message: str,
    algorithm: Algorithm | SignalAlgorithm,
    passphrase: str | None,
    overwrite: bool,
) -> float:
    """Do what encode does. Return what every sample was multiplied by: 1, or less to prevent clipping."""
    if isinstance(algorithm, LegacyAlgorithm):
        raise UnsupportedAlgorithmError("This algorithm can only read old files, not hide messages.")
    check_algorithm(algorithm)
    check_key(algorithm, passphrase)
    check_library(algorithm)
    passphrase_bytes = None
    if passphrase is not None:
        passphrase_bytes = crypto.passphrase_to_bytes(passphrase)
        crypto.check_available()
    message_bytes = message_to_bytes(message)
    output_path = normalize_output_path(output_path)
    check_output_path(input_path, output_path, overwrite)
    audio = read_audio(input_path)
    samples = len(audio.frames) // audio.sample_width
    check_capacity(len(message_bytes), samples, algorithm, passphrase is not None, audio.channels)

    gain = 1.0
    if isinstance(algorithm, SignalAlgorithm):
        container = build_container(message_bytes, passphrase_bytes)
        gain = signal_file.embed_container(audio, container, algorithm)
    elif algorithm.keyed and passphrase_bytes is not None:
        container, order = keyed.build_container(message_bytes, passphrase_bytes, algorithm, samples)
        embed_container(audio, container, algorithm, order)
    else:
        embed_container(audio, build_container(message_bytes, passphrase_bytes), algorithm, count())
    write_audio(input_path, output_path, audio, overwrite)
    return gain


def read_hidden_bytes(audio: wave.Wave_read, algorithm: Algorithm, size: int) -> bytes:
    """Read the first hidden bytes from the lowest byte of each sample."""
    samples = size * 8 // algorithm.bits_per_byte * algorithm.samples_per_group
    sample_width = audio.getsampwidth()
    sample_bytes = read_first_bytes(audio, samples * sample_width)
    return bits_to_bytes(extract_groups(sample_bytes[::sample_width], algorithm))


def find_header(audio: wave.Wave_read, path: str, algorithm: Algorithm | SignalAlgorithm) -> Header | None:
    """Read the container header, and refuse a length that does not fit in the audio."""
    if isinstance(algorithm, SignalAlgorithm):
        found = signal_file.find_header(signal_file.sound_in_file(audio, path), algorithm)
        return None if found is None else found[0]
    header = parse_header(read_hidden_bytes(audio, algorithm, HEADER_SIZE))
    if header is None:
        return None
    samples = count_sample_bytes(audio, path) // audio.getsampwidth()
    if header.container_size > algorithm.count_bytes(samples):
        raise DamagedMessageError("The hidden message is damaged: it is longer than the audio file.")
    return header


def read_header(path: str, algorithm: Algorithm | SignalAlgorithm) -> Header | None:
    """Return the header of a hidden message, or None if this algorithm finds no message."""
    with open_pcm_wav(path) as audio:
        return find_header(audio, path, algorithm)


def read_container(
    audio: wave.Wave_read, path: str, algorithm: Algorithm | SignalAlgorithm, header: Header
) -> bytes:
    """Read the whole container that a header describes, or as much of it as there is."""
    if isinstance(algorithm, SignalAlgorithm):
        sound = signal_file.sound_in_file(audio, path)
        return signal_file.read_container(sound, algorithm, header).data
    return read_hidden_bytes(audio, algorithm, header.container_size)


def decode(path: str, algorithm: Algorithm | SignalAlgorithm, *, passphrase: str | None = None) -> str:
    """
    Read a hidden message from a WAV file.

    :param path: Path to the encoded audio file
    :param algorithm: The algorithm that was used to hide the message
    :param passphrase: The passphrase of an encrypted message
    :return: The hidden message
    """
    check_algorithm(algorithm)
    check_key(algorithm, passphrase)
    passphrase_bytes = None if passphrase is None else crypto.passphrase_to_bytes(passphrase)
    with open_pcm_wav(path) as audio:
        if isinstance(algorithm, Algorithm) and algorithm.keyed and passphrase_bytes is not None:
            samples = count_sample_bytes(audio, path) // audio.getsampwidth()
            return bytes_to_message(keyed.read_message(audio, samples, passphrase_bytes, algorithm))
        header = find_header(audio, path, algorithm)
        if header is None:
            raise NoMessageError("No hidden message was found. Check the file and the algorithm.")
        check_passphrase_use(header, passphrase)
        container = read_container(audio, path, algorithm, header)

    if len(container) < header.container_size:
        raise DamagedMessageError("The audio file ends before the hidden message does.")
    return bytes_to_message(open_container(container, passphrase_bytes))
