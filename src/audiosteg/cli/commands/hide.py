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
    file_path,
    message_source,
    passphrase_source,
)
from audiosteg.cli.passphrase import PassphraseSource, can_ask
from audiosteg.cli.questions import ask_yes_no
from audiosteg.cli.results import HideResult
from audiosteg.cli.views import View, display_path
from audiosteg.core import crypto
from audiosteg.core.header import container_overhead
from audiosteg.core.message_codec import message_to_bytes
from audiosteg.core.signal_algorithm import SignalAlgorithm, check_library
from audiosteg.core.stego_file import count_message_bytes, hide_message, message_fits
from audiosteg.core.wav_io import AudioSize, measure_input
from audiosteg.errors import CapacityError, PassphraseRequiredError, UnsafeOutputError
from audiosteg.utils.output_path import check_output_path, normalize_output_path
from audiosteg.utils.text import escape_text

HELP = "hide a message in a copy of a WAV file"
EXAMPLES = """examples:
  audiosteg hide sample -m "Hello"            use the included sample
  audiosteg hide song.wav -p                  ask for message and passphrase
  audiosteg hide song.wav -o secret.wav -a lsb_2 --message_file letter.txt
  audiosteg hide song.wav -a lsb_keyed -p     encrypt it and scatter its bits
  printf "Hello" | audiosteg hide song.wav    take the message from a pipe
"""
SAMPLE_FILE = str(files("audiosteg") / "data" / "sample.wav")
SAMPLE_WORD = "sample"
SIZE_ADVICE = "Use a longer audio file or a shorter message."
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


def check_not_source(output_file: str, sources: list[str | None]) -> None:
    """Refuse to replace a file that holds the message or the passphrase."""
    for source in sources:
        if source is not None and os.path.exists(output_file) and os.path.samefile(source, output_file):
            raise UnsafeOutputError("The output path is the message file or the passphrase file.")


def largest_message(size: AudioSize, encrypted: bool) -> int:
    """Return the size of the largest message that fits with any algorithm."""
    return max(
        count_message_bytes(size.samples, known, encrypted, size.channels) for known in ALGORITHMS.values()
    )


def fitting_algorithms(message: str, size: AudioSize, encrypted: bool) -> list[str]:
    """Return the names of the algorithms that can hold a message."""
    length = len(message_to_bytes(message))
    return [
        key
        for key, algorithm in ALGORITHMS.items()
        if message_fits(length, size.samples, algorithm, encrypted, size.channels)
    ]


def find_seconds(length: int, algorithm: SignalAlgorithm, encrypted: bool, frame_rate: int) -> float:
    """Return how many seconds of sound a message of this many bytes needs."""
    return algorithm.needed_frames(container_overhead(encrypted) + length) / frame_rate


def advise(request: HideRequest) -> str:
    """Say how a message that is too large could fit."""
    size, encrypted = measure_input(request.input_file), request.passphrase is not None
    keys = fitting_algorithms(request.message, size, encrypted)
    advice = (
        f"Use the algorithm {keys[0]}, which can hold it, or a longer audio file." if keys else SIZE_ADVICE
    )
    algorithm = ALGORITHMS[request.algorithm]
    if not isinstance(algorithm, SignalAlgorithm):
        return advice
    length = len(message_to_bytes(request.message))
    seconds = find_seconds(length, algorithm, encrypted, size.frame_rate)
    return (
        f"With {request.algorithm}, this message needs at least {seconds:.1f} s of sound like this. {advice}"
    )


def hide(request: HideRequest) -> HideResult:
    """Hide a message."""
    try:
        gain = hide_message(
            request.input_file,
            request.output_file,
            request.message,
            ALGORITHMS[request.algorithm],
            request.passphrase,
            request.overwrite,
        )
    except CapacityError as error:
        raise CapacityError(f"{error} {advise(request)}") from error
    return HideResult(
        request.input_file, request.output_file, request.algorithm, request.passphrase is not None, gain
    )


def may_replace(output_file: str, force: bool) -> bool:
    """Ask before replacing a file. Without a terminal, only --force replaces it."""
    if force:
        return True
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise FileExistsError(f"The output file already exists: {display_path(output_file)}")
    if not ask_yes_no(f"{escape_text(display_path(output_file))} already exists. Overwrite it?"):
        raise CancelledError("Nothing was written.")
    return True


def find_passphrases(args: argparse.Namespace) -> PassphraseSource:
    """Return where the passphrase comes from. A keyed algorithm asks for one if nothing else says where."""
    passphrases = passphrase_source(args)
    if passphrases.wanted or not ALGORITHMS[args.algorithm].keyed:
        return passphrases
    if not can_ask():
        raise PassphraseRequiredError(
            f"{args.algorithm} always encrypts the message. A passphrase is needed."
        )
    return PassphraseSource(prompt=True, file=None)


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    input_file = find_input(args.input)
    size = measure_input(input_file)
    chosen_output = default_output(input_file) if args.output is None else args.output
    output_file, exists = check_output(input_file, chosen_output)
    check_not_source(output_file, [args.message_file, args.passphrase_file])
    overwrite = exists and may_replace(output_file, args.force)
    check_library(ALGORITHMS[args.algorithm])
    passphrases = find_passphrases(args)
    if passphrases.wanted:
        crypto.check_available()
    limit = largest_message(size, passphrases.wanted)
    message = message_source(args).read("Message to hide: ", limit, SIZE_ADVICE)
    passphrase = passphrases.read_new(view.note)
    view.progress("Hiding the message...")
    view.show_hide(hide(HideRequest(input_file, output_file, message, args.algorithm, passphrase, overwrite)))
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument(
        "input",
        type=file_path,
        metavar="INPUT",
        help="the WAV file to copy, or the word sample (./sample means a file)",
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
        "-o",
        "--output",
        type=file_path,
        metavar="OUTPUT",
        help="the new WAV file (default: INPUT.stego.wav in this folder)",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
