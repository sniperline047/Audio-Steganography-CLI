"""Get a passphrase from the person at the terminal or from a file."""

import os
import stat
import sys
import unicodedata
import warnings
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from getpass import GetPassWarning, getpass

from audiosteg.core.crypto import passphrase_to_bytes

MAX_FILE_SIZE = 65536
BYTE_ORDER_MARK = "\ufeff"
PROMPT = "Passphrase, not shown while you type: "
REPEAT_PROMPT = "Repeat the passphrase: "


def can_ask() -> bool:
    """Say whether a person can be asked."""
    return any(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))


def ask_hidden(prompt: str) -> str:
    """Ask for one line without showing it."""
    if not can_ask():
        raise OSError("There is no terminal to ask for the passphrase. Use --passphrase_file.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        try:
            with suppress(UnicodeDecodeError):
                return getpass(prompt)
        except GetPassWarning as error:
            raise OSError("This terminal cannot hide the passphrase. Use --passphrase_file.") from error
    raise ValueError("The passphrase contains characters that are not valid text.")


def check_new_passphrase(passphrase: str) -> None:
    """Refuse a passphrase that could not be typed again, such as one with a pasted line break."""
    passphrase_to_bytes(passphrase)
    if any(unicodedata.category(character) in ("Cc", "Zl", "Zp") for character in passphrase):
        raise ValueError("The passphrase contains a line break or another control character.")


def ask_new_passphrase(
    ask: Callable[[], str], repeat: Callable[[], str | None], show: Callable[[str], None]
) -> str:
    """
    Ask for a passphrase twice, until both match and it can be used.

    :param ask: Function that asks for the passphrase
    :param repeat: Function that asks for it again, or returns None to start again
    :param show: Function that says why it is asked again
    :return: The passphrase
    """
    while True:
        passphrase = ask()
        try:
            check_new_passphrase(passphrase)
        except ValueError as error:
            show(f"{error} Please try again.")
            continue
        repeated = repeat()
        if repeated == passphrase:
            return passphrase
        if repeated is not None:
            show("The passphrases do not match. Please try again.")


def check_regular(mode: int, path: str) -> None:
    """Refuse folders, pipes, devices, and other things that are not regular files."""
    if not stat.S_ISREG(mode):
        raise ValueError(f"The passphrase file is not a regular file: {path}")


def read_passphrase_file(path: str, show: Callable[[str], None]) -> str:
    """
    Read a passphrase from a file, without the newline at its end.

    :param path: Path to a regular file
    :param show: Function that shows a warning
    :return: The passphrase
    """
    check_regular(os.stat(path).st_mode, path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        mode = os.fstat(source.fileno()).st_mode
        check_regular(mode, path)
        data = source.read(MAX_FILE_SIZE + 1)
    if os.name != "nt" and mode & (stat.S_IRGRP | stat.S_IROTH):
        show(f"Warning: other users can read the passphrase file: {path}")
    return decode_passphrase(data)


def decode_passphrase(data: bytes) -> str:
    """Remove exactly one newline from the end, and refuse what cannot be a passphrase."""
    if len(data) > MAX_FILE_SIZE:
        raise ValueError("The passphrase file is too large. The limit is 64 KiB.")
    newline = b"\r\n" if data.endswith(b"\r\n") else b"\n"
    data = data.removesuffix(newline)
    if not data:
        raise ValueError("The passphrase file is empty.")
    if b"\0" in data:
        raise ValueError("The passphrase file contains a null character.")
    with suppress(UnicodeDecodeError):
        return data.decode("utf-8")
    raise ValueError("The passphrase file is not valid UTF-8 text.")


@dataclass(frozen=True)
class PassphraseSource:
    """Where a passphrase comes from: a prompt, a file, or nowhere."""

    prompt: bool
    file: str | None

    @property
    def wanted(self) -> bool:
        """Say whether the command line asks for a passphrase."""
        return self.prompt or self.file is not None

    def read_new(self, show: Callable[[str], None]) -> str | None:
        """Get a passphrase for a new message, or None if it should not be encrypted."""
        if self.file is not None:
            passphrase = read_passphrase_file(self.file, show)
            if passphrase.startswith(BYTE_ORDER_MARK):
                raise ValueError(
                    "The passphrase file starts with a byte order mark (BOM). Save it as UTF-8 without BOM."
                )
            check_new_passphrase(passphrase)
            return passphrase
        if not self.prompt:
            return None
        return ask_new_passphrase(lambda: ask_hidden(PROMPT), lambda: ask_hidden(REPEAT_PROMPT), show)

    def read(self, show: Callable[[str], None]) -> str | None:
        """Get the passphrase of an encrypted message, or None if nobody can be asked."""
        if self.file is not None:
            return read_passphrase_file(self.file, show)
        return ask_hidden(PROMPT) if self.prompt or can_ask() else None
