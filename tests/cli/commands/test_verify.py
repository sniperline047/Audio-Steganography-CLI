"""Tests for audiosteg/cli/commands/verify.py."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg import encode
from audiosteg.algorithms.registry import ALGORITHMS


@pytest.mark.parametrize("key", ALGORITHMS)
def test_a_match_changes_nothing(run: Any, make_wav: Callable[..., Path], tmp_path: Path, key: str) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden 🎵", ALGORITHMS[key])
    content = output.read_bytes()
    output.chmod(0o444)
    modified = output.stat().st_mtime_ns
    try:
        result = run("verify", output, "-m", "hidden 🎵", cwd=tmp_path)
    finally:
        output.chmod(0o644)
    assert (result.code, result.errors) == (0, "")
    assert "Exact match: yes\nAccuracy: 100.00%\n" in result.output
    assert "This message was not encrypted" in result.output
    assert output.read_bytes() == content
    assert output.stat().st_mtime_ns == modified
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "output.wav"]


def test_a_difference_is_reported_and_fails(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden", ALGORITHMS["lsb"])
    result = run("verify", output, stdin=b"hidXen??")
    assert result.code == 1
    assert "Exact match: no\nAccuracy: 62.50%\nExpected length: 8\nFound length: 6\n" in result.output
    as_json = run("verify", output, "-m", "hidXen??", "--json")
    assert as_json.code == 1
    assert json.loads(as_json.output) == {
        "ok": True,
        "command": "verify",
        "file": str(output),
        "algorithm": "lsb",
        "legacy": False,
        "encrypted": False,
        "exact_match": False,
        "percentage": 62.5,
        "expected_length": 8,
        "found_length": 6,
    }


@pytest.mark.needs_crypto
def test_an_encrypted_message_is_compared(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes], known_answer: Any, tmp_path: Path
) -> None:
    path, key_file = make_wav(frames=embed(known_answer.container, 1)), tmp_path / "key.txt"
    key_file.write_bytes(known_answer.passphrase.encode())
    result = run("verify", path, "-m", known_answer.message, "--passphrase_file", key_file)
    assert result.code == 0
    assert "Protection: This message was encrypted.\n" in result.output


def test_a_file_without_a_message_is_an_error_not_a_score(run: Any, make_wav: Callable[..., Path]) -> None:
    result = run("verify", make_wav(frames=b"\xff" * 200), "-m", "")
    assert (result.code, result.output) == (1, "")
    assert "No hidden message" in result.errors


def test_an_old_file_is_compared(run: Any, make_wav: Callable[..., Path]) -> None:
    path = make_wav(frames=bytes(32))
    assert run("verify", path, "-m", "", "--legacy", "basic").code == 0
