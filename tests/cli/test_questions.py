"""Tests for audiosteg/cli/questions.py."""

import io

import pytest

from audiosteg.cli.questions import ask_line, ask_yes_no


def type_lines(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [("y", True), ("YES", True), (" yes ", True), ("n", False), ("No", False), ("", False), ("  ", False)],
)
def test_yes_no_answers(monkeypatch: pytest.MonkeyPatch, text: str, expected: bool) -> None:
    type_lines(monkeypatch, f"{text}\n")
    assert ask_yes_no("Sure?") is expected


def test_an_unclear_answer_is_asked_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    type_lines(monkeypatch, "maybe\nyess\n/some/path.wav\ny\n")
    assert ask_yes_no("Sure?") is True
    shown = capsys.readouterr()
    assert shown.out == ""
    assert shown.err.count("Sure? (y/N): ") == 4
    assert shown.err.count("Please answer y or n.") == 3


def test_a_line_is_read_as_it_is(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    type_lines(monkeypatch, " a message \t\nnext")
    assert ask_line("Message: ") == " a message \t"
    assert capsys.readouterr().err == "Message: "


def test_the_end_of_input_is_not_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    type_lines(monkeypatch, "")
    with pytest.raises(EOFError):
        ask_yes_no("Sure?")
