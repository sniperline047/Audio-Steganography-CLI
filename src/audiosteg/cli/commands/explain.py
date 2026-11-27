"""The explain command."""

import argparse
import sys
from collections.abc import Callable

from audiosteg.algorithms.echo import EchoHiding
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.commands.hide import SAMPLE_WORD, find_input
from audiosteg.cli.errors import UsageError
from audiosteg.cli.options import algorithm_key, file_path
from audiosteg.cli.questions import ask_line
from audiosteg.cli.views import View
from audiosteg.core.algorithm import Algorithm

HELP = "explain how an algorithm hides a character"
EXAMPLES = """examples:
  audiosteg explain
  audiosteg explain lsb
  audiosteg explain lsb_2 --letter A --file song.wav
"""
DEFAULT_LETTER = "h"
CONTINUE = "Press Enter to continue."


def one_character(text: str) -> str:
    """Check that there is exactly one character, which can be stored as UTF-8."""
    if len(text) != 1 or "\ud800" <= text <= "\udfff":
        raise UsageError("--letter needs exactly one character. Some emoji are several characters.")
    return text


def check_options(args: argparse.Namespace) -> None:
    """Refuse options that cannot be used."""
    options = {"--letter": args.letter, "--file": args.file, "--step": args.step or None}
    given = [name for name, value in options.items() if value is not None]
    if given and args.algorithm is None:
        raise UsageError(f"{given[0]} needs one of these algorithms: {', '.join(ALGORITHMS)}.")
    if args.step and args.json:
        raise UsageError("--step cannot be used with --json.")
    if args.step and not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise UsageError("--step needs a terminal.")


def wait_for_enter() -> None:
    """Wait until the person wants to continue."""
    ask_line(CONTINUE)


def explain_hiding(view: View, key: str, letter: str, path: str, pause: Callable[[], None] | None) -> None:
    """Hide a character in memory, in the way of the algorithm, and show how."""
    algorithm = ALGORITHMS[key]
    if isinstance(algorithm, Algorithm):
        from audiosteg.analysis.walkthrough import walk_through
        from audiosteg.cli.explain_view import show_walkthrough

        show_walkthrough(view, key, path, walk_through(path, letter, algorithm), algorithm, pause)
    elif isinstance(algorithm, EchoHiding):
        from audiosteg.analysis.echo_walkthrough import walk_through_echo
        from audiosteg.cli.echo_view import show_echo_walkthrough

        walkthrough = walk_through_echo(path, letter, algorithm)
        show_echo_walkthrough(view, key, path, walkthrough, algorithm, pause)


def explain(
    view: View,
    key: str | None,
    letter: str = DEFAULT_LETTER,
    word: str = SAMPLE_WORD,
    pause: Callable[[], None] | None = None,
) -> None:
    """
    Explain one algorithm, or list all of them.

    :param key: The name of the algorithm, or None to list them
    :param letter: The character to hide
    :param word: The path of a WAV file, or the word sample
    :param pause: Function that is called between the steps
    """
    from audiosteg.cli.explain_view import show_list

    if key is None:
        show_list(view)
    else:
        explain_hiding(view, key, letter, find_input(word), pause)


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    check_options(args)
    letter = DEFAULT_LETTER if args.letter is None else args.letter
    word = SAMPLE_WORD if args.file is None else args.file
    explain(view, args.algorithm, letter, word, wait_for_enter if args.step else None)
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument(
        "algorithm",
        nargs="?",
        type=algorithm_key,
        metavar="ALGORITHM",
        help="the algorithm to explain (default: list them)",
    )
    parser.add_argument(
        "--letter",
        type=one_character,
        metavar="CHARACTER",
        help=f"the character to hide (default: {DEFAULT_LETTER})",
    )
    parser.add_argument(
        "--file", type=file_path, metavar="FILE", help="take the samples from this WAV file (default: sample)"
    )
    parser.add_argument("--step", action="store_true", help="wait for Enter after each step")
