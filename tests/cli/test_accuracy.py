"""Tests for audiosteg/cli/accuracy.py."""

import pytest

from audiosteg.cli.accuracy import AccuracyResult, compare_messages


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
