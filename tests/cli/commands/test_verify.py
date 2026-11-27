"""Tests for audiosteg/cli/commands/verify.py."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, EVERY_KEY, needed_passphrase, noise_for

from audiosteg import encode
from audiosteg.algorithms.registry import ALGORITHMS


@pytest.mark.parametrize("key", EVERY_KEY)
@pytest.mark.usefixtures("fast_scrypt")
def test_a_match_changes_nothing(run: Any, make_wav: Callable[..., Path], tmp_path: Path, key: str) -> None:
    output, passphrase = tmp_path / "output.wav", needed_passphrase(key)
    source = make_wav(frames=noise_for(key))
    encode(str(source), str(output), "hidden 🎵", ALGORITHMS[key], passphrase=passphrase)
    content = output.read_bytes()
    output.chmod(0o444)
    modified = output.stat().st_mtime_ns
    asks = {"hidden": (passphrase,), "terminals": ("stderr",), "NO_COLOR": "1"} if passphrase else {}
    try:
        result = run(
            "verify", output, "-m", "hidden 🎵", *(["-p"] if passphrase else []), cwd=tmp_path, **asks
        )
    finally:
        output.chmod(0o644)
    assert (result.code, result.errors) == (0, "")
    assert "Exact match: yes\nAccuracy: 100.00%\n" in result.output
    protection = "This message was encrypted" if passphrase else "This message was not encrypted"
    assert protection in result.output
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
@pytest.mark.usefixtures("fast_scrypt")
def test_an_encrypted_message_is_compared(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    path, key_file = tmp_path / "output.wav", tmp_path / "key.txt"
    encode(str(make_wav()), str(path), "hidden", ALGORITHMS["lsb"], passphrase="sesame")
    key_file.write_text("sesame")
    result = run("verify", path, "-m", "hidden", "--passphrase_file", key_file)
    assert result.code == 0
    assert "Protection: This message was encrypted.\n" in result.output
    wrong = run("verify", path, "-m", "hidden", hidden=("wrong",), terminals=ALL)
    assert (wrong.code, "Accuracy" in wrong.seen, "hidden" in wrong.output) == (1, False, False)


def test_the_expected_message_comes_from_a_file_or_a_terminal(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    path, expected = tmp_path / "output.wav", tmp_path / "expected.txt"
    encode(str(make_wav()), str(path), "Hé\n", ALGORITHMS["lsb"])
    expected.write_bytes("Hé\n".encode())
    assert run("verify", path, "--message_file", expected).code == 0
    typed = run("verify", path, stdin="Hé\n".encode(), terminals=ALL)
    assert typed.code == 1
    assert "Expected message: " in typed.errors
    nothing = run("verify", path)
    assert (nothing.code, nothing.output) == (2, "")


def test_a_damaged_message_is_an_error_not_a_score(
    run: Any, make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    result = run("verify", make_wav(frames=embed(b"ASTG\x01\0\0\0\0\x01A\0\0\0\0", 1)), "-m", "A")
    assert (result.code, result.output) == (1, "")
    assert "Error: The hidden message is damaged" in result.errors


@pytest.mark.parametrize(("key", "bits"), [("basic", 1), ("enhanced", 2)])
def test_an_expected_message_may_be_as_long_as_an_old_message(
    run: Any, make_wav: Callable[..., Path], key: str, bits: int
) -> None:
    path = make_wav(frames=bytes(320))
    limit = 2 * ((320 * bits - 32) // 8)
    fits = run("verify", path, "--legacy", key, stdin=b"x" * limit)
    assert (fits.code, "Accuracy: 0.00%" in fits.output) == (1, True)
    assert run("verify", path, "--legacy", key, stdin=b"x" * (limit + 1)).output == ""


def test_a_long_latin_1_message_of_an_old_file_matches(run: Any, make_wav: Callable[..., Path]) -> None:
    hidden = b"\xe9" * 100
    digits = f"{len(hidden) * 8:032b}" + "".join(f"{byte:08b}" for byte in hidden)
    path = make_wav(frames=bytes(int(digit) for digit in digits))
    assert run("reveal", path, "--legacy", "basic").output == "é" * 100
    assert run("verify", path, "--legacy", "basic", stdin=("é" * 100).encode()).code == 0


def test_an_expected_message_may_be_as_long_as_the_largest_message(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output, message = tmp_path / "output.wav", b"x" * (4008 // 2 - 14)
    encode(str(make_wav()), str(output), message.decode(), ALGORITHMS["lsb_4"])
    assert run("verify", output, stdin=message).code == 0
    assert run("verify", output, stdin=message + b"x").output == ""


def test_a_too_long_expected_message_is_not_answered_with_advice_for_hide(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden", ALGORITHMS["lsb"])
    result = run("verify", output, stdin=b"x" * 5000)
    assert result.code == 1
    assert "longer audio file" not in result.errors


def test_a_missing_expected_message_is_not_answered_with_advice_for_hide(
    run: Any, make_wav: Callable[..., Path]
) -> None:
    result = run("verify", make_wav())
    assert result.code == 2
    assert "To hide nothing" not in result.errors


def test_a_file_without_a_message_is_an_error_not_a_score(run: Any, make_wav: Callable[..., Path]) -> None:
    result = run("verify", make_wav(frames=b"\xff" * 200), "-m", "")
    assert (result.code, result.output) == (1, "")
    assert "No hidden message" in result.errors


def test_an_old_file_is_compared(run: Any, make_wav: Callable[..., Path]) -> None:
    path = make_wav(frames=bytes(32))
    assert run("verify", path, "-m", "", "--legacy", "basic").code == 0
