"""Tests for algorithms/enhanced_lsb_steganography_no_flip.py."""

import random
import wave
from collections.abc import Callable
from itertools import product
from pathlib import Path
from types import ModuleType

import pytest

from algorithms import basic_lsb_steganography, enhanced_lsb_steganography_no_flip
from utils.errors import CapacityError, NoMessageError

BITS_PER_BYTE = 2
COVER = bytes((index * 37 + 11) % 256 for index in range(80))
UTF8_CARRIER = bytes.fromhex(
    "0330517293c0e102335071a2c3e419325780a9c2ef10315e8ba8c9f6173c6186abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
OLD_ASCII_CARRIER = bytes.fromhex(
    "0330517293c0e102335071a2c3e419325780adcee7183d5287a8c5f2173c6186abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)
OLD_LATIN_1_CARRIER = bytes.fromhex(
    "0330517293c0e102335071a2c3e811325788a1cee718315687a8c5fa1f386986abd0f51a3f6489ae"
    "d3f81d42678cb1d6fb20456a8fb4d9fe23486d92b7dc01264b7095badf04294e7398bde2072c5176"
)


def test_known_answer_bytes_for_encode(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    enhanced_lsb_steganography_no_flip.encode(str(make_wav(frames=COVER)), str(output), "Hé")
    assert read_frames(output) == UTF8_CARRIER


@pytest.mark.parametrize(
    ("carrier", "message"),
    [(UTF8_CARRIER, "Hé"), (OLD_ASCII_CARRIER, "Old"), (OLD_LATIN_1_CARRIER, "café")],
    ids=["utf_8", "old_ascii", "old_latin_1"],
)
def test_known_answer_bytes_for_decode(make_wav: Callable[..., Path], carrier: bytes, message: str) -> None:
    assert enhanced_lsb_steganography_no_flip.decode(str(make_wav(frames=carrier))) == message


def test_round_trip_at_every_length_from_0_to_400(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    letters = random.Random(11)
    for length in range(401):
        message = "".join(chr(letters.randrange(32, 127)) for _ in range(length))
        enhanced_lsb_steganography_no_flip.encode(str(source), str(output), message, overwrite=True)
        assert enhanced_lsb_steganography_no_flip.decode(str(output)) == message


@pytest.mark.parametrize("sample_bytes", [32, 33, 39, 40, 41, 200])
def test_exact_capacity_fits_and_one_byte_more_does_not(
    make_wav: Callable[..., Path], tmp_path: Path, sample_bytes: int
) -> None:
    source = make_wav(frames=bytes(sample_bytes))
    output = tmp_path / "output.wav"
    capacity = (sample_bytes * BITS_PER_BYTE - 32) // 8
    with pytest.raises(CapacityError, match=f"can hold {capacity} bytes"):
        enhanced_lsb_steganography_no_flip.encode(str(source), str(output), "x" * (capacity + 1))
    assert not output.exists()
    enhanced_lsb_steganography_no_flip.encode(str(source), str(output), "x" * capacity)
    assert enhanced_lsb_steganography_no_flip.decode(str(output)) == "x" * capacity


def test_capacity_counts_utf_8_bytes_not_characters(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav(frames=bytes(64 // BITS_PER_BYTE))
    output = tmp_path / "output.wav"
    with pytest.raises(CapacityError):
        enhanced_lsb_steganography_no_flip.encode(str(source), str(output), "🎵é")
    enhanced_lsb_steganography_no_flip.encode(str(source), str(output), "🎵")
    assert enhanced_lsb_steganography_no_flip.decode(str(output)) == "🎵"


@pytest.mark.parametrize(
    "message",
    ["日本語 العربية", "👨\u200d👩\u200d👧 e\u0301", "a\0b\0", "\x1b[31m\r\n\t", "####"],
    ids=["scripts", "joined_emoji", "nul", "control", "hashes"],
)
def test_special_text_round_trips_unchanged(
    make_wav: Callable[..., Path], tmp_path: Path, message: str
) -> None:
    output = tmp_path / "output.wav"
    enhanced_lsb_steganography_no_flip.encode(str(make_wav()), str(output), message)
    assert enhanced_lsb_steganography_no_flip.decode(str(output)) == message


@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2, 6])
def test_every_audio_shape_keeps_its_properties_and_message(
    make_wav: Callable[..., Path], tmp_path: Path, channels: int, sample_width: int
) -> None:
    frames = random.Random(3).randbytes(channels * sample_width * 180)
    source = make_wav(frames=frames, channels=channels, sample_width=sample_width, frame_rate=44100)
    original = source.read_bytes()
    output = tmp_path / "output.wav"
    enhanced_lsb_steganography_no_flip.encode(str(source), str(output), "shape")
    assert enhanced_lsb_steganography_no_flip.decode(str(output)) == "shape"
    assert source.read_bytes() == original
    with wave.open(str(output), "rb") as audio:
        assert audio.getparams()[:4] == (channels, sample_width, 44100, 180)
        changed = audio.readframes(180)
    used = (32 + 40) // BITS_PER_BYTE
    assert changed[:used] != frames[:used]
    assert changed[used:] == frames[used:]


@pytest.mark.parametrize("other", [basic_lsb_steganography])
def test_decoding_with_another_kind_of_algorithm_does_not_reveal_the_message(
    make_wav: Callable[..., Path], tmp_path: Path, other: ModuleType
) -> None:
    output = tmp_path / "output.wav"
    enhanced_lsb_steganography_no_flip.encode(str(make_wav()), str(output), "secret")
    with pytest.raises(NoMessageError):
        other.decode(str(output))


def test_audio_too_short_for_a_header_holds_no_message(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav(frames=bytes(32 // BITS_PER_BYTE - 1))
    output = tmp_path / "output.wav"
    with pytest.raises(NoMessageError):
        enhanced_lsb_steganography_no_flip.decode(str(source))
    with pytest.raises(CapacityError):
        enhanced_lsb_steganography_no_flip.encode(str(source), str(output), "")
    assert not output.exists()


def test_only_the_two_hidden_bits_of_a_byte_change() -> None:
    for byte, high, low in product(range(256), range(2), range(2)):
        hidden_bits = high * 8 + low * 4
        low_bits = byte & 3
        expected = (byte & 240) + hidden_bits + low_bits
        assert enhanced_lsb_steganography_no_flip.embed_bits(byte, (high, low)) == expected
