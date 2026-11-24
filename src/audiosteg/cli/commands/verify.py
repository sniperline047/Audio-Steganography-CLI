"""The verify command."""

import argparse
import os

from audiosteg.cli.accuracy import compare_messages
from audiosteg.cli.commands.reveal import reveal
from audiosteg.cli.options import add_message_options, add_reading_options, message_source
from audiosteg.cli.results import RevealResult, VerifyResult
from audiosteg.cli.views import View
from audiosteg.core.wav_io import check_regular_file

HELP = "compare a hidden message with the expected one"
EXAMPLES = """examples:
  audiosteg verify song.stego.wav -m "Hello"
  audiosteg verify song.stego.wav --message_file letter.txt
"""


def verify(revealed: RevealResult, expected: str) -> VerifyResult:
    """Compare a message that was found with the expected one."""
    return VerifyResult(revealed, compare_messages(expected, revealed.message))


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code, which is 1 if the messages differ."""
    check_regular_file(args.file)
    expected = message_source(args).read("Expected message: ", os.path.getsize(args.file))
    result = verify(reveal(args, view), expected)
    view.show_verify(result)
    return 0 if result.accuracy.exact_match else 1


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument("file", metavar="FILE", help="the WAV file with the hidden message")
    add_message_options(parser)
    add_reading_options(parser)
