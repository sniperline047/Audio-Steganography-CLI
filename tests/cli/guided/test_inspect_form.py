"""Tests for audiosteg/cli/guided/inspect_form.py."""

import json
import os
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
INSPECT = ("What would you like to do?", DOWN * 3 + ENTER)
FILE = "WAV file (sample means the included tune) [sample]:"
SAME = "The same as a command: "


def test_the_sample_is_offered(guide: Any) -> None:
    result = guide(INSPECT, (FILE, ENTER))
    assert result.code == 0
    assert "94,400 frames" in result.text
    assert f"{SAME}audiosteg inspect sample\n" in result.text


def test_a_file_can_be_typed_after_back(guide: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(frames=bytes(8))
    result = guide(INSPECT, (FILE, ESCAPE), INSPECT, (FILE, f"  input.wav {ENTER}"))
    assert result.code == 0
    assert result.text.count(SAME) == 1
    assert f"{SAME}audiosteg inspect input.wav\n" in result.text


@pytest.mark.parametrize(("key", "code"), [(CTRL_C, 130), (CTRL_D, 1)])
def test_leaving(guide: Any, key: str, code: int) -> None:
    assert guide(INSPECT, (FILE, key), leave=False).code == code


@pytest.mark.skipif(os.name == "nt", reason="Windows shows fewer names")
@pytest.mark.parametrize("name", ["-p.wav", "--json", "my song's.wav", "$(x).wav"])
def test_the_command_really_does_the_same(
    guide: Any, run: Any, make_wav: Callable[..., Path], name: str
) -> None:
    make_wav(name, bytes(8))
    result = guide(INSPECT, (FILE, f"{name}{ENTER}"))
    command = result.text.split(SAME)[1].splitlines()[0]
    again = run(*shlex.split(command)[1:], "--json")
    assert json.loads(again.output)["frames"] == 8


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow such names")
def test_a_name_with_unusual_characters(guide: Any, make_wav: Callable[..., Path]) -> None:
    make_wav("x‮.wav", bytes(8))
    result = guide(INSPECT, (FILE, f"x‮.wav{ENTER}"))
    assert "The same command cannot be shown: a file name or another answer has unusual" in result.text
    assert "x\\u202e.wav" in result.text
