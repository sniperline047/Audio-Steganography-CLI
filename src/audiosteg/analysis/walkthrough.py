"""Hide one character in real samples, one step at a time."""

import hashlib
import wave
from dataclasses import dataclass
from itertools import islice, product

from audiosteg.analysis.samples import Part, SampleFormat, read_blocks, read_format, to_values
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.header import container_overhead
from audiosteg.core.keyed import count_groups, scattered_samples, split_key
from audiosteg.core.message_codec import (
    bits_to_bytes,
    bytes_to_bits,
    bytes_to_message,
    extract_groups,
    message_to_bytes,
)
from audiosteg.core.wav_io import open_pcm_wav
from audiosteg.errors import CapacityError

SCAN_FRAMES = 4096
LOUD_ENOUGH = 16
DEMO_SEED = "audiosteg demo"


@dataclass(frozen=True)
class SampleChange:
    """
    What happened to one sample.

    :param number: Its number in the walkthrough, from 1 on
    :param group: The number of its group, from 1 on
    :param position: Its place in the file, counting the samples of every channel, from 0 on
    :param hidden_bits: The bits that its group carries
    :param byte_before: Its lowest byte before the change
    :param byte_after: Its lowest byte after the change
    :param value_before: Its value before the change
    :param value_after: Its value after the change
    """

    number: int
    group: int
    position: int
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
class GroupChange:
    """
    What happened to a group of samples.

    :param number: The number of the group, from 1 on
    :param samples: Its samples
    """

    number: int
    samples: tuple[SampleChange, ...]

    @property
    def changed(self) -> SampleChange | None:
        """Return the sample that changed."""
        return next((sample for sample in self.samples if sample.change), None)


@dataclass(frozen=True)
class Walkthrough:
    """
    One character that was hidden in real samples.

    :param letter: The character
    :param data: Its UTF-8 bytes
    :param format: The format of the file
    :param first_frame: The frame that holds the earliest sample
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

    @property
    def groups(self) -> list[GroupChange]:
        """Return the samples in their groups."""
        numbers = dict.fromkeys(change.group for change in self.changes)
        return [
            GroupChange(number, tuple(change for change in self.changes if change.group == number))
            for number in numbers
        ]


def largest_possible_change(algorithm: Algorithm) -> int:
    """Return the largest change that the algorithm can make to a sample, tried on 16-bit samples."""
    largest = 0
    for byte, bits in product(range(256), product(range(2), repeat=algorithm.bits_per_byte)):
        group = bytes((byte, 0)) * algorithm.samples_per_group
        before, after = to_values(group, 2), to_values(algorithm.embed_group(group, 2, bits), 2)
        largest = max(largest, *(abs(new - old) for old, new in zip(before, after, strict=True)))
    return largest


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


def change_samples(
    block: bytes, data: bytes, algorithm: Algorithm, sample_width: int, positions: list[int]
) -> list[SampleChange]:
    """Hide bytes in samples with the function of the algorithm."""
    bits = list(bytes_to_bits(data))
    size, group_size = algorithm.bits_per_byte, algorithm.samples_per_group
    changes = []
    for group in range(len(bits) // size):
        hidden = tuple(bits[group * size : (group + 1) * size])
        start = group * group_size * sample_width
        before = block[start : start + group_size * sample_width]
        after = algorithm.embed_group(before, sample_width, hidden)
        values = zip(to_values(before, sample_width), to_values(after, sample_width), strict=True)
        for index, (old, new) in enumerate(values):
            number = group * group_size + index
            low_byte = index * sample_width
            changes.append(
                SampleChange(
                    number + 1,
                    group + 1,
                    positions[number],
                    hidden,
                    before[low_byte],
                    after[low_byte],
                    old,
                    new,
                )
            )
    return changes


def demo_positions(samples: int, count: int, algorithm: Algorithm) -> list[int]:
    """Return the first samples in the order of a demo seed, which is never made from a passphrase."""
    keys = split_key(hashlib.sha256(DEMO_SEED.encode()).digest())
    return list(islice(scattered_samples(keys.order, samples, algorithm), count))


def check_length(available: int, needed: int, algorithm: Algorithm) -> None:
    """Refuse a file that is too short. A keyed algorithm needs room for a whole container."""
    if algorithm.keyed:
        needed = max(needed, count_groups(container_overhead(encrypted=True), algorithm))
    if available < needed:
        raise CapacityError("The audio file is too short to hide one character.")


def read_samples(audio: wave.Wave_read, positions: list[int]) -> bytes:
    """Return the bytes of these samples, in this order."""
    sample_format = read_format(audio)
    block = b""
    for position in positions:
        frame, channel = divmod(position, sample_format.channels)
        (data,) = read_blocks(audio, Part(frame, 1))
        block += data[channel * sample_format.sample_width :][: sample_format.sample_width]
    return block


def walk_through(path: str, letter: str, algorithm: Algorithm) -> Walkthrough:
    """Hide one character in a part of a WAV file that can be heard. No file is changed."""
    data = message_to_bytes(letter)
    samples = count_groups(len(data), algorithm) * algorithm.samples_per_group
    with open_pcm_wav(path) as audio:
        sample_format = read_format(audio)
        channels = sample_format.channels
        frames = -(-samples // channels)
        check_length(audio.getnframes() * channels, frames * channels, algorithm)
        sound, volume = find_sound(audio)
        if algorithm.keyed:
            positions = demo_positions(audio.getnframes() * channels, samples, algorithm)
        else:
            start = min(sound, audio.getnframes() - frames) * channels
            positions = list(range(start, start + samples))
        block = read_samples(audio, positions)
    changes = change_samples(block, data, algorithm, sample_format.sample_width, positions)
    hidden = extract_groups(bytes(change.byte_after for change in changes), algorithm)
    read_back = bytes_to_message(bits_to_bytes(hidden))
    first_frame = min(positions) // channels
    return Walkthrough(letter, data, sample_format, first_frame, volume == 0, tuple(changes), read_back)
