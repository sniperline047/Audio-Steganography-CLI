"""Tests for audiosteg/core/keyed.py."""

import os
import wave
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from audiosteg.core import crypto, keyed, wav_io
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.stego_file import decode, encode
from audiosteg.errors import (
    DamagedMessageError,
    MissingLibraryError,
    NoMessageError,
    StegoError,
    UnsupportedFormatError,
)

ONE_BIT = Algorithm("One", 1, lambda b, bits: b & 254 | bits[0], lambda b: (b & 1,), keyed=True)
TWO_BITS = Algorithm(
    "Two", 2, lambda b, bits: b & 252 | bits[0] << 1 | bits[1], lambda b: (b >> 1 & 1, b & 1), keyed=True
)
NOT_FOUND = "No hidden message was found with this passphrase"


@pytest.fixture
def hidden(make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path) -> Path:
    output = tmp_path / "hidden.wav"
    encode(str(make_wav(frames=bytes(1000))), str(output), "secret", ONE_BIT, passphrase="key")
    return output


def places(path: Path, key: str = "key") -> list[int]:
    """Return the samples of every bit of the container."""
    with wave.open(str(path), "rb") as audio:
        frames = audio.readframes(audio.getnframes())
    salt = keyed.bits_to_bytes(byte & 1 for byte in frames[:128])
    order = keyed.split_key(crypto.derive_key(key.encode(), salt)).order
    return list(keyed.container_order(keyed.scattered_samples(order, len(frames), ONE_BIT), ONE_BIT))


def flip(path: Path, *samples: int) -> None:
    content = bytearray(path.read_bytes())
    for sample in samples:
        content[44 + sample] ^= 1
    path.write_bytes(content)


def test_the_two_keys_are_independent() -> None:
    keys = keyed.split_key(bytes(32))
    assert len({keys.order, keys.encryption, bytes(32)}) == 3
    assert {len(key) for key in keys} == {32}


@pytest.mark.parametrize(("algorithm", "header", "salt"), [(ONE_BIT, 80, 128), (TWO_BITS, 40, 64)])
def test_the_order_uses_every_sample_once(algorithm: Algorithm, header: int, salt: int) -> None:
    scattered = keyed.scattered_samples(bytes(32), 1000, algorithm)
    order = list(keyed.container_order(scattered, algorithm))
    assert sorted(order) == list(range(1000))
    assert order[header : header + salt] == list(range(salt))


@pytest.mark.needs_crypto
@pytest.mark.parametrize("algorithm", [ONE_BIT, TWO_BITS])
@pytest.mark.parametrize("batch", [1, 7, 1 << 18])
def test_round_trips(
    make_wav: Callable[..., Path],
    fast_scrypt: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    algorithm: Algorithm,
    batch: int,
) -> None:
    monkeypatch.setattr(wav_io, "SCATTERED_BATCH", batch)
    output = str(tmp_path / "output.wav")
    for message in ("", "a", "Hé 🎵", "x" * 300):
        encode(str(make_wav()), output, message, algorithm, passphrase="key", overwrite=True)
        assert decode(output, algorithm, passphrase="key") == message


@pytest.mark.needs_crypto
def test_every_changed_bit_is_noticed(hidden: Path) -> None:
    order = places(hidden)
    for position in range((54 + 6) * 8):
        flip(hidden, order[position])
        with pytest.raises(StegoError) as caught:
            decode(str(hidden), ONE_BIT, passphrase="key")
        if position < 32 or 80 <= position < 208:
            expected: set[type[StegoError]] = {NoMessageError}
        elif position < 47:
            expected = {UnsupportedFormatError}
        else:
            expected = {DamagedMessageError}
        assert type(caught.value) in expected, position
        assert "secret" not in str(caught.value)
        flip(hidden, order[position])
    assert decode(str(hidden), ONE_BIT, passphrase="key") == "secret"


@pytest.mark.needs_crypto
def test_changes_elsewhere_do_no_harm(hidden: Path) -> None:
    flip(hidden, *places(hidden)[(54 + 6) * 8 :])
    assert decode(str(hidden), ONE_BIT, passphrase="key") == "secret"


@pytest.mark.needs_crypto
@pytest.mark.parametrize("wrong", ["Key", "key ", "ke"])
def test_a_wrong_passphrase_and_no_message_give_the_same_error(
    hidden: Path, make_wav: Callable[..., Path], wrong: str
) -> None:
    reasons = set()
    for path in (hidden, make_wav(), make_wav(frames=bytes(431)), make_wav(frames=b"")):
        with pytest.raises(NoMessageError, match=NOT_FOUND) as caught:
            decode(str(path), ONE_BIT, passphrase=wrong)
        reasons.add(str(caught.value))
    assert len(reasons) == 1


@pytest.mark.needs_crypto
def test_a_cut_or_extended_file_holds_nothing(hidden: Path, make_wav: Callable[..., Path]) -> None:
    frames = hidden.read_bytes()[44:]
    for changed in (frames[:-1], frames + b"\0", frames[1:]):
        with pytest.raises(NoMessageError):
            decode(str(make_wav(frames=changed)), ONE_BIT, passphrase="key")


@pytest.mark.needs_crypto
def test_a_file_that_ends_before_its_header_says(hidden: Path) -> None:
    content = hidden.read_bytes()
    used = places(hidden)[: (54 + 6) * 8]
    for missing in range(1, 45):
        hidden.write_bytes(content[:-missing])
        if max(used) < 1000 - missing:
            assert decode(str(hidden), ONE_BIT, passphrase="key") == "secret"
        else:
            with pytest.raises((NoMessageError, DamagedMessageError)):
                decode(str(hidden), ONE_BIT, passphrase="key")
    for missing in (45, 900, 999):
        hidden.write_bytes(content[:-missing])
        with pytest.raises(NoMessageError):
            decode(str(hidden), ONE_BIT, passphrase="key")


@pytest.mark.needs_crypto
def test_a_message_that_is_cut_off(hidden: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    last = places(hidden)[(54 + 6) * 8 - 1]
    read = wav_io.read_sorted_low_bytes

    def read_others(audio: wave.Wave_read, samples: list[int]) -> Iterator[tuple[int, int]]:
        yield from (found for found in read(audio, samples) if found[0] != last)

    monkeypatch.setattr(wav_io, "read_sorted_low_bytes", read_others)
    with pytest.raises(DamagedMessageError, match="ends before"):
        decode(str(hidden), ONE_BIT, passphrase="key")


@pytest.fixture
def slow_work(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Return the names of the expensive steps that were taken."""
    steps: list[str] = []
    derive_key, read_low_bytes = crypto.derive_key, keyed.read_low_bytes

    def derive(passphrase: bytes, salt: bytes) -> bytes:
        steps.append("key")
        return derive_key(passphrase, salt)

    def read(audio: wave.Wave_read, samples: Iterator[int]) -> Iterator[int]:
        chosen = list(samples)
        steps.append(f"read {len(chosen)}")
        return read_low_bytes(audio, chosen)

    monkeypatch.setattr(crypto, "derive_key", derive)
    monkeypatch.setattr(keyed, "read_low_bytes", read)
    return steps


@pytest.mark.needs_crypto
def test_one_key_is_made_and_little_is_read_before_the_passphrase_proves_right(
    hidden: Path, make_wav: Callable[..., Path], slow_work: list[str]
) -> None:
    with pytest.raises(NoMessageError):
        decode(str(hidden), ONE_BIT, passphrase="wrong")
    assert slow_work == ["read 128", "key", "read 80"]
    slow_work.clear()
    assert decode(str(hidden), ONE_BIT, passphrase="key") == "secret"
    assert slow_work == ["read 128", "key", "read 80", "read 272"]
    slow_work.clear()
    with pytest.raises(NoMessageError):
        decode(str(make_wav(frames=bytes(431))), ONE_BIT, passphrase="key")
    assert slow_work == []


@pytest.mark.needs_crypto
@pytest.mark.parametrize("length", [72, 2**32 - 1])
def test_a_length_that_cannot_fit_is_refused_before_it_is_used(
    make_wav: Callable[..., Path], fast_scrypt: None, slow_work: list[str], length: int
) -> None:
    path = make_wav(frames=bytes(1000))
    header = b"ASTG\x01\x01" + length.to_bytes(4, "big")
    digits = "".join(f"{byte:08b}" for byte in header)
    flip(path, *(place for place, digit in zip(places(path), digits, strict=False) if digit == "1"))
    slow_work.clear()
    with pytest.raises(DamagedMessageError, match="damaged or was changed"):
        decode(str(path), ONE_BIT, passphrase="key")
    assert slow_work == ["read 128", "key", "read 80"]


def test_a_message_without_the_library(
    make_wav: Callable[..., Path], no_library: None, slow_work: list[str], tmp_path: Path
) -> None:
    with pytest.raises(MissingLibraryError):
        encode(str(make_wav()), str(tmp_path / "o.wav"), "m", ONE_BIT, passphrase="key")
    assert os.listdir(tmp_path) == ["input.wav"]
    with pytest.raises(MissingLibraryError):
        decode(str(make_wav()), ONE_BIT, passphrase="key")
    assert slow_work == []


@pytest.mark.needs_crypto
@pytest.mark.parametrize("passphrase", ["key", "wrong"])
def test_the_error_without_the_library_does_not_depend_on_the_passphrase(
    hidden: Path, no_library: None, passphrase: str
) -> None:
    with pytest.raises(MissingLibraryError, match="Encryption needs an optional library"):
        decode(str(hidden), ONE_BIT, passphrase=passphrase)


@pytest.mark.parametrize("passphrase", ["", "a\0b", "\udcff"])
def test_an_unusable_passphrase(make_wav: Callable[..., Path], passphrase: str) -> None:
    with pytest.raises(ValueError, match="The passphrase"):
        decode(str(make_wav()), ONE_BIT, passphrase=passphrase)
