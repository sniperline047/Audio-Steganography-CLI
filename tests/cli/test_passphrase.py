"""Tests for audiosteg/cli/passphrase.py."""

import io
import os
import warnings
from collections.abc import Callable
from functools import partial
from getpass import GetPassWarning
from pathlib import Path

import pytest

from audiosteg.cli import passphrase
from audiosteg.cli.passphrase import (
    PassphraseSource,
    ask_hidden,
    ask_new_passphrase,
    decode_passphrase,
    read_passphrase_file,
)

SetGetpass = Callable[[Callable[[str], str]], None]


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> SetGetpass:
    """Return a function that pretends that there is a terminal with this getpass."""

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    def set_getpass(getpass: Callable[[str], str]) -> None:
        monkeypatch.setattr("sys.stdin", Terminal())
        monkeypatch.setattr(passphrase, "getpass", getpass)

    return set_getpass


def test_a_terminal_hides_the_answer(terminal: SetGetpass) -> None:
    prompts: list[str] = []
    terminal(lambda prompt: prompts.append(prompt) or " key ")
    assert ask_hidden("Passphrase: ") == " key "
    assert prompts == ["Passphrase: "]


def test_a_terminal_that_cannot_hide_the_answer_is_refused(terminal: SetGetpass) -> None:
    def show(prompt: str) -> str:
        warnings.warn("Can not control echo on the terminal.", GetPassWarning, stacklevel=2)
        return "key"

    terminal(show)
    with pytest.raises(OSError, match="cannot hide the passphrase"):
        ask_hidden("Passphrase: ")


def test_without_a_terminal_nothing_is_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("stdin", "stdout", "stderr"):
        monkeypatch.setattr(f"sys.{name}", io.StringIO("key\n"))
    with pytest.raises(OSError, match="--passphrase_file"):
        ask_hidden("Passphrase: ")
    assert PassphraseSource(prompt=False, file=None).read(print) is None


def test_hidden_bytes_that_are_not_text_are_refused_without_showing_them(terminal: SetGetpass) -> None:
    terminal(lambda prompt: b"secret \xff".decode("utf-8"))
    with pytest.raises(ValueError, match="not valid text") as caught:
        ask_hidden("Passphrase: ")
    assert type(caught.value) is ValueError
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_leaving_a_hidden_prompt_is_not_an_empty_answer(
    terminal: SetGetpass, error: type[BaseException]
) -> None:
    def leave(prompt: str) -> str:
        raise error

    terminal(leave)
    with pytest.raises(error):
        ask_new_passphrase(lambda: ask_hidden(""), lambda: ask_hidden(""), print)


def test_a_new_passphrase_must_be_repeated_and_not_empty(terminal: SetGetpass) -> None:
    answers = ["key", "Key", "", "key\n", "a\tb", "key ", "key", "key", "key"]
    terminal(lambda prompt: answers.pop(0))
    shown: list[str] = []
    ask = partial(ask_hidden, "")
    assert ask_new_passphrase(ask, ask, shown.append) == "key"
    assert answers == []
    mismatch = "The passphrases do not match. Please try again."
    control = "The passphrase contains a line break or another control character. Please try again."
    empty = "The passphrase is empty. Please try again."
    assert shown == [mismatch, empty, control, control, mismatch]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"key", "key"),
        (b"key\n", "key"),
        (b"key\r\n", "key"),
        (b"key\n\n", "key\n"),
        (b" key \n", " key "),
        ("sésame".encode(), "sésame"),
    ],
)
def test_exactly_one_newline_is_removed(data: bytes, expected: str) -> None:
    assert decode_passphrase(data) == expected


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "empty"),
        (b"\n", "empty"),
        (b"a\0b", "null"),
        (b"TOP_SECRET \xff", "not valid UTF-8"),
        (b"x" * 65537, "too large"),
    ],
)
def test_an_unusable_passphrase_file_is_refused_without_showing_it(data: bytes, reason: str) -> None:
    with pytest.raises(ValueError, match=reason) as caught:
        decode_passphrase(data)
    assert "SECRET" not in str(caught.value)
    assert caught.value.__context__ is None


def test_only_regular_files_are_read(tmp_path: Path) -> None:
    paths = [tmp_path, Path(os.devnull)]
    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "pipe")
        paths.append(tmp_path / "pipe")
    for path in paths:
        with pytest.raises((ValueError, OSError)):
            read_passphrase_file(str(path), print)


@pytest.mark.skipif(os.name == "nt", reason="Windows has no such permissions")
@pytest.mark.parametrize(("mode", "warned"), [(0o600, False), (0o640, True), (0o604, True)])
def test_a_file_that_others_can_read_is_a_warning(tmp_path: Path, mode: int, warned: bool) -> None:
    path = tmp_path / "key.txt"
    path.write_bytes(b"key\n")
    path.chmod(mode)
    shown: list[str] = []
    assert read_passphrase_file(str(path), shown.append) == "key"
    assert bool(shown) is warned


@pytest.mark.parametrize("data", [b"a\nb", b"a\tb", "a\u2028b".encode(), b"key\r", b"", b"\x7f"])
def test_a_passphrase_file_that_could_not_be_typed_is_refused_for_a_new_message_only(
    tmp_path: Path, data: bytes
) -> None:
    path = tmp_path / "key.txt"
    path.write_bytes(data)
    path.chmod(0o600)
    source = PassphraseSource(prompt=False, file=str(path))
    with pytest.raises(ValueError, match="control character|empty"):
        source.read_new(print)
    if data:
        assert source.read(print) == data.decode()


def test_the_limit_of_a_passphrase_file(tmp_path: Path) -> None:
    path = tmp_path / "key.txt"
    path.write_bytes(b"x" * 65536)
    path.chmod(0o600)
    assert read_passphrase_file(str(path), print) == "x" * 65536


def test_going_back_from_the_repetition_asks_for_the_passphrase_without_a_complaint() -> None:
    asked, repeated, shown = ["one", "two"], [None, "two"], []
    passphrase_found = ask_new_passphrase(lambda: asked.pop(0), lambda: repeated.pop(0), shown.append)
    assert (passphrase_found, shown) == ("two", [])


def test_invisible_but_typable_characters_are_allowed() -> None:
    passphrase.check_new_passphrase("a\u200d\u00a0b 🎵")


def test_no_prompt_and_no_file_means_no_encryption() -> None:
    source = PassphraseSource(prompt=False, file=None)
    assert (source.wanted, source.read_new(print)) == (False, None)
