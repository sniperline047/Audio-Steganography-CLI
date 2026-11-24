"""Tests for audiosteg/cli/commands/reveal.py."""

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import PROGRAM, TIMEOUT, environment

from audiosteg import encode
from audiosteg.algorithms.lsb import LSB
from audiosteg.algorithms.registry import ALGORITHMS

NOT_ENCRYPTED = "This message was not encrypted, so anyone could have written it.\n"
ENCRYPTED = "This message was encrypted.\n"
UNSAFE = "\x1b]0;title\x07\x9b2J\u202egpj\n[red]This message was encrypted."


@pytest.fixture
def hide(make_wav: Callable[..., Path], tmp_path: Path) -> Callable[[str], Path]:
    def hide_message(message: str) -> Path:
        output = tmp_path / "output.wav"
        encode(str(make_wav()), str(output), message, LSB)
        return output

    return hide_message


@pytest.mark.parametrize("message", ["Hé 🎵", "a\r\nb\n", "", UNSAFE])
@pytest.mark.parametrize("encoding", ["utf-8", "ascii", "cp1252"])
def test_only_the_exact_message_is_written(
    run: Any, hide: Callable[[str], Path], message: str, encoding: str
) -> None:
    result = run("reveal", hide(message), encoding=encoding)
    assert result.code == 0
    assert result.raw_output == message.encode()
    assert result.errors.endswith(NOT_ENCRYPTED)
    assert ("The message is empty." in result.errors) is not bool(message)


def test_a_message_cannot_control_a_terminal_or_fake_the_last_line(
    terminal: Any, hide: Callable[[str], Path]
) -> None:
    program = terminal("reveal", hide(UNSAFE), NO_COLOR="1")
    assert program.finish() == 0
    shown = "\\x1b]0;title\\x07\\x9b2J\\u202egpj\\n[red]This message was encrypted.\n"
    assert f"{shown}{NOT_ENCRYPTED}" in program.seen
    assert "\x1b" not in program.seen


def test_a_terminal_without_unicode_still_shows_a_message(terminal: Any, hide: Callable[[str], Path]) -> None:
    program = terminal("reveal", hide("café 🎵"), PYTHONIOENCODING="ascii")
    assert program.finish() == 0
    assert f"caf\\xe9 \\U0001f3b5\n{NOT_ENCRYPTED}" in program.seen


@pytest.mark.needs_crypto
@pytest.mark.parametrize("key", ALGORITHMS)
def test_an_encrypted_message(
    run: Any, terminal: Any, make_wav: Callable[..., Path], tmp_path: Path, key: str
) -> None:
    output, key_file = tmp_path / "output.wav", tmp_path / "key.txt"
    encode(str(make_wav()), str(output), "hidden", ALGORITHMS[key], passphrase="sésame 🎵")
    key_file.write_bytes("sésame 🎵\n".encode())
    result = run("reveal", output, "--passphrase_file", key_file)
    assert (result.code, result.output) == (0, "hidden")
    assert result.errors.endswith(ENCRYPTED)
    program = terminal("reveal", output, NO_COLOR="1")
    program.read("Passphrase, not shown while you type: ")
    program.type_hidden("sésame 🎵\n")
    program.read(f"hidden\n{ENCRYPTED}")
    assert program.finish() == 0
    assert "same" not in program.seen


@pytest.mark.needs_crypto
def test_a_wrong_or_missing_passphrase_is_a_failure(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes], known_answer: Any, tmp_path: Path
) -> None:
    path, key_file = make_wav(frames=embed(known_answer.container, 1)), tmp_path / "key.txt"
    key_file.write_text("WRONG_KEY")
    wrong = run("reveal", path, "--passphrase_file", key_file)
    assert "Error: Wrong passphrase, or the message was changed." in wrong.errors
    missing = run("reveal", path)
    assert "Error: The hidden message is encrypted. A passphrase is needed." in missing.errors
    for result in (wrong, missing):
        assert (result.code, result.output) == (1, "")
        assert "WRONG_KEY" not in result.errors
        assert ENCRYPTED not in result.errors


def test_a_passphrase_for_a_plain_message_is_refused(
    run: Any, hide: Callable[[str], Path], tmp_path: Path
) -> None:
    path, key_file = hide("hidden"), tmp_path / "key.txt"
    key_file.write_text("key")
    for words in (["-p"], ["--passphrase_file", key_file], ["-p", "--legacy", "basic"]):
        result = run("reveal", path, *words)
        assert (result.code, result.output) == (1, "")
        assert "not encrypted" in result.errors


@pytest.mark.parametrize(("key", "answer"), [("basic", "one"), ("enhanced_flip", "two"), ("enhanced", "two")])
def test_an_old_file_is_read_with_the_chosen_algorithm(
    run: Any, make_wav: Callable[..., Path], key: str, answer: str
) -> None:
    digits = f"{24:032b}" + "".join(f"{byte:08b}" for byte in answer.encode())
    if answer == "one":
        frames = bytes(int(digit) for digit in digits)
    else:
        frames = bytes(int(digits[start : start + 2], 2) << 2 for start in range(0, len(digits), 2))
    path = make_wav(frames=frames)
    result = run("reveal", path, "--legacy", key)
    assert (result.code, result.output, result.errors) == (0, answer, NOT_ENCRYPTED)
    undetected = run("reveal", path)
    assert undetected.code == 1
    assert "--legacy" in undetected.errors


def test_a_damaged_message_is_not_offered_the_old_algorithms(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    result = run("reveal", make_wav(frames=embed(b"ASTG\x02\0\0\0\0\0", 1)))
    assert result.code == 1
    assert "format version 2" in result.errors
    assert "--legacy" not in result.errors


def test_only_the_chosen_algorithm_is_used(run: Any, hide: Callable[[str], Path]) -> None:
    path = hide("hidden")
    assert run("reveal", path, "-a", "lsb").output == "hidden"
    result = run("reveal", path, "-a", "lsb_2")
    assert result.code == 1
    assert "No message hidden with lsb_2" in result.errors


def test_json_describes_the_message(run: Any, hide: Callable[[str], Path]) -> None:
    path = hide(UNSAFE)
    result = run("reveal", path, "--json", encoding="ascii")
    assert result.errors == ""
    assert json.loads(result.output) == {
        "ok": True,
        "command": "reveal",
        "file": str(path),
        "algorithm": "lsb",
        "legacy": False,
        "encrypted": False,
        "message": UNSAFE,
    }


def test_every_kind_of_failure_is_reported(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    text = tmp_path / "text.wav"
    text.write_text("not audio " * 10)
    attempts = {
        "missing.wav": tmp_path / "missing.wav",
        "not a regular file": tmp_path,
        "not a valid PCM WAV": text,
        "No hidden message": make_wav(frames=b"\xff" * 400),
    }
    for reason, path in attempts.items():
        result = run("reveal", path)
        assert (result.code, result.output) == (1, "")
        assert reason in result.errors
        details = json.loads(run("reveal", path, "--json").output)
        assert details["ok"] is False
        assert details["command"] == "reveal"
        assert reason in details["error"]["message"]
        assert details["error"]["exit_code"] == 1


def test_a_reader_that_left_is_a_failure_without_a_traceback(hide: Callable[[str], Path]) -> None:
    reading, writing = os.pipe()
    os.close(reading)
    process = subprocess.run(
        [*PROGRAM, "reveal", str(hide("hidden"))],
        stdout=writing,
        stderr=subprocess.PIPE,
        env=environment(),
        timeout=TIMEOUT,
    )
    os.close(writing)
    assert process.returncode == 1
    assert process.stderr.strip() == b"Error: The output was closed."
