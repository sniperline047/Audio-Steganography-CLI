"""Hide one character in real samples, one step at a time."""

import wave
from dataclasses import dataclass
from itertools import product

from audiosteg.analysis.samples import Part, SampleFormat, read_blocks, read_format, to_values
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.message_codec import bits_to_bytes, bytes_to_bits, bytes_to_message, message_to_bytes
from audiosteg.core.wav_io import open_pcm_wav
from audiosteg.errors import CapacityError

SCAN_FRAMES = 4096
LOUD_ENOUGH = 16


@dataclass(frozen=True)
class SampleChange:
    """What happened to one sample."""

    number: int
    hidden_bits: tuple[int, ...]
    byte_before: int
    byte_after: int
    value_before: int
    value_after: int

    @property
    def change(self) -> int:
        """Return how much the sample changed."""
        return self.value_after - self.value_before


@dataclass(frozen=True)
class Walkthrough:
    """
    One character that was hidden in real samples.

    :param letter: The character
    :param data: Its UTF-8 bytes
    :param format: The format of the file
    :param first_frame: The frame that holds the first sample
    :param silent: Whether the whole file is silent
    :param changes: What happened to each sample
    :param read_back: The character that was read from the changed samples
    """

    letter: str
    data: bytes
    format: SampleFormat
    first_frame: int
    silent: bool
    changes: tuple[SampleChange, ...]
    read_back: str


def largest_possible_change(algorithm: Algorithm) -> int:
    """Return the largest change that the algorithm can make to a sample."""
    groups = list(product(range(2), repeat=algorithm.bits_per_byte))
    return max(abs(algorithm.embed_bits(byte, group) - byte) for byte in range(256) for group in groups)


def find_sound(audio: wave.Wave_read) -> tuple[int, int]:
    """Return the loudest frame of the first place that is not quiet, or of the file, and how loud it is."""
    sample_format = read_format(audio)
    loudest = (0, 0)
    frames = audio.getnframes()
    for start in range(0, frames, SCAN_FRAMES):
        block = b"".join(read_blocks(audio, Part(start, min(SCAN_FRAMES, frames - start))))
        volumes = [abs(value) for value in to_values(block, sample_format.sample_width)]
        peak = max(volumes)
        if peak > loudest[1]:
            loudest = (start + volumes.index(peak) // sample_format.channels, peak)
        if peak >= sample_format.full_scale // LOUD_ENOUGH:
            break
    return loudest


def change_samples(block: bytes, data: bytes, algorithm: Algorithm, sample_width: int) -> list[SampleChange]:
    """Hide bytes in samples with the function of the algorithm."""
    bits = list(bytes_to_bits(data))
    changes = []
    for number in range(len(bits) // algorithm.bits_per_byte):
        start = number * sample_width
        before = block[start : start + sample_width]
        group = tuple(bits[number * algorithm.bits_per_byte : (number + 1) * algorithm.bits_per_byte])
        low_byte = algorithm.embed_bits(before[0], group)
        after = bytes([low_byte]) + before[1:]
        changes.append(
            SampleChange(
                number + 1,
                group,
                before[0],
                low_byte,
                to_values(before, sample_width)[0],
                to_values(after, sample_width)[0],
            )
        )
    return changes


def walk_through(path: str, letter: str, algorithm: Algorithm) -> Walkthrough:
    """Hide one character in a part of a WAV file that can be heard. No file is changed."""
    data = message_to_bytes(letter)
    samples = len(data) * 8 // algorithm.bits_per_byte
    with open_pcm_wav(path) as audio:
        sample_format = read_format(audio)
        frames = -(-samples // sample_format.channels)
        if audio.getnframes() < frames:
            raise CapacityError("The audio file is too short to hide one character.")
        sound, volume = find_sound(audio)
        first = min(sound, audio.getnframes() - frames)
        block = b"".join(read_blocks(audio, Part(first, frames)))
    changes = change_samples(block, data, algorithm, sample_format.sample_width)
    hidden = [bit for change in changes for bit in algorithm.extract_bits(change.byte_after)]
    read_back = bytes_to_message(bits_to_bytes(hidden))
    return Walkthrough(letter, data, sample_format, first, volume == 0, tuple(changes), read_back)
