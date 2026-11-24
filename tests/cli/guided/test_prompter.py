"""Tests for audiosteg/cli/guided/prompter.py."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from audiosteg.cli.guided import prompter as prompter_module
from audiosteg.cli.guided.prompter import GoBack, Prompter


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


def test_an_empty_path_without_a_default_is_refused(prompter: Callable[[str], Prompter]) -> None:
    with pytest.raises(ValueError, match="path is empty"):
        prompter("  ").file("Input")
