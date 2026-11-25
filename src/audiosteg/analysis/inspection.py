"""Find out what a WAV file is, how much it can hold, and whether it holds a message."""

import wave
from dataclasses import dataclass

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.analysis.samples import BLOCK_BYTES, SampleFormat, is_complete, read_format
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.stego_file import count_message_bytes, read_header
from audiosteg.core.wav_io import count_input_samples, open_pcm_wav
from audiosteg.errors import DamagedMessageError, UnsupportedFormatError


@dataclass(frozen=True)
class Capacity:
    """
    The size of the largest message that one algorithm can hide, in bytes.

    :param always_encrypted: Whether the algorithm cannot hide a plain message, so that plain is 0
    """

    algorithm: str
    plain: int
    encrypted: int
    always_encrypted: bool = False


@dataclass(frozen=True)
class FoundMessage:
    """A hidden message that was detected. With a problem, its header could not be used."""

    algorithm: str
    encrypted: bool | None = None
    size: int | None = None
    problem: str | None = None


@dataclass(frozen=True)
class Inspection:
    """What is known about a WAV file."""

    format: SampleFormat
    frames: int
    cannot_hide: str | None
    capacities: tuple[Capacity, ...]
    messages: tuple[FoundMessage, ...]


def count_present_frames(audio: wave.Wave_read) -> int:
    """Return how many whole frames the file really holds, even if its header promises more."""
    if is_complete(audio):
        return audio.getnframes()
    frame_size = read_format(audio).frame_size
    audio.rewind()
    present = 0
    while block := audio.readframes(max(BLOCK_BYTES // frame_size, 1)):
        present += len(block) // frame_size
    return present


def find_message(path: str, key: str, algorithm: Algorithm) -> FoundMessage | None:
    """Look for a message of one algorithm. Only its header is read."""
    try:
        header = read_header(path, algorithm)
    except (DamagedMessageError, UnsupportedFormatError) as error:
        return FoundMessage(key, problem=str(error))
    return None if header is None else FoundMessage(key, header.encrypted, header.message_length)


def inspect(path: str) -> Inspection:
    """Describe a WAV file without reading any hidden message."""
    with open_pcm_wav(path) as audio:
        sample_format = read_format(audio)
        frames = count_present_frames(audio)
    try:
        samples, cannot_hide = count_input_samples(path), None
    except UnsupportedFormatError as error:
        samples, cannot_hide = 0, str(error)
    capacities = [
        Capacity(
            key,
            0 if algorithm.keyed else count_message_bytes(samples, algorithm, encrypted=False),
            count_message_bytes(samples, algorithm, encrypted=True),
            algorithm.keyed,
        )
        for key, algorithm in ALGORITHMS.items()
    ]
    found = [
        find_message(path, key, algorithm) for key, algorithm in ALGORITHMS.items() if algorithm.detectable
    ]
    return Inspection(
        sample_format,
        frames,
        cannot_hide,
        () if cannot_hide else tuple(capacities),
        tuple(message for message in found if message is not None),
    )
