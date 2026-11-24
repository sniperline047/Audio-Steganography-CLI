"""Tests for audiosteg/cli/commands/inspect.py."""

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL

from audiosteg.cli.commands.hide import SAMPLE_FILE
from audiosteg.core import crypto


@pytest.mark.parametrize("words", [[], ["--json"], ["--plain"]])
def test_a_message_is_never_read_and_a_passphrase_is_never_asked(
    run: Any,
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    monkeypatch: pytest.MonkeyPatch,
    words: list[str],
) -> None:
    def refuse(*args: Any) -> bytes:
        raise AssertionError("a message was read")

    monkeypatch.setattr(crypto, "decrypt", refuse)
    monkeypatch.setattr(crypto, "check_available", refuse)
    make_wav("private.wav", embed(known_answer.container, 1))
    make_wav("plain.wav", embed(b"ASTG\x01\x00\x00\x00\x00\x06SECRETxxxx", 1))
    for name, said in (("private.wav", "encrypted"), ("plain.wav", "not encrypted")):
        result = run("inspect", name, *words, terminals=ALL)
        assert result.code == 0
        assert "SECRET" not in result.seen
        if not words or words == ["--plain"]:
            assert f"lsb, {said}, " in result.output


def test_the_sample_word(run: Any, tmp_path: Path) -> None:
    assert json.loads(run("inspect", "sample", "--json").output)["file"] == SAMPLE_FILE
    assert run("inspect", "./sample").code == 1
    shutil.copy(SAMPLE_FILE, tmp_path / "sample")
    assert json.loads(run("inspect", "./sample", "--json").output)["file"] == "./sample"
    assert os.listdir(tmp_path) == ["sample"]


@pytest.mark.parametrize(
    ("words", "code", "reason"),
    [
        ([], 2, "The following arguments are required: FILE."),
        ([""], 2, "A path is empty."),
        (["a.wav", "-p"], 2, "unknown option or an extra word"),
        (["missing.wav"], 1, "does not exist: missing.wav"),
        (["folder"], 1, "not a regular file"),
        (["text.wav"], 1, "not a valid PCM WAV file"),
    ],
)
def test_errors(run: Any, tmp_path: Path, words: list[str], code: int, reason: str) -> None:
    (tmp_path / "folder").mkdir()
    (tmp_path / "text.wav").write_text("text")
    result = run("inspect", *words)
    assert (result.code, result.output) == (code, "")
    assert reason in result.errors
