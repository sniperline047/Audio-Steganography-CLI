"""The reveal command, and reading messages for other commands."""

import argparse
from dataclasses import dataclass

from audiosteg.algorithms.detection import decode, detect
from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.options import add_reading_options, file_path, passphrase_source
from audiosteg.cli.passphrase import BYTE_ORDER_MARK, PassphraseSource
from audiosteg.cli.results import RevealResult
from audiosteg.cli.views import View
from audiosteg.core import crypto
from audiosteg.core.stego_file import read_header
from audiosteg.errors import NoMessageError, NotEncryptedError, WrongPassphraseError

HELP = "read a hidden message"
EXAMPLES = """examples:
  audiosteg reveal song.stego.wav
  audiosteg reveal song.stego.wav > message.txt
  audiosteg reveal song.stego.wav --passphrase_file key.txt
  audiosteg reveal old.wav --legacy basic
"""


@dataclass(frozen=True)
class HiddenMessage:
    """Where a message is and how to read it."""

    file: str
    algorithm: str
    legacy: bool
    encrypted: bool


def find_message(file: str, algorithm: str | None = None, legacy: str | None = None) -> HiddenMessage:
    """
    Find out how a message is hidden.

    :param file: Path to the encoded audio file
    :param algorithm: The name of the algorithm, or None to detect it
    :param legacy: The name of an algorithm of older versions, which are not detected
    :return: How to read the message
    """
    if legacy is not None:
        return HiddenMessage(file, legacy, legacy=True, encrypted=False)
    if algorithm is not None:
        header = read_header(file, ALGORITHMS[algorithm])
        if header is None:
            error = NoMessageError(f"No message hidden with {algorithm} was found.")
            error.add_note(
                "To detect the algorithm, leave out -a. For a file of an older version, use --legacy."
            )
            raise error
        return HiddenMessage(file, algorithm, legacy=False, encrypted=header.encrypted)
    detected = detect(file)
    if detected is None:
        raise NoMessageError("No hidden message was found.")
    keys = [key for key, known in ALGORITHMS.items() if known is detected[0]]
    return HiddenMessage(file, keys[0], legacy=False, encrypted=detected[1].encrypted)


def read_message(hidden: HiddenMessage, passphrase: str | None) -> RevealResult:
    """Read a message."""
    algorithm = LEGACY_ALGORITHMS[hidden.algorithm] if hidden.legacy else ALGORITHMS[hidden.algorithm]
    message = decode(hidden.file, algorithm, passphrase=passphrase)
    return RevealResult(hidden.file, hidden.algorithm, hidden.legacy, passphrase is not None, message)


def get_passphrase(hidden: HiddenMessage, passphrases: PassphraseSource, view: View) -> str | None:
    """Get the passphrase of an encrypted message, and refuse one that cannot protect a message."""
    if hidden.encrypted:
        crypto.check_available()
        return passphrases.read(view.note)
    if passphrases.wanted:
        raise NotEncryptedError(
            "The hidden message is not encrypted, so the passphrase cannot protect it. It may not be the "
            "message you expect. To read it anyway, leave out the passphrase option."
        )
    return None


def reveal(args: argparse.Namespace, view: View) -> RevealResult:
    """Read the message that the command line describes."""
    hidden = find_message(args.file, args.algorithm, args.legacy)
    passphrase = get_passphrase(hidden, passphrase_source(args), view)
    try:
        return read_message(hidden, passphrase)
    except WrongPassphraseError as error:
        if passphrase is not None and passphrase.startswith(BYTE_ORDER_MARK):
            error.add_note(
                "The passphrase file starts with a byte order mark (BOM), which counts as part of the "
                "passphrase. Try the file saved as UTF-8 without BOM."
            )
        raise


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    view.show_reveal(reveal(args, view))
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument("file", type=file_path, metavar="FILE", help="the WAV file with the hidden message")
    add_reading_options(parser)
