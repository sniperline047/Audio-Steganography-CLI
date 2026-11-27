"""Tests for audiosteg/cli/inspect_view.py."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL

from audiosteg.analysis.inspection import FoundMessage
from audiosteg.cli.inspect_view import describe_message

NONE = "Messages of lsb_keyed, of older versions, and of other tools cannot be detected.\n"
HEADER = "Only the header of the message was read, so damage further on is not detected."
LOOKS_LIKE_LSB = "A message hidden with lsb_matching looks the same as one hidden with lsb."


@pytest.mark.needs_signal
def test_every_line_about_a_file(run: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(frames=bytes(2 * 3 * 4440), channels=2, sample_width=3, frame_rate=44100)
    result = run("inspect", "input.wav")
    assert (result.code, result.errors) == (0, NONE)
    assert result.output.splitlines() == [
        "What this file holds",
        "File: input.wav",
        "Format: 24-bit PCM WAV",
        "Channels: 2 (stereo)",
        "Sample rate: 44,100 Hz",
        "Duration: 0.1007 s (4,440 frames)",
        "Room with lsb: 1,096 bytes, or 1,056 encrypted",
        "Room with lsb_2: 2,206 bytes, or 2,166 encrypted",
        "Room with lsb_4: 4,426 bytes, or 4,386 encrypted",
        "Room with lsb_matching: 1,096 bytes, or 1,056 encrypted",
        "Room with lsb_parity: 124 bytes, or 84 encrypted",
        "Room with lsb_keyed: 1,056 bytes, always encrypted",
        "Room with echo: none, the sound is too short",
        "Hidden message: none detected",
    ]


def test_a_file_in_the_current_folder_is_shown_by_its_name(run: Any, make_wav: Callable[..., Path]) -> None:
    path = os.path.realpath(make_wav())
    assert "\nFile: input.wav\n" in run("inspect", path).output


@pytest.mark.parametrize(("channels", "shown"), [(1, "1 (mono)"), (2, "2 (stereo)"), (3, "3"), (255, "255")])
def test_the_channels(run: Any, make_wav: Callable[..., Path], channels: int, shown: str) -> None:
    make_wav(frames=bytes(channels), channels=channels)
    output = run("inspect", "input.wav").output
    assert f"\nChannels: {shown}\n" in output
    assert "Duration: 0.0002 s (1 frame)\n" in output


@pytest.mark.parametrize(
    ("message", "shown"),
    [
        (FoundMessage("lsb", False, 1), "lsb, not encrypted, 1 byte"),
        (FoundMessage("lsb_2", True, 1234), "lsb_2, encrypted, 1,234 bytes"),
        (FoundMessage("lsb", False, 0), "lsb, not encrypted, 0 bytes"),
        (FoundMessage("lsb", problem="It is damaged."), "lsb, cannot be used. It is damaged."),
    ],
)
def test_a_message_in_one_line(message: FoundMessage, shown: str) -> None:
    assert describe_message(message) == shown


def test_a_message_without_size_is_a_mistake_of_the_program() -> None:
    with pytest.raises(ValueError, match="needs a size"):
        describe_message(FoundMessage("lsb", True))


def test_files_that_cannot_hide_anything(run: Any, make_wav: Callable[..., Path]) -> None:
    path = make_wav(frames=b"")
    output = run("inspect", "input.wav").output
    assert "Duration: 0.000 s (no samples)\nRoom with lsb: 0 bytes, or 0 encrypted\n" in output
    path = make_wav(frames=bytes(8000))
    path.write_bytes(path.read_bytes()[:-1])
    output = run("inspect", "input.wav").output
    assert "Duration: 0.9999 s (7,999 frames)\nRoom: none. The WAV file is shorter than its" in output
    assert "Room with" not in output


@pytest.mark.needs_signal
def test_json(run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes]) -> None:
    make_wav(frames=embed(b"ASTG\x01\x00\x00\x00\x00\x06SECRETxxxx", 2, 2), sample_width=2, frame_rate=16000)
    result = run("inspect", "input.wav", "--json", terminals=ALL)
    assert (result.code, result.errors) == (0, "")
    assert json.loads(result.output) == {
        "ok": True,
        "command": "inspect",
        "file": "input.wav",
        "bits": 16,
        "channels": 1,
        "sample_rate": 16000,
        "frames": 104,
        "seconds": 0.0065,
        "cannot_hide": None,
        "capacity": [
            {"algorithm": "lsb", "plain": 0, "encrypted": 0, "always_encrypted": False, "at_most": False},
            {"algorithm": "lsb_2", "plain": 12, "encrypted": 0, "always_encrypted": False, "at_most": False},
            {"algorithm": "lsb_4", "plain": 38, "encrypted": 0, "always_encrypted": False, "at_most": False},
            {
                "algorithm": "lsb_matching",
                "plain": 0,
                "encrypted": 0,
                "always_encrypted": False,
                "at_most": False,
            },
            {
                "algorithm": "lsb_parity",
                "plain": 0,
                "encrypted": 0,
                "always_encrypted": False,
                "at_most": False,
            },
            {
                "algorithm": "lsb_keyed",
                "plain": 0,
                "encrypted": 0,
                "always_encrypted": True,
                "at_most": False,
            },
            {"algorithm": "echo", "plain": 0, "encrypted": 0, "always_encrypted": False, "at_most": True},
        ],
        "messages": [{"algorithm": "lsb_2", "encrypted": False, "size": 6, "problem": None}],
        "not_checked": [],
    }


def test_room_that_is_no_promise(run: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(frames=bytes(2 * 2 * 2583 * 1024), channels=2, sample_width=2, frame_rate=44100)
    output = run("inspect", "input.wav").output
    assert "\nRoom with echo: at most 144 bytes, or 104 encrypted. Not every sound works.\n" in output


def test_what_cannot_be_looked_for_without_numpy_is_said(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes], no_numpy: None
) -> None:
    missing = (
        "Messages of echo cannot be detected here, because NumPy is missing. "
        'To install it, run: pip install ".[signal]"\n'
    )
    make_wav()
    assert run("inspect", "input.wav").errors == f"{NONE.strip()} {missing}"
    assert json.loads(run("inspect", "input.wav", "--json").output)["not_checked"] == ["echo"]
    make_wav(frames=embed(b"ASTG\x01\x00\x00\x00\x00\x00abcd", 2))
    assert run("inspect", "input.wav").errors == f"{HEADER}\n"


def test_json_of_a_problem_and_a_truncated_file(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    path = make_wav(frames=embed(b"ASTG\x09\x00\x00\x00\x00\x06", 1))
    path.write_bytes(path.read_bytes()[:-1])
    result = json.loads(run("inspect", "input.wav", "--json").output)
    assert (result["cannot_hide"], result["capacity"]) == (
        "The WAV file is shorter than its header says.",
        [],
    )
    (message,) = result["messages"]
    assert (message["algorithm"], message["encrypted"], message["size"]) == ("lsb", None, None)
    assert "version 9" in message["problem"]
    shown = run("inspect", "input.wav")
    assert "Hidden message: lsb, cannot be used. The hidden message uses format version 9" in shown.output
    assert shown.errors == f"{HEADER} {LOOKS_LIKE_LSB}\n"


def test_only_a_message_that_could_be_of_two_algorithms_is_called_so(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    for size, note in ((1, f"{HEADER} {LOOKS_LIKE_LSB}\n"), (2, f"{HEADER}\n"), (4, f"{HEADER}\n")):
        make_wav(frames=embed(b"ASTG\x01\x00\x00\x00\x00\x00abcd", size))
        assert run("inspect", "input.wav").errors == note


@pytest.mark.parametrize(("columns", "boxes"), [(80, True), (30, True), (12, True), (80, False)])
def test_a_panel_fits_in_a_narrow_terminal(
    run: Any, make_wav: Callable[..., Path], columns: int, boxes: bool
) -> None:
    make_wav()
    words = [] if boxes else ["--plain"]
    result = run("inspect", "input.wav", *words, terminals=ALL, columns=columns, NO_COLOR="1")
    assert ("╭" in result.output) is boxes
    if boxes:
        assert max(map(len, result.output.splitlines())) <= columns
    ascii_only = run("inspect", "input.wav", terminals=ALL, encoding="ascii")
    assert ascii_only.output.isascii() and "\nChannels: 1 (mono)\n" in ascii_only.output


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow such names")
@pytest.mark.parametrize("terminals", [(), ALL])
def test_a_name_cannot_control_the_terminal(
    run: Any, make_wav: Callable[..., Path], terminals: tuple[str, ...]
) -> None:
    name = "x\x1b[2J\x1b]0;t\x07‮\n[red].wav"
    make_wav(name)
    result = run("inspect", name, terminals=terminals)
    assert "x\\x1b[2J\\x1b]0;t\\x07\\u202e\\n[red].wav" in result.text
    for unsafe in ("\x1b[2J", "\x1b]", "\x07", "‮"):
        assert unsafe not in result.seen
    assert json.loads(run("inspect", name, "--json").output)["file"] == name
