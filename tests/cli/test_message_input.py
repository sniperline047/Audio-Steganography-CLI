"""Tests for audiosteg/cli/message_input.py."""

import io
from pathlib import Path

import pytest

from audiosteg.cli.message_input import MessageSource, read_utf8
from audiosteg.errors import CapacityError, InvalidMessageError


def test_the_limit_counts_bytes_and_nothing_more_is_read() -> None:
    source = io.BytesIO("éé".encode() + b"x" * 1000)
    with pytest.raises(CapacityError, match="can hold 3 bytes"):
        read_utf8(source, 3)
    assert source.tell() == 4
    assert read_utf8(io.BytesIO("éé".encode()), 4) == "éé"


def test_bytes_that_are_not_text_are_refused_without_showing_them() -> None:
    with pytest.raises(InvalidMessageError) as caught:
        read_utf8(io.BytesIO(b"PRIVATE \xff"), 100)
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__context__ is None


def test_a_byte_order_mark_and_line_ends_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "message.txt"
    path.write_bytes(b"\xef\xbb\xbfa\r\nb\r")
    assert MessageSource(None, str(path)).read("", 100).encode() == path.read_bytes()


def test_an_empty_text_or_file_is_a_message(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").touch()
    assert MessageSource("", None).read("", 0) == ""
    assert MessageSource(None, str(tmp_path / "empty.txt")).read("", 0) == ""


def test_a_source_does_not_show_its_message() -> None:
    assert "PRIVATE" not in repr(MessageSource("PRIVATE", None))
