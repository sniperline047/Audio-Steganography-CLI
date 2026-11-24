"""Tests for cli/helpers.py."""

from collections.abc import Callable

import pytest

from cli.helpers import ask_yes_no, get_file_path, get_user_choice

Answer = Callable[..., list[str]]


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch) -> Answer:
    """Return a function that sets the next answers and collects the prompts."""

    def set_answers(*answers: str) -> list[str]:
        remaining = list(answers)
        prompts: list[str] = []

        def fake_input(prompt: str = "") -> str:
            prompts.append(prompt)
            return remaining.pop(0)

        monkeypatch.setattr("builtins.input", fake_input)
        return prompts

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


@pytest.mark.parametrize("default", [True, False])
@pytest.mark.parametrize(
    ("text", "expected"),
    [("y", True), ("YES", True), (" yes ", True), ("n", False), ("No", False), ("", None), ("  ", None)],
)
def test_yes_no_answers(answer: Answer, text: str, expected: bool | None, default: bool) -> None:
    answer(text)
    assert ask_yes_no("Sure?", default) is (default if expected is None else expected)


def test_an_unclear_answer_is_asked_again(answer: Answer) -> None:
    prompts = answer("maybe", "yess", "/some/path.wav", "n")
    assert ask_yes_no("Sure?", default=True) is False
    assert len(prompts) == 4


def test_the_hint_shows_the_default(answer: Answer) -> None:
    prompts = answer("", "")
    ask_yes_no("Sure?", default=True)
    ask_yes_no("Sure?", default=False)
    assert "Y/n" in prompts[0] and "y/N" in prompts[1]


@pytest.mark.parametrize(
    ("answers", "path"),
    [
        ([""], "default.wav"),
        (["yes"], "default.wav"),
        (["n", "other.wav"], "other.wav"),
        (["no", "my folder/a file.wav"], "my folder/a file.wav"),
        (["n", ""], "default.wav"),
        (["n", "   "], "default.wav"),
    ],
)
def test_file_path_answers(answer: Answer, answers: list[str], path: str) -> None:
    answer(*answers)
    assert get_file_path("input audio file", "default.wav") == path


def test_an_unsafe_default_path_is_shown_escaped_but_used_as_it_is(answer: Answer) -> None:
    prompts = answer("")
    assert get_file_path("input audio file", "a\x1b[2J\u202e.wav") == "a\x1b[2J\u202e.wav"
    assert "\x1b" not in prompts[0] and "\\x1b[2J\\u202e.wav" in prompts[0]
