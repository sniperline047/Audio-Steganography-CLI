"""Show how an algorithm hides a character."""

import unicodedata
from collections.abc import Callable
from typing import Any

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.analysis.samples import seconds
from audiosteg.analysis.walkthrough import SampleChange, Walkthrough, largest_possible_change
from audiosteg.cli.commands.hide import SAMPLE_FILE, SAMPLE_WORD
from audiosteg.cli.views import View, clean_for_json, count_word, describe, display_path

REPLACED = " (old files only)"
BITS_IN_A_BYTE = 8


def mark_changed(byte: int, other: int) -> list[tuple[str, bool]]:
    """Return the bits of a byte in groups, each with whether the other byte differs there."""
    groups: list[tuple[str, bool]] = []
    for shift in reversed(range(BITS_IN_A_BYTE)):
        bit = str(byte >> shift & 1)
        changed = bool((byte ^ other) >> shift & 1)
        if groups and groups[-1][1] == changed:
            groups[-1] = (groups[-1][0] + bit, changed)
        else:
            groups.append((bit, changed))
    return groups


def bit_spans(byte: int, other: int) -> list[tuple[str, str]]:
    """Return the bits of a byte with the changed ones in brackets."""
    return [
        (f"[{bits}]", "bold black on yellow") if changed else (bits, "")
        for bits, changed in mark_changed(byte, other)
    ]


def width_of(spans: list[tuple[str, str]]) -> int:
    """Return how many characters the texts have together."""
    return sum(len(text) for text, _ in spans)


def join_bits(bits: tuple[int, ...]) -> str:
    """Return bits as text."""
    return "".join(map(str, bits))


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


def show_place(view: View, path: str, walkthrough: Walkthrough) -> None:
    """Show which samples are used."""
    name = "the included tune" if path == SAMPLE_FILE else display_path(path)
    sample_format = walkthrough.format
    count = len(walkthrough.changes)
    time = float(seconds(walkthrough.first_frame, sample_format))
    silence = ["The whole file is silent."] if walkthrough.silent else []
    show_step(
        view,
        "Step 2: take real samples",
        f"{count_word(count, 'sample')} of {name}, from {time:.3f} s on (frame {walkthrough.first_frame:,}).",
        *silence,
        "The hide command itself starts at the first sample and puts a header before the message.",
    )


def change_word(change: SampleChange) -> str:
    """Say how much a sample changed."""
    return f"{change.change:+d}" if change.change else "no change"


def show_changes(view: View, walkthrough: Walkthrough) -> None:
    """Show the lowest byte of every sample before and after."""
    changes = walkthrough.changes
    show_step(
        view,
        "Step 3: put the bits into the samples",
        "These are the bits of the lowest byte of each sample. Changed bits are in [brackets].",
    )
    before = [bit_spans(change.byte_before, change.byte_after) for change in changes]
    after = [bit_spans(change.byte_after, change.byte_before) for change in changes]
    widest = max(map(width_of, before))
    numbers = len(str(len(changes)))
    values = max(len(f"{change.value_before} -> {change.value_after}") for change in changes)
    for change, old, new in zip(changes, before, after, strict=True):
        padding = " " * (widest - width_of(old))
        value = f"{change.value_before} -> {change.value_after}"
        view.out.spans(
            (f"  {change.number:>{numbers}}. hide {join_bits(change.hidden_bits)}: ", ""),
            *old,
            (f"{padding} -> ", ""),
            *new,
            (f"{padding}  value {value:<{values}}  {change_word(change)}", ""),
        )


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
    show_step(
        view,
        "Try it",
        f'  audiosteg hide {SAMPLE_WORD} -m "Hello" -a {key}',
        f"  audiosteg compare {SAMPLE_WORD} {SAMPLE_WORD}.stego.wav --details",
    )


def change_fields(change: SampleChange) -> dict[str, Any]:
    """Return the JSON fields of one sample."""
    return {
        "hidden_bits": join_bits(change.hidden_bits),
        "low_byte_before": f"{change.byte_before:08b}",
        "low_byte_after": f"{change.byte_after:08b}",
        "value_before": change.value_before,
        "value_after": change.value_after,
        "change": change.change,
    }


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
            "samples": [change_fields(change) for change in walkthrough.changes],
            "read_back": walkthrough.read_back,
            "largest_possible_change": largest_possible_change(algorithm),
            "strengths": list(algorithm.strengths),
            "weaknesses": list(algorithm.weaknesses),
        }
        view.show_json("explain", True, fields)
        return
    steps: list[Callable[[], None]] = [
        lambda: show_character(view, walkthrough),
        lambda: show_place(view, path, walkthrough),
        lambda: show_changes(view, walkthrough),
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
