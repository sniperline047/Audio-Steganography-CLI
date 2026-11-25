"""Show results and errors as text or JSON. All text from outside is escaped here."""

import contextlib
import json
import os
from collections.abc import Mapping
from typing import Any, TextIO

from rich.cells import cell_len
from rich.console import Console, detect_legacy_windows
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.accuracy import AccuracyResult
from audiosteg.cli.errors import OutputClosedError, UsageError, error_type, explain, next_step
from audiosteg.cli.logo import MINIMUM_WIDTH, draw_logo, plain_title
from audiosteg.cli.results import HideResult, RevealResult, VerifyResult
from audiosteg.core.algorithm import Algorithm, LegacyAlgorithm
from audiosteg.core.signal_algorithm import SignalAlgorithm
from audiosteg.utils.text import escape_text

DRAWING_CHARACTERS = "╭─╮│╰╯▀▄"
DUMB_TERMINALS = ("dumb", "unknown")
NOT_ENCRYPTED = "This message was not encrypted, so anyone could have written it."
ENCRYPTED = "This message was encrypted."
MADE_QUIETER = (
    "The result would have been too loud, so the whole file was made quieter ({:.1%} of its level)."
)
COLUMN_GAP = 2
PANEL_FRAME = 6
FEWEST_DIGITS, MOST_DIGITS = 3, 9
Rows = list[tuple[str, str]]


def is_dumb_terminal() -> bool:
    """Say whether the terminal can only show lines of text."""
    return os.environ.get("TERM", "").lower() in DUMB_TERMINALS


def can_draw(stream: TextIO, plain: bool) -> bool:
    """Say whether boxes and colours can be shown."""
    if plain or not stream.isatty() or is_dumb_terminal() or detect_legacy_windows():
        return False
    try:
        DRAWING_CHARACTERS.encode(stream.encoding)
    except UnicodeEncodeError:
        return False
    return True


def clean_for_json(text: str) -> str:
    """Replace lone surrogates, which are not valid in JSON text."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def protection(encrypted: bool) -> str:
    """Say whether a message that was read had been encrypted."""
    return ENCRYPTED if encrypted else NOT_ENCRYPTED


def count_word(count: int, word: str) -> str:
    """Return a number with thousands separators and a word in the right form."""
    return f"{count:,} {word}" if count == 1 else f"{count:,} {word}s"


def format_time(frame: int, frame_rate: int) -> str:
    """Return the time of a frame with as many digits as --from and --to need to find this frame again."""
    for digits in range(FEWEST_DIGITS, MOST_DIGITS + 1):
        unit = 10**digits
        units = -(-frame * unit // frame_rate)
        if units * frame_rate // unit == frame:
            break
    else:
        units = frame * unit // frame_rate
    return f"{units // unit}.{units % unit:0{digits}} s"


def yes_no(value: bool) -> str:
    """Return yes or no."""
    return "yes" if value else "no"


def display_path(path: str) -> str:
    """Return an absolute path relative to the current folder if it is inside that folder."""
    try:
        folder = os.path.realpath(os.curdir)
        inside = os.path.commonpath([folder, path]) == folder
        return os.path.relpath(path, folder) if inside else path
    except (OSError, ValueError):
        return path


def format_percentage(accuracy: AccuracyResult) -> str:
    """Return a percentage with two decimals. Only an exact match is shown as 100.00%."""
    percentage = accuracy.percentage if accuracy.exact_match else min(accuracy.percentage, 99.99)
    return f"{percentage:.2f}%"


class Screen:
    """One output stream, and what it can show."""

    def __init__(self, stream: TextIO, plain: bool) -> None:
        """Find out what the stream can show."""
        self.stream = stream
        self.is_terminal = stream.isatty()
        self.drawn = can_draw(stream, plain)
        self.coloured = self.drawn and not os.environ.get("NO_COLOR")
        self.console = Console(
            file=stream,
            force_terminal=self.drawn,
            color_system="auto" if self.coloured else None,
            markup=False,
            emoji=False,
            highlight=False,
        )

    def write(self, text: str) -> None:
        """Write text, and stop if nobody can see it."""
        try:
            self.stream.write(text)
            self.stream.flush()
        except OSError as error:
            raise OutputClosedError("The output was closed.") from error

    def line(self, text: str, style: str = "", start: str = "") -> None:
        """Write one escaped line at once, in colour if possible, after the start."""
        shown = Text(start).append(escape_text(text), style if self.coloured else "")
        if self.coloured and style:
            self.draw(shown, soft_wrap=True)
        else:
            self.write(f"{shown.plain}\n")

    def spans(self, *spans: tuple[str, str]) -> None:
        """Write one line of escaped texts, each with its style, in colour if possible."""
        shown = Text.assemble(*[(escape_text(text), style if self.coloured else "") for text, style in spans])
        if self.coloured:
            self.draw(shown, soft_wrap=True)
        else:
            self.write(f"{shown.plain}\n")

    def draw(self, renderable: Panel | Text, soft_wrap: bool = False) -> None:
        """Draw something. Rich never writes to the stream itself, so it cannot end the program."""
        with self.console.capture() as captured:
            self.console.print(renderable, soft_wrap=soft_wrap)
        self.write(captured.get())

    def fits_in_panel(self, rows: Rows, path: str) -> bool:
        """Say whether a path fits on one line of a panel."""
        names = max(cell_len(name) for name, _ in rows)
        return names + COLUMN_GAP + cell_len(escape_text(path)) + PANEL_FRAME <= self.console.width

    def panel(self, title: str, rows: Rows, style: str) -> None:
        """Show names and values in a panel, or as lines where panels cannot be drawn."""
        if not self.drawn:
            self.line(title)
            for name, value in rows:
                self.line(f"{name}: {value}")
            return
        table = Table.grid(padding=(0, COLUMN_GAP, 0, 0))
        table.add_column(style="bold", no_wrap=True)
        table.add_column(overflow="fold")
        for name, value in rows:
            table.add_row(Text(name), Text(escape_text(value)))
        self.draw(Panel(table, title=Text(title), title_align="left", border_style=style, expand=False))


class View:
    """Show what the program did, as text or as one JSON document."""

    def __init__(self, stdout: TextIO, stderr: TextIO, *, plain: bool = False, as_json: bool = False):
        """Prepare both output streams."""
        self.plain = plain
        self.as_json = as_json
        self.out = Screen(stdout, plain)
        self.err = Screen(stderr, plain)

    def show_json(self, command: str | None, ok: bool, fields: dict[str, Any]) -> None:
        """Write the only JSON document."""
        self.out.write(json.dumps({"ok": ok, "command": command, **fields}) + "\n")

    def note(self, text: str, style: str = "", start: str = "") -> None:
        """Write a line for the person, away from the result. Nobody has to see it."""
        with contextlib.suppress(OutputClosedError):
            self.err.line(text, style, start)

    def progress(self, text: str) -> None:
        """Say what is happening, if a person is watching."""
        if self.err.is_terminal and not self.as_json:
            self.note(text)

    def show_error(self, error: BaseException, command: str | None, exit_code: int) -> None:
        """Explain an error and say what to do next."""
        for_command = command is not None or self.as_json or isinstance(error, UsageError)
        hint = next_step(error) if for_command else None
        if self.as_json and not isinstance(error, OutputClosedError):
            details = {
                "type": error_type(error),
                "message": clean_for_json(explain(error)),
                "hint": hint,
                "exit_code": exit_code,
            }
            self.show_json(command, False, {"error": details})
            return
        self.note(f"Error: {explain(error)}", "bold red")
        if hint is not None:
            self.note(hint)

    def show_hide(self, result: HideResult) -> None:
        """Show where a message was hidden."""
        if self.as_json:
            fields = {
                "input": clean_for_json(result.input_file),
                "output": clean_for_json(result.output_file),
                "algorithm": result.algorithm,
                "encrypted": result.encrypted,
                "gain": result.gain,
            }
            self.show_json("hide", True, fields)
            return
        path = display_path(result.output_file)
        output = ("Output", path)
        rows = [
            ("Algorithm", result.algorithm),
            ("Encrypted", "yes" if result.encrypted else "no, anyone can read the message"),
        ]
        fits = not self.out.drawn or self.out.fits_in_panel([output, *rows], path)
        self.out.panel("Message hidden", [output, *rows] if fits else rows, "green")
        if not fits:
            self.out.line("Output:")
            self.out.line(path)
        if result.gain < 1:
            self.note(MADE_QUIETER.format(result.gain))

    def show_reveal(self, result: RevealResult) -> None:
        """Write the message to stdout and everything else to stderr, the protection line last."""
        if self.as_json:
            fields = {**reveal_fields(result), "message": clean_for_json(result.message)}
            self.show_json("reveal", True, fields)
            return
        start = ""
        if not result.message:
            self.note("The message is empty.")
        elif self.out.is_terminal:
            self.out.line(result.message)
        else:
            self.write_exactly(result.message)
            start = "\n" if self.err.is_terminal else ""
        self.note(protection(result.encrypted), "green" if result.encrypted else "yellow", start)

    def write_exactly(self, message: str) -> None:
        """Write a message as UTF-8, whatever the encoding of the output is."""
        try:
            self.out.stream.flush()
            self.out.stream.buffer.write(message.encode("utf-8"))
            self.out.stream.flush()
        except OSError as error:
            raise OutputClosedError("The output was closed.") from error

    def show_verify(self, result: VerifyResult) -> None:
        """Show how much of the message matches."""
        accuracy = result.accuracy
        if self.as_json:
            fields = {
                **reveal_fields(result.revealed),
                "exact_match": accuracy.exact_match,
                "percentage": accuracy.percentage,
                "expected_length": accuracy.expected_length,
                "found_length": accuracy.decoded_length,
            }
            self.show_json("verify", True, fields)
            return
        rows = [
            ("Exact match", yes_no(accuracy.exact_match)),
            ("Accuracy", format_percentage(accuracy)),
            ("Expected length", str(accuracy.expected_length)),
            ("Found length", str(accuracy.decoded_length)),
            ("Protection", protection(result.revealed.encrypted)),
        ]
        title = "The message matches" if accuracy.exact_match else "The message does not match"
        self.out.panel(title, rows, "green" if accuracy.exact_match else "red")

    def show_algorithms(self) -> None:
        """Show every algorithm."""
        if self.as_json:
            fields = {"algorithms": describe(ALGORITHMS), "legacy": describe(LEGACY_ALGORITHMS)}
            self.show_json("algorithms", True, fields)
            return
        rows = [(key, algorithm.explanation) for key, algorithm in ALGORITHMS.items()]
        legacy_rows = [(key, algorithm.explanation) for key, algorithm in LEGACY_ALGORITHMS.items()]
        self.out.panel("Algorithms (-a)", rows, "cyan")
        self.out.panel("Old files (--legacy)", legacy_rows, "cyan")

    def show_version(self, version: str) -> None:
        """Show the version."""
        if self.as_json:
            self.show_json(None, True, {"version": version})
        else:
            self.out.line(f"audiosteg {version}")

    def show_welcome(self) -> None:
        """Show the logo, or a title where the logo cannot be drawn."""
        console = self.out.console
        if self.out.coloured and console.color_system == "truecolor" and console.width >= MINIMUM_WIDTH:
            self.out.write("\n")
            self.out.draw(draw_logo())
            self.out.write("\n")
        else:
            self.out.write(f"{plain_title()}\n\n")


def reveal_fields(result: RevealResult) -> dict[str, Any]:
    """Return the JSON fields that describe a message, without the message."""
    return {
        "file": clean_for_json(result.file),
        "algorithm": result.algorithm,
        "legacy": result.legacy,
        "encrypted": result.encrypted,
    }


def describe(
    algorithms: Mapping[str, Algorithm | SignalAlgorithm] | Mapping[str, LegacyAlgorithm],
) -> list[dict[str, Any]]:
    """Return the JSON fields that describe algorithms."""
    return [
        {
            "key": key,
            "name": algorithm.name,
            "bits_per_byte": algorithm.bits_per_byte,
            "explanation": algorithm.explanation,
            **group_fields(algorithm),
        }
        for key, algorithm in algorithms.items()
    ]


def group_fields(algorithm: Algorithm | SignalAlgorithm | LegacyAlgorithm) -> dict[str, Any]:
    """Return the JSON fields that only an algorithm that can hide messages has."""
    if isinstance(algorithm, LegacyAlgorithm):
        return {}
    return {
        "samples_per_group": algorithm.samples_per_group,
        "needs_passphrase": algorithm.keyed,
        "reads_like": next((key for key, known in ALGORITHMS.items() if known is algorithm.reads_like), None),
        "frames_per_bit": algorithm.block_frames if isinstance(algorithm, SignalAlgorithm) else None,
    }
