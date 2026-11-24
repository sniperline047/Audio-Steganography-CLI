"""Tests for audiosteg/analysis/samples.py."""

import io
import os
import wave
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import pack

from audiosteg.analysis import samples
from audiosteg.analysis.samples import (
    Part,
    SampleFormat,
    open_pair,
    read_blocks,
    seconds,
    to_bytes,
    to_values,
    write_wav,
)
from audiosteg.errors import UnsupportedFormatError

KNOWN = [
    (1, "00 01 7f 80 81 ff", [-128, -127, -1, 0, 1, 127]),
    (2, "0080 0180 ffff 0000 0100 3412 ff7f", [-32768, -32767, -1, 0, 1, 0x1234, 32767]),
    (3, "000080 ffffff 000000 010000 563412 ffff7f", [-8388608, -1, 0, 1, 0x123456, 8388607]),
    (4, "00000080 ffffffff 00000000 78563412 ffffff7f", [-2147483648, -1, 0, 0x12345678, 2147483647]),
]


@pytest.mark.parametrize(("width", "stored", "values"), KNOWN)
def test_samples_are_little_endian_numbers_around_silence(width: int, stored: str, values: list[int]) -> None:
    assert to_values(bytes.fromhex(stored), width) == values
    assert to_bytes(values, width) == bytes.fromhex(stored)


def test_24_bits_are_put_at_the_right_place_on_a_big_endian_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(samples, "sys", SimpleNamespace(byteorder="big"))
    shown: list[bytes] = []
    real = memoryview

    def record(data: bytes) -> Any:
        shown.append(bytes(data))
        return real(data)

    monkeypatch.setattr(samples, "memoryview", record, raising=False)
    to_values(b"\x01\x02\x03", 3)
    assert shown == [b"\x01\x02\x03\x00"]
    words = SimpleNamespace(tobytes=lambda: b"\x11\x22\x33\x44")
    monkeypatch.setattr(samples, "array", lambda code, values: words)
    assert to_bytes([0], 3) == b"\x22\x33\x44"


@pytest.mark.parametrize(
    ("part", "count", "sizes"),
    [
        (Part(0, 10), 10, [1] * 10),
        (Part(5, 7), 10, [0, 1, 1, 0, 1, 1, 0, 1, 1, 1]),
        (Part(0, 25), 10, [2, 3, 2, 3, 2, 3, 2, 3, 2, 3]),
        (Part(3, 0), 10, [0] * 10),
    ],
)
def test_a_part_is_split_without_gaps(part: Part, count: int, sizes: list[int]) -> None:
    pieces = part.split(count)
    assert [piece.frames for piece in pieces] == sizes
    assert [piece.first for piece in pieces] == [part.first + sum(sizes[:n]) for n in range(count)]


@pytest.mark.parametrize(("width", "full"), [(1, 128), (2, 32768), (3, 8388608), (4, 2147483648)])
def test_the_numbers_of_a_format(width: int, full: int) -> None:
    sample_format = SampleFormat(255, width, 3)
    assert (sample_format.full_scale, sample_format.frame_size) == (full, 255 * width)
    assert seconds(2, sample_format) == Fraction(2, 3)


@pytest.mark.parametrize("channels", [1, 2, 3, 255])
@pytest.mark.parametrize("bits", [8, 16, 24, 32])
def test_blocks_hold_exactly_the_part(
    make_samples: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, bits: int, channels: int
) -> None:
    monkeypatch.setattr(samples, "BLOCK_BYTES", 100)
    values = [(number * 7) % 251 - 125 for number in range(40 * channels)]
    path = make_samples("a.wav", values, bits, channels)
    for first, frames in [(0, 40), (0, 0), (39, 1), (11, 13), (40, 0)]:
        with wave.open(str(path)) as audio:
            blocks = list(read_blocks(audio, Part(first, frames)))
        assert b"".join(blocks) == pack(values[first * channels : (first + frames) * channels], bits)
        size = channels * bits // 8
        assert all(0 < len(block) <= max(100, size) and len(block) % size == 0 for block in blocks)


def test_a_written_file_says_how_long_it_really_is() -> None:
    target = io.BytesIO()
    write_wav(target, SampleFormat(2, 3, 11025), 9, [b"abcdef", b"ghijkl"])
    with wave.open(io.BytesIO(target.getvalue())) as audio:
        assert audio.getparams()[:4] == (2, 3, 11025, 2)
        assert audio.readframes(9) == b"abcdefghijkl"


DIFFERENCES = [
    ({"channels": 2}, "The channels differ: 1 and 2. The lengths differ: 12 and 6 frames."),
    ({"sample_width": 2}, "The sample sizes differ: 8 and 16 bits. The lengths differ: 12 and 6 frames."),
    ({"frame_rate": 8001}, "The sample rates differ: 8000 and 8001 Hz."),
    ({"frames": b"x" * 11}, "The lengths differ: 12 and 11 frames."),
]


@pytest.mark.parametrize(("changes", "reason"), DIFFERENCES)
def test_every_property_that_differs_is_named(
    make_wav: Callable[..., Path], changes: dict[str, Any], reason: str
) -> None:
    usual = {"frames": b"x" * 12}
    paths = str(make_wav("a.wav", **usual)), str(make_wav("b.wav", **{**usual, **changes}))
    with pytest.raises(UnsupportedFormatError) as error, open_pair(*paths):
        pass
    assert str(error.value) == f"The files cannot be compared. {reason}"
    assert error.value.__notes__ == ["Compare a WAV file with the copy of it that hide made."]


@pytest.mark.parametrize("name", ["original", "encoded"])
@pytest.mark.parametrize("problem", ["short", "no audio"])
def test_a_bad_file_is_named(make_wav: Callable[..., Path], name: str, problem: str) -> None:
    paths = {"original": make_wav("a.wav"), "encoded": make_wav("b.wav")}
    data = paths[name].read_bytes()
    paths[name].write_bytes(data[:-1] if problem == "short" else b"text" * 20)
    with pytest.raises(UnsupportedFormatError) as error, open_pair(*map(str, paths.values())):
        pass
    assert error.value.__notes__ == [f"This is about the {name} file."]
    if problem == "short":
        assert str(error.value) == "The WAV file is shorter than its header says."


def test_files_without_samples_can_be_compared(make_wav: Callable[..., Path]) -> None:
    path = str(make_wav(frames=b""))
    with open_pair(path, path) as pair:
        assert (pair.frames, pair.format) == (0, SampleFormat(1, 1, 8000))


def test_a_file_that_gets_shorter_while_it_is_read(make_wav: Callable[..., Path]) -> None:
    path = make_wav(frames=bytes(1_000_000))
    with open_pair(str(path), str(path)) as pair:
        os.truncate(path, path.stat().st_size - 1)
        with pytest.raises(UnsupportedFormatError, match="shorter than its header says"):
            list(read_blocks(pair.original, Part(0, 1_000_000)))
