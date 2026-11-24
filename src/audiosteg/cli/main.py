"""The program: parse the command line, run the command, and return the exit code."""

import argparse
import contextlib
import io
import os
import sys
from collections.abc import Sequence
from importlib.metadata import version

from audiosteg.cli.errors import CancelledError, OutputClosedError, UsageError
from audiosteg.cli.parser import COMMANDS, Parser, build_parser, parse
from audiosteg.cli.views import View, is_dumb_terminal
from audiosteg.errors import StegoError

SUCCESS, FAILURE, WRONG_USAGE, INTERRUPTED = 0, 1, 2, 130
HANDLED = (
    StegoError,
    UsageError,
    CancelledError,
    OutputClosedError,
    OSError,
    ValueError,
    MemoryError,
    EOFError,
    KeyboardInterrupt,
)


def exit_code_of(error: BaseException) -> int:
    """Return the exit code of an error."""
    if isinstance(error, UsageError):
        return WRONG_USAGE
    return INTERRUPTED if isinstance(error, KeyboardInterrupt) else FAILURE


def prepare_streams() -> None:
    """Accept and show text that the terminal's encoding does not support."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    if isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(errors="surrogateescape")


def silence(stream_name: str) -> None:
    """Send a closed stream nowhere, so that Python does not complain about it at the end."""
    with contextlib.suppress(OSError, ValueError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), getattr(sys, stream_name).fileno())


def flush_output() -> bool:
    """Write any waiting output. Return False if the output is closed."""
    working = True
    for name in ("stderr", "stdout"):
        try:
            getattr(sys, name).flush()
        except OSError:
            silence(name)
            working = name != "stdout"
    return working


def run_guided(parser: Parser, args: argparse.Namespace, view: View) -> int:
    """Start the guided mode, or show how to use the commands where it cannot run."""
    if args.json:
        raise UsageError("--json needs a command.")
    if not sys.stdin.isatty() or not sys.stdout.isatty() or is_dumb_terminal():
        view.err.write(parser.format_help())
        view.note("")
        view.note("Error: The guided mode needs a terminal. Choose a command instead.", "bold red")
        return WRONG_USAGE
    from audiosteg.cli.guided import run

    return run(view)


def run_command(words: Sequence[str]) -> int:
    """Parse the command line and run what it asks for. Return the exit code."""
    options = list(words[: words.index("--")]) if "--" in words else list(words)
    view = View(sys.stdout, sys.stderr, plain="--plain" in options, as_json="--json" in options)
    command = next((word for word in options if word in COMMANDS), None)
    try:
        parser, commands = build_parser()
        args = parse(parser, commands, words)
        command = args.command
        if args.version:
            view.show_version(version("audiosteg"))
            return SUCCESS
        if command is None:
            return run_guided(parser, args, view)
        exit_code: int = COMMANDS[command].run(args, view)
        return exit_code
    except HANDLED as error:
        if isinstance(error, (KeyboardInterrupt, EOFError)) and view.err.is_terminal:
            view.note("")
        failure = exit_code_of(error)
        with contextlib.suppress(OutputClosedError):
            view.show_error(error, command, failure)
        return failure


def main(words: Sequence[str] | None = None) -> int:
    """Run the program."""
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    if sys.stdin is None:
        sys.stdin = open(os.devnull)  # noqa: SIM115
    if sys.stdout is None:
        with contextlib.suppress(OSError):
            print("Error: The program needs an open output.", file=sys.stderr)
        return FAILURE
    prepare_streams()
    try:
        exit_code = run_command(sys.argv[1:] if words is None else words)
    except SystemExit as finished:
        exit_code = finished.code if isinstance(finished.code, int) else FAILURE
    except KeyboardInterrupt:
        exit_code = INTERRUPTED
    if not flush_output():
        return exit_code or FAILURE
    return exit_code
