"""Tests for audiosteg/cli/accuracy.py."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from audiosteg import encode
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.accuracy import AccuracyResult, calculate_accuracy, compare_messages
from audiosteg.errors import NoMessageError


@pytest.mark.parametrize(
    ("expected", "decoded", "percentage"),
    [
        ("", "", 100.0),
        ("same 🎵", "same 🎵", 100.0),
        ("abcd", "abXd", 75.0),
        ("abcd", "ab", 50.0),
        ("ab", "abcd", 50.0),
        ("ab", "", 0.0),
        ("", "ab", 0.0),
        ("abcd", "bcda", 0.0),
        ("é", "e\u0301", 0.0),
    ],
    ids=["empty", "same", "one_wrong", "missing", "extra", "none", "unexpected", "shifted", "other_form"],
)
def test_score_counts_missing_and_extra_characters(expected: str, decoded: str, percentage: float) -> None:
    result = compare_messages(expected, decoded)
    assert result == AccuracyResult(percentage, expected == decoded, len(expected), len(decoded))


def test_a_rounded_score_of_100_is_not_reported_as_exact() -> None:
    result = compare_messages("x" * 100000, "x" * 99999 + "y")
    assert f"{result.percentage:.2f}" == "100.00"
    assert not result.exact_match


@pytest.mark.parametrize("number", sorted(ALGORITHMS))
def test_checking_a_file_changes_nothing(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, number: int
) -> None:
    algorithm = ALGORITHMS[number]
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden", algorithm)
    content = output.read_bytes()
    output.chmod(0o444)
    modified = output.stat().st_mtime_ns
    monkeypatch.chdir(tmp_path)
    try:
        assert calculate_accuracy("hiddenX", str(output), algorithm).decoded_length == 6
    finally:
        output.chmod(0o644)
    assert output.read_bytes() == content
    assert output.stat().st_mtime_ns == modified
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "output.wav"]


def test_a_file_without_a_message_is_an_error_not_a_score(make_wav: Callable[..., Path]) -> None:
    with pytest.raises(NoMessageError):
        calculate_accuracy("", str(make_wav(frames=b"\xff" * 200)), ALGORITHMS[1])
