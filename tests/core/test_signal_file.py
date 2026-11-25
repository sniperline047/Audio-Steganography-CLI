"""Tests for audiosteg/core/signal_file.py."""

import math
import os
import random
import tracemalloc
import wave
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from conftest import pack

from audiosteg import decode, encode
from audiosteg.algorithms.echo import ECHO
from audiosteg.core import signal_file
from audiosteg.core.signal_file import embed_container, find_header, sound_in_memory
from audiosteg.core.stego_file import read_header
from audiosteg.core.wav_io import AudioData
from audiosteg.errors import (
    CapacityError,
    DamagedMessageError,
    NoMessageError,
    StegoError,
    UnsuitableAudioError,
    WrongPassphraseError,
)

pytestmark = pytest.mark.needs_signal

BLOCK = 1024
SMALLEST = 46 * 8 * BLOCK


def noise(samples: int, bits: int, share: float = 0.3, seed: int = 1) -> list[int]:
    limit = int(((1 << bits - 1) - 1) * share)
    chooser = random.Random(seed)
    return [chooser.randint(-limit, limit) for _ in range(samples)]


def numbers(data: bytes, bits: int) -> list[int]:
    if bits == 8:
        return [value - 128 for value in data]
    size = bits // 8
    return [
        int.from_bytes(data[start : start + size], "little", signed=True)
        for start in range(0, len(data), size)
    ]


@pytest.mark.parametrize(("bits", "channels"), [(8, 1), (16, 2), (24, 1), (32, 3)])
@pytest.mark.parametrize("frame_rate", [8000, 44100])
def test_a_round_trip(
    make_samples: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    tmp_path: Path,
    bits: int,
    channels: int,
    frame_rate: int,
) -> None:
    frames = SMALLEST + 16 * 8 * BLOCK + 777
    values = noise(frames, bits)
    sound = [value for value in values for _ in range(channels)]
    source = make_samples("input.wav", sound, bits, channels=channels, frame_rate=frame_rate)
    original, output = source.read_bytes(), tmp_path / "output.wav"
    encode(str(source), str(output), "Héllo 🎵", ECHO)
    assert decode(str(output)) == decode(str(output), ECHO) == "Héllo 🎵"
    assert source.read_bytes() == original
    with wave.open(str(output)) as audio:
        assert audio.getparams()[:4] == (channels, bits // 8, frame_rate, frames)
    used = (26 + 15 + 16) * 8 * BLOCK + 128
    size = used * channels * bits // 8
    assert read_frames(output)[size:] == read_frames(source)[size:]


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
def test_an_encrypted_round_trip(make_samples: Callable[..., Path], tmp_path: Path) -> None:
    source, output = make_samples("input.wav", noise(130 * 8 * BLOCK, 16)), str(tmp_path / "output.wav")
    encode(str(source), output, "hidden", ECHO, passphrase="sesame")
    assert decode(output, passphrase="sesame") == "hidden"
    with pytest.raises(WrongPassphraseError):
        decode(output, passphrase="wrong")


def test_the_empty_message_and_the_exact_limit(make_samples: Callable[..., Path], tmp_path: Path) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_samples("input.wav", noise(SMALLEST, 16))), output, "", ECHO)
    assert decode(output) == ""
    short = str(make_samples("short.wav", noise(SMALLEST - 1, 16)))
    with pytest.raises(CapacityError, match="needs 0 bytes and the audio file can hold 0"):
        encode(short, output, "", ECHO, overwrite=True)
    encode(str(make_samples("more.wav", noise(146 * 8 * BLOCK, 16))), output, "x" * 56, ECHO, overwrite=True)
    assert decode(output) == "x" * 56
    with pytest.raises(CapacityError, match="needs 57 bytes and the audio file can hold 56"):
        encode(str(tmp_path / "more.wav"), output, "x" * 57, ECHO, overwrite=True)


@pytest.mark.parametrize("bits", [8, 16, 24, 32])
def test_the_loudest_sound_becomes_quieter_and_never_wraps_around(
    make_samples: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path, bits: int
) -> None:
    smallest, largest = -(1 << bits - 1), (1 << bits - 1) - 1
    chooser = random.Random(1)
    values = [chooser.choice([smallest, largest]) for _ in range(SMALLEST + 4096)]
    output = tmp_path / "output.wav"
    encode(str(make_samples("input.wav", values, bits)), str(output), "", ECHO)
    changed = numbers(read_frames(output), bits)
    assert decode(str(output)) == ""
    assert max(map(abs, changed)) <= largest
    assert all((old > 0) == (new > 0) for old, new in zip(values, changed, strict=True))
    tail = {abs(value) for value in changed[SMALLEST + 128 :]}
    assert max(tail) - min(tail) <= 1
    assert max(tail) / largest == pytest.approx(1 / 1.2, abs=0.01)


def silence(frames: int) -> list[int]:
    return [0] * frames


def tone(frames: int) -> list[int]:
    """Return a tone that repeats after 25 frames, so that both echoes are the same."""
    return [round(9000 * math.sin(2 * math.pi * frame / 25)) for frame in range(frames)]


def clicks(frames: int) -> list[int]:
    return [20000 if frame % 50000 == 7 else 0 for frame in range(frames)]


def half_silent(frames: int) -> list[int]:
    return noise(frames // 2, 16) + silence(frames - frames // 2)


@pytest.mark.parametrize("sound", [silence, tone, clicks, half_silent])
def test_a_sound_that_cannot_carry_the_message_is_refused(
    make_samples: Callable[..., Path], tmp_path: Path, sound: Callable[[int], list[int]]
) -> None:
    source = make_samples("input.wav", sound(SMALLEST + 5 * 8 * BLOCK))
    for overwrite in (False, True):
        with pytest.raises(UnsuitableAudioError, match="nothing was saved"):
            encode(str(source), str(tmp_path / "output.wav"), "Hello", ECHO, overwrite=overwrite)
    assert os.listdir(tmp_path) == ["input.wav"]


def test_channels_that_cancel_each_other_are_refused(
    make_samples: Callable[..., Path], tmp_path: Path
) -> None:
    values = [value for number in noise(SMALLEST, 16) for value in (number, -number)]
    with pytest.raises(UnsuitableAudioError):
        encode(str(make_samples("input.wav", values, channels=2)), str(tmp_path / "o.wav"), "", ECHO)


@pytest.mark.parametrize(
    ("strains", "used"),
    [
        ([0.5], 1),
        ([None, 0.51, 0.1], 3),
        ([None, None, None, 1.0], 4),
        ([0.9, 0.9, 0.9, 0.9], 4),
        ([0.9, 0.9, 0.9, None], None),
    ],
)
def test_the_weakest_comfortable_level_is_used_and_the_last_only_if_it_must(
    monkeypatch: pytest.MonkeyPatch, strains: list[float | None], used: int | None
) -> None:
    tried: list[float] = []

    def embed_bits(audio: AudioData, original: bytes, bits: list[int], algorithm: Any, level: float) -> float:
        tried.append(level)
        return 1.0

    answers = iter(strains)
    monkeypatch.setattr(signal_file, "embed_bits", embed_bits)
    monkeypatch.setattr(signal_file, "read_back", lambda audio, container, algorithm: next(answers))
    audio = AudioData(1, 2, 8000, bytearray(2000))
    if used is None:
        with pytest.raises(UnsuitableAudioError):
            embed_container(audio, b"ASTG\x01\0\0\0\0\0\x88\x4c\xb7\x7e", ECHO)
    else:
        embed_container(audio, b"ASTG\x01\0\0\0\0\0\x88\x4c\xb7\x7e", ECHO)
        assert tried == list(ECHO.levels[:used])


def test_a_container_that_reads_differently_is_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    audio = AudioData(1, 2, 8000, bytearray(pack(noise(SMALLEST, 16), 16)))
    embed_container(audio, b"ASTG\x01\0\0\0\0\0good", ECHO)
    assert signal_file.read_back(audio, b"ASTG\x01\0\0\0\0\0good", ECHO) is not None
    assert signal_file.read_back(audio, b"ASTG\x01\0\0\0\0\0evil", ECHO) is None


def damaged_copy(path: Path, name: str, change: Callable[[bytearray], None]) -> str:
    data = bytearray(path.read_bytes())
    change(data)
    (path.parent / name).write_bytes(data)
    return str(path.parent / name)


@pytest.fixture
def hidden(make_samples: Callable[..., Path], tmp_path: Path) -> Path:
    """A file that holds Hello and 100 more blocks."""
    output = tmp_path / "hidden.wav"
    frames = SMALLEST + 5 * 8 * BLOCK + 100 * BLOCK
    encode(str(make_samples("input.wav", noise(frames, 16))), str(output), "Hello", ECHO)
    return output


def replace_frames(first: int, count: int, seed: int) -> Callable[[bytearray], None]:
    def change(data: bytearray) -> None:
        data[44 + 2 * first : 44 + 2 * (first + count)] = pack(noise(count, 16, seed=seed), 16)

    return change


def test_some_lost_sound_is_corrected_and_more_is_reported(hidden: Path) -> None:
    body = 26 * 8 * BLOCK
    assert decode(damaged_copy(hidden, "a.wav", replace_frames(0, 5 * 8 * BLOCK, 9)), ECHO) == "Hello"
    assert decode(damaged_copy(hidden, "b.wav", replace_frames(body, 6 * 8 * BLOCK, 9)), ECHO) == "Hello"
    with pytest.raises(NoMessageError):
        decode(damaged_copy(hidden, "c.wav", replace_frames(0, 20 * 8 * BLOCK, 9)), ECHO)
    with pytest.raises(DamagedMessageError, match="too much of it"):
        decode(damaged_copy(hidden, "d.wav", replace_frames(body, 20 * 8 * BLOCK, 9)), ECHO)


@pytest.mark.parametrize("seed", range(25))
def test_damage_never_gives_a_wrong_text(hidden: Path, seed: int) -> None:
    chooser = random.Random(seed)
    frames = SMALLEST + 5 * 8 * BLOCK

    def change(data: bytearray) -> None:
        for _ in range(chooser.randint(1, 6)):
            start = chooser.randrange(frames)
            replace_frames(start, min(chooser.randrange(frames // 4), frames - start), seed)(data)

    try:
        assert decode(damaged_copy(hidden, "damaged.wav", change), ECHO) == "Hello"
    except StegoError as error:
        assert isinstance(error, (NoMessageError, DamagedMessageError))


@pytest.mark.parametrize("cut", [1, 2, 200 * BLOCK, 202 * BLOCK + 1, 600 * BLOCK, 900 * BLOCK])
def test_a_file_that_ends_early(hidden: Path, cut: int) -> None:
    path = damaged_copy(hidden, "cut.wav", lambda data: data.__delitem__(slice(len(data) - cut, None)))
    remaining = (508 * BLOCK * 2 - cut) // (2 * BLOCK)
    if remaining >= 408:
        assert decode(path, ECHO) == "Hello"
        return
    with pytest.raises(DamagedMessageError if remaining >= 208 else NoMessageError):
        decode(path, ECHO)


def test_a_header_that_promises_more_than_the_file_is_not_believed(hidden: Path) -> None:
    def change(data: bytearray) -> None:
        data[40:44] = (2**32 - 100).to_bytes(4, "little")

    assert decode(damaged_copy(hidden, "large.wav", change), ECHO) == "Hello"


@pytest.mark.parametrize("frames", [0, 1, BLOCK, 207 * BLOCK, 208 * BLOCK, 300 * BLOCK])
def test_a_tiny_file_has_no_message(make_samples: Callable[..., Path], frames: int) -> None:
    path = str(make_samples("input.wav", noise(frames, 16)))
    assert read_header(path, ECHO) is None
    with pytest.raises(NoMessageError):
        decode(path)


@pytest.mark.parametrize("sound", [silence, tone, clicks])
def test_a_sound_without_a_message_has_none(
    make_samples: Callable[..., Path], sound: Callable[[int], list[int]]
) -> None:
    assert read_header(str(make_samples("input.wav", sound(300 * BLOCK))), ECHO) is None


def test_a_length_that_cannot_be_true_is_damage(make_samples: Callable[..., Path]) -> None:
    from audiosteg.core.reed_solomon import make_parity

    header = b"ASTG\x01\x00" + (2**32 - 1).to_bytes(4, "big")
    bits = [int(digit) for byte in header + make_parity(header, 16) for digit in f"{byte:08b}"]
    audio = AudioData(1, 2, 8000, bytearray(pack(noise(SMALLEST, 16), 16)))
    signal_file.embed_bits(audio, bytes(audio.frames), bits, ECHO, 0.4)
    with pytest.raises(DamagedMessageError, match="longer than the audio file"):
        find_header(sound_in_memory(audio), ECHO)
    path = make_samples("input.wav", numbers(bytes(audio.frames), 16))
    with pytest.raises(DamagedMessageError, match="longer than the audio file"):
        decode(str(path))


def test_small_pieces_give_the_same(
    make_samples: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    values = [value for value in noise(SMALLEST, 16, share=1.0) for _ in range(2)]
    source = str(make_samples("input.wav", values, channels=2))
    encode(source, str(tmp_path / "large.wav"), "", ECHO)
    monkeypatch.setattr(signal_file, "BLOCKS_AT_A_TIME", 1)
    monkeypatch.setattr(signal_file, "BYTES_AT_A_TIME", 3000)
    encode(source, str(tmp_path / "small.wav"), "", ECHO)
    large, small = (tmp_path / "large.wav").read_bytes(), (tmp_path / "small.wav").read_bytes()
    assert large == small
    assert decode(str(tmp_path / "small.wav")) == ""


def test_a_header_is_found_without_reading_a_large_file(
    make_wav: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = str(make_wav(frames=bytes(30_000_000), channels=2, sample_width=2))
    assert read_header(path, ECHO) is None
    tracemalloc.start()
    try:
        assert read_header(path, ECHO) is None
        assert tracemalloc.get_traced_memory()[1] < 12_000_000
    finally:
        tracemalloc.stop()


def test_an_older_message_of_another_algorithm_is_not_left_behind(
    make_samples: Callable[..., Path], tmp_path: Path
) -> None:
    first, second = str(tmp_path / "first.wav"), str(tmp_path / "second.wav")
    quiet = silence(2000) + noise(SMALLEST + 40 * 8 * BLOCK, 16)
    for algorithm in ECHO.earlier:
        encode(str(make_samples("input.wav", quiet)), first, "older", algorithm, overwrite=True)
        untouched = replace(ECHO, earlier=())
        encode(first, second, "x", untouched, overwrite=True)
        assert read_header(second, algorithm) is not None
        encode(first, second, "x", ECHO, overwrite=True)
        assert decode(second) == "x"


def test_a_body_that_ends_early_in_a_file_that_hides_it(
    make_samples: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_samples("input.wav", noise(SMALLEST, 16))), str(output), "", ECHO)
    path = damaged_copy(output, "cut.wav", lambda data: data.__delitem__(slice(len(data) - 2, None)))
    with pytest.raises(DamagedMessageError, match="ends before the hidden message does"):
        decode(path, ECHO)
