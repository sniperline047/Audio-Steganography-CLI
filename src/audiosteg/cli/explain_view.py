"""Show how an algorithm hides a character."""

import unicodedata
from collections.abc import Callable

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.analysis.walkthrough import DEMO_SEED, Walkthrough, largest_possible_change
from audiosteg.cli.change_view import change_fields, group_fields, show_groups, show_samples
from audiosteg.cli.commands.hide import SAMPLE_FILE, SAMPLE_WORD
from audiosteg.cli.views import View, clean_for_json, count_word, describe, display_path, format_time
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.signal_algorithm import SignalAlgorithm

FROM_THE_START = "The hide command itself starts at the first sample and puts a header before the message."
DEMO = f'This is a demo: the seed "{DEMO_SEED}" made the order. It never uses a passphrase of yours.'
SCATTERED = (
    "The hide command itself makes the order from your passphrase and a random salt, "
    "encrypts the message, and scatters a header with it."
)
ALREADY_HELD = (
    "These samples already held the bits, so nothing had to change. "
    "To see a change, try another character (--letter) or another file (--file)."
)


def show_letter(letter: str) -> str:
    """Return a character in quotes. A mark that joins the character before it is named instead."""
    if unicodedata.category(letter).startswith("M"):
        return f"U+{ord(letter):04X}, which joins the character before it,"
    quote = '"' if letter == "'" else "'"
    return f"{quote}{letter}{quote}"


def show_list(view: View) -> None:
    """Show one line about every algorithm."""
    if view.as_json:
        view.show_json("explain", True, {"algorithms": describe(ALGORITHMS)})
        return
    rows = [(key, known.explanation) for key, known in ALGORITHMS.items()]
    view.out.panel("What can be explained", rows, "cyan")
    view.note(f"To see one work, name it: audiosteg explain {next(iter(ALGORITHMS))}")


def show_step(view: View, title: str, *lines: str) -> None:
    """Show the title and the lines of one step."""
    view.out.spans((title, "bold cyan"))
    for line in lines:
        view.out.line(line)


def show_character(view: View, letter: str, data: bytes) -> None:
    """Show the bytes and the bits of the character."""
    show_step(
        view,
        "Step 1: turn the character into bits",
        f"The character {show_letter(letter)} is {count_word(len(data), 'byte')} in UTF-8:",
        *[f"  {byte:#04x} = {byte:08b}" for byte in data],
    )


def source_name(path: str) -> str:
    """Return the name of the file that the sound comes from."""
    return "the included tune" if path == SAMPLE_FILE else display_path(path)


def show_place(view: View, path: str, walkthrough: Walkthrough, algorithm: Algorithm) -> None:
    """Show which samples are used."""
    name = source_name(path)
    sample_format = walkthrough.format
    count = len(walkthrough.changes)
    time = format_time(walkthrough.first_frame, sample_format.frame_rate)
    silence = ["The whole file is silent."] if walkthrough.silent else []
    if algorithm.keyed:
        where = [f"{count_word(count, 'sample')}, scattered over {name}.", *silence, DEMO, SCATTERED]
    else:
        place = (
            f"{count_word(count, 'sample')} of {name}, from {time} on (frame {walkthrough.first_frame:,})."
        )
        where = [place, *silence, FROM_THE_START]
    show_step(view, "Step 2: take real samples", *where)


def show_changes(view: View, walkthrough: Walkthrough, algorithm: Algorithm) -> None:
    """Show the lowest bits of the samples before and after."""
    how = [algorithm.how] if algorithm.how else []
    show_step(view, "Step 3: put the bits into the samples", *how)
    if algorithm.parity:
        show_groups(view, walkthrough.groups)
    else:
        show_samples(view, walkthrough.changes, algorithm)
    if not any(change.change for change in walkthrough.changes):
        view.out.line(ALREADY_HELD)


def show_result(view: View, walkthrough: Walkthrough, algorithm: Algorithm) -> None:
    """Show what the changes mean and that the character can be read again."""
    changed = sum(change.change != 0 for change in walkthrough.changes)
    largest = max(abs(change.change) for change in walkthrough.changes)
    show_step(
        view,
        "Step 4: read the bits back",
        f"Reading the same bits gives {show_letter(walkthrough.read_back)} again.",
        f"{changed} of {count_word(len(walkthrough.changes), 'sample')} changed, by at most {largest} here. "
        f"This algorithm can change a sample by at most {largest_possible_change(algorithm)}, "
        f"out of {walkthrough.format.full_scale:,}.",
    )


def show_sentences(view: View, algorithm: Algorithm | SignalAlgorithm) -> None:
    """Show the strengths and the weaknesses."""
    for title, sentences in (("Strengths", algorithm.strengths), ("Weaknesses", algorithm.weaknesses)):
        if sentences:
            show_step(view, title, *[f"- {sentence}" for sentence in sentences])


def show_advice(view: View, key: str, algorithm: Algorithm) -> None:
    """Show the strengths, the weaknesses, and commands to try."""
    show_sentences(view, algorithm)
    passphrase = " -p" if algorithm.keyed else ""
    show_step(
        view,
        "Try it",
        f'  audiosteg hide {SAMPLE_WORD} -m "Hello" -a {key}{passphrase}',
        f"  audiosteg compare {SAMPLE_WORD} {SAMPLE_WORD}.stego.wav --details",
    )


def show_steps(
    view: View,
    algorithm: Algorithm | SignalAlgorithm,
    steps: list[Callable[[], None]],
    pause: Callable[[], None] | None,
) -> None:
    """Show the name of an algorithm and every step, with a pause between them if that is wanted."""
    view.out.spans((algorithm.name, "bold"))
    view.out.line(algorithm.explanation)
    for number, step in enumerate(steps):
        if pause is not None and number:
            pause()
        view.out.line("")
        step()


def show_walkthrough(
    view: View,
    key: str,
    path: str,
    walkthrough: Walkthrough,
    algorithm: Algorithm,
    pause: Callable[[], None] | None,
) -> None:
    """Show what happened to real samples."""
    if view.as_json:
        fields = {
            **describe({key: algorithm})[0],
            "letter": walkthrough.letter,
            "utf_8": walkthrough.data.hex(),
            "file": clean_for_json(path),
            "first_frame": walkthrough.first_frame,
            "silent": walkthrough.silent,
            "how": algorithm.how,
            "demo_seed": DEMO_SEED if algorithm.keyed else None,
            "samples": [change_fields(change) for change in walkthrough.changes],
            "groups": [group_fields(group) for group in walkthrough.groups] if algorithm.parity else [],
            "read_back": walkthrough.read_back,
            "largest_possible_change": largest_possible_change(algorithm),
            "strengths": list(algorithm.strengths),
            "weaknesses": list(algorithm.weaknesses),
        }
        view.show_json("explain", True, fields)
        return
    steps: list[Callable[[], None]] = [
        lambda: show_character(view, walkthrough.letter, walkthrough.data),
        lambda: show_place(view, path, walkthrough, algorithm),
        lambda: show_changes(view, walkthrough, algorithm),
        lambda: show_result(view, walkthrough, algorithm),
        lambda: show_advice(view, key, algorithm),
    ]
    show_steps(view, algorithm, steps, pause)
