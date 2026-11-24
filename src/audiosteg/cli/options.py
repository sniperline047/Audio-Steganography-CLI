"""Options that several commands share."""

import argparse

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.errors import UsageError
from audiosteg.cli.message_input import MessageSource
from audiosteg.cli.passphrase import PassphraseSource


def algorithm_key(text: str) -> str:
    """Check the name of an algorithm."""
    if text not in ALGORITHMS:
        raise UsageError(f"Unknown algorithm. Choose from: {', '.join(ALGORITHMS)}.")
    return text


def legacy_key(text: str) -> str:
    """Check the name of an algorithm of older versions."""
    if text not in LEGACY_ALGORITHMS:
        raise UsageError(f"Unknown old algorithm. Choose from: {', '.join(LEGACY_ALGORITHMS)}.")
    return text


def file_path(text: str) -> str:
    """Refuse an empty path."""
    if not text:
        raise UsageError("A path is empty.")
    return text


def add_output_options(parser: argparse.ArgumentParser, default: object = argparse.SUPPRESS) -> None:
    """Add the options that choose how results are shown."""
    parser.add_argument(
        "--json", action="store_true", default=default, help="write one JSON document to stdout"
    )
    parser.add_argument(
        "--plain", action="store_true", default=default, help="no colour, no drawing, only lines of text"
    )


def add_message_options(parser: argparse.ArgumentParser) -> None:
    """Add the options that give a message."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-m", "--message", metavar="TEXT", help="the message; other programs on this computer may see it"
    )
    group.add_argument(
        "--message_file", type=file_path, metavar="FILE", help="read the message from a UTF-8 text file"
    )


def add_passphrase_options(parser: argparse.ArgumentParser, purpose: str) -> None:
    """Add the options that ask for a passphrase. A passphrase is never a value on the command line."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-p", "--passphrase", action="store_true", help=f"ask for a passphrase {purpose}")
    group.add_argument(
        "--passphrase_file", type=file_path, metavar="FILE", help="read the passphrase from a file"
    )


def add_reading_options(parser: argparse.ArgumentParser) -> None:
    """Add the options that say how to read a message."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-a",
        "--algorithm",
        type=algorithm_key,
        metavar="ALGORITHM",
        help=f"{', '.join(ALGORITHMS)} (default: detect it)",
    )
    group.add_argument(
        "--legacy",
        type=legacy_key,
        metavar="ALGORITHM",
        help=f"for files of older versions: {', '.join(LEGACY_ALGORITHMS)}",
    )
    add_passphrase_options(parser, "to read an encrypted message")


def message_source(args: argparse.Namespace) -> MessageSource:
    """Return where the message comes from."""
    return MessageSource(args.message, args.message_file)


def passphrase_source(args: argparse.Namespace) -> PassphraseSource:
    """Return where the passphrase comes from."""
    return PassphraseSource(args.passphrase, args.passphrase_file)
