"""Tests for audiosteg/analysis/inspection.py."""

import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zlib import crc32

import pytest

from audiosteg import decode
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.analysis import inspection
from audiosteg.analysis.inspection import Capacity, FoundMessage, inspect
from audiosteg.core import wav_io
from audiosteg.core.algorithm import Algorithm
from audiosteg.errors import UnsupportedFormatError


@pytest.mark.parametrize(
    ("samples", "lsb", "lsb_2"),
    [
        (0, (0, 0), (0, 0)),
        (112, (0, 0), (14, 0)),
        (119, (0, 0), (15, 0)),
        (120, (1, 0), (16, 0)),
        (432, (40, 0), (94, 54)),
        (440, (41, 1), (96, 56)),
    ],
)
@pytest.mark.parametrize(("width", "channels"), [(1, 1), (3, 1), (4, 2)])
def test_the_room_that_the_documentation_promises(
    make_wav: Callable[..., Path],
    samples: int,
    lsb: tuple[int, int],
    lsb_2: tuple[int, int],
    width: int,
    channels: int,
) -> None:
    samples -= samples % channels
    path = make_wav(frames=bytes(samples * width), channels=channels, sample_width=width, frame_rate=11025)
    found = inspect(str(path))
    assert found.format == (channels, width, 11025)
    assert found.frames == samples // channels
    if samples % 8 == 0:
        assert found.capacities[:2] == (Capacity("lsb", *lsb), Capacity("lsb_2", *lsb_2))
        lsb_4 = Capacity("lsb_4", max(samples // 2 - 14, 0), max(samples // 2 - 54, 0))
        parity = Capacity("lsb_parity", max(samples // 64 - 14, 0), max(samples // 64 - 54, 0))
        keyed = Capacity("lsb_keyed", 0, lsb[1], always_encrypted=True)
        echo = Capacity("echo", 0, 0, at_most=True)
        assert found.capacities[2:] == (lsb_4, Capacity("lsb_matching", *lsb), parity, keyed, echo)
    assert (found.cannot_hide, found.messages) == (None, ())


@pytest.mark.parametrize(("key", "size"), [("lsb", 1), ("lsb_2", 2)])
@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_a_message_is_described_by_its_header_only(
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    key: str,
    size: int,
    width: int,
) -> None:
    damaged = b"ASTG\x01\x00" + (5).to_bytes(4, "big") + b"HELLO" + b"bad!"
    path = make_wav(frames=embed(damaged, size, width), sample_width=width)
    assert inspect(str(path)).messages == (FoundMessage(key, False, 5),)
    path = make_wav(frames=embed(known_answer.container, size, width), sample_width=width)
    assert inspect(str(path)).messages == (FoundMessage(key, True, 8),)


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        (
            "02 00 00000000",
            "The hidden message uses format version 2, which this program cannot read, or it is",
        ),
        (
            "01 04 00000000",
            "The hidden message uses unknown flags (4), which this program cannot read, or it is",
        ),
        ("01 00 ffffffff", "The hidden message is damaged: it is longer than the audio file."),
    ],
)
def test_a_header_that_cannot_be_used(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], header: str, problem: str
) -> None:
    path = make_wav(frames=embed(b"ASTG" + bytes.fromhex(header) + bytes(4), 1))
    (message,) = inspect(str(path)).messages
    assert (message.algorithm, message.encrypted, message.size) == ("lsb", None, None)
    assert message.problem is not None and message.problem.startswith(problem)


def test_messages_of_two_algorithms_are_both_found(
    make_wav: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, embed: Callable[..., bytes]
) -> None:
    known = list(ALGORITHMS)
    second = Algorithm("", 1, lambda b, bits: (b & 253) | bits[0] << 1, lambda b: ((b >> 1) & 1,))
    monkeypatch.setitem(ALGORITHMS, "second", second)
    frames = bytearray(embed(b"ASTG\x01\x00\x00\x00\x00\x01A\x00\x00\x00\x00", 1))
    digits = "".join(f"{byte:08b}" for byte in b"ASTG\x01\x01\x00\x00\x00\x00" + bytes(44))
    frames += bytes(400)
    for index, digit in enumerate(digits):
        frames[index] = frames[index] & 253 | int(digit) << 1
    found = inspect(str(make_wav(frames=bytes(frames))))
    assert found.messages == (FoundMessage("lsb", False, 1), FoundMessage("second", True, 0))
    assert [capacity.algorithm for capacity in found.capacities] == [*known, "second"]


@pytest.mark.parametrize("missing", [1, 4, 5, 399])
@pytest.mark.parametrize("block_bytes", [1, 1 << 18])
def test_a_truncated_file(
    make_wav: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, missing: int, block_bytes: int
) -> None:
    monkeypatch.setattr(inspection, "BLOCK_BYTES", block_bytes)
    path = make_wav(frames=bytes(400), channels=2, sample_width=2)
    path.write_bytes(path.read_bytes()[:-missing])
    found = inspect(str(path))
    assert found.frames == (400 - missing) // 4
    assert found.cannot_hide == "The WAV file is shorter than its header says."
    assert (found.capacities, found.messages) == ((), ())


def test_a_message_in_a_truncated_file_is_found(
    make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    path = make_wav(frames=embed(b"ASTG\x01\x00\x00\x00\x00\x64" + bytes(104), 1))
    whole = path.read_bytes()
    path.write_bytes(whole[:-1])
    assert inspect(str(path)).messages == (FoundMessage("lsb", False, 100),)
    path.write_bytes(whole[:500])
    (message,) = inspect(str(path)).messages
    assert message.problem == "The hidden message is damaged: it is longer than the audio file."


def test_a_file_that_is_too_large_to_hide_in(
    make_wav: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wav_io, "MAX_INPUT_SIZE", 100)
    found = inspect(str(make_wav(frames=bytes(200))))
    assert found.cannot_hide == "The input file is too large. The limit is 1 GiB."
    assert (found.frames, found.capacities) == (200, ())


def test_a_header_that_promises_4_gib_is_not_believed(make_wav: Callable[..., Path]) -> None:
    path = make_wav(frames=bytes(64))
    data = bytearray(path.read_bytes())
    data[4:8], data[40:44] = struct.pack("<I", 0xFFFFFFF0), struct.pack("<I", 0xFFFFFFF0 - 36)
    path.write_bytes(data)
    found = inspect(str(path))
    assert (found.frames, found.capacities) == (64, ())
    assert found.cannot_hide == "The WAV file is shorter than its header says."


def test_a_file_whose_two_sizes_disagree(make_wav: Callable[..., Path], embed: Callable[..., bytes]) -> None:
    container = b"ASTG\x01\x00\x00\x00\x00\x01A"
    path = make_wav(frames=embed(container + crc32(container).to_bytes(4, "big"), 1))
    data = bytearray(path.read_bytes())
    data[40:44] = struct.pack("<I", 5000)
    path.write_bytes(data)
    assert decode(str(path)) == "A"
    assert inspect(str(path)).messages == (FoundMessage("lsb", False, 1),)


def test_a_file_that_is_not_a_wav_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.wav").write_text("text")
    with pytest.raises(UnsupportedFormatError):
        inspect(str(tmp_path / "a.wav"))
