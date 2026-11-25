"""Read and write samples as numbers, a small block at a time."""

import sys
import wave
from array import array
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from fractions import Fraction
from typing import BinaryIO, NamedTuple

from audiosteg.core.wav_io import open_pcm_wav
from audiosteg.errors import UnsupportedFormatError

BLOCK_BYTES = 1 << 18
FLIP_HIGHEST_BIT = bytes(byte ^ 128 for byte in range(256))
TOO_SHORT = "The WAV file is shorter than its header says."


class SampleFormat(NamedTuple):
    """How the samples of a WAV file are stored."""

    channels: int
    sample_width: int
    frame_rate: int

    @property
    def frame_size(self) -> int:
        """Return the size of one frame, which is one sample of every channel, in bytes."""
        return self.channels * self.sample_width

    @property
    def full_scale(self) -> int:
        """Return the largest distance of a sample from silence."""
        return 1 << (8 * self.sample_width - 1)


class Part(NamedTuple):
    """A part of a WAV file, in frames."""

    first: int
    frames: int

    def split(self, count: int) -> list["Part"]:
        """Split into this many parts of almost the same size."""
        edges = [self.first + self.frames * number // count for number in range(count + 1)]
        return [Part(start, end - start) for start, end in zip(edges, edges[1:], strict=False)]


class Pair(NamedTuple):
    """Two open WAV files with the same format and the same number of frames."""

    original: wave.Wave_read
    encoded: wave.Wave_read
    format: SampleFormat
    frames: int


def read_format(audio: wave.Wave_read) -> SampleFormat:
    """Return the format of an open WAV file."""
    return SampleFormat(audio.getnchannels(), audio.getsampwidth(), audio.getframerate())


def seconds(frames: int, sample_format: SampleFormat) -> Fraction:
    """Return how long this many frames are."""
    return Fraction(frames, sample_format.frame_rate)


def is_complete(audio: wave.Wave_read) -> bool:
    """Say whether an open WAV file holds every frame that its header promises."""
    frames = audio.getnframes()
    if frames == 0:
        return True
    audio.setpos(frames - 1)
    try:
        return len(audio.readframes(1)) == read_format(audio).frame_size
    except RuntimeError:
        return False


def check_input(path: str, name: str) -> None:
    """Refuse a file that cannot be measured, and say which one it is."""
    try:
        with open_pcm_wav(path) as audio:
            if not is_complete(audio):
                raise UnsupportedFormatError(TOO_SHORT)
    except UnsupportedFormatError as error:
        error.add_note(f"This is about the {name} file.")
        raise


@contextmanager
def open_pair(original_path: str, encoded_path: str) -> Iterator[Pair]:
    """Open two WAV files, and refuse files that cannot be compared."""
    check_input(original_path, "original")
    check_input(encoded_path, "encoded")
    with open_pcm_wav(original_path) as original, open_pcm_wav(encoded_path) as encoded:
        pair = Pair(original, encoded, read_format(original), original.getnframes())
        differences = list(find_differences(pair))
        if differences:
            error = UnsupportedFormatError(f"The files cannot be compared. {' '.join(differences)}")
            error.add_note("Compare a WAV file with the copy of it that hide made.")
            raise error
        yield pair


def find_differences(pair: Pair) -> Iterator[str]:
    """Yield one sentence for every property that differs."""
    other = read_format(pair.encoded)
    frames = pair.encoded.getnframes()
    if pair.format.channels != other.channels:
        yield f"The channels differ: {pair.format.channels} and {other.channels}."
    if pair.format.sample_width != other.sample_width:
        yield f"The sample sizes differ: {8 * pair.format.sample_width} and {8 * other.sample_width} bits."
    if pair.format.frame_rate != other.frame_rate:
        yield f"The sample rates differ: {pair.format.frame_rate} and {other.frame_rate} Hz."
    if pair.frames != frames:
        yield f"The lengths differ: {pair.frames} and {frames} frames."


def read_blocks(audio: wave.Wave_read, part: Part) -> Iterator[bytes]:
    """Yield the bytes of a part, a block at a time."""
    frame_size = read_format(audio).frame_size
    block_frames = max(BLOCK_BYTES // frame_size, 1)
    audio.setpos(part.first)
    remaining = part.frames
    while remaining:
        wanted = min(remaining, block_frames)
        block = audio.readframes(wanted)
        if len(block) < wanted * frame_size:
            raise UnsupportedFormatError(TOO_SHORT)
        yield block
        remaining -= wanted


def read_pairs(pair: Pair, part: Part) -> Iterator[tuple[bytes, bytes]]:
    """Yield the bytes of a part of both files, a block at a time."""
    yield from zip(read_blocks(pair.original, part), read_blocks(pair.encoded, part), strict=True)


def to_values(data: bytes, sample_width: int) -> list[int]:
    """Return samples as whole numbers, where 0 is silence."""
    if sample_width == 1:
        return memoryview(data.translate(FLIP_HIGHEST_BIT)).cast("b").tolist()
    if sample_width == 2:
        return memoryview(data).cast("h").tolist()
    if sample_width == 4:
        return memoryview(data).cast("i").tolist()
    wide = bytearray(len(data) // 3 * 4)
    start = 1 if sys.byteorder == "little" else 0
    for position in range(3):
        wide[start + position :: 4] = data[position::3]
    return [value >> 8 for value in memoryview(wide).cast("i")]


def to_bytes(values: Iterable[int], sample_width: int) -> bytes:
    """Return whole numbers as samples."""
    if sample_width == 1:
        return array("b", values).tobytes().translate(FLIP_HIGHEST_BIT)
    if sample_width == 2:
        return array("h", values).tobytes()
    wide = array("i", values).tobytes()
    if sample_width == 4:
        return wide
    data = bytearray(len(wide) // 4 * 3)
    start = 0 if sys.byteorder == "little" else 1
    for position in range(3):
        data[position::3] = wide[start + position :: 4]
    return bytes(data)


def write_wav(
    destination: BinaryIO, sample_format: SampleFormat, frames: int, blocks: Iterable[bytes]
) -> None:
    """Write blocks of samples as a WAV file."""
    with wave.open(destination, "wb") as audio:
        audio.setnchannels(sample_format.channels)
        audio.setsampwidth(sample_format.sample_width)
        audio.setframerate(sample_format.frame_rate)
        audio.setnframes(frames)
        for block in blocks:
            audio.writeframesraw(block)
