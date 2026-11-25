"""Tests for audiosteg/algorithms/lsb_four.py."""

import random
from collections.abc import Callable
from itertools import product
from pathlib import Path

import pytest

from audiosteg import decode, encode
from audiosteg.algorithms.lsb_four import LSB_4
from audiosteg.errors import CapacityError, DamagedMessageError, StegoError

CONTAINER = bytes.fromhex("4153544701000000000348c3a9a411cc3b")


@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2])
def test_known_answer_bytes(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    embed: Callable[..., bytes],
    tmp_path: Path,
    sample_width: int,
    channels: int,
) -> None:
    cover = random.Random(1).randbytes(200 * sample_width)
    output = tmp_path / "output.wav"
    source = make_wav(frames=cover, sample_width=sample_width, channels=channels)
    encode(str(source), str(output), "Hé", LSB_4)
    assert read_frames(output) == embed(CONTAINER, 4, sample_width, cover)
    assert decode(str(output)) == "Hé"


def test_only_the_four_lowest_bits_of_a_byte_change() -> None:
    for byte, bits in product(range(256), product(range(2), repeat=4)):
        changed = byte // 16 * 16 + int("".join(map(str, bits)), 2)
        assert LSB_4.embed_bits(byte, bits) == changed
        assert LSB_4.extract_bits(changed) == bits


@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
@pytest.mark.parametrize("cover", [0x00, 0xFF, 0x80, 0x7F])
def test_extreme_samples_move_by_at_most_15(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    tmp_path: Path,
    sample_width: int,
    cover: int,
) -> None:
    frames = (bytes([cover]) * sample_width) * 300
    output = tmp_path / "output.wav"
    encode(str(make_wav(frames=frames, sample_width=sample_width)), str(output), "\0\x0f" * 60, LSB_4)
    assert decode(str(output), LSB_4) == "\0\x0f" * 60
    changed = read_frames(output)
    signed = sample_width > 1
    changes = [
        int.from_bytes(changed[start : start + sample_width], "little", signed=signed)
        - int.from_bytes(frames[start : start + sample_width], "little", signed=signed)
        for start in range(0, len(frames), sample_width)
    ]
    assert max(map(abs, changes)) == 15


@pytest.mark.parametrize(("samples", "capacity"), [(28, 0), (29, 0), (30, 1), (1000, 486)])
def test_the_exact_capacity(
    make_wav: Callable[..., Path], tmp_path: Path, samples: int, capacity: int
) -> None:
    source, output = make_wav(frames=bytes(samples)), tmp_path / "output.wav"
    with pytest.raises(CapacityError, match=f"can hold {capacity} bytes"):
        encode(str(source), str(output), "x" * (capacity + 1), LSB_4)
    encode(str(source), str(output), "x" * capacity, LSB_4)
    assert decode(str(output)) == "x" * capacity
    with pytest.raises(CapacityError):
        encode(str(make_wav(frames=bytes(27))), str(output), "", LSB_4, overwrite=True)


def test_every_changed_bit_is_noticed(make_wav: Callable[..., Path], embed: Callable[..., bytes]) -> None:
    for position in range(len(CONTAINER) * 8):
        changed = bytearray(CONTAINER)
        changed[position // 8] ^= 128 >> position % 8
        with pytest.raises(StegoError) as caught:
            decode(str(make_wav(frames=embed(bytes(changed), 4))), LSB_4)
        assert position < 48 or type(caught.value) is DamagedMessageError


@pytest.mark.needs_crypto
def test_an_encrypted_message(make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_wav()), output, "hidden 🎵", LSB_4, passphrase="key")
    assert decode(output, passphrase="key") == "hidden 🎵"
