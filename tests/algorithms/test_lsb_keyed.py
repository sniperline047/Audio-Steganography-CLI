"""Tests for audiosteg/algorithms/lsb_keyed.py."""

import hashlib
import hmac
import random
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from audiosteg import CapacityError, NoMessageError, PassphraseRequiredError, decode, encode
from audiosteg.algorithms.detection import detect
from audiosteg.algorithms.lsb_keyed import LSB_KEYED
from audiosteg.analysis.inspection import inspect
from audiosteg.core import crypto

KNOWN_FILE = "228b414ad7a527e1107b4cdcc36ebee5ddb79bb21cd9c615bd3eda6c8eae6a59"
SHAPES = [(1, 1), (2, 1), (3, 1), (4, 1), (1, 2), (2, 2), (3, 2), (4, 2), (2, 5)]


def subkey(passphrase: str, salt: bytes, purpose: bytes) -> bytes:
    key = hashlib.scrypt(passphrase.encode(), salt=salt, n=crypto.SCRYPT_N, r=8, p=1, maxmem=2**29, dklen=32)
    return hmac.new(key, b"audiosteg keyed 1: " + purpose + b"\x01", hashlib.sha256).digest()


def scattered(key: bytes, limit: int) -> Iterator[int]:
    half = 1
    while 4**half < limit:
        half += 1
    data = [
        hashlib.shake_256(key + limit.to_bytes(8, "big") + bytes([step])).digest(2 * 2**half)
        for step in range(10)
    ]
    for start in range(limit):
        number = start
        while True:
            left, right = divmod(number, 2**half)
            for table in data:
                left, right = right, left ^ int.from_bytes(table[2 * right : 2 * right + 2], "big") % 2**half
            number = left * 2**half + right
            if number < limit:
                break
        yield number


def find_samples(passphrase: str, salt: bytes, samples: int) -> Iterator[int]:
    """Yield the samples of the header, the nonce, the ciphertext, and the tag, as the documentation says."""
    for number in scattered(subkey(passphrase, salt, b"order"), samples - 128):
        yield 128 + number


def read_bytes(lowest: list[int], places: Iterator[int], size: int) -> bytes:
    digits = "".join(str(lowest[next(places)]) for _ in range(8 * size))
    return int(digits or "0", 2).to_bytes(size, "big")


def read_independently(frames: bytes, width: int, passphrase: str) -> str:
    """Read a keyed message as the documentation says, without the package."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    lowest = [byte & 1 for byte in frames[::width]]
    salt = read_bytes(lowest, iter(range(128)), 16)
    places = find_samples(passphrase, salt, len(lowest))
    header = read_bytes(lowest, places, 10)
    assert header[:6] == b"ASTG\x01\x01"
    nonce = read_bytes(lowest, places, 12)
    ciphertext = read_bytes(lowest, places, int.from_bytes(header[6:], "big") + 16)
    return AESGCM(subkey(passphrase, salt, b"encryption")).decrypt(nonce, ciphertext, header).decode()


def hide_independently(
    frames: bytes, width: int, passphrase: str, message: bytes, random_bytes: Any
) -> bytes:
    """Hide a keyed message as the documentation says, without the package."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, nonce = random_bytes.salt, random_bytes.nonce
    header = b"ASTG\x01\x01" + len(message).to_bytes(4, "big")
    ciphertext = AESGCM(subkey(passphrase, salt, b"encryption")).encrypt(nonce, message, header)
    changed = bytearray(frames)
    places = [*range(128)], find_samples(passphrase, salt, len(frames) // width)
    for data, order in ((salt, iter(places[0])), (header + nonce + ciphertext, places[1])):
        for digit in "".join(f"{byte:08b}" for byte in data):
            place = next(order) * width
            changed[place] = changed[place] & 254 | int(digit)
    return bytes(changed)


@pytest.mark.needs_crypto
@pytest.mark.parametrize(("width", "channels"), SHAPES)
@pytest.mark.parametrize("cover", ["noise", "silence", "extremes"])
def test_another_program_reads_what_is_hidden(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    fast_scrypt: None,
    tmp_path: Path,
    width: int,
    channels: int,
    cover: str,
) -> None:
    extremes = [b"\xff" * width, bytes(width), b"\xff" * (width - 1) + b"\x7f", bytes(width - 1) + b"\x80"]
    frames = {
        "noise": random.Random(8).randbytes(1200 * width * channels),
        "silence": bytes(1200 * width * channels),
        "extremes": b"".join(extremes) * 300 * channels,
    }[cover]
    source = make_wav(frames=frames, sample_width=width, channels=channels)
    output = tmp_path / "output.wav"
    encode(str(source), str(output), "Hé 🎵", LSB_KEYED, passphrase="sésame")
    changed = read_frames(output)
    assert read_independently(changed, width, "sésame") == "Hé 🎵"
    assert decode(str(output), passphrase="sésame") == "Hé 🎵"
    different = [index for index in range(len(frames)) if frames[index] != changed[index]]
    assert all(index % width == 0 and frames[index] ^ changed[index] == 1 for index in different)
    assert max(different) > len(frames) * 0.9


@pytest.mark.needs_crypto
@pytest.mark.parametrize(("width", "channels"), [(1, 1), (2, 2), (3, 1)])
def test_known_answer_bytes_of_another_program(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    known_answer: Any,
    known_randomness: None,
    tmp_path: Path,
    width: int,
    channels: int,
) -> None:
    frames = random.Random(9).randbytes(1000 * width * channels)
    message = known_answer.message
    expected = hide_independently(frames, width, "Café ☕", message.encode(), known_answer)
    output = tmp_path / "output.wav"
    source = make_wav(frames=frames, sample_width=width, channels=channels)
    encode(str(source), str(output), message, LSB_KEYED, passphrase="Café ☕")
    assert read_frames(output) == expected
    read = make_wav("theirs.wav", expected, sample_width=width, channels=channels)
    assert decode(str(read), LSB_KEYED, passphrase="Café ☕") == message


@pytest.mark.needs_crypto
def test_a_file_that_was_made_once_can_always_be_read(
    make_wav: Callable[..., Path],
    read_frames: Callable[[Path], bytes],
    known_randomness: None,
    tmp_path: Path,
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav(frames=bytes(1000))), str(output), "Hé", LSB_KEYED, passphrase="Café ☕")
    assert hashlib.sha256(read_frames(output)).hexdigest() == KNOWN_FILE


@pytest.mark.needs_crypto
def test_nothing_can_be_found_without_the_passphrase(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], fast_scrypt: None, tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden", LSB_KEYED, passphrase="sesame")
    assert detect(str(output)) is None
    assert inspect(str(output)).messages == ()
    digits = "".join(str(byte & 1) for byte in read_frames(output))
    assert "".join(f"{byte:08b}" for byte in b"ASTG") not in digits
    with pytest.raises(NoMessageError, match="No hidden message was found.$"):
        decode(str(output))
    with pytest.raises(PassphraseRequiredError):
        decode(str(output), LSB_KEYED)


@pytest.mark.needs_crypto
def test_the_salt_and_the_places_are_new_for_every_message(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], fast_scrypt: None, tmp_path: Path
) -> None:
    source, output = make_wav(frames=bytes(4000)), tmp_path / "output.wav"
    seen = set()
    for _ in range(10):
        encode(str(source), str(output), "same", LSB_KEYED, passphrase="same", overwrite=True)
        frames = read_frames(output)
        seen |= {frames[:128], frames[128:]}
    assert len(seen) == 20


@pytest.mark.needs_crypto
@pytest.mark.parametrize("length", [0, 1, 45, 46])
def test_the_exact_capacity(
    make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path, length: int
) -> None:
    samples = (length + 54) * 8
    output = tmp_path / "output.wav"
    for spare in (0, 1, 7):
        source = make_wav(frames=bytes(samples + spare))
        with pytest.raises(CapacityError, match=f"can hold {length} bytes"):
            encode(str(source), str(output), "x" * (length + 1), LSB_KEYED, passphrase="key")
        encode(str(source), str(output), "x" * length, LSB_KEYED, passphrase="key", overwrite=True)
        assert decode(str(output), passphrase="key") == "x" * length
        output.unlink()
