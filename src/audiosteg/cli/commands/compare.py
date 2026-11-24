"""The compare command."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from audiosteg.cli.commands.hide import check_output, find_input, may_replace
from audiosteg.cli.errors import UsageError
from audiosteg.cli.options import file_path
from audiosteg.cli.views import View
from audiosteg.utils.output_path import check_output_path

if TYPE_CHECKING:
    from audiosteg.analysis.quality import Quality
    from audiosteg.analysis.samples import Pair, Part

HELP = "measure how much a copy differs from the original"
EXAMPLES = """examples:
  audiosteg compare song.wav song.stego.wav
  audiosteg compare song.wav song.stego.wav --details
  audiosteg compare song.wav song.stego.wav --show snr,changes
  audiosteg compare song.wav song.stego.wav --from 0 --to 0.2
  audiosteg compare song.wav song.stego.wav --save_difference difference.wav
"""
METRICS = ("snr", "psnr", "changes", "where", "waveform")
NUMBERS = METRICS[:4]
SOUNDS = ("original", "encoded", "difference")
EVERY_SOUND = "all"
NO_SOUND_NAMED = "\0"
MINIMUM_WIDTH, MAXIMUM_WIDTH = 20, 500
USUAL_WIDTH = 100
JSON_WIDTH = 80
NUMBER = re.compile(r"[0-9]{1,9}(\.[0-9]{1,9})?")
NO_DIFFERENCE = "There is no difference in what was compared, so nothing was saved."
NOT_A_SOUND = f"--play can have one of these values: {', '.join(SOUNDS)}."
HINT = "To see every number, add --details. To listen, add --play."


@dataclass(frozen=True)
class CompareRequest:
    """What to compare and what to show. Without metrics, the simple summary is shown."""

    original: str
    encoded: str
    metrics: tuple[str, ...] = ()
    start: Fraction | None = None
    end: Fraction | None = None
    width: int | None = None
    gain: Fraction | None = None


@dataclass(frozen=True)
class SavedDifference:
    """The difference was written to a file."""

    file: str
    gain: Fraction
    wanted_gain: Fraction | None


def metric_list(text: str) -> list[str]:
    """Check a list of metrics."""
    chosen = text.split(",")
    if not all(name in METRICS for name in chosen):
        raise UsageError(f"--show needs names separated by commas. Choose from: {', '.join(METRICS)}.")
    return chosen


def in_order(chosen: list[str]) -> tuple[str, ...]:
    """Return the chosen metrics once each, in the order in which they are shown."""
    return tuple(name for name in METRICS if name in chosen)


def sound_name(text: str) -> str:
    """Check what should be played."""
    if text == NO_SOUND_NAMED:
        return EVERY_SOUND
    if text not in SOUNDS:
        raise UsageError(NOT_A_SOUND)
    return text


def number(text: str) -> Fraction:
    """Read a number that is not negative."""
    if NUMBER.fullmatch(text) is None:
        raise UsageError("--from, --to, and --gain need a number such as 2 or 0.5.")
    return Fraction(text)


def gain_number(text: str) -> Fraction:
    """Read a gain, which can only make the difference louder."""
    gain = number(text)
    if gain < 1:
        raise UsageError("--gain needs a number from 1 on.")
    return gain


def width_number(text: str) -> int:
    """Read the width of a drawing."""
    if re.fullmatch("[0-9]{1,9}", text) is None or not MINIMUM_WIDTH <= int(text) <= MAXIMUM_WIDTH:
        raise UsageError(f"--width needs a whole number from {MINIMUM_WIDTH} to {MAXIMUM_WIDTH}.")
    return int(text)


def check_options(args: argparse.Namespace) -> None:
    """Refuse options that contradict each other."""
    if args.json and args.play is not None:
        raise UsageError("--play cannot be used with --json.")
    if (
        args.gain is not None
        and args.play not in (EVERY_SOUND, "difference")
        and args.save_difference is None
    ):
        raise UsageError("--gain needs --play, --play difference, or --save_difference.")
    if args.force and args.save_difference is None:
        raise UsageError("--force needs --save_difference.")
    if args.width is not None and not args.details and "waveform" not in args.show:
        raise UsageError("--width needs --details or --show waveform.")
    if args.start is not None and args.end is not None and args.start >= args.end:
        raise UsageError("--from must be smaller than --to.")


def find_part(pair: Pair, start: Fraction | None, end: Fraction | None) -> Part:
    """Return the part of the files between two times."""
    from audiosteg.analysis.samples import Part

    if pair.frames == 0 and (start is not None or end is not None):
        raise UsageError("The files have no samples, so leave out --from and --to.")
    rate = pair.format.frame_rate
    first = 0 if start is None else int(start * rate)
    last = pair.frames if end is None else int(end * rate)
    if last > pair.frames or (start is not None and first >= pair.frames):
        duration = pair.frames * 1000 // rate / 1000
        raise UsageError(f"--from and --to must be inside the audio, which is {duration:.3f} s long.")
    if first >= last and (start is not None or end is not None):
        raise UsageError("There is no sample between --from and --to. Choose a longer part.")
    return Part(first, last - first)


def waveforms(pair: Pair, part: Part, columns: int) -> dict[str, list[int]]:
    """Return the largest samples along the original, the encoded file, and their difference."""
    from audiosteg.analysis.waveform import difference_peaks, peaks

    return {
        "original": peaks(pair.original, part, columns),
        "encoded": peaks(pair.encoded, part, columns),
        "difference": difference_peaks(pair, part, columns),
    }


def count_columns(request: CompareRequest, view: View) -> int:
    """Return how many columns a waveform has. It fits in a terminal, and does not matter to JSON."""
    if view.as_json:
        return request.width or JSON_WIDTH
    available = max(view.out.console.width, 1)
    if request.width is None:
        return min(available, USUAL_WIDTH)
    return min(available, request.width) if view.out.is_terminal else request.width


def check_difference_output(request: CompareRequest, chosen_path: str) -> tuple[str, bool]:
    """Refuse an unsafe path. Return it normalized, and whether a file would be replaced."""
    output_file, exists = check_output(request.original, chosen_path)
    check_output_path(request.encoded, output_file, overwrite=True)
    return output_file, exists


def save_difference(
    request: CompareRequest, pair: Pair, quality: Quality, output_file: str, overwrite: bool
) -> SavedDifference:
    """Write the amplified difference to a file."""
    from audiosteg.analysis.difference import choose_gain, write_difference
    from audiosteg.utils.safe_write import safe_output

    gain = choose_gain(quality.largest_change, pair.format.full_scale, request.gain)
    with safe_output(request.original, output_file, overwrite) as destination:
        write_difference(destination, pair, quality.part, gain)
        check_output_path(request.encoded, output_file, overwrite)
    return SavedDifference(output_file, gain, request.gain)


def play_sounds(request: CompareRequest, sound: str, view: View) -> None:
    """Play one sound or all of them."""
    from audiosteg.analysis.difference import choose_gain, write_difference, write_encoded, write_original
    from audiosteg.analysis.quality import measure
    from audiosteg.analysis.samples import open_pair, seconds
    from audiosteg.cli.compare_view import format_gain
    from audiosteg.cli.player import play_private

    with open_pair(request.original, request.encoded) as pair:
        part = find_part(pair, request.start, request.end)
        duration = float(seconds(part.frames, pair.format))
        if sound in (EVERY_SOUND, "original"):
            view.note(f"Playing the original ({duration:.3f} s). Ctrl-C stops.")
            play_private(lambda target: write_original(target, pair, part), duration)
        if sound in (EVERY_SOUND, "encoded"):
            view.note(f"Playing the encoded file ({duration:.3f} s). Ctrl-C stops.")
            play_private(lambda target: write_encoded(target, pair, part), duration)
        if sound not in (EVERY_SOUND, "difference"):
            return
        quality = measure(pair, part)
        if quality.identical:
            view.note("There is no difference to play in what was compared.")
            return
        gain = choose_gain(quality.largest_change, pair.format.full_scale, request.gain)
        view.note(
            f"Playing the difference, {format_gain(gain, request.gain)} ({duration:.3f} s). Ctrl-C stops."
        )
        play_private(lambda target: write_difference(target, pair, part, gain), duration)


def check_pair(request: CompareRequest) -> None:
    """Refuse files that cannot be compared."""
    from audiosteg.analysis.samples import open_pair

    with open_pair(request.original, request.encoded):
        pass


def compare(request: CompareRequest, view: View, save_to: str | None = None, force: bool = False) -> None:
    """Compare two files, show the result, and save the difference if that is wanted."""
    from audiosteg.analysis.quality import measure
    from audiosteg.analysis.samples import open_pair
    from audiosteg.cli.compare_view import show_comparison

    with open_pair(request.original, request.encoded) as pair:
        part = find_part(pair, request.start, request.end)
        output_file, exists = ("", False) if save_to is None else check_difference_output(request, save_to)
        view.progress("Comparing the files...")
        quality = measure(pair, part)
        drawings = None
        if "waveform" in request.metrics:
            drawings = waveforms(pair, part, count_columns(request, view))
        saved = None
        if save_to is not None and not quality.identical:
            overwrite = exists and may_replace(output_file, force)
            saved = save_difference(request, pair, quality, output_file, overwrite)
    show_comparison(view, request, quality, drawings, saved)
    if save_to is not None and saved is None:
        view.note(NO_DIFFERENCE)


def run(args: argparse.Namespace, view: View) -> int:
    """Run the command. Return the exit code."""
    check_options(args)
    request = CompareRequest(
        find_input(args.original),
        find_input(args.encoded),
        METRICS if args.details else in_order(args.show),
        args.start,
        args.end,
        args.width,
        args.gain,
    )
    if args.play is not None:
        from audiosteg.cli.player import check_player

        check_player()
    try:
        compare(request, view, args.save_difference, args.force)
    except FileExistsError as error:
        error.add_note("Add --force to replace it, or choose another name for the difference.")
        raise
    if args.play is not None:
        play_sounds(request, args.play, view)
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options of this command."""
    parser.add_argument(
        "original",
        type=file_path,
        metavar="ORIGINAL",
        help="the WAV file before hiding, or the word sample (./sample means a file)",
    )
    parser.add_argument("encoded", type=file_path, metavar="ENCODED", help="the copy that hide made")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--details", action="store_true", help="show and explain every metric")
    group.add_argument(
        "--show",
        action="extend",
        type=metric_list,
        default=[],
        metavar="NAMES",
        help=f"show only these, separated by commas: {', '.join(METRICS)}",
    )
    parser.add_argument(
        "--from", dest="start", type=number, metavar="SECONDS", help="start here (default: the start)"
    )
    parser.add_argument(
        "--to", dest="end", type=number, metavar="SECONDS", help="stop here (default: the end)"
    )
    parser.add_argument(
        "--width",
        type=width_number,
        metavar="COLUMNS",
        help=f"width of the waveforms, {MINIMUM_WIDTH} to {MAXIMUM_WIDTH} (default: fit the terminal)",
    )
    parser.add_argument(
        "--play",
        nargs="?",
        const=EVERY_SOUND,
        type=sound_name,
        metavar="WHAT",
        help=f"listen to {', '.join(SOUNDS)}, or without a value to all three",
    )
    parser.add_argument(
        "--gain",
        type=gain_number,
        metavar="N",
        help="amplify the difference N times, up to a safe level (default: up to that level)",
    )
    parser.add_argument(
        "--save_difference",
        type=file_path,
        metavar="FILE",
        help="write the amplified difference to a WAV file",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing difference file")
