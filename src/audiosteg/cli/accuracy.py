"""Compare a hidden message with the message that was expected."""

from typing import NamedTuple


class AccuracyResult(NamedTuple):
    """The result of comparing two messages."""

    percentage: float
    exact_match: bool
    expected_length: int
    decoded_length: int


def compare_messages(expected_message: str, decoded_message: str) -> AccuracyResult:
    """
    Compare two messages character by character.

    The score is the number of matching positions divided by the longer length,
    so missing and extra characters both lower it.

    :param expected_message: The message that should be hidden
    :param decoded_message: The message that was found
    :return: The comparison result
    """
    longest = max(len(expected_message), len(decoded_message))
    matches = sum(a == b for a, b in zip(expected_message, decoded_message, strict=False))
    return AccuracyResult(
        percentage=100.0 if longest == 0 else matches / longest * 100,
        exact_match=expected_message == decoded_message,
        expected_length=len(expected_message),
        decoded_length=len(decoded_message),
    )
