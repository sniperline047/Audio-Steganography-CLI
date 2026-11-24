"""Tests for audiosteg/cli/guided/prompter.py."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from questionary import Choice

from audiosteg.cli.guided import prompter as prompter_module
from audiosteg.cli.guided.prompter import GoBack, Prompter

DOWN, UP, ENTER = "\x1b[B", "\x1b[A", "\r"
MENU = "What would you like to do?"


@pytest.fixture
def prompter(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], Prompter]:
    """Return a function that makes a prompter whose next text answer is known."""

    class Out:
        coloured = False

    class View:
        out = Out()

    def make(answer: str) -> Prompter:
        made = Prompter(View())  # type: ignore[arg-type]
        monkeypatch.setattr(prompter_module.questionary, "text", lambda *args, **options: None)
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


def test_a_default_is_used_as_it_is(prompter: Callable[[str], Prompter]) -> None:
    assert prompter("").file("Output file", " ~a .wav ") == " ~a .wav "


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


def test_an_empty_path_without_a_default_is_refused(prompter: Callable[[str], Prompter]) -> None:
    with pytest.raises(ValueError, match="path is empty"):
        prompter("  ").file("Input")


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


def test_an_unsafe_default_is_shown_escaped_but_used_as_it_is(
    guide: Any, make_wav: Callable[..., Path], tmp_path: Path, no_library: None
) -> None:
    make_wav(name="gpj\u202e.wav")
    result = guide(
        (MENU, ENTER),
        ("Which audio file?", DOWN + ENTER),
        ("Path of the WAV file:", f"gpj\u202e.wav{ENTER}"),
        ("Message to hide:", f"x{ENTER}"),
        ("Which algorithm?", ENTER),
        ("Output file [gpj\\u202e.stego.wav]:", ENTER),
    )
    assert result.code == 0
    assert (tmp_path / "gpj\u202e.stego.wav").exists()


def test_an_interrupt_from_outside_is_not_lost(guide: Any) -> None:
    def interrupt(application: Any) -> None:
        application.key_processor.send_sigint()

    for number, question in ((0, "Which audio file?"), (1, "WAV file with the hidden message")):
        result = guide((MENU, DOWN * number + ENTER), (question, interrupt), leave=False)
        assert result.code == 130


def test_a_terminal_that_closes_ends_the_program(guide: Any) -> None:
    def close(application: Any) -> None:
        application.exit(exception=OSError(5, "Input/output error"))

    result = guide((MENU, DOWN + ENTER), ("WAV file with the hidden message", close), leave=False)
    assert result.code == 1
    assert "Error: The terminal was closed." in result.text


@pytest.mark.parametrize(
    ("words", "changes", "coloured"),
    [([], {}, True), ([], {"NO_COLOR": "1"}, False), (["--plain"], {}, False)],
)
def test_colours_only_where_they_are_wanted(
    run: Any, words: list[str], changes: dict[str, str], coloured: bool
) -> None:
    prompts = ((MENU, DOWN + ENTER), ("hidden message:", f"missing.wav{ENTER}"), ("hidden message:", "\x04"))
    result = run(*words, prompts=prompts, terminals=("stdin", "stdout", "stderr"), **changes)
    assert result.code == 1
    assert (";38;" in result.seen) is coloured


def test_the_arrow_keys_wrap_around(guide: Any) -> None:
    assert guide((MENU, UP + ENTER), leave=False).code == 0


def test_menu_values_that_are_false_are_answers(prompter: Callable[[str], Prompter]) -> None:
    for value in (False, ""):
        made = prompter("")
        made.ask = lambda question, end_with_ctrl_d, value=value: value  # type: ignore[method-assign]
        assert made.choose("?", [Choice("no", value=value)]) == value
