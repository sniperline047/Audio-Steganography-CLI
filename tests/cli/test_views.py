"""Tests for audiosteg/cli/views.py."""

import io
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL

from audiosteg import encode
from audiosteg.algorithms.lsb import LSB
from audiosteg.cli import views
from audiosteg.cli.accuracy import compare_messages
from audiosteg.cli.results import HideResult, RevealResult
from audiosteg.cli.views import View, clean_for_json, display_path, format_percentage

INJECTION = "[red]x[/red]:smile:[link=http://a]\x1b[2J\x1b]0;t\x07\x9b1m\u202egpj\u2066\r\n\u200b"
SHOWN = "[red]x[/red]:smile:[link=http://a]\\x1b[2J\\x1b]0;t\\x07\\x9b1m\\u202egpj\\u2066\\r\\n\\u200b"


@pytest.mark.parametrize(
    ("options", "boxes", "colours"),
    [
        ({}, True, True),
        ({"COLORTERM": "truecolor"}, True, True),
        ({"NO_COLOR": "1"}, True, False),
        ({"NO_COLOR": ""}, True, True),
        ({"TERM": "dumb"}, False, False),
        ({"TERM": "unknown"}, False, False),
        ({"TERM": "DUMB", "FORCE_COLOR": "1"}, False, False),
        ({"encoding": "ascii"}, False, False),
        ({"encoding": "cp1252"}, False, False),
        ({"terminals": ()}, False, False),
        ({"terminals": (), "FORCE_COLOR": "1", "COLORTERM": "truecolor"}, False, False),
        ({"terminals": ("stdin", "stderr")}, False, False),
    ],
)
@pytest.mark.parametrize("plain", [False, True])
def test_boxes_and_colours_only_where_they_can_be_shown(
    run: Any, make_wav: Callable[..., Path], options: dict[str, Any], boxes: bool, colours: bool, plain: bool
) -> None:
    make_wav()
    words = ["hide", "input.wav", "-m", "x", *(["--plain"] if plain else [])]
    result = run(*words, **{"terminals": ALL, **options})
    assert result.code == 0
    assert ("╭" in result.output) is (boxes and not plain)
    assert ("\x1b[32m" in result.output) is (colours and not plain)
    if not boxes or plain:
        assert "\x1b" not in result.output
        assert "Message hidden\nOutput: input.stego.wav\nAlgorithm: lsb\nEncrypted: no" in result.output


@pytest.mark.parametrize("options", [{}, {"terminals": ALL, "COLORTERM": "truecolor"}])
def test_nothing_from_outside_controls_the_terminal(run: Any, options: dict[str, Any]) -> None:
    for words in (["reveal", INJECTION], ["hide", INJECTION, "-m", "x"], ["verify", INJECTION, "-m", "x"]):
        result = run(*words, **options)
        assert result.code == 1
        assert SHOWN in result.text
        for character in "\x9b\u202e\u2066\u200b\x07\r":
            assert character not in result.seen
        assert "\x1b[2J" not in result.seen and "\x1b]" not in result.seen
        as_json = run(*words, "--json", **options)
        assert INJECTION in json.loads(as_json.output)["error"]["message"]
        assert as_json.output.isascii() and "\x1b" not in as_json.output


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow such names")
@pytest.mark.parametrize("columns", [40, 400])
def test_an_output_name_cannot_control_the_terminal(
    run: Any, make_wav: Callable[..., Path], columns: int
) -> None:
    name = INJECTION.replace("/", "|")
    words = ["hide", make_wav(), "-m", "x", "-o", name]
    result = run(*words, terminals=ALL, columns=columns, COLORTERM="truecolor")
    assert result.code == 0
    assert SHOWN.replace("/", "|") in result.text
    for text in ("\x9b", "\u202e", "\u2066", "\u200b", "\x07", "\x1b[2J", "\x1b]"):
        assert text not in result.seen
    again = run(*words, terminals=ALL, stdin=b"n\n")
    assert again.code == 1
    assert "\u202e" not in again.seen and "\x1b[2J" not in again.seen


@pytest.mark.parametrize("terminals", [(), ALL])
def test_a_long_path_is_never_cut_or_wrapped(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, terminals: tuple[str, ...]
) -> None:
    path = os.path.join("folder_" + "x" * 30, "y" * 50 + ".wav")
    result = run("hide", make_wav(), "-m", "x", "-o", path, terminals=terminals, columns=60)
    assert result.code == 0
    assert path in result.text


@pytest.mark.parametrize("spare", [0, -1])
def test_a_path_is_in_the_panel_only_if_it_fits_on_one_line(
    run: Any, make_wav: Callable[..., Path], spare: int
) -> None:
    name = "x" * 60 + ".wav"
    columns = len("Algorithm") + 2 + len(name) + 6 + spare
    result = run("hide", make_wav(), "-m", "x", "-o", name, terminals=ALL, columns=columns, NO_COLOR="1")
    assert (f"│ Output     {name}" in result.text) is (spare == 0)
    assert f"Output:\n{name}\n" in result.text if spare else f"Output:\n{name}" not in result.text
    assert max(map(len, result.output.splitlines())) <= columns


def test_a_path_is_shown_relative_only_inside_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = Path(os.path.realpath(tmp_path)) / "here"
    folder.mkdir()
    monkeypatch.chdir(folder)
    assert display_path(str(folder / "a" / "b.wav")) == os.path.join("a", "b.wav")
    for outside in (folder.parent / "b.wav", folder.parent / "here_too" / "b.wav"):
        assert display_path(str(outside)) == str(outside)


def test_a_path_on_another_drive_is_shown_as_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(paths: list[str]) -> str:
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(views.os.path, "commonpath", refuse)
    assert display_path("other") == "other"


@pytest.mark.parametrize(
    ("expected", "found", "shown"),
    [
        ("a" * 100_000, "a" * 99_999 + "b", "99.99%"),
        ("a" * 10_000, "a" * 9_999 + "b", "99.99%"),
        ("a" * 3, "aab", "66.67%"),
        ("a", "a", "100.00%"),
        ("a", "b", "0.00%"),
    ],
)
def test_only_an_exact_match_is_shown_as_100_percent(expected: str, found: str, shown: str) -> None:
    assert format_percentage(compare_messages(expected, found)) == shown


def test_json_is_valid_for_names_that_are_not_text() -> None:
    assert clean_for_json("a\udcff\x1b🎵") == "a\\udcff\x1b🎵"
    output = io.StringIO()
    View(output, io.StringIO(), as_json=True).show_hide(HideResult("in\udcff", "out\udcff", "lsb", True))
    assert json.loads(output.getvalue())["output"] == "out\\udcff"
    assert "ud" not in output.getvalue().replace("\\\\udcff", "")


def test_a_result_does_not_show_its_message() -> None:
    assert "PRIVATE" not in repr(RevealResult("a.wav", "lsb", False, False, "PRIVATE"))


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", ["hide", "reveal", "verify", "algorithms"])
@pytest.mark.parametrize("broken", ["stdout", "stderr"])
def test_a_reader_that_left(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, command: str, broken: str, as_json: bool
) -> None:
    encode(str(make_wav()), str(tmp_path / "plain.wav"), "x", LSB)
    words = {"hide": ["input.wav", "-m", "x"], "reveal": ["plain.wav"], "verify": ["plain.wav", "-m", "x"]}
    options = ["--json"] if as_json else []
    result = run(command, *words.get(command, []), *options, broken=(broken,))
    assert result.code == (1 if broken == "stdout" else 0)
    if broken == "stdout":
        assert result.errors.endswith("Error: The output was closed.\n")
    else:
        assert result.output


@pytest.mark.parametrize("stream", ALL)
def test_progress_is_for_a_person_only(run: Any, make_wav: Callable[..., Path], stream: str) -> None:
    make_wav()
    words = ["hide", "input.wav", "-m", "x", "--force"]
    assert ("Hiding the message..." in run(*words, terminals=(stream,)).errors) is (stream == "stderr")
    assert run(*words, "--json", terminals=ALL).errors == ""
