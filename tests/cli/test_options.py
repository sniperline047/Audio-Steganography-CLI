"""Tests for audiosteg/cli/options.py."""

import argparse
from collections.abc import Callable

import pytest

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.errors import UsageError
from audiosteg.cli.options import (
    add_message_options,
    add_reading_options,
    algorithm_key,
    file_path,
    legacy_key,
    message_source,
    passphrase_source,
)


@pytest.mark.parametrize(("check", "known"), [(algorithm_key, ALGORITHMS), (legacy_key, LEGACY_ALGORITHMS)])
def test_only_known_names_are_accepted(check: Callable[[str], str], known: dict[str, object]) -> None:
    assert [check(name) for name in known] == list(known)
    for name in ("PRIVATE", "", "LSB", "lsb "):
        with pytest.raises(UsageError, match=", ".join(known)) as caught:
            check(name)
        assert "PRIVATE" not in str(caught.value)


def test_an_empty_path_is_refused() -> None:
    assert file_path(" ") == " "
    with pytest.raises(UsageError):
        file_path("")


def test_the_sources_are_what_the_command_line_says() -> None:
    parser = argparse.ArgumentParser()
    add_message_options(parser)
    add_reading_options(parser)
    given = parser.parse_args(["--message_file", "m.txt", "--passphrase_file", "k.txt"])
    assert (message_source(given).text, message_source(given).file) == (None, "m.txt")
    assert (passphrase_source(given).prompt, passphrase_source(given).file) == (False, "k.txt")
    assert passphrase_source(given).wanted
    short = parser.parse_args(["-m", "", "-p"])
    assert (message_source(short).text, passphrase_source(short).prompt) == ("", True)
    nothing = parser.parse_args([])
    assert message_source(nothing).text is None
    assert not passphrase_source(nothing).wanted
