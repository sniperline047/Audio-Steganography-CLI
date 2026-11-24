"""Tests for algorithms/basic_lsb_steganography.py."""

import random
import wave
from collections.abc import Callable
from itertools import product
from pathlib import Path
from types import ModuleType

import pytest

from algorithms import (
    basic_lsb_steganography,
    enhanced_lsb_steganography_no_flip,
    enhanced_lsb_steganography_with_flip,
)
from utils.errors import CapacityError, NoMessageError

BITS_PER_BYTE = 1
COVER = bytes((index * 37 + 11) % 256 for index in range(80))
UTF8_CARRIER = bytes.fromhex(
    "0a30547a9ec4e80e32587ca2c6ec10365a80a4caee14385e82a8ccf3173c6086aad1f41a3f6488ae"
    "d3f91c42668cb1d7fb20456a8fb4d8ff23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
OLD_ASCII_CARRIER = bytes.fromhex(
    "0a30547a9ec4e80e32587ca2c6ec10365a80a4caee14385e82a8ccf3173c6086aad1f41a3f6589af"
    "d2f91d42678db0d6fa21456a8eb5d8fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
OLD_LATIN_1_CARRIER = bytes.fromhex(
    "0a30547a9ec4e80e32587ca2c6ec10365a80a4caee14385e82a8cdf2163c6086aad1f51a3e6489af"
    "d2f91d42668cb0d7fa21456a8eb5d9fe23496d92b7dc00274b7095badf04294e7398bde2072c5176"
)


def test_known_answer_bytes_for_encode(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(make_wav(frames=COVER)), str(output), "Hé")
    assert read_frames(output) == UTF8_CARRIER


@pytest.mark.parametrize(
    ("carrier", "message"),
    [(UTF8_CARRIER, "Hé"), (OLD_ASCII_CARRIER, "Old"), (OLD_LATIN_1_CARRIER, "café")],
    ids=["utf_8", "old_ascii", "old_latin_1"],
)
def test_known_answer_bytes_for_decode(make_wav: Callable[..., Path], carrier: bytes, message: str) -> None:
    assert basic_lsb_steganography.decode(str(make_wav(frames=carrier))) == message


def test_round_trip_at_every_length_from_0_to_400(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    letters = random.Random(11)
    for length in range(401):
        message = "".join(chr(letters.randrange(32, 127)) for _ in range(length))
        basic_lsb_steganography.encode(str(source), str(output), message, overwrite=True)
        assert basic_lsb_steganography.decode(str(output)) == message


@pytest.mark.parametrize("sample_bytes", [32, 33, 39, 40, 41, 200])
def test_exact_capacity_fits_and_one_byte_more_does_not(
    make_wav: Callable[..., Path], tmp_path: Path, sample_bytes: int
) -> None:
    source = make_wav(frames=bytes(sample_bytes))
    output = tmp_path / "output.wav"
    capacity = (sample_bytes * BITS_PER_BYTE - 32) // 8
    with pytest.raises(CapacityError, match=f"can hold {capacity} bytes"):
        basic_lsb_steganography.encode(str(source), str(output), "x" * (capacity + 1))
    assert not output.exists()
    basic_lsb_steganography.encode(str(source), str(output), "x" * capacity)
    assert basic_lsb_steganography.decode(str(output)) == "x" * capacity


def test_capacity_counts_utf_8_bytes_not_characters(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav(frames=bytes(64 // BITS_PER_BYTE))
    output = tmp_path / "output.wav"
    with pytest.raises(CapacityError):
        basic_lsb_steganography.encode(str(source), str(output), "🎵é")
    basic_lsb_steganography.encode(str(source), str(output), "🎵")
    assert basic_lsb_steganography.decode(str(output)) == "🎵"


@pytest.mark.parametrize(
    "message",
    ["日本語 العربية", "👨\u200d👩\u200d👧 e\u0301", "a\0b\0", "\x1b[31m\r\n\t", "####"],
    ids=["scripts", "joined_emoji", "nul", "control", "hashes"],
)
def test_special_text_round_trips_unchanged(
    make_wav: Callable[..., Path], tmp_path: Path, message: str
) -> None:
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(make_wav()), str(output), message)
    assert basic_lsb_steganography.decode(str(output)) == message


@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2, 6])
def test_every_audio_shape_keeps_its_properties_and_message(
    make_wav: Callable[..., Path], tmp_path: Path, channels: int, sample_width: int
) -> None:
    frames = random.Random(3).randbytes(channels * sample_width * 180)
    source = make_wav(frames=frames, channels=channels, sample_width=sample_width, frame_rate=44100)
    original = source.read_bytes()
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(source), str(output), "shape")
    assert basic_lsb_steganography.decode(str(output)) == "shape"
    assert source.read_bytes() == original
    with wave.open(str(output), "rb") as audio:
        assert audio.getparams()[:4] == (channels, sample_width, 44100, 180)
        changed = audio.readframes(180)
    used = (32 + 40) // BITS_PER_BYTE
    assert changed[:used] != frames[:used]
    assert changed[used:] == frames[used:]


@pytest.mark.parametrize("other", [enhanced_lsb_steganography_no_flip, enhanced_lsb_steganography_with_flip])
def test_decoding_with_another_kind_of_algorithm_does_not_reveal_the_message(
    make_wav: Callable[..., Path], tmp_path: Path, other: ModuleType
) -> None:
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(make_wav()), str(output), "secret")
    with pytest.raises(NoMessageError):
        other.decode(str(output))


def test_audio_too_short_for_a_header_holds_no_message(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav(frames=bytes(32 // BITS_PER_BYTE - 1))
    output = tmp_path / "output.wav"
    with pytest.raises(NoMessageError):
        basic_lsb_steganography.decode(str(source))
    with pytest.raises(CapacityError):
        basic_lsb_steganography.encode(str(source), str(output), "")
    assert not output.exists()


def test_only_the_lowest_bit_of_a_byte_changes() -> None:
    for byte, bit in product(range(256), range(2)):
        assert basic_lsb_steganography.embed_bits(byte, (bit,)) == byte // 2 * 2 + bit
