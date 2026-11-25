"""The reveal command, and reading messages for other commands."""

import argparse
from dataclasses import dataclass

from audiosteg.algorithms.detection import decode, detect, undetectable_here
from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS, reading_key
from audiosteg.cli.errors import CHECK_THE_FILE, NO_MESSAGE_HINT
from audiosteg.cli.options import add_reading_options, file_path, passphrase_source
from audiosteg.cli.passphrase import BYTE_ORDER_MARK, PassphraseSource
from audiosteg.cli.results import RevealResult
from audiosteg.cli.views import View
from audiosteg.core import crypto
from audiosteg.core.stego_file import read_header
from audiosteg.core.wav_io import open_pcm_wav
from audiosteg.errors import NoMessageError, NotEncryptedError, WrongPassphraseError

HELP = "read a hidden message"
EXAMPLES = """examples:
  audiosteg reveal song.stego.wav
  audiosteg reveal song.stego.wav > message.txt
  audiosteg reveal song.stego.wav --passphrase_file key.txt
  audiosteg reveal old.wav --legacy basic
"""
KEYED_ALGORITHM = next(key for key, known in ALGORITHMS.items() if known.keyed)


def not_checked(keys: tuple[str, ...]) -> list[str]:
    """Return a sentence about the algorithms whose messages could not be looked for, if there are any."""
    if not keys:
        return []
    return [
        f"Messages of {' and '.join(keys)} cannot be detected here, because NumPy is missing. "
        'To install it, run: pip install ".[signal]"'
    ]


@dataclass(frozen=True)
class HiddenMessage:
    """Where a message is, or may be, and how to read it."""

    file: str
    algorithm: str
    legacy: bool
    encrypted: bool


def find_message(
    file: str, algorithm: str | None = None, legacy: str | None = None, has_passphrase: bool = False
) -> HiddenMessage:
    """
    Find out how a message is hidden.

    :param file: Path to the encoded audio file
    :param algorithm: The name of the algorithm, or None to detect it
    :param legacy: The name of an algorithm of older versions, which are not detected
    :param has_passphrase: Whether there is a passphrase to try if no message is detected
    :return: How to read the message
    """
    if legacy is not None:
        return HiddenMessage(file, legacy, legacy=True, encrypted=False)
    if algorithm is not None and ALGORITHMS[algorithm].keyed:
        with open_pcm_wav(file):
            return HiddenMessage(file, algorithm, legacy=False, encrypted=True)
    if algorithm is not None:
        header = read_header(file, ALGORITHMS[algorithm])
        if header is None:
            error = NoMessageError(f"No message hidden with {algorithm} was found.")
            error.add_note(
                "To detect the algorithm, leave out -a. For a file of an older version, use --legacy."
            )
            raise error
        return HiddenMessage(file, reading_key(algorithm), legacy=False, encrypted=header.encrypted)
    detected = detect(file)
    if detected is None and has_passphrase:
        return HiddenMessage(file, KEYED_ALGORITHM, legacy=False, encrypted=True)
    if detected is None:
        error = NoMessageError("No hidden message was found.")
        error.add_note(NO_MESSAGE_HINT)
        error.add_note(f"If it was hidden with {KEYED_ALGORITHM}, add -p and the passphrase that hid it.")
        for sentence in not_checked(undetectable_here()):
            error.add_note(sentence)
        raise error
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
    passphrases = passphrase_source(args)
    hidden = find_message(args.file, args.algorithm, args.legacy, passphrases.wanted)
    passphrase = get_passphrase(hidden, passphrases, view)
    try:
        return read_message(hidden, passphrase)
    except (NoMessageError, WrongPassphraseError) as error:
        if hidden.legacy:
            others = " or ".join(key for key in LEGACY_ALGORITHMS if key != hidden.algorithm)
            error.add_note(f"{CHECK_THE_FILE} Or try another old algorithm: --legacy {others}.")
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
