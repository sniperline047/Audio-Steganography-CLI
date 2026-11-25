"""Tests for audiosteg/cli/guided/explain_form.py."""

import os
import shlex
from typing import Any

import pytest

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.core.algorithm import Algorithm

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
EXPLAIN = ("What would you like to do?", DOWN * 5 + ENTER)
ALGORITHM = "Which algorithm?"
LETTER = "Character to hide [h]:"
SAME = "The same as a command: "


@pytest.mark.parametrize(("number", "key"), list(enumerate([*ALGORITHMS, *LEGACY_ALGORITHMS])))
def test_every_algorithm(guide: Any, run: Any, number: int, key: str) -> None:
    letter = [(LETTER, ENTER)] if key in ALGORITHMS else []
    result = guide(EXPLAIN, (ALGORITHM, DOWN * number + ENTER), *letter, NO_COLOR="1")
    assert result.code == 0
    assert f"{SAME}audiosteg explain {key}\n" in result.text
    assert run("explain", key).output in result.text


def test_every_algorithm_is_named_old_ones_last(guide: Any) -> None:
    menu = guide(EXPLAIN, (ALGORITHM, ESCAPE)).text
    names = [f"{key}: {value.explanation}" for key, value in ALGORITHMS.items()]
    names += [f"{key} (old files only): {value.explanation}" for key, value in LEGACY_ALGORITHMS.items()]
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
        (ALGORITHM, DOWN * 2 + ENTER),
        EXPLAIN,
        (ALGORITHM, ENTER),
        (LETTER, ESCAPE),
        (ALGORITHM, DOWN * 5 + ENTER),
    )
    assert result.code == 0
    assert [line for line in result.text.splitlines() if SAME in line] == [f"{SAME}audiosteg explain basic"]


@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
@pytest.mark.parametrize("before", [[], [(ALGORITHM, ENTER)]])
def test_leaving(guide: Any, key: str, code: int, before: list[Any]) -> None:
    question = LETTER if before else ALGORITHM
    assert guide(EXPLAIN, *before, (question, key), leave=False).code == code


def test_a_new_algorithm_is_offered(guide: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    new = Algorithm("New", 1, lambda byte, bits: byte & 254 | bits[0], lambda byte: (byte & 1,), "A new one.")
    monkeypatch.setitem(ALGORITHMS, "new_one", new)
    result = guide(EXPLAIN, (ALGORITHM, DOWN * 2 + ENTER), (LETTER, ENTER))
    assert "new_one: A new one." in result.text
    assert f"{SAME}audiosteg explain new_one\n" in result.text
