"""Encrypt and decrypt message bytes with a passphrase."""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

from audiosteg.errors import MissingLibraryError, WrongPassphraseError

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
OVERHEAD = SALT_SIZE + NONCE_SIZE + TAG_SIZE

KEY_SIZE = 32
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAX_MEMORY = 2 * 128 * SCRYPT_N * SCRYPT_R


def load_aes_gcm() -> type[AESGCM]:
    """Import the encryption library only when it is needed."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as error:
        raise MissingLibraryError(
            'Encryption needs an optional library. To install it, run: pip install ".[crypto]"'
        ) from error
    return AESGCM


@contextmanager
def explain_refusals() -> Iterator[None]:
    """Explain an encryption library that is installed but refuses AES-GCM."""
    from cryptography.exceptions import UnsupportedAlgorithm

    try:
        yield
    except UnsupportedAlgorithm as error:
        raise MissingLibraryError("The encryption library does not support AES-GCM.") from error


def check_available() -> None:
    """Make sure that this system can encrypt, without the cost of a real key."""
    aes_gcm = load_aes_gcm()
    run_scrypt(b"test", b"test", n=2, r=1)
    with explain_refusals():
        aes_gcm(bytes(KEY_SIZE))


def passphrase_to_bytes(passphrase: str) -> bytes:
    """Return the same bytes for every way to type the same characters."""
    if not passphrase:
        raise ValueError("The passphrase is empty.")
    if "\0" in passphrase:
        raise ValueError("The passphrase contains a null character.")
    with suppress(UnicodeEncodeError):
        return unicodedata.normalize("NFC", passphrase).encode("utf-8")
    raise ValueError("The passphrase contains characters that are not valid text.")


def run_scrypt(passphrase: bytes, salt: bytes, n: int, r: int) -> bytes:
    """Run scrypt, and explain a Python or OpenSSL that does not offer it."""
    scrypt = getattr(hashlib, "scrypt", None)
    if scrypt is None:
        raise MissingLibraryError("This Python installation does not support scrypt, which encryption needs.")
    try:
        key: bytes = scrypt(
            passphrase, salt=salt, n=n, r=r, p=SCRYPT_P, maxmem=SCRYPT_MAX_MEMORY, dklen=KEY_SIZE
        )
    except ValueError as error:
        raise MissingLibraryError(f"This system refuses scrypt, which encryption needs: {error}") from error
    return key


def derive_key(passphrase: bytes, salt: bytes) -> bytes:
    """Turn a passphrase into an AES-256 key."""
    return run_scrypt(passphrase, salt, n=SCRYPT_N, r=SCRYPT_R)


def encrypt(message: bytes, header: bytes, passphrase: bytes) -> bytes:
    """
    Encrypt a message and protect its header against changes.

    :param message: The message bytes
    :param header: The container header, which is not encrypted
    :param passphrase: The bytes from passphrase_to_bytes
    :return: The salt, the nonce, the encrypted message, and the tag
    """
    aes_gcm = load_aes_gcm()
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    key = derive_key(passphrase, salt)
    with explain_refusals():
        return salt + nonce + aes_gcm(key).encrypt(nonce, message, header)


def decrypt(body: bytes, header: bytes, passphrase: bytes) -> bytes:
    """
    Decrypt the result of encrypt. Any change to the body or header is an error.

    :param body: The salt, the nonce, the encrypted message, and the tag
    :param header: The container header
    :param passphrase: The bytes from passphrase_to_bytes
    :return: The message bytes
    """
    aes_gcm = load_aes_gcm()
    from cryptography.exceptions import InvalidTag

    salt = body[:SALT_SIZE]
    nonce = body[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
    ciphertext = body[SALT_SIZE + NONCE_SIZE :]
    key = derive_key(passphrase, salt)
    try:
        with explain_refusals():
            return aes_gcm(key).decrypt(nonce, ciphertext, header)
    except InvalidTag as error:
        raise WrongPassphraseError("Wrong passphrase, or the message was changed.") from error
