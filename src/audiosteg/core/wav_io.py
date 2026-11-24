"""Read and write PCM WAV files."""

import os
import stat
import struct
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO, NamedTuple

from audiosteg.errors import UnsupportedFormatError
from audiosteg.utils.safe_write import safe_output

WAVE_FORMAT_IEEE_FLOAT = 3
MAX_BYTES_PER_SECOND = 2**32 - 1
UNKNOWN_DATA_SIZE = 2**32 - 1
MAX_INPUT_SIZE = 2**30


class AudioData(NamedTuple):
    """The properties and raw sample bytes of a PCM WAV file."""

    channels: int
    sample_width: int
    frame_rate: int
    frames: bytearray


def check_regular_file(path: str) -> None:
    """Reject directories, pipes, devices, and other files that are not regular files."""
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise UnsupportedFormatError(f"The input is not a regular file: {path}")


def check_header(source: BinaryIO) -> None:
    """Check fields that the wave module ignores. Stop at the start of the audio, as that module does."""
    expected_size = 0
    stored_size = 0
    source.seek(12)
    name, size = struct.unpack("<4sI", source.read(8))
    while name != b"data":
        chunk_start = source.tell()
        if name == b"fmt ":
            channels, stored_size, bits = struct.unpack("<2xH8xHH", source.read(16))
            expected_size = channels * ((bits + 7) // 8)
        source.seek(chunk_start + size + size % 2)
        name, size = struct.unpack("<4sI", source.read(8))
    if size == UNKNOWN_DATA_SIZE:
        raise UnsupportedFormatError("The WAV file does not state its audio size (a streamed file).")
    if stored_size != expected_size:
        raise UnsupportedFormatError("WAV files with padded samples are not supported.")


@contextmanager
def open_pcm_wav(path: str) -> Iterator[wave.Wave_read]:
    """Open a PCM WAV file for reading."""
    check_regular_file(path)
    with open(path, "rb") as source:
        try:
            with wave.open(source, "rb") as audio:
                check_pcm(audio)
                check_header(source)
                yield audio
        except (wave.Error, EOFError, RuntimeError, struct.error) as error:
            detail = str(error) or "the file is damaged or ends too early"
            raise UnsupportedFormatError(f"The input is not a valid PCM WAV file: {detail}") from error


def check_pcm(audio: wave.Wave_read) -> None:
    """Reject audio that is not 8, 16, 24, or 32-bit integer PCM."""
    get_format = getattr(audio, "getformat", None)
    if get_format is not None and get_format() == WAVE_FORMAT_IEEE_FLOAT:
        raise UnsupportedFormatError("Floating point WAV files are not supported. Use a PCM WAV file.")
    if not 1 <= audio.getsampwidth() <= 4:
        raise UnsupportedFormatError("Only 8, 16, 24, and 32-bit PCM WAV files are supported.")
    if audio.getframerate() < 1:
        raise UnsupportedFormatError("The WAV file has an invalid sample rate.")
    frame_size = audio.getnchannels() * audio.getsampwidth()
    if frame_size * audio.getframerate() > MAX_BYTES_PER_SECOND:
        raise UnsupportedFormatError("The WAV file has too high a sample rate.")


def count_frames(audio: wave.Wave_read, file_size: int) -> int:
    """Return the number of frames, ignoring a header that claims more than the file can hold."""
    frame_size = audio.getnchannels() * audio.getsampwidth()
    return min(audio.getnframes(), file_size // frame_size)


def read_audio(path: str) -> AudioData:
    """Read a whole PCM WAV file."""
    if os.path.getsize(path) > MAX_INPUT_SIZE:
        raise UnsupportedFormatError("The input file is too large. The limit is 1 GiB.")
    with open_pcm_wav(path) as audio:
        frame_size = audio.getnchannels() * audio.getsampwidth()
        frames = bytearray(audio.readframes(count_frames(audio, os.path.getsize(path))))
        if len(frames) < audio.getnframes() * frame_size:
            raise UnsupportedFormatError("The WAV file is shorter than its header says.")
        return AudioData(audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), frames)


def count_sample_bytes(audio: wave.Wave_read, path: str) -> int:
    """Return how many sample bytes the file holds."""
    frame_size = audio.getnchannels() * audio.getsampwidth()
    return count_frames(audio, os.path.getsize(path)) * frame_size


def read_first_bytes(audio: wave.Wave_read, count: int) -> bytes:
    """Read only the frames that contain the first sample bytes."""
    frame_size = audio.getnchannels() * audio.getsampwidth()
    frames_needed = -(-count // frame_size)
    audio.rewind()
    return audio.readframes(frames_needed)[:count]


def write_audio(input_path: str, output_path: str, audio: AudioData, overwrite: bool) -> None:
    """Write a WAV file safely. The output path must come from normalize_output_path."""
    with (
        safe_output(input_path, output_path, overwrite) as destination,
        wave.open(destination, "wb") as new_audio,
    ):
        new_audio.setnchannels(audio.channels)
        new_audio.setsampwidth(audio.sample_width)
        new_audio.setframerate(audio.frame_rate)
        new_audio.writeframes(audio.frames)
