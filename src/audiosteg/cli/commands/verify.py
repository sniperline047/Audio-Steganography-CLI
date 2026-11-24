"""The verify command."""

import argparse

from audiosteg.algorithms.legacy import HEADER_BITS
from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.accuracy import compare_messages
from audiosteg.cli.commands.reveal import reveal
from audiosteg.cli.options import add_message_options, add_reading_options, file_path, message_source
from audiosteg.cli.results import RevealResult, VerifyResult
from audiosteg.cli.views import View
from audiosteg.core.stego_file import count_message_bytes
from audiosteg.core.wav_io import count_sample_bytes, open_pcm_wav

HELP = "compare a hidden message with the expected one"
EXAMPLES = """examples:
  audiosteg verify song.stego.wav -m "Hello"
  audiosteg verify song.stego.wav --message_file letter.txt
"""


def verify(revealed: RevealResult, expected: str) -> VerifyResult:
    """Compare a message that was found with the expected one."""
    return VerifyResult(revealed, compare_messages(expected, revealed.message))


def largest_message(file: str, legacy: str | None) -> int:
    """Return the size of the largest message that a WAV file can hold."""
    with open_pcm_wav(file) as audio:
        sample_bytes = count_sample_bytes(audio, file)
        samples = sample_bytes // audio.getsampwidth()
    if legacy is not None:
        return max(sample_bytes * LEGACY_ALGORITHMS[legacy].bits_per_byte - HEADER_BITS, 0) // 8
    return max(count_message_bytes(samples, known.bits_per_byte, False) for known in ALGORITHMS.values())


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code, which is 1 if the messages differ."""
    limit = largest_message(args.file, args.legacy)
    expected = message_source(args).read("Expected message: ", limit)
    result = verify(reveal(args, view), expected)
    view.show_verify(result)
    return 0 if result.accuracy.exact_match else 1


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument("file", type=file_path, metavar="FILE", help="the WAV file with the hidden message")
    add_message_options(parser)
    add_reading_options(parser)
