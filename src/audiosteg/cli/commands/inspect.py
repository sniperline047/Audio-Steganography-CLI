"""The inspect command."""

import argparse

from audiosteg.cli.commands.hide import find_input
from audiosteg.cli.options import file_path
from audiosteg.cli.views import View

HELP = "describe a WAV file and look for a hidden message"
EXAMPLES = """examples:
  audiosteg inspect sample
  audiosteg inspect song.stego.wav
  audiosteg inspect song.stego.wav --json
"""


def inspect_file(word: str, view: View) -> None:
    """Show what is known about a file, or about the sample."""
    from audiosteg.analysis.inspection import inspect
    from audiosteg.cli.inspect_view import show_inspection

    path = find_input(word)
    show_inspection(view, path, inspect(path))


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    inspect_file(args.file, view)
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument(
        "file",
        type=file_path,
        metavar="FILE",
        help="the WAV file, or the word sample (./sample means a file)",
    )
