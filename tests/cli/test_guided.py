"""Tests for audiosteg/cli/guided.py."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg import decode, encode
from audiosteg.algorithms.lsb import LSB
from audiosteg.cli import guided
from audiosteg.cli.guided import GoBack, Prompter

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
MENU = "What would you like to do?"
ENCRYPTION = "Encrypt the message?"


def answer_all(program: Any, answers: list[tuple[str, str]]) -> None:
    for question, keys in answers:
        program.answer(question, keys)


def skip_encryption() -> list[tuple[str, str]]:
    import importlib.util

    return [(ENCRYPTION, ENTER)] if importlib.util.find_spec("cryptography") else []


def test_hide_reveal_and_verify_the_sample(terminal: Any, tmp_path: Path) -> None:
    program = terminal()
    answer_all(
        program,
        [
            (MENU, ENTER),
            ("Which audio file?", ENTER),
            ("Message to hide:", f"my message{ENTER}"),
            ("Which algorithm?", DOWN + ENTER),
            *skip_encryption(),
            ("Output file [sample.stego.wav]:", ENTER),
            ("audiosteg hide sample -a lsb_2 -o sample.stego.wav", ""),
            (MENU, DOWN + ENTER),
            ("hidden message [sample.stego.wav]:", ENTER),
            ("audiosteg reveal sample.stego.wav", ""),
            ("my message", ""),
            ("not encrypted, so anyone", ""),
            (MENU, DOWN * 2 + ENTER),
            ("hidden message [sample.stego.wav]:", ENTER),
            ("Expected message:", f"other{ENTER}"),
            ("The message does not match", ""),
            (MENU, DOWN * 3 + ENTER),
            ("enhanced_flip", ""),
            (MENU, DOWN * 4 + ENTER),
        ],
    )
    assert program.finish() == 0
    assert decode(str(tmp_path / "sample.stego.wav")) == "my message"
    assert program.seen.count("Audio Steganography CLI") == 1


@pytest.mark.needs_crypto
def test_a_passphrase_is_never_shown(terminal: Any, tmp_path: Path) -> None:
    program = terminal()
    answer_all(
        program,
        [
            (MENU, ENTER),
            ("Which audio file?", ENTER),
            ("Message to hide:", f"hidden{ENTER}"),
            ("Which algorithm?", ENTER),
            (ENCRYPTION, DOWN + ENTER),
            ("Passphrase:", f"sesame{ENTER}"),
            ("Repeat the passphrase:", f"sesam{ENTER}"),
            ("do not match", ""),
            ("Passphrase:", f"sesame{ENTER}"),
            ("Repeat the passphrase:", f"sesame{ENTER}"),
            ("Output file", ENTER),
            ("sample.stego.wav -p", ""),
            (MENU, DOWN + ENTER),
            ("hidden message", ENTER),
            ("Passphrase:", f"sesame{ENTER}"),
            ("This message was encrypted.", ""),
            (MENU, CTRL_D),
        ],
    )
    assert program.finish() == 0
    assert "sesam" not in program.seen
    assert decode(str(tmp_path / "sample.stego.wav"), passphrase="sesame") == "hidden"


def test_escape_goes_back_one_question(terminal: Any) -> None:
    program = terminal()
    answer_all(
        program,
        [
            (MENU, ENTER),
            ("Which audio file?", DOWN + ENTER),
            ("Path of the WAV file:", ESCAPE),
            ("Which audio file?", ESCAPE),
            (MENU, DOWN + ENTER),
            ("WAV file with the hidden message:", ESCAPE),
            (MENU, CTRL_C),
            ("Interrupted.", ""),
        ],
    )
    assert program.finish() == 130


def test_a_wrong_path_is_asked_again_and_old_files_can_be_read(
    terminal: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(name="old.wav", frames=bytes(32))
    program = terminal()
    answer_all(
        program,
        [
            (MENU, DOWN + ENTER),
            ("hidden message:", f"missing.wav{ENTER}"),
            ("does not exist", ""),
            ("hidden message:", f"old.wav{ENTER}"),
            ("older version hide", ENTER),
            ("audiosteg reveal old.wav --legacy basic", ""),
            ("The message is empty.", ""),
            (MENU, DOWN * 4 + ENTER),
        ],
    )
    assert program.finish() == 0


@pytest.mark.parametrize(("keys", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
def test_leaving_the_overwrite_question_keeps_the_file(
    terminal: Any, make_wav: Callable[..., Path], tmp_path: Path, keys: str, code: int
) -> None:
    output = tmp_path / "input.stego.wav"
    encode(str(make_wav()), str(output), "keep me", LSB)
    program = terminal()
    answer_all(
        program,
        [
            (MENU, ENTER),
            ("Which audio file?", DOWN + ENTER),
            ("Path of the WAV file:", f"input.wav{ENTER}"),
            ("Message to hide:", f"new{ENTER}"),
            ("Which algorithm?", ENTER),
            *skip_encryption(),
            ("Output file", ENTER),
            ("Overwrite it?", f"n{ENTER}" if keys == CTRL_D else keys),
        ],
    )
    if keys == CTRL_D:
        program.answer("Output file", keys)
    assert program.finish() == code
    assert decode(str(output)) == "keep me"


@pytest.fixture
def prompter(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], Prompter]:
    """Return a function that makes a prompter whose next text answer is known."""

    class Out:
        coloured = False

    class View:
        out = Out()

    def make(answer: str) -> Prompter:
        made = Prompter(View())  # type: ignore[arg-type]
        monkeypatch.setattr(guided.questionary, "text", lambda *args, **options: None)
        monkeypatch.setattr(made, "ask", lambda question: answer)
        return made

    return make


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("", "default.wav"),
        ("   ", "default.wav"),
        ("other.wav", "other.wav"),
        ("my folder/a file.wav", "my folder/a file.wav"),
        (" \t other.wav \t", "other.wav"),
    ],
)
def test_file_path_answers(prompter: Callable[[str], Prompter], text: str, path: str) -> None:
    assert prompter(text).file("Output file", "default.wav") == path


def test_a_tilde_means_the_home_folder(
    prompter: Callable[[str], Prompter], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for variable in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(tmp_path))
    assert Path(prompter(" ~/a.wav ").file("Input")) == tmp_path / "a.wav"
    assert prompter("./~/a.wav").file("Input") == "./~/a.wav"


@pytest.mark.skipif(os.name == "nt", reason="Windows guesses the folder of an unknown user")
def test_an_unknown_home_folder_is_refused(prompter: Callable[[str], Prompter]) -> None:
    with pytest.raises(FileNotFoundError, match="No home folder"):
        prompter("~no_such_user_here/a.wav").file("Input")


def test_going_back_skips_questions_that_were_not_asked(prompter: Callable[[str], Prompter]) -> None:
    asked: list[str] = []

    def first() -> bool:
        asked.append("first")
        return True

    def skipped() -> bool:
        return False

    def last() -> bool:
        asked.append("last")
        if asked.count("last") == 1:
            raise GoBack
        return True

    assert prompter("").run([first, skipped, last]) is True
    assert asked == ["first", "last", "first", "last"]


@pytest.mark.parametrize(
    ("words", "shown"),
    [
        (("audiosteg", "reveal", "a.wav"), "audiosteg reveal a.wav"),
        (("audiosteg", "reveal", "a\x1b[2J.wav"), None),
        (("audiosteg", "reveal", "a\u202e.wav"), None),
    ],
)
def test_only_commands_that_can_be_shown_are_shown(words: tuple[str, ...], shown: str | None) -> None:
    assert guided.command_line(*words) == shown
