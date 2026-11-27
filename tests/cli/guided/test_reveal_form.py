"""Tests for audiosteg/cli/guided/reveal_form.py."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import noise_for

from audiosteg import encode
from audiosteg.algorithms.echo import ECHO
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_keyed import LSB_KEYED

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
REVEAL, VERIFY = (("What would you like to do?", DOWN * number + ENTER) for number in (1, 2))
FILE = "WAV file with the hidden message:"
UNDETECTED = "How may the message be hidden?"
OTHER_FILE, KEYED = ((UNDETECTED, DOWN * number + ENTER) for number in range(2))
NEXT = "What next?"
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
def test_a_back_out_of_the_question_leads_to_a_detected_file(
    guide: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(name="silent.wav", frames=bytes(32))
    result = guide(
        REVEAL,
        file("silent.wav"),
        (UNDETECTED, DOWN * 2 + ENTER),
        file("silent.wav"),
        (UNDETECTED, ESCAPE),
        file("plain.wav"),
    )
    assert "\nplain message\n" in result.text
    assert "The same as a command: audiosteg reveal plain.wav\n" in result.text


@pytest.mark.usefixtures("plain")
def test_a_file_without_a_message_after_back_is_not_read_as_the_file_before(
    guide: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(name="silent.wav", frames=bytes(32))
    result = guide(
        VERIFY,
        file("plain.wav"),
        ("Expected", ESCAPE),
        file("silent.wav"),
        OTHER_FILE,
        file("plain.wav"),
        ("Expected", f"plain message{ENTER}"),
    )
    assert (result.code, "The message matches" in result.text) == (0, True)
    assert "No message was detected." in result.text


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
def test_a_failure_does_not_show_hints_about_options(guide: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(name="other.wav", frames=b"\xff" * 400)
    result = guide(REVEAL, file("other.wav"), KEYED, passphrase("sesame"), (NEXT, CTRL_C), leave=False)
    assert "Error: No hidden message was found with this passphrase." in result.text
    assert "hide made" not in result.text and "add -p" not in result.text


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


@pytest.fixture
def scattered(make_wav: Callable[..., Path], tmp_path: Path, fast_scrypt: None) -> None:
    output = tmp_path / "scattered.wav"
    encode(str(make_wav()), str(output), "my secret", LSB_KEYED, passphrase="sésame")


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("scattered")
def test_a_keyed_message_is_read_after_a_wrong_passphrase(guide: Any, run: Any) -> None:
    result = guide(
        VERIFY,
        file("scattered.wav"),
        KEYED,
        passphrase("wrong"),
        (NEXT, ENTER),
        passphrase(""),
        passphrase("sésame"),
        ("Expected message:", f"my secret{ENTER}"),
    )
    assert (result.code, "The message matches" in result.text) == (0, True)
    assert "Error: No hidden message was found with this passphrase." in result.text
    command = "audiosteg verify scattered.wav -a lsb_keyed"
    assert f"The same as a command: {command}\n" in result.text
    words = [*command.split()[1:], "-m", "my secret"]
    assert run(*words, hidden=("sésame",), terminals=("stdin", "stderr")).code == 0


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("scattered", "plain")
def test_back_out_of_a_keyed_message(guide: Any) -> None:
    result = guide(
        VERIFY,
        file("scattered.wav"),
        KEYED,
        passphrase("sésame"),
        ("Expected", ESCAPE),
        ("Passphrase:", ESCAPE),
        (UNDETECTED, ESCAPE),
        file("plain.wav"),
        ("Expected", f"plain message{ENTER}"),
    )
    assert (result.code, "The message matches" in result.text) == (0, True)


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt", "no_numpy")
def test_a_passphrase_that_finds_nothing_names_what_was_not_looked_for(
    guide: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(name="nothing.wav")
    result = guide(REVEAL, file("nothing.wav"), KEYED, passphrase("wrong"), (NEXT, CTRL_C), leave=False)
    after = result.text.split("Error: No hidden message was found with this passphrase.")[1]
    assert "Messages of echo cannot be detected here, because NumPy is missing." in after


@pytest.mark.needs_crypto
@pytest.mark.needs_signal
@pytest.mark.usefixtures("fast_scrypt")
def test_a_keyed_message_behind_an_encrypted_echo_can_be_read(
    guide: Any, run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    echo, both = str(tmp_path / "echo.wav"), str(tmp_path / "both.wav")
    encode(str(make_wav(frames=noise_for("echo"))), echo, "in the sound", ECHO, passphrase="other")
    encode(echo, both, "scattered", LSB_KEYED, passphrase="sésame")
    keyed = (NEXT, DOWN + ENTER)
    result = guide(REVEAL, file("both.wav"), passphrase("sésame"), keyed, passphrase("sésame"))
    assert (result.code, "\nscattered\n" in result.text) == (0, True)
    command = "audiosteg reveal both.wav -a lsb_keyed"
    assert f"The same as a command: {command}\n" in result.text
    assert run(*command.split()[1:], hidden=("sésame",), terminals=("stdin", "stderr")).output == "scattered"
    again = guide(REVEAL, file("both.wav"), passphrase("wrong"), (NEXT, ENTER), passphrase("other"))
    assert (again.code, "\nin the sound\n" in again.text) == (0, True)
    back = guide(
        REVEAL, file("both.wav"), passphrase("wrong"), keyed, ("Passphrase:", ESCAPE),
        file("both.wav"), passphrase("other"),
    )  # fmt: skip
    assert "\nin the sound\n" in back.text
    assert "The same as a command: audiosteg reveal both.wav\n" in back.text


@pytest.mark.usefixtures("plain")
def test_a_keyed_message_cannot_be_read_without_the_library(
    guide: Any, make_wav: Callable[..., Path], no_library: None
) -> None:
    make_wav(name="silent.wav", frames=bytes(32))
    result = guide(REVEAL, file("silent.wav"), KEYED, OTHER_FILE, file("plain.wav"))
    assert "Error: Encryption needs an optional library." in result.text
    assert "The same as a command: audiosteg reveal plain.wav\n" in result.text


@pytest.mark.needs_crypto
@pytest.mark.parametrize("back", [ESCAPE, DOWN + ENTER])
def test_a_passphrase_that_finds_nothing_is_no_trap(
    guide: Any, make_wav: Callable[..., Path], plain: None, fast_scrypt: None, back: str
) -> None:
    make_wav(name="nothing.wav")
    result = guide(
        REVEAL,
        file("nothing.wav"),
        KEYED,
        passphrase("sesame"),
        (NEXT, ENTER),
        passphrase("sesame"),
        (NEXT, back),
        OTHER_FILE,
        file("plain.wav"),
    )
    assert (result.code, "\nplain message\n" in result.text) == (0, True)
    assert result.text.count("Error: No hidden message was found with this passphrase.") == 2


@pytest.mark.usefixtures("plain")
def test_enter_for_a_file_without_a_message_asks_for_another_file(
    guide: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(name="nothing.wav")
    result = guide(REVEAL, file("nothing.wav"), OTHER_FILE, file("plain.wav"))
    assert (result.code, "Passphrase:" in result.text) == (0, False)
    assert "No message was detected. lsb_keyed may have made this file." in result.text
    assert "\nplain message\n" in result.text


@pytest.mark.needs_crypto
@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
@pytest.mark.usefixtures("scattered")
def test_leaving_after_a_passphrase_that_finds_nothing(guide: Any, key: str, code: int) -> None:
    result = guide(REVEAL, file("scattered.wav"), KEYED, passphrase("wrong"), (NEXT, key), leave=False)
    assert result.code == code
