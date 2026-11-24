"""Read PCM WAV files and write them without damaging existing files."""

import os
import secrets
import shutil
import stat
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from utils.errors import UnsafeOutputError, UnsupportedFormatError

WAVE_FORMAT_IEEE_FLOAT = 3
MAX_FRAME_SIZE = 2**16 - 1
MAX_BYTES_PER_SECOND = 2**32 - 1


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


@contextmanager
def open_pcm_wav(path: str) -> Iterator[wave.Wave_read]:
    """Open a PCM WAV file for reading."""
    check_regular_file(path)
    with open(path, "rb") as source:
        try:
            with wave.open(source, "rb") as audio:
                check_pcm(audio)
                yield audio
        except (wave.Error, EOFError, RuntimeError) as error:
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
    if frame_size > MAX_FRAME_SIZE or frame_size * audio.getframerate() > MAX_BYTES_PER_SECOND:
        raise UnsupportedFormatError("The WAV file has too many channels or too high a sample rate.")


def count_frames(audio: wave.Wave_read, file_size: int) -> int:
    """Return the number of frames, ignoring a header that claims more than the file can hold."""
    frame_size = audio.getnchannels() * audio.getsampwidth()
    return min(audio.getnframes(), file_size // frame_size)


def read_audio(path: str) -> AudioData:
    """Read a whole PCM WAV file."""
    with open_pcm_wav(path) as audio:
        frame_size = audio.getnchannels() * audio.getsampwidth()
        frames = bytearray(audio.readframes(count_frames(audio, os.path.getsize(path))))
        del frames[len(frames) - len(frames) % frame_size :]
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


def check_output_path(input_path: str, output_path: str, overwrite: bool) -> None:
    """Refuse output paths that could damage the input or another existing file."""
    if not output_path:
        raise UnsafeOutputError("The output path is empty.")
    if os.path.islink(output_path):
        raise UnsafeOutputError(f"The output path is a symbolic link: {output_path}")
    if not os.path.exists(output_path):
        return
    if os.path.samefile(input_path, output_path):
        raise UnsafeOutputError("The input and output must be different files.")
    if not os.path.isfile(output_path):
        raise UnsafeOutputError(f"The output path is not a regular file: {output_path}")
    if not overwrite:
        raise FileExistsError(f"The output file already exists: {output_path}")
    if not os.access(output_path, os.W_OK):
        raise PermissionError(f"The output file is read-only: {output_path}")


def write_audio(input_path: str, output_path: str, audio: AudioData, overwrite: bool) -> None:
    """Write a WAV file to a temporary file, then move it into place in one step."""
    check_output_path(input_path, output_path, overwrite)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".stego_{secrets.token_hex(8)}.tmp"
    try:
        with open(temporary, "xb") as destination:
            with wave.open(destination, "wb") as new_audio:
                new_audio.setnchannels(audio.channels)
                new_audio.setsampwidth(audio.sample_width)
                new_audio.setframerate(audio.frame_rate)
                new_audio.writeframes(audio.frames)
            destination.flush()
            os.fsync(destination.fileno())
        if target.exists():
            shutil.copymode(target, temporary)
        check_output_path(input_path, output_path, overwrite)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
