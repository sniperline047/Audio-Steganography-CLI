"""Tests for audiosteg/cli/parser.py."""

import json
import re
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL

from audiosteg import decode, encode
from audiosteg.algorithms.lsb import LSB
from audiosteg.cli.parser import COMMANDS, follows_play, join_play_value

PASSPHRASE_HELP = "-p takes no value: it asks for the passphrase."


@pytest.mark.parametrize(
    ("words", "reason"),
    [
        (["hide", "in.wav", "-m", "x", "-p", "TOP_SECRET"], PASSPHRASE_HELP),
        (["hide", "in.wav", "-p=TOP_SECRET"], PASSPHRASE_HELP),
        (["hide", "in.wav", "-pTOP_SECRET"], PASSPHRASE_HELP),
        (["reveal", "-po", "SECRET"], PASSPHRASE_HELP),
        (["hide", "in.wav", "--passphrase=TOP_SECRET"], "A value was given to an option that takes none."),
        (["hide", "in.wav", "--force=SECRET"], "A value was given to an option that takes none."),
        (["hide", "in.wav", "-a", "TOP_SECRET"], "Unknown algorithm. Choose from: lsb, lsb_2."),
        (["reveal", "in.wav", "--legacy", "TOP_SECRET"], "Unknown old algorithm. Choose from: basic,"),
        (["reveal", "in.wav", "--TOP_SECRET"], "unknown option or an extra word"),
        (["reveal", "in.wav", "--passphrase_fil=SECRET"], "Did you mean --passphrase_file?"),
        (["reveal", "in.wav", "--legcy", "SECRET"], "Did you mean --legacy?"),
        (["-p", "TOP_SECRET"], ""),
        (
            ["TOP_SECRET"],
            "Unknown command. Choose from: hide, reveal, verify, inspect, compare, explain, algorithms.",
        ),
        (["invalid SECRET, not allowed with argument"], "Unknown command."),
        (["hide"], "The following arguments are required: INPUT."),
        (["hide", "in.wav", "-m"], "--message needs a value. If it starts with a dash, write --message="),
        (["hide", "in.wav", "-m", "-SECRET"], "--message needs a value."),
        (["hide", "in.wav", "-m", "x", "--message_file", "TOP_SECRET"], "not allowed with argument"),
        (["reveal", "in.wav", "-a", "lsb", "--legacy", "basic"], "not allowed with argument"),
        (["reveal", "in.wav", "-p", "--passphrase_file", "SECRET"], "not allowed with argument"),
        (["--TOP_SECRET"], "unknown option or an extra word"),
        (["--versio"], "Did you mean --version?"),
        (["reveal", "in.wav", "--mess", "SECRET"], "unknown option or an extra word"),
        (["hide", "in.wav", "--mess", "SECRET"], ""),
        (["algorithms", "SECRET"], "unknown option or an extra word"),
        (["reveal", "in.wav", "--force"], "unknown option or an extra word"),
    ],
)
def test_wrong_usage_is_explained_without_any_value(run: Any, words: list[str], reason: str) -> None:
    result = run(*words)
    assert (result.code, result.output) == (2, "")
    assert result.errors.startswith("Error: ")
    assert reason in result.errors
    as_json = run(*words, "--json")
    error = json.loads(as_json.output)["error"]
    assert (as_json.code, error["type"], error["exit_code"]) == (2, "usage", 2)
    for shown in (result.errors, as_json.output, as_json.errors):
        assert "SECRET" not in shown


def test_a_value_that_looks_like_an_option_is_a_value(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav(name="--json")
    for words, message in [
        (["--message=-p secret", "-o", "1.wav", "--", "--json"], "-p secret"),
        (["--message=--json", "-o", "2.wav", "./--json"], "--json"),
    ]:
        result = run("hide", *words)
        assert (result.code, result.output.startswith("Message hidden")) == (0, True)
        output = tmp_path / words[words.index("-o") + 1]
        assert decode(str(output)) == message


def test_a_name_after_two_dashes_is_not_an_option(run: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(name="-p.wav")
    assert run("hide", "-m", "x", "-o", "out.wav", "--", "-p.wav").code == 0


@pytest.mark.parametrize("position", [0, 1, 3])
def test_output_options_may_be_anywhere(run: Any, make_wav: Callable[..., Path], position: int) -> None:
    make_wav(frames=b"\xff" * 400)
    words = ["reveal", "input.wav", "-a", "lsb"]
    words.insert(position if position != 3 else 4, "--json")
    assert json.loads(run(*words).output)["command"] == "reveal"


@pytest.mark.parametrize("command", [None, *COMMANDS])
def test_help_is_text_everywhere(run: Any, command: str | None) -> None:
    words = [command] if command else []
    result = run(*words, "--help", encoding="ascii", terminals=ALL, FORCE_COLOR="1", columns=80)
    assert (result.code, result.errors) == (0, "")
    assert "\nexamples:\n" in result.output
    assert result.output.isascii() and "\x1b" not in result.output
    assert run(*words, "--help", "--json").output.startswith("usage: ")


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
@pytest.mark.parametrize("command", [None, *COMMANDS])
def test_the_examples_in_the_help_work(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, command: str | None
) -> None:
    help_text = run(*([command] if command else []), "--help").output
    lines = re.search("^examples:\n((?:  .+\n)+)", help_text, re.MULTILINE)
    assert lines is not None
    for line in lines[1].splitlines():
        for name in ("song.wav", "old.wav"):
            make_wav(name=name, frames=bytes(4000))
        (tmp_path / "letter.txt").write_text("Hello")
        (tmp_path / "key.txt").write_text("sesame")
        key = {"passphrase": "sesame"} if "--passphrase_file" in line else {}
        for name in ("song.stego.wav", "sample.stego.wav"):
            (tmp_path / name).unlink(missing_ok=True)
            if command != "hide" and "audiosteg hide" not in line:
                encode(str(tmp_path / "song.wav"), str(tmp_path / name), "Hello", LSB, **key)
        example = re.split(" {2,}| > ", line.strip())[0]
        piped = example.startswith("printf")
        words = shlex.split(example.split(" | ")[-1])
        if words == ["audiosteg"]:
            continue
        assert words[0] == "audiosteg"
        asks = "-p" in words
        result = run(
            *words[1:],
            stdin=b"Hello\n" if not piped else b"Hello",
            hidden=("sesame", "sesame") if asks else (),
            terminals=ALL if asks else (),
        )
        assert result.code == 0, line


@pytest.mark.parametrize("words", [[], *([name] for name in COMMANDS)])
def test_the_help_fits_in_80_columns(run: Any, words: list[str]) -> None:
    lines = run(*words, "--help", COLUMNS="80").output.splitlines()
    assert max(map(len, lines)) <= 80


@pytest.mark.parametrize(
    ("words", "joined"),
    [
        ([], []),
        (["compare", "a", "b"], ["compare", "a", "b"]),
        (["--play"], ["--play=\0"]),
        (["--play", "original"], ["--play=original"]),
        (["--play", "./original"], ["--play=\0", "./original"]),
        (["--play", "--play", "encoded"], ["--play=\0", "--play=encoded"]),
        (["--play", "encoded", "difference"], ["--play=encoded", "difference"]),
        (["original", "--play"], ["original", "--play=\0"]),
        (["--play", "--", "original"], ["--play=\0", "--", "original"]),
        (["a", "--", "--play", "original"], ["a", "--", "--play", "original"]),
        (["--play=original", "encoded"], ["--play=original", "encoded"]),
    ],
)
def test_play_takes_only_a_sound(words: list[str], joined: list[str]) -> None:
    assert join_play_value(words) == joined


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        (["--play", "SECRET"], True),
        (["--play", "original"], False),
        (["--play", "--plain"], False),
        (["--play"], False),
        (["SECRET", "a"], False),
    ],
)
def test_a_misspelled_sound(words: list[str], expected: bool) -> None:
    assert follows_play(words) is expected


def test_a_word_after_play_is_never_repeated(run: Any) -> None:
    result = run("compare", "a", "b", "--play", "SECRET")
    assert result.code == 2
    assert "There is an extra word. --play can have one of these values: original, encoded" in result.errors
    assert "SECRET" not in result.errors
    for words in (["compare", "a", "b", "c"], ["compare", "a", "--play", "b", "c", "--", "d"]):
        assert run(*words).code == 2
    assert "--play" not in run("inspect", "a", "--play", "SECRET").errors


def test_an_option_of_another_command_is_not_a_misspelling(run: Any) -> None:
    for words in (
        ["hide", "a.wav", "--play"],
        ["reveal", "a.wav", "--letter=x"],
        ["inspect", "a", "--from", "1"],
    ):
        assert "Did you mean" not in run(*words).errors
