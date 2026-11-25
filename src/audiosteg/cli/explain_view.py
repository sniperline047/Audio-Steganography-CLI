"""Show how an algorithm hides a character."""

import unicodedata
from collections.abc import Callable

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.analysis.walkthrough import DEMO_SEED, Walkthrough, largest_possible_change
from audiosteg.cli.change_view import change_fields, group_fields, show_groups, show_samples
from audiosteg.cli.commands.hide import SAMPLE_FILE, SAMPLE_WORD
from audiosteg.cli.views import View, clean_for_json, count_word, describe, display_path, format_time

REPLACED = " (old files only)"
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
        fields = {"algorithms": describe(ALGORITHMS), "legacy": describe(LEGACY_ALGORITHMS)}
        view.show_json("explain", True, fields)
        return
    rows = [(key, known.explanation) for key, known in ALGORITHMS.items()]
    rows += [(key, f"{known.explanation}{REPLACED}") for key, known in LEGACY_ALGORITHMS.items()]
    view.out.panel("What can be explained", rows, "cyan")
    view.note(f"To see one work, name it: audiosteg explain {next(iter(ALGORITHMS))}")


def show_legacy(view: View, key: str) -> None:
    """Explain why an algorithm of older versions was replaced."""
    algorithm = LEGACY_ALGORITHMS[key]
    if view.as_json:
        fields = {**describe({key: algorithm})[0], "legacy": True}
        view.show_json("explain", True, {**fields, "replaced_because": list(algorithm.replaced_because)})
        return
    view.out.spans((algorithm.name, "bold"))
    view.out.line(algorithm.explanation)
    view.out.line("It can read old files, but it cannot hide new messages. It was replaced because:")
    for reason in algorithm.replaced_because:
        view.out.line(f"- {reason}")
    view.out.line(f"To read an old file: audiosteg reveal old.wav --legacy {key}")


def show_step(view: View, title: str, *lines: str) -> None:
    """Show the title and the lines of one step."""
    view.out.spans((title, "bold cyan"))
    for line in lines:
        view.out.line(line)


def show_character(view: View, walkthrough: Walkthrough) -> None:
    """Show the bytes and the bits of the character."""
    data = walkthrough.data
    show_step(
        view,
        "Step 1: turn the character into bits",
        f"The character {show_letter(walkthrough.letter)} is {count_word(len(data), 'byte')} in UTF-8:",
        *[f"  {byte:#04x} = {byte:08b}" for byte in data],
    )


def show_place(view: View, key: str, path: str, walkthrough: Walkthrough) -> None:
    """Show which samples are used."""
    name = "the included tune" if path == SAMPLE_FILE else display_path(path)
    sample_format = walkthrough.format
    count = len(walkthrough.changes)
    time = format_time(walkthrough.first_frame, sample_format.frame_rate)
    silence = ["The whole file is silent."] if walkthrough.silent else []
    if ALGORITHMS[key].keyed:
        where = [f"{count_word(count, 'sample')}, scattered over {name}.", *silence, DEMO, SCATTERED]
    else:
        place = (
            f"{count_word(count, 'sample')} of {name}, from {time} on (frame {walkthrough.first_frame:,})."
        )
        where = [place, *silence, FROM_THE_START]
    show_step(view, "Step 2: take real samples", *where)


def show_changes(view: View, key: str, walkthrough: Walkthrough) -> None:
    """Show the lowest bits of the samples before and after."""
    algorithm = ALGORITHMS[key]
    how = [algorithm.how] if algorithm.how else []
    show_step(view, "Step 3: put the bits into the samples", *how)
    if algorithm.samples_per_group > 1:
        show_groups(view, walkthrough.groups)
    else:
        show_samples(view, walkthrough.changes, scattered=algorithm.keyed)
    if not any(change.change for change in walkthrough.changes):
        view.out.line(ALREADY_HELD)


def show_result(view: View, key: str, walkthrough: Walkthrough) -> None:
    """Show what the changes mean and that the character can be read again."""
    changed = sum(change.change != 0 for change in walkthrough.changes)
    largest = max(abs(change.change) for change in walkthrough.changes)
    algorithm = ALGORITHMS[key]
    show_step(
        view,
        "Step 4: read the bits back",
        f"Reading the same bits gives {show_letter(walkthrough.read_back)} again.",
        f"{changed} of {count_word(len(walkthrough.changes), 'sample')} changed, by at most {largest} here. "
        f"This algorithm can change a sample by at most {largest_possible_change(algorithm)}, "
        f"out of {walkthrough.format.full_scale:,}.",
    )


def show_advice(view: View, key: str) -> None:
    """Show the strengths, the weaknesses, and commands to try."""
    algorithm = ALGORITHMS[key]
    for title, sentences in (("Strengths", algorithm.strengths), ("Weaknesses", algorithm.weaknesses)):
        if sentences:
            show_step(view, title, *[f"- {sentence}" for sentence in sentences])
    passphrase = " -p" if algorithm.keyed else ""
    show_step(
        view,
        "Try it",
        f'  audiosteg hide {SAMPLE_WORD} -m "Hello" -a {key}{passphrase}',
        f"  audiosteg compare {SAMPLE_WORD} {SAMPLE_WORD}.stego.wav --details",
    )


def show_walkthrough(
    view: View, key: str, path: str, walkthrough: Walkthrough, pause: Callable[[], None] | None
) -> None:
    """Show every step, with a pause between them if that is wanted."""
    algorithm = ALGORITHMS[key]
    if view.as_json:
        fields = {
            **describe({key: algorithm})[0],
            "legacy": False,
            "letter": walkthrough.letter,
            "utf_8": walkthrough.data.hex(),
            "file": clean_for_json(path),
            "first_frame": walkthrough.first_frame,
            "silent": walkthrough.silent,
            "how": algorithm.how,
            "demo_seed": DEMO_SEED if algorithm.keyed else None,
            "samples": [change_fields(change) for change in walkthrough.changes],
            "groups": [group_fields(group) for group in walkthrough.groups],
            "read_back": walkthrough.read_back,
            "largest_possible_change": largest_possible_change(algorithm),
            "strengths": list(algorithm.strengths),
            "weaknesses": list(algorithm.weaknesses),
        }
        view.show_json("explain", True, fields)
        return
    steps: list[Callable[[], None]] = [
        lambda: show_character(view, walkthrough),
        lambda: show_place(view, key, path, walkthrough),
        lambda: show_changes(view, key, walkthrough),
        lambda: show_result(view, key, walkthrough),
        lambda: show_advice(view, key),
    ]
    view.out.spans((algorithm.name, "bold"))
    view.out.line(algorithm.explanation)
    for number, step in enumerate(steps):
        if pause is not None and number:
            pause()
        view.out.line("")
        step()
