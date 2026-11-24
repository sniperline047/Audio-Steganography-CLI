"""Tests for cli/helpers.py."""

import io
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from cli.config import ALGORITHMS
from cli.helpers import OutputClosedError, ask, ask_yes_no, choose_algorithm, get_file_path, get_user_choice

Answer = Callable[..., list[str]]


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch) -> Answer:
    """Return a function that sets the next answers and returns the ones not used yet."""

    def set_answers(*answers: str) -> list[str]:
        remaining = list(answers)
        monkeypatch.setattr("builtins.input", lambda prompt="": remaining.pop(0))
        return remaining

    return set_answers


@pytest.mark.parametrize(("text", "choice"), [("1", 1), ("3", 3), (" 2 ", 2)])
def test_a_valid_choice_is_returned(answer: Answer, text: str, choice: int) -> None:
    answer(text)
    assert get_user_choice(3) == choice


@pytest.mark.parametrize("text", ["0", "4", "-1", "", "abc", "1.0", "1 2", "9" * 5000])
def test_an_invalid_choice_is_explained(
    answer: Answer, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    answer(text)
    assert get_user_choice(3) is None
    assert "valid" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("text", "expected"),
    [("y", True), ("YES", True), (" yes ", True), ("n", False), ("No", False), ("", False), ("  ", False)],
)
def test_yes_no_answers(answer: Answer, text: str, expected: bool) -> None:
    answer(text)
    assert ask_yes_no("Sure?") is expected


def test_an_unclear_answer_is_asked_again(answer: Answer, capsys: pytest.CaptureFixture[str]) -> None:
    remaining = answer("maybe", "yess", "/some/path.wav", "y")
    assert ask_yes_no("Sure?") is True
    assert remaining == []
    output = capsys.readouterr().out
    assert output.count("Sure? (y/N): ") == 4
    assert output.count("Please answer y or n.") == 3


def test_an_invalid_algorithm_is_asked_again(answer: Answer, capsys: pytest.CaptureFixture[str]) -> None:
    answer("0", "x", "5", "2")
    assert choose_algorithm() is ALGORITHMS[2]
    assert capsys.readouterr().out.count("Select an algorithm:") == 4


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
def test_file_path_answers(answer: Answer, text: str, path: str) -> None:
    answer(text)
    assert get_file_path("Input audio file", "default.wav") == path


def test_a_tilde_means_the_home_folder(
    answer: Answer, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for variable in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(tmp_path))
    answer(" ~/a.wav ", "./~/a.wav")
    assert Path(get_file_path("Input audio file", "default.wav")) == tmp_path / "a.wav"
    assert get_file_path("Input audio file", "default.wav") == "./~/a.wav"


def test_an_unsafe_default_path_is_shown_escaped_but_used_as_it_is(
    answer: Answer, capsys: pytest.CaptureFixture[str]
) -> None:
    answer("")
    assert get_file_path("Input audio file", "a\x1b[2J\u202e.wav") == "a\x1b[2J\u202e.wav"
    assert capsys.readouterr().out == "\nInput audio file [a\\x1b[2J\\u202e.wav]: "


def test_nothing_is_read_after_the_output_is_closed(answer: Answer, monkeypatch: pytest.MonkeyPatch) -> None:
    class ClosedOutput(io.StringIO):
        def flush(self) -> None:
            raise BrokenPipeError

    remaining = answer("unread")
    monkeypatch.setattr("sys.stdout", ClosedOutput())
    with pytest.raises(OutputClosedError):
        ask("Prompt: ")
    assert remaining == ["unread"]


def test_back_chooses_no_algorithm(answer: Answer, capsys: pytest.CaptureFixture[str]) -> None:
    answer("4")
    assert choose_algorithm() is None
    assert "4) Back" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="Windows guesses the folder of an unknown user")
def test_an_unknown_home_folder_is_refused(answer: Answer) -> None:
    answer("~no_such_user_here/a.wav")
    with pytest.raises(FileNotFoundError, match="No home folder"):
        get_file_path("Output audio file", "default.wav")
