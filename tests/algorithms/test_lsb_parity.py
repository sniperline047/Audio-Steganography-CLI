"""Tests for audiosteg/algorithms/lsb_parity.py."""

import random
from collections.abc import Callable
from dataclasses import replace
from itertools import product
from pathlib import Path

import pytest

from audiosteg import CapacityError, DamagedMessageError, NoMessageError, StegoError, decode, encode
from audiosteg.algorithms.detection import detect
from audiosteg.algorithms.lsb import LSB
from audiosteg.algorithms.lsb_parity import LSB_PARITY
from audiosteg.core.header import Header

CONTAINER = bytes.fromhex("4153544701000000000348c3a9a411cc3b")
DIGITS = "".join(f"{byte:08b}" for byte in CONTAINER)


def groups_of(frames: bytes, width: int) -> list[bytes]:
    return [
        frames[start : start + 8 * width]
        for start in range(0, len(frames) // width // 8 * 8 * width, 8 * width)
    ]


def parity(group: bytes, width: int) -> int:
    return sum(group[::width][index] % 2 for index in range(8)) % 2


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2, 3])
def test_every_group_carries_one_bit(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    tmp_path: Path,
    width: int,
    channels: int,
) -> None:
    cover = random.Random(6).randbytes(1200 * width)
    cover = bytes(8 * width) + (b"\xff" * width + bytes(width - 1) + b"\x80") * 4 + cover[16 * width :]
    cover = cover[: 1200 * width]
    source = make_wav(frames=cover, sample_width=width, channels=channels)
    output = tmp_path / "output.wav"
    encode(str(source), str(output), "Hé", LSB_PARITY)
    changed = read_frames(output)
    pairs = list(zip(groups_of(cover, width), groups_of(changed, width), strict=True))
    for number, (before, after) in enumerate(pairs):
        different = [index for index in range(8 * width) if before[index] != after[index]]
        wrong = number < len(DIGITS) and parity(before, width) != int(DIGITS[number])
        assert len(different) == wrong
        assert all(index % width == 0 and before[index] ^ after[index] == 1 for index in different)
    assert "".join(str(parity(after, width)) for _, after in pairs)[: len(DIGITS)] == DIGITS
    assert detect(str(output)) == (LSB_PARITY, Header(False, 3))
    assert decode(str(output)) == "Hé"


def test_every_sample_of_a_group_can_be_chosen_and_can_carry_the_change() -> None:
    for chosen, low in product(range(8), [0, 1, 254, 255]):
        limits: list[int] = []

        def choose(limit: int, chosen: int = chosen, limits: list[int] = limits) -> int:
            limits.append(limit)
            return chosen

        group = bytes([low, 9]) * 8
        algorithm = replace(LSB_PARITY, choose=choose)
        assert algorithm.embed_group(group, 2, (0,)) == group
        changed = algorithm.embed_group(group, 2, (1,))
        assert [index for index in range(16) if group[index] != changed[index]] == [2 * chosen]
        assert changed[2 * chosen] == low ^ 1
        assert limits == [8]


def test_the_choice_is_really_random(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav(frames=bytes(8000))), str(output), "x" * 100, LSB_PARITY)
    assert {index % 8 for index, byte in enumerate(read_frames(output)) if byte} == set(range(8))


@pytest.mark.parametrize(("samples", "capacity"), [(896, 0), (959, 0), (960, 1), (1023, 1), (1024, 2)])
def test_the_exact_capacity(
    make_wav: Callable[..., Path], tmp_path: Path, samples: int, capacity: int
) -> None:
    source, output = make_wav(frames=bytes(samples)), tmp_path / "output.wav"
    with pytest.raises(CapacityError, match=f"can hold {capacity} bytes"):
        encode(str(source), str(output), "x" * (capacity + 1), LSB_PARITY)
    encode(str(source), str(output), "x" * capacity, LSB_PARITY)
    assert decode(str(output), LSB_PARITY) == "x" * capacity


def carrier(container: bytes) -> bytes:
    return b"".join(bytes([int(digit)]) + bytes(7) for byte in container for digit in f"{byte:08b}")


def test_every_changed_bit_is_noticed(make_wav: Callable[..., Path]) -> None:
    assert decode(str(make_wav(frames=carrier(CONTAINER)))) == "Hé"
    for position in range(len(CONTAINER) * 8):
        changed = bytearray(carrier(CONTAINER))
        changed[position * 8 + position % 8] ^= 1
        with pytest.raises(StegoError) as caught:
            decode(str(make_wav(frames=bytes(changed))), LSB_PARITY)
        assert position < 48 or type(caught.value) is DamagedMessageError


def test_a_length_that_cannot_fit_is_refused_before_it_is_used(make_wav: Callable[..., Path]) -> None:
    for length in (4, 2**32 - 1):
        header = b"ASTG\x01\0" + length.to_bytes(4, "big")
        path = make_wav(frames=carrier(header + CONTAINER[10:]) + bytes(7))
        with pytest.raises(DamagedMessageError, match="longer than the audio file"):
            decode(str(path), LSB_PARITY)


def test_a_group_that_was_cut_off_is_not_read(make_wav: Callable[..., Path]) -> None:
    path = make_wav(frames=carrier(CONTAINER) + bytes(100))
    content = path.read_bytes()
    end = 44 + len(CONTAINER) * 64
    path.write_bytes(content[:end])
    assert decode(str(path), LSB_PARITY) == "Hé"
    path.write_bytes(content[: end - 1])
    with pytest.raises(DamagedMessageError, match="ends before"):
        decode(str(path), LSB_PARITY)
    path.write_bytes(make_wav(frames=carrier(CONTAINER)[:639]).read_bytes())
    with pytest.raises(NoMessageError):
        decode(str(path), LSB_PARITY)


def test_it_is_not_read_as_lsb(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_wav()), output, "hidden", LSB_PARITY)
    with pytest.raises(NoMessageError):
        decode(output, LSB)


@pytest.mark.needs_crypto
def test_an_encrypted_message(make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_wav(frames=bytes(8000))), output, "hidden 🎵", LSB_PARITY, passphrase="key")
    assert decode(output, passphrase="key") == "hidden 🎵"
