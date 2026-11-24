"""Encrypt and decrypt message bytes with a passphrase."""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
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


def is_available() -> bool:
    """Return whether the encryption library is installed."""
    try:
        load_aes_gcm()
    except MissingLibraryError:
        return False
    return True


def passphrase_to_bytes(passphrase: str) -> bytes:
    """Return the same bytes for every way to type the same characters."""
    if not passphrase:
        raise ValueError("The passphrase is empty.")
    try:
        return unicodedata.normalize("NFC", passphrase).encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("The passphrase contains characters that are not valid text.") from None


def derive_key(passphrase: bytes, salt: bytes) -> bytes:
    """Turn a passphrase into an AES-256 key."""
    return hashlib.scrypt(
        passphrase,
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAX_MEMORY,
        dklen=KEY_SIZE,
    )


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
    return salt + nonce + aes_gcm(derive_key(passphrase, salt)).encrypt(nonce, message, header)


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
    try:
        return aes_gcm(derive_key(passphrase, salt)).decrypt(nonce, ciphertext, header)
    except InvalidTag as error:
        raise WrongPassphraseError("Wrong passphrase, or the message was changed.") from error
