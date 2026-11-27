"""Tests for audiosteg/cli/guided/explain_form.py."""

import os
import shlex
from typing import Any

import pytest
from conftest import ALL, marked

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.core.algorithm import Algorithm

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
EXPLAIN = ("What would you like to do?", DOWN * 5 + ENTER)
ALGORITHM = "Which algorithm?"
LETTER = "Character to hide [h]:"
SAME = "The same as a command: "


CHOICES = [
    pytest.param(number, *marked(key).values, marks=marked(key).marks if key == "echo" else ())
    for number, key in enumerate(ALGORITHMS)
]


@pytest.mark.parametrize(("number", "key"), CHOICES)
@pytest.mark.usefixtures("first_choices")
def test_every_algorithm(guide: Any, run: Any, number: int, key: str) -> None:
    result = guide(EXPLAIN, (ALGORITHM, DOWN * number + ENTER), (LETTER, ENTER), NO_COLOR="1")
    assert result.code == 0
    assert f"{SAME}audiosteg explain {key}\n" in result.text
    assert run("explain", key, terminals=ALL, NO_COLOR="1").output in result.text


def test_an_algorithm_without_its_library_is_explained(guide: Any, no_numpy: None) -> None:
    number = list(ALGORITHMS).index("echo")
    result = guide(EXPLAIN, (ALGORITHM, DOWN * number + ENTER), (ALGORITHM, CTRL_C), leave=False)
    assert "echo (needs NumPy): " in result.text
    assert "Error: This algorithm needs an optional library (NumPy)." in result.text
    assert "lsb_keyed: " in result.text


@pytest.mark.needs_signal
def test_every_algorithm_is_named_in_order(guide: Any) -> None:
    menu = guide(EXPLAIN, (ALGORITHM, ESCAPE)).text
    names = [f"{key}: {value.explanation}" for key, value in ALGORITHMS.items()]
    positions = [menu.index(name) for name in names]
    assert positions == sorted(positions)


@pytest.mark.skipif(os.name == "nt", reason="Windows shows fewer characters")
@pytest.mark.parametrize("letter", ["A", "é", "🎵", "'", "\\", " ", "-", "$", "́"])
def test_the_command_really_does_the_same(guide: Any, run: Any, letter: str) -> None:
    result = guide(EXPLAIN, (ALGORITHM, ENTER), (LETTER, f"{letter}{ENTER}"), NO_COLOR="1")
    assert result.code == 0
    words = shlex.split(result.text.split(SAME)[1].splitlines()[0])
    assert words == ["audiosteg", "explain", "lsb", "--letter", letter]
    assert run(*words[1:]).output in result.text


def test_a_character_that_cannot_be_shown(guide: Any) -> None:
    result = guide(EXPLAIN, (ALGORITHM, ENTER), (LETTER, f"‮{ENTER}"))
    assert "The character '\\u202e' is 3 bytes" in result.text
    assert "another answer has unusual characters" in result.text


def test_a_wrong_answer_is_asked_again(guide: Any) -> None:
    result = guide(
        EXPLAIN, (ALGORITHM, ENTER), (LETTER, f"ab{ENTER}"), (LETTER, f"é{ENTER}"), (LETTER, f"b{ENTER}")
    )
    assert result.code == 0
    assert result.text.count("Error: Type exactly one character. Some emoji are several characters.") == 2
    assert "--letter" not in result.text.split(SAME)[0]
    assert f"{SAME}audiosteg explain lsb --letter b\n" in result.text


def test_back_forgets_the_character(guide: Any) -> None:
    result = guide(
        EXPLAIN,
        (ALGORITHM, ENTER),
        (LETTER, ESCAPE),
        (ALGORITHM, DOWN + ENTER),
        (LETTER, ENTER),
    )
    assert result.code == 0
    assert [line for line in result.text.splitlines() if SAME in line] == [f"{SAME}audiosteg explain lsb_2"]


@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
@pytest.mark.parametrize("before", [[], [(ALGORITHM, ENTER)]])
def test_leaving(guide: Any, key: str, code: int, before: list[Any]) -> None:
    question = LETTER if before else ALGORITHM
    assert guide(EXPLAIN, *before, (question, key), leave=False).code == code


def test_a_new_algorithm_is_offered(guide: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    new = Algorithm("New", 1, lambda byte, bits: byte & 254 | bits[0], lambda byte: (byte & 1,), "A new one.")
    monkeypatch.setitem(ALGORITHMS, "new_one", new)
    result = guide(EXPLAIN, (ALGORITHM, DOWN * (len(ALGORITHMS) - 1) + ENTER), (LETTER, ENTER))
    assert "new_one: A new one." in result.text
    assert f"{SAME}audiosteg explain new_one\n" in result.text
