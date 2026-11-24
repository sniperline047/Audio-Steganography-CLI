"""Get a message from the command line, a file, a pipe, or the person at the terminal."""

import sys
from contextlib import suppress
from dataclasses import dataclass, field
from typing import BinaryIO

from audiosteg.cli.errors import UsageError
from audiosteg.cli.questions import ask_line
from audiosteg.errors import CapacityError, InvalidMessageError


@dataclass(frozen=True)
class MessageSource:
    """Where a message comes from. Without a text or a file, it is typed or piped."""

    text: str | None = field(repr=False)
    file: str | None

    def read(self, question: str, limit: int) -> str:
        """
        Get the message. Files and pipes are read exactly as they are.

        :param question: The question for the person at the terminal
        :param limit: The most bytes that the audio file can hold, so that nothing larger is read
        :return: The message
        """
        if self.text is not None:
            return self.text
        if self.file is not None:
            with open(self.file, "rb") as source:
                return read_utf8(source, limit)
        if sys.stdin.isatty():
            return ask_line(question)
        message = read_utf8(sys.stdin.buffer, limit)
        if not message:
            raise UsageError(
                'No message was given. Use -m, --message_file, or a pipe. To hide nothing, use -m "".'
            )
        return message


def read_utf8(source: BinaryIO, limit: int) -> str:
    """Read UTF-8 text, and refuse more bytes than the limit."""
    data = source.read(limit + 1)
    if len(data) > limit:
        raise CapacityError(
            f"The message is too large: the audio file can hold {limit} bytes. "
            "Use a longer audio file or a shorter message."
        )
    with suppress(UnicodeDecodeError):
        return data.decode("utf-8")
    raise InvalidMessageError("The message is not valid UTF-8 text.")
