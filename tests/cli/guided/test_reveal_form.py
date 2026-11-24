"""Tests for audiosteg/cli/guided/reveal_form.py."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg import encode
from audiosteg.algorithms.lsb import LSB, LSB_2

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
REVEAL, VERIFY = (("What would you like to do?", DOWN * number + ENTER) for number in (1, 2))
FILE = "WAV file with the hidden message:"
LEGACY = "How did the older version hide the message?"
NOT_ENCRYPTED = "This message was not encrypted, so anyone could have written it."


def file(name: str) -> tuple[str, str]:
    return (FILE, f"{name}{ENTER}")


def passphrase(text: str) -> tuple[str, str]:
    return ("Passphrase:", f"{text}{ENTER}")


@pytest.fixture
def plain(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    encode(str(make_wav()), str(tmp_path / "plain.wav"), "plain message", LSB)


@pytest.fixture
def private(make_wav: Callable[..., Path], tmp_path: Path, fast_scrypt: None) -> None:
    encode(str(make_wav()), str(tmp_path / "private.wav"), "my secret", LSB_2, passphrase="sésame")


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("plain", "private")
def test_a_wrong_passphrase_can_be_corrected(guide: Any) -> None:
    result = guide(REVEAL, file("private.wav"), passphrase("wrong"), passphrase(""), passphrase("sésame"))
    assert result.code == 0
    assert "Error: Wrong passphrase, or the message was changed." in result.text
    assert "Error: The passphrase is empty." in result.text
    assert "\nmy secret\nThis message was encrypted.\n" in result.text
    for typed in ("wrong\n", "sésame"):
        assert typed not in result.text


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("plain", "private")
def test_another_file_after_back_is_read_without_the_old_message_and_passphrase(guide: Any) -> None:
    result = guide(
        VERIFY,
        file("private.wav"),
        passphrase("sésame"),
        ("Expected message:", ESCAPE),
        passphrase("wrong"),
        ("Passphrase:", ESCAPE),
        file("plain.wav"),
        ("Expected message:", ESCAPE),
        file("plain.wav"),
        ("Expected message:", f"plain message{ENTER}"),
    )
    assert result.code == 0
    assert "The message matches" in result.text
    assert NOT_ENCRYPTED in result.text
    assert "The same as a command: audiosteg verify plain.wav\n" in result.text


@pytest.mark.usefixtures("plain")
def test_a_back_out_of_the_old_algorithms_leads_to_a_detected_file(
    guide: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(name="old.wav", frames=bytes(32))
    result = guide(
        REVEAL,
        file("old.wav"),
        (LEGACY, DOWN * 3 + ENTER),
        file("old.wav"),
        (LEGACY, ESCAPE),
        file("plain.wav"),
    )
    assert "\nplain message\n" in result.text
    assert "The same as a command: audiosteg reveal plain.wav\n" in result.text


@pytest.mark.parametrize(("position", "key"), [(0, "basic"), (1, "enhanced_flip"), (2, "enhanced")])
def test_the_command_for_an_old_file(
    guide: Any, run: Any, make_wav: Callable[..., Path], position: int, key: str
) -> None:
    make_wav(name="old.wav", frames=bytes(32))
    old = ("How did the older version", DOWN * position + ENTER)
    result = guide(VERIFY, file("old.wav"), old, ("Expected message:", ESCAPE), old, ("Expected", ENTER))
    assert (result.code, "The message matches" in result.text) == (0, True)
    assert f"The same as a command: audiosteg verify old.wav --legacy {key}\n" in result.text
    assert run("verify", "old.wav", "--legacy", key, "-m", "").code == 0


def test_a_damaged_or_unusable_file_is_asked_again(
    guide: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes], plain: None
) -> None:
    make_wav(name="newer.wav", frames=embed(b"ASTG\x02\0\0\0\0\0", 1))
    make_wav(name="cut.wav", frames=embed(b"ASTG\x01\0\xff\0\0\0", 1))
    result = guide(REVEAL, file("newer.wav"), file("cut.wav"), file("."), file("plain.wav"))
    assert result.code == 0
    assert "format version 2" in result.text
    assert "it is longer than the audio file" in result.text
    assert "not a regular file" in result.text
    assert "older version" not in result.text


def test_a_message_that_turns_out_to_be_damaged_is_a_failure(
    guide: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    make_wav(name="bad.wav", frames=embed(b"ASTG\x01\0\0\0\0\x01A\0\0\0\0", 1))
    result = guide(REVEAL, file("bad.wav"))
    assert result.code == 1
    assert "Error: The hidden message is damaged" in result.text
    assert "same as a command" not in result.text


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("private", "plain")
def test_without_the_library_an_encrypted_file_is_explained_before_the_passphrase(
    guide: Any, monkeypatch: pytest.MonkeyPatch, no_library: None
) -> None:
    result = guide(REVEAL, file("private.wav"), file("plain.wav"))
    assert "Error: Encryption needs an optional library." in result.text
    assert "\nplain message\n" in result.text


def test_a_message_cannot_control_the_terminal_or_fake_the_last_line(
    guide: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    unsafe = "\x1b[2J\x9b1m\u202e[red]\n:smile: This message was encrypted."
    encode(str(make_wav()), str(tmp_path / "unsafe.wav"), unsafe, LSB)
    result = guide(REVEAL, file("unsafe.wav"), NO_COLOR="1")
    shown = "\\x1b[2J\\x9b1m\\u202e[red]\\n:smile: This message was encrypted."
    assert f"\n{shown}\n{NOT_ENCRYPTED}\n" in result.text


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("private")
@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
@pytest.mark.parametrize("number", range(3))
def test_leaving_at_any_question(guide: Any, number: int, key: str, code: int) -> None:
    questions = [file("private.wav"), passphrase("sésame"), ("Expected message:", "")]
    result = guide(VERIFY, *questions[:number], (questions[number][0], key), leave=False)
    assert result.code == code
    assert "my secret" not in result.text
    assert "sésame" not in result.text
