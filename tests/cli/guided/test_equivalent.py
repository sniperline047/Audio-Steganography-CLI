"""Tests for audiosteg/cli/guided/equivalent.py."""

import pytest

from audiosteg.cli.guided.equivalent import command_line


@pytest.mark.parametrize(
    ("words", "shown"),
    [
        (("audiosteg", "reveal", "a.wav"), "audiosteg reveal a.wav"),
        (("audiosteg", "reveal", "a\x1b[2J.wav"), None),
        (("audiosteg", "reveal", "a\u202e.wav"), None),
    ],
)
def test_only_commands_that_can_be_shown_are_shown(words: tuple[str, ...], shown: str | None) -> None:
    assert command_line(*words) == shown
