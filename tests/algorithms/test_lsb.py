"""Tests for audiosteg/algorithms/lsb.py."""

import random
import wave
from collections.abc import Callable
from itertools import product
from pathlib import Path

import pytest

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.errors import CapacityError, NoMessageError

CONTAINER = bytes.fromhex("4153544701000000000348c3a9a411cc3b")
OVERHEAD = 14

both = pytest.mark.parametrize("algorithm", [LSB, LSB_2], ids=["LSB", "LSB_2"])


@both
@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
def test_known_answer_bytes(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    tmp_path: Path,
    algorithm: Algorithm,
    sample_width: int,
) -> None:
    size = algorithm.bits_per_byte
    cover = bytes((index * 37 + 11) % 256 for index in range(200 * sample_width))
    digits = "".join(f"{byte:08b}" for byte in CONTAINER)
    expected = bytearray(cover)
    for sample in range(len(digits) // size):
        position = sample * sample_width
        group = int(digits[sample * size : (sample + 1) * size], 2)
        expected[position] = cover[position] >> size << size | group
    output = tmp_path / "output.wav"
    encode(str(make_wav(frames=cover, sample_width=sample_width)), str(output), "Hé", algorithm)
    assert read_frames(output) == expected
    assert decode(str(output), algorithm) == "Hé"


@both
def test_round_trip_at_every_length_from_0_to_400(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm
) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    letters = random.Random(11)
    for length in range(401):
        message = "".join(chr(letters.randrange(32, 127)) for _ in range(length))
        encode(str(source), str(output), message, algorithm, overwrite=True)
        assert decode(str(output), algorithm) == message


@both
@pytest.mark.parametrize("spare_samples", [0, 1, 7, 8, 9, 200])
def test_exact_capacity_fits_and_one_byte_more_does_not(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm, spare_samples: int
) -> None:
    samples = OVERHEAD * 8 // algorithm.bits_per_byte + spare_samples
    source = make_wav(frames=bytes(samples))
    output = tmp_path / "output.wav"
    capacity = samples * algorithm.bits_per_byte // 8 - OVERHEAD
    with pytest.raises(CapacityError, match=f"can hold {capacity} bytes"):
        encode(str(source), str(output), "x" * (capacity + 1), algorithm)
    assert not output.exists()
    encode(str(source), str(output), "x" * capacity, algorithm)
    assert decode(str(output), algorithm) == "x" * capacity


@both
def test_capacity_counts_utf_8_bytes_not_characters(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm
) -> None:
    source = make_wav(frames=bytes((OVERHEAD + 4) * 8 // algorithm.bits_per_byte))
    output = tmp_path / "output.wav"
    with pytest.raises(CapacityError):
        encode(str(source), str(output), "🎵é", algorithm)
    encode(str(source), str(output), "🎵", algorithm)
    assert decode(str(output), algorithm) == "🎵"


@both
@pytest.mark.parametrize(
    "message",
    ["日本語 العربية", "👨\u200d👩\u200d👧 e\u0301", "a\0b\0", "\x1b[31m\r\n\t", "####"],
    ids=["scripts", "joined_emoji", "nul", "control", "hashes"],
)
def test_special_text_round_trips_unchanged(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm, message: str
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), message, algorithm)
    assert decode(str(output), algorithm) == message


@both
@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2, 6])
def test_every_audio_shape_keeps_its_properties_and_message(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm, channels: int, sample_width: int
) -> None:
    frames = random.Random(3).randbytes(channels * sample_width * 180)
    source = make_wav(frames=frames, channels=channels, sample_width=sample_width, frame_rate=44100)
    original = source.read_bytes()
    output = tmp_path / "output.wav"
    encode(str(source), str(output), "shape", algorithm)
    assert decode(str(output), algorithm) == "shape"
    assert source.read_bytes() == original
    with wave.open(str(output), "rb") as audio:
        assert audio.getparams()[:4] == (channels, sample_width, 44100, 180)
        changed = audio.readframes(180)
    used = (OVERHEAD + 5) * 8 // algorithm.bits_per_byte * sample_width
    assert changed[:used] != frames[:used]
    assert changed[used:] == frames[used:]


@pytest.mark.parametrize(("algorithm", "other"), [(LSB, LSB_2), (LSB_2, LSB)])
def test_decoding_with_another_algorithm_does_not_reveal_the_message(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm, other: Algorithm
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "secret", algorithm)
    with pytest.raises(NoMessageError):
        decode(str(output), other)


@both
def test_audio_too_short_for_a_container_holds_no_message(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Algorithm
) -> None:
    source = make_wav(frames=bytes(OVERHEAD * 8 // algorithm.bits_per_byte - 1))
    output = tmp_path / "output.wav"
    with pytest.raises(NoMessageError):
        decode(str(source), algorithm)
    with pytest.raises(CapacityError):
        encode(str(source), str(output), "", algorithm)
    assert not output.exists()


def test_only_the_lowest_bits_of_a_byte_change() -> None:
    for byte, high, low in product(range(256), range(2), range(2)):
        assert LSB.embed_bits(byte, (low,)) == byte // 2 * 2 + low
        assert LSB_2.embed_bits(byte, (high, low)) == byte // 4 * 4 + high * 2 + low
