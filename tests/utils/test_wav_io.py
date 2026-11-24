"""Tests for utils/wav_io.py."""

import os
import struct
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from utils import wav_io
from utils.errors import UnsupportedFormatError
from utils.wav_io import (
    AudioData,
    check_regular_file,
    count_sample_bytes,
    open_pcm_wav,
    read_audio,
    read_first_bytes,
    write_audio,
)

PCM, ADPCM, FLOAT, MU_LAW, EXTENSIBLE = 1, 2, 3, 7, 0xFFFE
PCM_SUBTYPE = bytes.fromhex("0100000000001000800000aa00389b71")
FLOAT_SUBTYPE = bytes.fromhex("0300000000001000800000aa00389b71")


def chunk(name: bytes, body: bytes, size: int | None = None) -> bytes:
    """Build one RIFF chunk, with a pad byte after an odd body."""
    return name + struct.pack("<I", len(body) if size is None else size) + body + b"\0" * (len(body) % 2)


def build_wav(
    audio_format: int = PCM,
    channels: int = 1,
    frame_rate: int = 8000,
    block_align: int = 2,
    bits: int = 16,
    extension: bytes = b"",
    before_format: bytes = b"",
    before_data: bytes = b"",
    data: bytes = bytes(range(200)),
    data_size: int | None = None,
) -> bytes:
    """Build the bytes of a WAV file with any header values."""
    bytes_per_second = frame_rate * block_align % 2**32
    fields = struct.pack("<HHIIHH", audio_format, channels, frame_rate, bytes_per_second, block_align, bits)
    format_chunk = chunk(b"fmt ", fields + extension)
    chunks = b"WAVE" + before_format + format_chunk + before_data + chunk(b"data", data, data_size)
    return chunk(b"RIFF", chunks)


def extensible(valid_bits: int, subtype: bytes) -> bytes:
    return struct.pack("<HHI", 22, valid_bits, 0) + subtype


@pytest.fixture
def save(tmp_path: Path) -> Callable[[bytes], str]:
    """Return a function that saves bytes as a file and returns its path."""

    def save_bytes(content: bytes) -> str:
        path = tmp_path / "input.wav"
        path.write_bytes(content)
        return str(path)

    return save_bytes


def test_a_valid_file_is_read_exactly(save: Callable[[bytes], str]) -> None:
    path = save(build_wav(channels=2, frame_rate=22050, block_align=4))
    assert read_audio(path) == AudioData(2, 2, 22050, bytearray(range(200)))


def test_other_chunks_are_skipped_even_with_odd_sizes(save: Callable[[bytes], str]) -> None:
    extra = chunk(b"LIST", b"odd") + chunk(b"JUNK", b"data" * 3) + chunk(b"PEAK", b"")
    path = save(build_wav(before_format=extra, before_data=extra) + chunk(b"id3 ", b"tags"))
    assert read_audio(path).frames == bytes(range(200))


def test_sample_bits_are_rounded_up_to_whole_bytes(save: Callable[[bytes], str]) -> None:
    assert read_audio(save(build_wav(bits=12))).sample_width == 2


@pytest.mark.parametrize("data_size", [2**32 - 2, 1000, 202])
def test_audio_shorter_than_its_header_says_is_refused(save: Callable[[bytes], str], data_size: int) -> None:
    with pytest.raises(UnsupportedFormatError):
        read_audio(save(build_wav(data_size=data_size)))


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"", "ends too early"),
        (b"RIFF", "ends too early"),
        (b"This is a text file, not audio.\n" * 20, "not a valid PCM WAV"),
        (chunk(b"RIFF", b"AVI " + bytes(100)), "not a valid PCM WAV"),
        (build_wav(audio_format=FLOAT, block_align=4, bits=32), "(?i)float|unknown format"),
        (build_wav(audio_format=FLOAT, block_align=8, bits=64), "(?i)float|unknown format"),
        (build_wav(audio_format=MU_LAW, block_align=1, bits=8), "unknown format"),
        (build_wav(block_align=4, bits=24), "padded"),
        (build_wav(block_align=2, bits=8), "padded"),
        (build_wav(block_align=4, bits=24, before_format=chunk(b"LIST", b"odd")), "padded"),
        (build_wav(before_format=chunk(b"LIST", b"even", size=10000)), "not a valid PCM WAV"),
        (build_wav(channels=2, block_align=2, bits=16), "padded"),
        (build_wav(data_size=2**32 - 1), "streamed"),
        (build_wav(channels=0, block_align=0), "channels"),
        (build_wav(block_align=0, bits=0), "sample width"),
        (build_wav(channels=0, block_align=2), "channels"),
        (build_wav(block_align=2, bits=0), "sample width"),
        (build_wav(audio_format=ADPCM, block_align=256, bits=4), "unknown format: 2"),
        (build_wav(block_align=8, bits=64), "8, 16, 24, and 32-bit"),
        (build_wav(block_align=5, bits=40), "8, 16, 24, and 32-bit"),
        (build_wav(frame_rate=0), "sample rate"),
        (build_wav(channels=40000, block_align=80000 % 2**16), "padded"),
        (build_wav(frame_rate=2**31), "too high a sample rate"),
        (chunk(b"RIFF", b"WAVE" + chunk(b"data", bytes(8))), "not a valid PCM WAV"),
        (chunk(b"RIFF", b"WAVE" + chunk(b"fmt ", bytes(4)) + chunk(b"data", b"")), "ends too early"),
        (build_wav()[:30], "ends too early"),
        (build_wav()[:40], "not a valid PCM WAV"),
    ],
    ids=[
        "empty", "four_bytes", "text", "other_riff", "float_32", "float_64", "mu_law", "padded_24_in_32",
        "padded_8_in_16", "padded_after_odd_chunk", "chunk_too_long", "block_too_small", "streamed",
        "no_channels", "no_bits", "no_channels_padded", "no_bits_padded", "adpcm",
        "64_bit", "40_bit", "no_rate", "too_many_channels", "rate_too_high",
        "no_format", "short_format", "cut_in_format", "no_data",
    ],
)  # fmt: skip
def test_unsupported_input_is_refused_with_a_reason(
    save: Callable[[bytes], str], content: bytes, reason: str
) -> None:
    with pytest.raises(UnsupportedFormatError, match=reason):
        read_audio(save(content))


def test_every_cut_of_a_valid_file_is_refused(save: Callable[[bytes], str]) -> None:
    content = build_wav(data=bytes(40))
    for length in range(len(content)):
        with pytest.raises(UnsupportedFormatError):
            read_audio(save(content[:length]))


@pytest.mark.skipif(sys.version_info >= (3, 12), reason="Python 3.12 and newer read extensible headers")
def test_extensible_files_are_refused_on_python_3_11(save: Callable[[bytes], str]) -> None:
    content = build_wav(audio_format=EXTENSIBLE, extension=extensible(16, PCM_SUBTYPE))
    with pytest.raises(UnsupportedFormatError, match="65534"):
        read_audio(save(content))


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python 3.11 cannot read extensible headers")
def test_extensible_pcm_files_are_read(save: Callable[[bytes], str]) -> None:
    content = build_wav(audio_format=EXTENSIBLE, extension=extensible(16, PCM_SUBTYPE))
    assert read_audio(save(content)) == AudioData(1, 2, 8000, bytearray(range(200)))


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python 3.11 cannot read extensible headers")
def test_extensible_float_files_are_refused(save: Callable[[bytes], str]) -> None:
    content = build_wav(
        audio_format=EXTENSIBLE, block_align=4, bits=32, extension=extensible(32, FLOAT_SUBTYPE)
    )
    with pytest.raises(UnsupportedFormatError):
        read_audio(save(content))


def test_input_over_the_size_limit_is_refused_before_it_is_read(
    save: Callable[[bytes], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    content = build_wav()
    path = save(content)
    monkeypatch.setattr(wav_io, "MAX_INPUT_SIZE", len(content))
    assert len(read_audio(path).frames) == 200
    monkeypatch.setattr(wav_io, "MAX_INPUT_SIZE", len(content) - 1)
    with pytest.raises(UnsupportedFormatError, match="too large"):
        read_audio(path)


def test_the_size_limit_is_one_gibibyte(tmp_path: Path) -> None:
    path = tmp_path / "huge.wav"
    path.write_bytes(build_wav(data_size=2**30))
    os.truncate(path, 2**30 + 1)
    with pytest.raises(UnsupportedFormatError, match="too large"):
        read_audio(str(path))


@pytest.mark.parametrize("check", [check_regular_file, read_audio])
def test_a_folder_is_not_an_input(tmp_path: Path, check: Callable[[str], object]) -> None:
    with pytest.raises(UnsupportedFormatError, match="not a regular file"):
        check(str(tmp_path))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="this system has no named pipes")
def test_a_named_pipe_is_refused_without_waiting(tmp_path: Path) -> None:
    path = tmp_path / "pipe"
    os.mkfifo(path)
    with pytest.raises(UnsupportedFormatError, match="not a regular file"), open_pcm_wav(str(path)):
        pass


def test_a_missing_file_is_reported_as_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_audio(str(tmp_path / "missing.wav"))


@pytest.mark.parametrize("count", [0, 1, 5, 6, 7, 200, 900])
def test_first_bytes_restart_and_stop_inside_a_frame(save: Callable[[bytes], str], count: int) -> None:
    path = save(build_wav(channels=2, block_align=4))
    with open_pcm_wav(path) as audio:
        read_first_bytes(audio, 13)
        assert read_first_bytes(audio, count) == bytes(range(200))[:count]


def test_a_header_that_claims_too_much_audio_is_limited_by_the_file_size(
    save: Callable[[bytes], str],
) -> None:
    content = build_wav(data_size=2**31)
    path = save(content)
    with open_pcm_wav(path) as audio:
        assert 200 <= count_sample_bytes(audio, path) <= len(content)


@pytest.mark.parametrize("frames", [b"", b"abc"], ids=["no_audio", "odd_size"])
def test_written_audio_is_read_back_and_replaces_nothing_else(
    tmp_path: Path, save: Callable[[bytes], str], frames: bytes
) -> None:
    audio = AudioData(1, 1, 44100, bytearray(frames))
    output = tmp_path / "output.wav"
    write_audio(save(build_wav()), str(output), audio, overwrite=False)
    assert read_audio(str(output)) == audio
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "output.wav"]


def test_the_output_is_a_plain_pcm_file(tmp_path: Path, save: Callable[[bytes], str]) -> None:
    output = tmp_path / "output.wav"
    write_audio(save(build_wav()), str(output), AudioData(1, 2, 8000, bytearray(range(200))), overwrite=False)
    assert output.read_bytes() == build_wav()
