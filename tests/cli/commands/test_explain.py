"""Tests for audiosteg/cli/commands/explain.py."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL

from audiosteg.cli.commands.explain import one_character
from audiosteg.cli.commands.hide import SAMPLE_FILE
from audiosteg.cli.errors import UsageError

NAMES = "lsb, lsb_2, lsb_4, lsb_matching, lsb_parity, lsb_keyed"


@pytest.mark.parametrize(
    ("words", "reason"),
    [
        (["SECRET"], f"Unknown algorithm. Choose from: {NAMES}, basic, enhanced_flip, enhanced."),
        (["LSB"], "Unknown algorithm."),
        (["lsb", "lsb_2"], "unknown option or an extra word"),
        (["lsb", "--letter", ""], "--letter needs exactly one character. Some emoji are several characters."),
        (["lsb", "--letter", "SECRET"], "--letter needs exactly one character."),
        (["lsb", "--letter", "é"], "--letter needs exactly one character."),
        (["lsb", "--letter", "👍🏽"], "--letter needs exactly one character."),
        (["lsb", "--letter", "\udcff"], "--letter needs exactly one character."),
        (["lsb", "--file", ""], "A path is empty."),
        (["--letter", "x"], f"--letter needs one of these algorithms: {NAMES}."),
        (["basic", "--letter", "x"], f"--letter needs one of these algorithms: {NAMES}."),
        (["enhanced", "--file", "a.wav"], "--file needs one of these algorithms"),
        (["enhanced_flip", "--step"], "--step needs one of these algorithms"),
        (["--step"], "--step needs one of these algorithms"),
        (["lsb", "--step"], "--step needs a terminal."),
        (["lsb", "--step", "--json"], "--step cannot be used with --json."),
    ],
)
def test_options_that_make_no_sense(run: Any, words: list[str], reason: str) -> None:
    result = run("explain", *words)
    assert result.code == 2
    assert reason in result.errors + result.output
    assert "SECRET" not in result.errors + result.output


@pytest.mark.parametrize("missing", ALL)
def test_every_stream_must_be_a_terminal_for_a_pause(run: Any, missing: str) -> None:
    terminals = tuple(name for name in ALL if name != missing)
    result = run("explain", "lsb", "--step", terminals=terminals, stdin=b"\n" * 9)
    assert (result.code, "--step needs a terminal." in result.errors) == (2, True)


@pytest.mark.parametrize("letter", ["h", " ", "\\", "'", "-", "é", "🎵", "\0", "́", "", "￿"])
def test_any_character_that_can_be_stored_is_accepted(letter: str) -> None:
    assert one_character(letter) == letter


@pytest.mark.parametrize("letter", ["", "ab", "\ud800", "\udfff"])
def test_anything_else_is_refused(letter: str) -> None:
    with pytest.raises(UsageError):
        one_character(letter)


def test_the_steps_wait_for_enter(run: Any) -> None:
    result = run("explain", "lsb", "--step", terminals=ALL, stdin=b"\n\nxyz\n\n")
    assert result.code == 0
    assert result.errors == "Press Enter to continue." * 4
    parts = result.text.split("Press Enter to continue.")
    for part, title in zip(parts, ["Step 1", "Step 2", "Step 3", "Step 4", "Strengths"], strict=True):
        assert f"\n{title}" in part
    without = run("explain", "lsb", terminals=ALL)
    assert without.errors == "" and without.output == result.output


def test_the_end_of_input_and_ctrl_c_while_waiting(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    ended = run("explain", "lsb", "--step", terminals=ALL, stdin=b"\n")
    assert (ended.code, "Step 3" in ended.text, "The input ended" in ended.text) == (1, False, True)

    def interrupt(question: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("audiosteg.cli.commands.explain.ask_line", interrupt)
    stopped = run("explain", "lsb", "--step", terminals=ALL)
    assert (stopped.code, "Step 2" in stopped.text) == (130, False)
    assert stopped.text.endswith("Error: Interrupted.\n")


def test_samples_of_another_file(run: Any, make_samples: Callable[..., Path], tmp_path: Path) -> None:
    make_samples("song.wav", [0] * 5 + [100, 101, 102, 103] + [0] * 40, 8)
    result = json.loads(run("explain", "lsb_2", "--letter", "A", "--file", "song.wav", "--json").output)
    assert (result["file"], result["letter"], result["first_frame"]) == ("song.wav", "A", 8)
    values = [(row["hidden_bits"], row["value_before"], row["value_after"]) for row in result["samples"]]
    assert values == [("01", 103, 101), ("00", 0, 0), ("00", 0, 0), ("01", 0, 1)]
    shutil.copy(tmp_path / "song.wav", tmp_path / "sample")
    assert json.loads(run("explain", "lsb", "--file", "./sample", "--json").output)["file"] == "./sample"
    assert json.loads(run("explain", "lsb", "--file", "sample", "--json").output)["file"] == SAMPLE_FILE


@pytest.mark.parametrize(
    ("words", "reason"),
    [
        (["--file", "missing.wav"], "does not exist: missing.wav"),
        (["--file", "short.wav"], "The audio file is too short to hide one character."),
        (["--file", "input.wav", "--letter", "é"], "The audio file is too short"),
        (["--file", "cut.wav"], "The WAV file is shorter than its header says."),
    ],
)
def test_files_that_cannot_be_used(
    run: Any, make_samples: Callable[..., Path], tmp_path: Path, words: list[str], reason: str
) -> None:
    make_samples("short.wav", [9] * 7)
    whole = make_samples("input.wav", [9] * 8).read_bytes()
    (tmp_path / "cut.wav").write_bytes(whole[:-1])
    result = run("explain", "lsb", *words)
    assert (result.code, result.output) == (1, "")
    assert reason in result.errors
