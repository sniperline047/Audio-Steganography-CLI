"""The hide command."""

import argparse
import os
import sys
from dataclasses import dataclass, field
from importlib.resources import files

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.errors import CancelledError
from audiosteg.cli.options import (
    add_message_options,
    add_passphrase_options,
    algorithm_key,
    message_source,
    passphrase_source,
)
from audiosteg.cli.questions import ask_yes_no
from audiosteg.cli.results import HideResult
from audiosteg.cli.views import View
from audiosteg.core import crypto
from audiosteg.core.stego_file import encode, file_can_hold
from audiosteg.core.wav_io import check_regular_file
from audiosteg.errors import CapacityError, UnsafeOutputError
from audiosteg.utils.output_path import check_output_path, normalize_output_path
from audiosteg.utils.text import escape_text

HELP = "hide a message in a copy of a WAV file"
EXAMPLES = """examples:
  audiosteg hide sample -m "Hello"            use the included sample
  audiosteg hide song.wav -p                  ask for the message and a passphrase
  audiosteg hide song.wav -o secret.wav -a lsb_2 --message_file letter.txt
  printf "Hello" | audiosteg hide song.wav    take the message from a pipe
"""
SAMPLE_FILE = str(files("audiosteg") / "data" / "sample.wav")
SAMPLE_WORD = "sample"
DEFAULT_ALGORITHM = next(iter(ALGORITHMS))


@dataclass(frozen=True)
class HideRequest:
    """Everything that is needed to hide a message. The output path must come from check_output."""

    input_file: str
    output_file: str
    message: str = field(repr=False)
    algorithm: str
    passphrase: str | None = field(repr=False)
    overwrite: bool


def find_input(word: str) -> str:
    """Return the path of the included sample for the word sample, and any other path unchanged."""
    return SAMPLE_FILE if word == SAMPLE_WORD else word


def default_output(input_file: str) -> str:
    """Return the name of the output file, in the current folder."""
    name = os.path.basename(input_file)
    stem, extension = os.path.splitext(name)
    return f"{stem if extension.lower() == '.wav' else name}.stego.wav"


def check_not_sample(output_file: str) -> None:
    """Refuse to replace the sample that is included in the package."""
    if not os.path.exists(output_file) or not os.path.exists(SAMPLE_FILE):
        return
    if os.path.samefile(output_file, SAMPLE_FILE):
        raise UnsafeOutputError("The output path is the included sample, which cannot be replaced.")


def check_output(input_file: str, chosen_path: str) -> tuple[str, bool]:
    """Refuse an unsafe output path. Return it normalized, and whether a file would be replaced."""
    output_file = normalize_output_path(chosen_path)
    check_output_path(input_file, output_file, overwrite=True)
    check_not_sample(output_file)
    return output_file, os.path.exists(output_file)


def advise(request: HideRequest) -> str:
    """Say how a message that is too large could fit."""
    for key, algorithm in ALGORITHMS.items():
        if file_can_hold(request.input_file, request.message, algorithm, request.passphrase is not None):
            return f"Use the algorithm {key}, which can hold it, or a longer audio file."
    return "Use a longer audio file or a shorter message."


def hide(request: HideRequest) -> HideResult:
    """Hide a message."""
    try:
        encode(
            request.input_file,
            request.output_file,
            request.message,
            ALGORITHMS[request.algorithm],
            passphrase=request.passphrase,
            overwrite=request.overwrite,
        )
    except CapacityError as error:
        raise CapacityError(f"{error} {advise(request)}") from error
    return HideResult(
        request.input_file, request.output_file, request.algorithm, request.passphrase is not None
    )


def may_replace(output_file: str, force: bool) -> bool:
    """Ask before replacing a file. Without a terminal, only --force replaces it."""
    if force:
        return True
    if not sys.stdin.isatty():
        raise FileExistsError(f"The output file already exists: {output_file}")
    if not ask_yes_no(f"{escape_text(output_file)} already exists. Overwrite it?"):
        raise CancelledError("Nothing was written.")
    return True


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    input_file = find_input(args.input)
    check_regular_file(input_file)
    output_file, exists = check_output(input_file, args.output or default_output(input_file))
    overwrite = exists and may_replace(output_file, args.force)
    passphrases = passphrase_source(args)
    if passphrases.wanted:
        crypto.check_available()
    message = message_source(args).read("Message to hide: ", os.path.getsize(input_file))
    passphrase = passphrases.read_new(view.note)
    view.progress("Hiding the message...")
    view.show_hide(hide(HideRequest(input_file, output_file, message, args.algorithm, passphrase, overwrite)))
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument(
        "input", metavar="INPUT", help="the WAV file to copy, or the word sample (./sample means a file)"
    )
    add_message_options(parser)
    parser.add_argument(
        "-a",
        "--algorithm",
        type=algorithm_key,
        default=DEFAULT_ALGORITHM,
        metavar="ALGORITHM",
        help=f"{', '.join(ALGORITHMS)} (default: {DEFAULT_ALGORITHM})",
    )
    add_passphrase_options(parser, "and encrypt the message")
    parser.add_argument(
        "-o", "--output", metavar="OUTPUT", help="the new WAV file (default: INPUT.stego.wav in this folder)"
    )
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
