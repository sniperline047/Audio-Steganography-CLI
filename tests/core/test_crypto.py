"""Tests for audiosteg/core/crypto.py."""

import hashlib
import subprocess
import sys
import traceback
import unicodedata
from typing import Any

import pytest

from audiosteg.core import crypto
from audiosteg.errors import MissingLibraryError, WrongPassphraseError

HEADER = b"header"
KEY = b"key"


def test_known_answer_key(known_answer: Any) -> None:
    passphrase = crypto.passphrase_to_bytes(known_answer.passphrase)
    assert crypto.derive_key(passphrase, known_answer.salt) == known_answer.key


@pytest.mark.needs_crypto
def test_known_answer_encryption(known_answer: Any, known_randomness: None) -> None:
    passphrase = known_answer.passphrase.encode()
    body = crypto.encrypt(known_answer.message.encode(), known_answer.header, passphrase)
    assert body == known_answer.body


@pytest.mark.needs_crypto
def test_known_answer_decryption(known_answer: Any) -> None:
    passphrase = known_answer.passphrase.encode()
    message = crypto.decrypt(known_answer.body, known_answer.header, passphrase)
    assert message.decode() == known_answer.message


@pytest.mark.needs_crypto
def test_the_salt_and_nonce_are_new_for_every_message(fast_scrypt: None) -> None:
    bodies = [crypto.encrypt(b"same", HEADER, KEY) for _ in range(20)]
    assert len({body[:16] for body in bodies}) == 20
    assert len({body[16:28] for body in bodies}) == 20
    assert all(len(body) == len(b"same") + crypto.OVERHEAD for body in bodies)


@pytest.mark.needs_crypto
def test_every_changed_bit_is_refused(fast_scrypt: None) -> None:
    body = crypto.encrypt(b"message", HEADER, KEY)
    assert crypto.decrypt(body, HEADER, KEY) == b"message"
    for position in range(len(body) * 8):
        changed = bytearray(body)
        changed[position // 8] ^= 1 << position % 8
        with pytest.raises(WrongPassphraseError, match="Wrong passphrase, or the message was changed"):
            crypto.decrypt(bytes(changed), HEADER, KEY)


@pytest.mark.needs_crypto
@pytest.mark.parametrize("header", [b"", b"headeR", b"header\0"])
def test_a_changed_header_is_refused(fast_scrypt: None, header: bytes) -> None:
    body = crypto.encrypt(b"message", HEADER, KEY)
    with pytest.raises(WrongPassphraseError):
        crypto.decrypt(body, header, KEY)


@pytest.mark.needs_crypto
def test_a_body_that_was_cut_or_extended_is_refused(fast_scrypt: None) -> None:
    body = crypto.encrypt(b"message", HEADER, KEY)
    for changed in (body[:-1], body[:-16], body[:28], body + b"\0"):
        with pytest.raises(WrongPassphraseError):
            crypto.decrypt(changed, HEADER, KEY)


@pytest.mark.needs_crypto
@pytest.mark.parametrize("wrong", ["Key", "key ", "ke", "kéy"])
def test_a_wrong_passphrase_is_refused(fast_scrypt: None, wrong: str) -> None:
    body = crypto.encrypt(b"message", HEADER, KEY)
    with pytest.raises(WrongPassphraseError) as caught:
        crypto.decrypt(body, HEADER, crypto.passphrase_to_bytes(wrong))
    assert wrong not in str(caught.value)


def test_a_passphrase_is_the_same_however_it_was_typed() -> None:
    composed = "Åé한"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert crypto.passphrase_to_bytes(decomposed) == crypto.passphrase_to_bytes(composed) == composed.encode()


@pytest.mark.parametrize(
    ("text", "other"), [("ﬁ", "fi"), ("a", "A"), (" key", "key"), ("①", "1"), ("a" * 10000, "a" * 9999)]
)
def test_different_passphrases_stay_different(text: str, other: str) -> None:
    assert crypto.passphrase_to_bytes(text) == text.encode()
    assert crypto.passphrase_to_bytes(text) != crypto.passphrase_to_bytes(other)


@pytest.mark.needs_crypto
def test_a_very_long_passphrase_works_to_its_last_character(fast_scrypt: None) -> None:
    passphrase = "🎵" * 50000
    body = crypto.encrypt(b"message", HEADER, crypto.passphrase_to_bytes(passphrase))
    assert crypto.decrypt(body, HEADER, crypto.passphrase_to_bytes(passphrase)) == b"message"
    with pytest.raises(WrongPassphraseError):
        crypto.decrypt(body, HEADER, crypto.passphrase_to_bytes(passphrase[:-1] + "x"))


@pytest.mark.parametrize(
    ("passphrase", "reason"),
    [
        ("", "empty"),
        ("\0", "null character"),
        ("my secret\0", "null character"),
        ("my secret \udcff", "not valid text"),
        ("\udc80 my secret", "not valid text"),
    ],
)
def test_an_unusable_passphrase_is_refused_without_showing_it(passphrase: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason) as caught:
        crypto.passphrase_to_bytes(passphrase)
    assert type(caught.value) is ValueError
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "secret" not in str(caught.value)
    assert "\\udcff" not in "".join(traceback.format_exception_only(caught.value))


@pytest.mark.needs_crypto
def test_this_system_can_encrypt() -> None:
    crypto.check_available()


@pytest.mark.needs_crypto
def test_checking_for_encryption_is_cheap(monkeypatch: pytest.MonkeyPatch) -> None:
    costs: list[int] = []
    scrypt = hashlib.scrypt

    def record(*args: Any, **options: Any) -> bytes:
        costs.append(options["n"] * options["r"])
        return scrypt(*args, **options)

    monkeypatch.setattr(hashlib, "scrypt", record)
    crypto.check_available()
    assert costs and max(costs) < 1000


def test_a_missing_library_is_explained(no_library: None, fast_scrypt: None) -> None:
    attempts = [
        lambda: crypto.check_available(),
        lambda: crypto.encrypt(b"message", HEADER, KEY),
        lambda: crypto.decrypt(bytes(50), HEADER, KEY),
    ]
    for attempt in attempts:
        with pytest.raises(MissingLibraryError, match=r'pip install "\.\[crypto\]"'):
            attempt()


@pytest.mark.needs_crypto
def test_the_library_is_imported_only_when_it_is_needed(tmp_path: Any) -> None:
    code = "import audiosteg, audiosteg.cli.main, sys; assert 'cryptography' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path, timeout=60)


def test_a_python_without_scrypt_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(hashlib, "scrypt")
    with pytest.raises(MissingLibraryError, match="does not support scrypt"):
        crypto.derive_key(KEY, bytes(16))


def test_a_system_that_refuses_scrypt_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **options: Any) -> bytes:
        raise ValueError("not in FIPS mode")

    monkeypatch.setattr(hashlib, "scrypt", refuse)
    with pytest.raises(MissingLibraryError, match="refuses scrypt.*not in FIPS mode"):
        crypto.derive_key(KEY, bytes(16))


@pytest.mark.needs_crypto
@pytest.mark.parametrize("refused", ["missing", "error"])
def test_encryption_is_not_available_without_scrypt(monkeypatch: pytest.MonkeyPatch, refused: str) -> None:
    def refuse(*args: Any, **options: Any) -> bytes:
        raise ValueError("refused")

    if refused == "missing":
        monkeypatch.delattr(hashlib, "scrypt")
    else:
        monkeypatch.setattr(hashlib, "scrypt", refuse)
    with pytest.raises(MissingLibraryError, match="scrypt"):
        crypto.check_available()


@pytest.mark.needs_crypto
def test_a_library_that_refuses_aes_gcm_is_explained(
    monkeypatch: pytest.MonkeyPatch, fast_scrypt: None
) -> None:
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.ciphers import aead

    class Refusing:
        def __init__(self, key: bytes) -> None:
            raise UnsupportedAlgorithm("refused")

    body = crypto.encrypt(b"message", HEADER, KEY)
    monkeypatch.setattr(aead, "AESGCM", Refusing)
    with pytest.raises(MissingLibraryError, match="does not support AES-GCM"):
        crypto.check_available()
    with pytest.raises(MissingLibraryError, match="does not support AES-GCM"):
        crypto.encrypt(b"message", HEADER, KEY)
    with pytest.raises(MissingLibraryError, match="does not support AES-GCM"):
        crypto.decrypt(body, HEADER, KEY)
