"""Tests for audiosteg/cli/errors.py."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, PROJECT_ROOT

from audiosteg import decode, encode
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.cli.commands import reveal
from audiosteg.cli.errors import CancelledError, UsageError, error_type, explain, next_step
from audiosteg.errors import (
    MissingLibraryError,
    NoMessageError,
    PassphraseRequiredError,
    UnsupportedAlgorithmError,
)


@pytest.fixture
def folder(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], tmp_path: Path, known_answer: Any
) -> Path:
    """A folder with one file for every kind of problem."""
    make_wav(frames=bytes(800))
    encode(str(tmp_path / "input.wav"), str(tmp_path / "plain.wav"), "PRIVATE", LSB)
    make_wav(name="private.wav", frames=embed(known_answer.container, 1))
    make_wav(name="damaged.wav", frames=embed(b"ASTG\x01\0\0\0\0\x01A\0\0\0\0", 1))
    make_wav(name="empty.wav", frames=b"\xff" * 800)
    make_wav(name="silence.wav", frames=bytes(500_000))
    (tmp_path / "text.wav").write_text("not audio " * 10)
    (tmp_path / "bytes.txt").write_bytes(b"PRIVATE \xff")
    (tmp_path / "large.txt").write_bytes(b"PRIVATE" * 100)
    (tmp_path / "key.txt").write_bytes(b"SECRET")
    (tmp_path / "bad_key.txt").write_bytes(b"SECRET\0")
    (tmp_path / "folder").mkdir()
    return tmp_path


HIDE = ["hide", "input.wav", "-m", "PRIVATE"]
KEY = ["--passphrase_file", "key.txt"]
EXTRAS = ("crypto", "signal")
ERRORS = [
    ("usage", 2, ["hide", "input.wav", "--PRIVATE"], {}),
    ("usage", 2, [], {}),
    ("cancelled", 1, [*HIDE, "-o", "plain.wav"], {"terminals": ALL, "stdin": b"n\n"}),
    ("input_ended", 1, [*HIDE, "-o", "plain.wav"], {"terminals": ALL}),
    ("file", 1, ["hide", "input.wav", "--message_file", "folder"], {}),
    ("file", 1, ["reveal", "private.wav", "-p"], {"crypto": True}),
    ("file_exists", 1, [*HIDE, "-o", "plain.wav"], {}),
    ("file_not_found", 1, ["reveal", "missing.wav"], {}),
    ("invalid_value", 1, [*HIDE, "--passphrase_file", "bad_key.txt"], {"crypto": True}),
    ("capacity", 1, ["hide", "input.wav", "-m", "PRIVATE" * 100], {}),
    ("capacity", 1, ["hide", "input.wav", "--message_file", "large.txt"], {}),
    ("damaged_message", 1, ["reveal", "damaged.wav"], {}),
    ("invalid_message", 1, ["hide", "input.wav", "--message_file", "bytes.txt"], {}),
    ("no_message", 1, ["verify", "empty.wav", "-m", "PRIVATE"], {}),
    ("not_encrypted", 1, ["reveal", "plain.wav", *KEY], {}),
    ("passphrase_required", 1, ["reveal", "private.wav"], {"crypto": True}),
    ("unsuitable_audio", 1, ["hide", "silence.wav", "-m", "PRIVATE", "-a", "echo"], {"signal": True}),
    ("unsafe_output", 1, [*HIDE, "-o", "folder"], {}),
    ("unsupported_format", 1, ["reveal", "text.wav"], {}),
    ("wrong_passphrase", 1, ["verify", "private.wav", "-m", "PRIVATE", *KEY], {"crypto": True}),
]


@pytest.mark.parametrize(
    ("name", "code", "words", "options"),
    [
        pytest.param(
            *case,
            marks=[getattr(pytest.mark, f"needs_{extra}") for extra in EXTRAS if case[3].get(extra)],
        )
        for case in ERRORS
    ],
)
def test_every_error_in_json(
    run: Any, folder: Path, name: str, code: int, words: list[str], options: dict[str, Any]
) -> None:
    options = {key: value for key, value in options.items() if key not in EXTRAS}
    result = run(*words, "--json", **options)
    assert result.code == code
    assert result.output.count("\n") == 1
    document = json.loads(result.output)
    assert set(document) == {"ok", "command", "error"}
    assert document["ok"] is False
    assert document["command"] == (words[0] if words else None)
    assert set(document["error"]) == {"type", "message", "hint", "exit_code"}
    assert (document["error"]["type"], document["error"]["exit_code"]) == (name, code)
    for secret in ("PRIVATE", "SECRET"):
        assert secret not in result.output + result.errors
    as_text = run(*words, NO_COLOR="1", **options)
    assert (as_text.code, as_text.output) == (code, "")
    if words:
        assert f"Error: {document['error']['message']}\n" in as_text.errors
        assert document["error"]["hint"] is None or document["error"]["hint"] in as_text.errors
    for secret in ("PRIVATE", "SECRET"):
        assert secret not in as_text.errors


def test_without_the_library(run: Any, folder: Path, no_library: None) -> None:
    result = run("hide", "input.wav", "-m", "PRIVATE", *KEY, "--json")
    error = json.loads(result.output)["error"]
    assert (result.code, error["type"]) == (1, "missing_library")
    assert error["hint"] == "Without it, only messages that are not encrypted can be used."
    assert run("hide", "input.wav", "-m", "PRIVATE").code == 0


@pytest.mark.parametrize(
    ("error", "name", "code", "shown"),
    [
        (KeyboardInterrupt(), "interrupted", 130, "Interrupted."),
        (MemoryError(), "out_of_memory", 1, "There is not enough memory for this operation."),
        (PermissionError(13, "x", "a.wav"), "file", 1, "Permission was denied: a.wav. Check"),
        (IsADirectoryError(21, "x", "a"), "file", 1, "This is a folder, not a file: a. Give"),
        (OSError(28, "No space left", "a.wav"), "file", 1, "No space left: a.wav"),
        (OSError(28, "No space left"), "file", 1, "No space left"),
        (OSError("No terminal."), "file", 1, "No terminal."),
        (FileExistsError(17, "x", "temporary", None, "target.wav"), "file_exists", 1, "exists: target.wav"),
        (FileNotFoundError(2, "x", ""), "file_not_found", 1, "The path is empty."),
        (OSError(40, "x", "gpj\u202e\x1b[2J.wav"), "file", 1, "x: gpj\u202e\x1b[2J.wav"),
        (OSError(40, "x", "lone\udcff.wav"), "file", 1, "x: lone\\udcff.wav"),
    ],
)
def test_errors_of_the_system(
    run: Any, monkeypatch: pytest.MonkeyPatch, error: BaseException, name: str, code: int, shown: str
) -> None:
    def fail(path: str) -> None:
        raise error

    monkeypatch.setattr(reveal, "detect", fail)
    result = run("reveal", "x.wav", "--json")
    details = json.loads(result.output)["error"]
    assert (result.code, details["type"], details["exit_code"]) == (code, name, code)
    assert shown in details["message"]
    as_text = run("reveal", "x.wav")
    assert (as_text.code, as_text.output) == (code, "")
    assert "\x1b" not in as_text.errors and "\u202e" not in as_text.errors


def test_the_documentation_lists_every_error_type() -> None:
    documentation = (PROJECT_ROOT / "docs" / "commands.md").read_text(encoding="utf-8")
    listed = set(re.findall("`([a-z_]+)`", re.search("The error types are (.*)\n", documentation)[1]))
    tested = {case[0] for case in ERRORS} | {"interrupted", "out_of_memory", "missing_library"}
    assert listed == tested | {error_type(UnsupportedAlgorithmError())}


def test_the_hint_for_an_existing_file_is_true(run: Any, folder: Path) -> None:
    hint = "Add --force to replace it, or choose another file with -o."
    assert hint in run(*HIDE, "-o", "plain.wav").errors
    assert run(*HIDE, "-o", "other.wav").code == 0
    assert run(*HIDE, "-o", "plain.wav", "--force").code == 0


@pytest.mark.needs_crypto
def test_the_hint_for_a_missing_passphrase_is_true(run: Any, folder: Path, known_answer: Any) -> None:
    hint = "Run the command in a terminal, or use --passphrase_file."
    assert hint in run("reveal", "private.wav").errors
    typed = run("reveal", "private.wav", hidden=(known_answer.passphrase,), terminals=ALL)
    assert typed.code == 0
    (folder / "right.txt").write_text(known_answer.passphrase, encoding="utf-8")
    assert run("reveal", "private.wav", "--passphrase_file", "right.txt").code == 0


def test_the_advice_for_a_passphrase_and_a_plain_message_is_true(run: Any, folder: Path) -> None:
    assert "To read it anyway, leave out the passphrase option." in run("reveal", "plain.wav", *KEY).errors
    assert run("reveal", "plain.wav").output == "PRIVATE"


def test_the_advice_for_a_large_message_is_true(run: Any, folder: Path) -> None:
    words = ["hide", "input.wav", "-m", "x" * 100, "-o", "out.wav"]
    assert "Use the algorithm lsb_2, which can hold it" in run(*words).errors
    assert run(*words, "-a", "lsb_2").code == 0
    assert decode(str(folder / "out.wav"), LSB_2) == "x" * 100


def test_the_hint_for_an_unknown_command_line_is_true(run: Any) -> None:
    assert "To see how a command is used, add --help." in run("hide").errors
    assert run("hide", "--help").code == 0


def test_the_hint_for_a_wrong_algorithm_helps(run: Any, folder: Path) -> None:
    result = run("reveal", "plain.wav", "-a", "lsb_2")
    assert run("reveal", "plain.wav").code == 0
    assert "without -a" in result.errors or "leave out -a" in result.errors


@pytest.mark.parametrize(
    ("error", "start"),
    [
        (UsageError("x"), "To see how a command is used"),
        (NoMessageError("x"), "Check that this is the file that hide made"),
        (PassphraseRequiredError("x"), "Run the command in a terminal"),
        (MissingLibraryError("x"), "Without it"),
        (CancelledError("x"), None),
        (FileNotFoundError("x"), None),
    ],
)
def test_hints(error: Exception, start: str | None) -> None:
    hint = next_step(error)
    assert hint is None if start is None else hint is not None and hint.startswith(start)
    assert explain(error) == "x"
