"""Tests for audiosteg/core/stego_file.py."""

import errno
import os
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg.core import crypto
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.header import build_container
from audiosteg.core.stego_file import check_capacity, decode, encode
from audiosteg.errors import (
    CapacityError,
    DamagedMessageError,
    InvalidMessageError,
    MissingLibraryError,
    NoMessageError,
    NotEncryptedError,
    PassphraseRequiredError,
    StegoError,
    UnsafeOutputError,
    UnsupportedFormatError,
    WrongPassphraseError,
)


def embed_bit(byte: int, bits: tuple[int, ...]) -> int:
    return (byte & 254) | bits[0]


def extract_bit(byte: int) -> tuple[int, ...]:
    return (byte & 1,)


LOWEST_BIT = Algorithm("Lowest bit", 1, embed_bit, extract_bit)


def hide(source: Path | str, output: Path | str, message: str = "hidden", overwrite: bool = False) -> None:
    encode(str(source), str(output), message, LOWEST_BIT, overwrite=overwrite)


def reveal(path: Path | str) -> str:
    return decode(str(path), LOWEST_BIT)


def carrier(length: int, message: bytes = b"", checksum: bytes | None = None) -> bytes:
    content = b"ASTG\x01\x00" + length.to_bytes(4, "big") + message
    content += zlib.crc32(content).to_bytes(4, "big") if checksum is None else checksum
    return bytes(int(digit) for byte in content for digit in f"{byte:08b}")


@pytest.mark.parametrize(
    ("samples", "bits_per_byte", "encrypted", "capacity"),
    [
        (112, 1, False, 0),
        (119, 1, False, 0),
        (120, 1, False, 1),
        (56, 2, False, 0),
        (60, 2, False, 1),
        (1000, 2, False, 236),
        (432, 1, True, 0),
        (440, 1, True, 1),
        (1000, 2, True, 196),
    ],
)
def test_capacity_limits(samples: int, bits_per_byte: int, encrypted: bool, capacity: int) -> None:
    check_capacity(capacity, samples, bits_per_byte, encrypted)
    with pytest.raises(CapacityError, match=f"needs {capacity + 1} bytes .* hold {capacity} bytes"):
        check_capacity(capacity + 1, samples, bits_per_byte, encrypted)


@pytest.mark.parametrize(
    ("samples", "bits_per_byte", "encrypted"),
    [(0, 1, False), (111, 1, False), (55, 2, False), (431, 1, True), (215, 2, True)],
)
def test_audio_without_room_for_the_container_holds_nothing(
    samples: int, bits_per_byte: int, encrypted: bool
) -> None:
    with pytest.raises(CapacityError, match="hold 0 bytes"):
        check_capacity(0, samples, bits_per_byte, encrypted)


def test_a_message_can_be_hidden_in_a_file_that_already_holds_one(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    hide(make_wav(), tmp_path / "first.wav", "a much longer first message")
    hide(tmp_path / "first.wav", tmp_path / "second.wav", "second")
    assert reveal(tmp_path / "second.wav") == "second"


@pytest.mark.parametrize("bits_per_byte", [1, 2, 4, 8])
def test_every_number_of_bits_fills_the_file_exactly(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path, bits_per_byte: int
) -> None:
    def embed(byte: int, bits: tuple[int, ...]) -> int:
        return (byte >> bits_per_byte << bits_per_byte) | int("".join(map(str, bits)), 2)

    def extract(byte: int) -> tuple[int, ...]:
        return tuple((byte >> shift) & 1 for shift in range(bits_per_byte - 1, -1, -1))

    algorithm = Algorithm("Test", bits_per_byte, embed, extract)
    used = (14 + 3) * 8 // bits_per_byte
    source = make_wav(frames=b"\xaa" * used)
    output = tmp_path / "output.wav"
    with pytest.raises(CapacityError, match="hold 3 bytes"):
        encode(str(source), str(output), "Hi!!", algorithm)
    encode(str(source), str(output), "Hi!", algorithm)
    assert decode(str(output), algorithm) == "Hi!"
    hidden = "".join(str(bit) for byte in read_frames(output) for bit in extract(byte))
    content = b"ASTG\x01\x00\0\0\0\x03Hi!"
    assert int(hidden, 2).to_bytes(17, "big") == content + zlib.crc32(content).to_bytes(4, "big")


@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize("name", ["input.wav", "input.wav/", "input.wav/.", "./input.wav", "", "."])
def test_the_input_is_never_replaced(
    make_wav: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, overwrite: bool
) -> None:
    source = make_wav()
    original = source.read_bytes()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(UnsafeOutputError):
        hide("input.wav", name, overwrite=overwrite)
    assert source.read_bytes() == original
    assert os.listdir(tmp_path) == ["input.wav"]


def test_a_linked_folder_cannot_hide_that_the_output_is_the_input(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_wav()
    original = source.read_bytes()
    try:
        (tmp_path / "linked").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("this system does not allow symbolic links")
    with pytest.raises(UnsafeOutputError):
        hide(source, tmp_path / "linked" / "input.wav", overwrite=True)
    assert source.read_bytes() == original


def test_an_existing_output_is_replaced_only_when_allowed(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    output.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        hide(source, output)
    assert output.read_bytes() == b"keep me"
    hide(source, output, overwrite=True)
    assert reveal(output) == "hidden"


def test_an_existing_output_is_refused_before_anything_is_written(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_full(descriptor: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    source = make_wav()
    monkeypatch.setattr(os, "fsync", disk_full)
    with pytest.raises(OSError) as caught:
        hide(source, tmp_path / "new.wav")
    assert caught.value.errno == errno.ENOSPC
    (tmp_path / "existing.wav").write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        hide(source, tmp_path / "existing.wav")


def test_a_file_that_appears_while_the_message_is_hidden_is_kept(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"

    def embed_while_a_file_appears(byte: int, bits: tuple[int, ...]) -> int:
        output.write_bytes(b"theirs")
        return embed_bit(byte, bits)

    algorithm = Algorithm("Test", 1, embed_while_a_file_appears, extract_bit)
    with pytest.raises(FileExistsError):
        encode(str(make_wav()), str(output), "hidden", algorithm)
    assert output.read_bytes() == b"theirs"


@pytest.mark.parametrize(
    ("content", "message", "error"),
    [
        (b"not audio", "hidden", UnsupportedFormatError),
        (None, "x" * 5000, CapacityError),
        (None, "bad \udcff", InvalidMessageError),
    ],
    ids=["not_audio", "too_large", "not_text"],
)
def test_a_refused_message_changes_no_file_and_creates_no_folder(
    make_wav: Callable[..., Path],
    tmp_path: Path,
    content: bytes | None,
    message: str,
    error: type[StegoError],
) -> None:
    source = make_wav()
    if content is not None:
        source.write_bytes(content)
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"keep me")
    for output in (existing, tmp_path / "new" / "output.wav"):
        with pytest.raises(error):
            hide(source, output, message, overwrite=True)
    assert existing.read_bytes() == b"keep me"
    assert sorted(os.listdir(tmp_path)) == ["existing.wav", "input.wav"]


def test_a_missing_input_creates_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        hide(tmp_path / "missing.wav", tmp_path / "new" / "output.wav")
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize(
    "frames",
    [
        carrier(6, b"hello"),
        carrier(2**32 - 1, b"hello"),
        carrier(5, b"hello", b"oops"),
        carrier(4, b"hello"),
        carrier(1, b"\xff"),
    ],
    ids=["one_byte_short", "huge", "wrong_checksum", "wrong_length", "not_text"],
)
def test_a_damaged_message_is_refused(make_wav: Callable[..., Path], frames: bytes) -> None:
    with pytest.raises(DamagedMessageError, match="damaged|not valid text"):
        reveal(make_wav(frames=frames))


@pytest.mark.parametrize(
    "frames", [carrier(0)[:79], b"", bytes(200)], ids=["half_header", "no_audio", "other"]
)
def test_audio_without_a_message_is_refused(make_wav: Callable[..., Path], frames: bytes) -> None:
    with pytest.raises(NoMessageError, match="No hidden message was found"):
        reveal(make_wav(frames=frames))


def test_a_message_that_fills_the_file_is_read(make_wav: Callable[..., Path]) -> None:
    assert reveal(make_wav(frames=carrier(5, b"hello"))) == "hello"


def test_a_message_cut_off_by_a_truncated_file_is_refused(make_wav: Callable[..., Path]) -> None:
    source = make_wav(frames=carrier(5, b"hello") + bytes(500))
    content = source.read_bytes()
    source.write_bytes(content[: 44 + 151])
    with pytest.raises(DamagedMessageError, match="ends before"):
        reveal(source)


def test_a_message_is_still_readable_when_only_audio_after_it_is_cut(make_wav: Callable[..., Path]) -> None:
    source = make_wav(frames=carrier(5, b"hello") + bytes(500))
    source.write_bytes(source.read_bytes()[: 44 + 152])
    assert reveal(source) == "hello"


def flip(data: bytes, position: int) -> bytes:
    changed = bytearray(data)
    changed[position // 8] ^= 128 >> position % 8
    return bytes(changed)


def expected_error(position: int, encrypted: bool) -> set[type[StegoError]]:
    """Return the errors that a flipped bit at this position of a container may cause."""
    if position < 32:
        return {NoMessageError}
    if position < 47:
        return {UnsupportedFormatError}
    if position == 47:
        return {NotEncryptedError} if encrypted else {PassphraseRequiredError}
    if position < 80:
        return {DamagedMessageError, WrongPassphraseError} if encrypted else {DamagedMessageError}
    return {WrongPassphraseError} if encrypted else {DamagedMessageError}


@pytest.mark.parametrize(
    ("passphrase", "size"), [(None, 17), pytest.param("key", 57, marks=pytest.mark.needs_crypto)]
)
def test_every_flipped_bit_is_noticed(
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    fast_scrypt: None,
    passphrase: str | None,
    size: int,
) -> None:
    container = build_container(b"hi!", None if passphrase is None else passphrase.encode())
    assert len(container) == size
    for position in range(size * 8):
        path = make_wav(frames=embed(flip(container, position), 1) + bytes(800))
        with pytest.raises(StegoError) as caught:
            decode(str(path), LOWEST_BIT, passphrase=passphrase)
        assert type(caught.value) in expected_error(position, passphrase is not None)


@pytest.mark.needs_crypto
def test_an_encrypted_message_is_not_stored_as_it_is(
    make_wav: Callable[..., Path], read_frames: Callable[[Path], bytes], fast_scrypt: None, tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    message = "a message that nobody may read"
    encode(str(make_wav()), str(output), message, LOWEST_BIT, passphrase="key")
    bits = [byte & 1 for byte in read_frames(output)[:1000]]
    hidden = bytes(int("".join(map(str, bits[start : start + 8])), 2) for start in range(0, 1000, 8))
    assert hidden.startswith(b"ASTG\x01\x01\0\0\0\x1e")
    assert b"message" not in hidden


@pytest.mark.needs_crypto
def test_only_the_right_passphrase_reads_an_encrypted_message(
    make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path
) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_wav()), output, "hidden", LOWEST_BIT, passphrase="Café")
    assert decode(output, LOWEST_BIT, passphrase="Cafe\u0301") == "hidden"
    with pytest.raises(WrongPassphraseError):
        decode(output, LOWEST_BIT, passphrase="Cafe")
    with pytest.raises(PassphraseRequiredError):
        decode(output, LOWEST_BIT)
    with pytest.raises(ValueError, match="empty"):
        decode(output, LOWEST_BIT, passphrase="")


@pytest.mark.needs_crypto
def test_an_encrypted_message_cannot_be_replaced_by_a_plain_one(
    make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path
) -> None:
    private = tmp_path / "private.wav"
    replaced = tmp_path / "replaced.wav"
    encode(str(make_wav()), str(private), "hidden", LOWEST_BIT, passphrase="key")
    hide(private, replaced, "forged")
    with pytest.raises(NotEncryptedError):
        decode(str(replaced), LOWEST_BIT, passphrase="key")


@pytest.mark.parametrize("passphrase", ["", "my secret\0", "my secret \udcff"])
def test_an_unusable_passphrase_changes_no_file(
    make_wav: Callable[..., Path], tmp_path: Path, passphrase: str
) -> None:
    source = make_wav()
    with pytest.raises(ValueError, match="The passphrase") as caught:
        encode(str(source), str(tmp_path / "new" / "o.wav"), "m", LOWEST_BIT, passphrase=passphrase)
    assert caught.value.__context__ is None
    assert "secret" not in str(caught.value)
    assert os.listdir(tmp_path) == ["input.wav"]


@pytest.mark.parametrize("message", ["m", "x" * 5000], ids=["fits", "too_large"])
def test_encryption_without_the_library_changes_no_file(
    make_wav: Callable[..., Path], no_library: None, tmp_path: Path, message: str
) -> None:
    source = make_wav()
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"keep me")
    for output in (existing, tmp_path / "new" / "output.wav"):
        with pytest.raises(MissingLibraryError):
            encode(str(source), str(output), message, LOWEST_BIT, passphrase="key", overwrite=True)
    assert existing.read_bytes() == b"keep me"
    assert sorted(os.listdir(tmp_path)) == ["existing.wav", "input.wav"]


@pytest.mark.needs_crypto
def test_a_key_is_not_made_for_a_message_that_does_not_fit(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(passphrase: bytes, salt: bytes) -> bytes:
        raise AssertionError("a key was made")

    monkeypatch.setattr(crypto, "derive_key", refuse)
    with pytest.raises(CapacityError):
        encode(str(make_wav()), str(tmp_path / "o.wav"), "x" * 5000, LOWEST_BIT, passphrase="key")
    path = make_wav(frames=bytes(800))
    with pytest.raises(NoMessageError):
        decode(str(path), LOWEST_BIT, passphrase="key")


def test_an_error_about_hidden_bytes_does_not_carry_them(make_wav: Callable[..., Path]) -> None:
    with pytest.raises(DamagedMessageError) as caught:
        reveal(make_wav(frames=carrier(7, b"secret\xff")))
    assert caught.value.__context__ is None


@pytest.mark.parametrize("algorithm", ["LSB", None, 1, Algorithm])
def test_something_that_is_not_an_algorithm_is_refused(
    make_wav: Callable[..., Path], tmp_path: Path, algorithm: Any
) -> None:
    source = make_wav()
    with pytest.raises(TypeError, match="must be an Algorithm"):
        encode(str(source), str(tmp_path / "output.wav"), "hidden", algorithm)
    with pytest.raises(TypeError, match="must be an Algorithm"):
        decode(str(source), algorithm)
    assert os.listdir(tmp_path) == ["input.wav"]


def test_odd_channels_and_wide_samples_use_every_sample_in_order(
    make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    content = carrier(3, b"odd")
    hidden = bytes(int("".join(map(str, content[start : start + 8])), 2) for start in range(0, 136, 8))
    frames = embed(hidden, 1, 3)
    frames += bytes(-len(frames) % 15)
    assert reveal(make_wav(frames=frames, channels=5, sample_width=3)) == "odd"
