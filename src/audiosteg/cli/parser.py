"""The command line. Error messages never repeat a value, because it may be a secret."""

import argparse
import difflib
from collections.abc import Sequence
from typing import Any, NoReturn

from audiosteg.cli.commands import algorithms, hide, reveal, verify
from audiosteg.cli.errors import UsageError
from audiosteg.cli.options import add_output_options

COMMANDS = {"hide": hide, "reveal": reveal, "verify": verify, "algorithms": algorithms}
SAFE_MESSAGES = ("the following arguments are required", "not allowed with argument")
EXAMPLES = """examples:
  audiosteg                                  start the guided mode
  audiosteg hide sample -m "Hello"           hide a message in the included sample
  audiosteg reveal sample.stego.wav          read it
  audiosteg verify sample.stego.wav -m "Hello"

exit codes: 0 success, 1 failure, 2 wrong usage, 130 Ctrl-C
"""


class Parser(argparse.ArgumentParser):
    """A parser that raises errors instead of ending the program."""

    def __init__(self, **options: Any) -> None:
        """Use the same style on every Python version."""
        super().__init__(formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False, **options)
        self.color = False

    def error(self, message: str) -> NoReturn:
        """Explain what is wrong without any value from the command line."""
        if "invalid choice" in message:
            raise UsageError(f"Unknown command. Choose from: {', '.join(COMMANDS)}.")
        if "ignored explicit argument" in message:
            raise UsageError("A value was given to an option that takes none. -p asks for the passphrase.")
        if message.endswith("expected one argument"):
            option = message.split(":")[0].removeprefix("argument ").split("/")[-1]
            raise UsageError(f"{option} needs a value. If it starts with a dash, write {option}=VALUE.")
        if any(safe in message for safe in SAFE_MESSAGES):
            raise UsageError(f"{message[0].upper()}{message[1:]}.")
        raise UsageError("The command line was not understood.")

    def known_options(self) -> list[str]:
        """Return the long options of this parser."""
        return [option for option in self._option_string_actions if option.startswith("--")]


def build_parser() -> tuple[Parser, dict[str, Parser]]:
    """Build the parser of the program and the parsers of its commands."""
    parser = Parser(
        prog="audiosteg",
        description="Hide text messages in WAV files and read them back. "
        "Without a command, a guided mode starts.",
        epilog=EXAMPLES,
    )
    parser.add_argument("--version", action="store_true", help="show the version and exit")
    add_output_options(parser, default=False)
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", title="commands")
    commands = {}
    for name, command in COMMANDS.items():
        description = f"{command.HELP[0].upper()}{command.HELP[1:]}."
        commands[name] = subparsers.add_parser(
            name, help=command.HELP, description=description, epilog=command.EXAMPLES
        )
        command.add_arguments(commands[name])
        add_output_options(commands[name])
    return parser, commands


def parse(parser: Parser, commands: dict[str, Parser], words: Sequence[str]) -> argparse.Namespace:
    """Parse the command line. Words that are not understood are never repeated."""
    options_only = words[: words.index("--")] if "--" in words else words
    if any(word.startswith("-p") and word != "-p" for word in options_only):
        raise UsageError("-p takes no value: it asks for the passphrase. Write other options separately.")
    args, extra = parser.parse_known_args(words)
    if not extra:
        return args
    options = commands[args.command].known_options() if args.command else parser.known_options()
    for word in extra:
        similar = difflib.get_close_matches(word, options, n=1)
        if word.startswith("--") and similar:
            raise UsageError(f"Unknown option. Did you mean {similar[0]}?")
    raise UsageError(
        "The command line has an unknown option or an extra word. "
        "It is not shown here because it may be private. -p takes no value: it asks for the passphrase."
    )
