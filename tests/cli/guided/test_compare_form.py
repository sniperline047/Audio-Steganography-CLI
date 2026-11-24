"""Tests for audiosteg/cli/guided/compare_form.py."""

import os
import shlex
from typing import Any

import pytest

from audiosteg.cli import player
from audiosteg.cli.guided import compare_form

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
COMPARE = ("What would you like to do?", DOWN * 4 + ENTER)
ORIGINAL = "Original (sample means the included tune) [sample]:"
COPY = "Copy with the hidden message:"
LEVEL = "How much do you want to see?"
NAMES = "Names from snr, psnr, changes, where, waveform, with commas [snr,changes]:"
LISTEN = "Listen to them? Ctrl-C stops the sound and leaves."
SAME = "The same as a command: "
FILES = [(ORIGINAL, f"a.wav{ENTER}"), (COPY, f"b.wav{ENTER}")]
SIMPLE, DETAILED, CHOOSE = ((LEVEL, DOWN * number + ENTER) for number in range(3))


@pytest.fixture(autouse=True)
def pair(make_pair: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Two files with one difference, on a system without a player."""
    monkeypatch.setattr(compare_form, "can_play", lambda: False)
    files: tuple[str, str] = make_pair([10, 20, 30], [10, 21, 30])
    return files


def commands(text: str) -> list[str]:
    return [line.removeprefix(f"{SAME}audiosteg ") for line in text.splitlines() if line.startswith(SAME)]


@pytest.mark.parametrize(
    ("answers", "options"),
    [
        ([SIMPLE], ""),
        ([DETAILED], " --details"),
        ([CHOOSE, (NAMES, ENTER)], " --show snr --show changes"),
        ([CHOOSE, (NAMES, f" where , psnr,where{ENTER}")], " --show psnr --show where"),
        ([CHOOSE, (NAMES, f"waveform{ENTER}")], " --show waveform"),
    ],
)
def test_what_is_shown_is_what_the_command_shows(
    guide: Any, run: Any, answers: list[Any], options: str
) -> None:
    result = guide(COMPARE, *FILES, *answers, NO_COLOR="1")
    assert result.code == 0
    assert commands(result.text) == [f"compare a.wav b.wav{options}"]
    words = shlex.split(commands(result.text)[0])
    again = run(*words, terminals=("stdin", "stdout", "stderr"), NO_COLOR="1")
    assert again.output.strip() in result.text


def test_wrong_names_are_asked_again(guide: Any) -> None:
    wrong = [(NAMES, f"{text}{ENTER}") for text in ("loud", "snr,,psnr", "  ")]
    result = guide(COMPARE, *FILES, CHOOSE, *wrong, (NAMES, f"psnr{ENTER}"))
    assert result.code == 0
    assert result.text.count("Error: Choose from: snr, psnr, changes, where, waveform.\n") == 3
    assert commands(result.text) == ["compare a.wav b.wav --show psnr"]


def test_files_that_cannot_be_compared_are_asked_again(guide: Any, make_samples: Any) -> None:
    make_samples("short.wav", [1])
    result = guide(
        COMPARE,
        (ORIGINAL, f"a.wav{ENTER}"),
        (COPY, ENTER),
        (COPY, f"missing.wav{ENTER}"),
        (COPY, f"short.wav{ENTER}"),
        (COPY, f"b.wav{ENTER}"),
        SIMPLE,
    )
    assert result.code == 0
    for text in ("The path is empty.", "does not exist: missing.wav", "The lengths differ: 3 and 1 frames."):
        assert f"Error: {text}" in result.text or text in result.text
    assert commands(result.text) == ["compare a.wav b.wav"]


def test_back_from_every_question(guide: Any) -> None:
    result = guide(
        COMPARE,
        (ORIGINAL, ESCAPE),
        COMPARE,
        (ORIGINAL, f"b.wav{ENTER}"),
        (COPY, ESCAPE),
        (ORIGINAL, f"a.wav{ENTER}"),
        (COPY, f"a.wav{ENTER}"),
        (LEVEL, DOWN * 3 + ENTER),
        (COPY, f"b.wav{ENTER}"),
        CHOOSE,
        (NAMES, ESCAPE),
        (LEVEL, ESCAPE),
        (COPY, f"b.wav{ENTER}"),
        CHOOSE,
        (NAMES, f"loud{ENTER}"),
        (NAMES, ESCAPE),
        SIMPLE,
    )
    assert result.code == 0
    assert commands(result.text) == ["compare a.wav b.wav"]
    assert "Sounds the same?" in result.text


def test_chosen_names_are_forgotten_when_everything_is_wanted(guide: Any) -> None:
    result = guide(COMPARE, *FILES, CHOOSE, (NAMES, ESCAPE), DETAILED)
    assert commands(result.text) == ["compare a.wav b.wav --details"]
    assert "PSNR: " in result.text


@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
@pytest.mark.parametrize("asked", range(4))
def test_leaving(guide: Any, key: str, code: int, asked: int) -> None:
    questions = [*FILES, CHOOSE, (NAMES, ENTER)]
    assert guide(COMPARE, *questions[:asked], (questions[asked][0], key), leave=False).code == code


@pytest.fixture
def listening(sounds: list[Any], monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The same, on a system with a player that plays nothing."""
    monkeypatch.setattr(compare_form, "can_play", lambda: True)
    return sounds


@pytest.mark.parametrize(
    ("answer", "played", "option"),
    [
        (ENTER, 0, None),
        (DOWN + ENTER, 3, "--play"),
        (DOWN * 2 + ENTER, 1, "--play original"),
        (DOWN * 3 + ENTER, 1, "--play encoded"),
        (DOWN * 4 + ENTER, 1, "--play difference"),
    ],
)
def test_listening(guide: Any, listening: list[Any], answer: str, played: int, option: str | None) -> None:
    result = guide(COMPARE, *FILES, SIMPLE, (LISTEN, answer))
    assert result.code == 0
    assert len(listening) == played
    expected = ["compare a.wav b.wav"]
    assert commands(result.text) == expected + ([f"{expected[0]} {option}"] if option else [])
    assert result.text.index("Sounds the same?") < result.text.index(LISTEN)


@pytest.mark.parametrize("back", [DOWN * 5 + ENTER, ESCAPE])
def test_back_instead_of_listening_returns_to_the_question_before(
    guide: Any, listening: list[Any], back: str
) -> None:
    result = guide(
        COMPARE,
        *FILES,
        CHOOSE,
        (NAMES, f"snr{ENTER}"),
        (LISTEN, back),
        (NAMES, ESCAPE),
        DETAILED,
        (LISTEN, back),
        (LEVEL, ESCAPE),
        (COPY, ESCAPE),
        (ORIGINAL, ESCAPE),
    )
    assert (result.code, listening) == (0, [])
    assert commands(result.text) == ["compare a.wav b.wav --show snr", "compare a.wav b.wav --details"]
    assert "add --details" not in result.text


def test_a_later_comparison_does_not_play(guide: Any, listening: list[Any]) -> None:
    result = guide(
        COMPARE, *FILES, SIMPLE, (LISTEN, DOWN * 2 + ENTER), COMPARE, *FILES, DETAILED, (LISTEN, ENTER)
    )
    assert len(listening) == 1
    assert commands(result.text)[-1] == "compare a.wav b.wav --details"


def test_a_player_that_fails_returns_to_the_menu(
    guide: Any, listening: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(path: str, seconds: float) -> None:
        raise player.PlayerError(player.FAILED)

    monkeypatch.setattr(player, "play", fail)
    result = guide(COMPARE, *FILES, SIMPLE, (LISTEN, DOWN + ENTER))
    assert result.code == 1
    assert "Error: The audio player failed." in result.text


@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
def test_leaving_instead_of_listening(guide: Any, listening: list[Any], key: str, code: int) -> None:
    result = guide(COMPARE, *FILES, SIMPLE, (LISTEN, key), leave=False)
    assert (result.code, listening) == (code, [])


@pytest.mark.skipif(os.name == "nt", reason="Windows shows fewer names")
def test_names_like_options_and_sounds(guide: Any, run: Any, make_samples: Any, listening: list[Any]) -> None:
    make_samples("--json", [1])
    make_samples("original", [2])
    answers = [(ORIGINAL, f"--json{ENTER}"), (COPY, f"original{ENTER}"), SIMPLE, (LISTEN, DOWN * 4 + ENTER)]
    result = guide(COMPARE, *answers)
    assert commands(result.text)[-1] == "compare ./--json original --play difference"
    assert run(*shlex.split(commands(result.text)[-1])).code == 0
    assert len(listening) == 2 and listening[0] == listening[1]
