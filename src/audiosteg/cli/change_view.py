"""Show what happened to samples when a character was hidden in them."""

from collections.abc import Sequence
from typing import Any

from audiosteg.analysis.walkthrough import GroupChange, SampleChange
from audiosteg.cli.views import View

BITS_IN_A_BYTE = 8
LOW_BYTES = "These are the bits of the lowest byte of each sample. Changed bits are in [brackets]."
LOWEST_BITS = "Each row shows the lowest bits of {} samples. Changed bits are in [brackets]."


def mark_changed(value: int, other: int, count: int = BITS_IN_A_BYTE) -> list[tuple[str, bool]]:
    """Return bits in runs, each with whether the other number differs there."""
    runs: list[tuple[str, bool]] = []
    for shift in reversed(range(count)):
        bit = str(value >> shift & 1)
        changed = bool((value ^ other) >> shift & 1)
        if runs and runs[-1][1] == changed:
            runs[-1] = (runs[-1][0] + bit, changed)
        else:
            runs.append((bit, changed))
    return runs


def bit_spans(value: int, other: int, count: int = BITS_IN_A_BYTE) -> list[tuple[str, str]]:
    """Return bits as text with the changed ones in brackets."""
    return [
        (f"[{bits}]", "bold black on yellow") if changed else (bits, "")
        for bits, changed in mark_changed(value, other, count)
    ]


def width_of(spans: list[tuple[str, str]]) -> int:
    """Return how many characters the texts have together."""
    return sum(len(text) for text, _ in spans)


def join_bits(bits: Sequence[int]) -> str:
    """Return bits as text."""
    return "".join(map(str, bits))


def lowest_bits(group: GroupChange) -> tuple[str, str]:
    """Return the lowest bits of the samples of a group, before and after."""
    before = join_bits([sample.byte_before & 1 for sample in group.samples])
    return before, join_bits([sample.byte_after & 1 for sample in group.samples])


def change_word(change: SampleChange) -> str:
    """Say how much a sample changed."""
    return f"{change.change:+d}" if change.change else "no change"


def show_rows(
    view: View, starts: list[str], bits: list[tuple[int, int]], ends: list[str], count: int
) -> None:
    """Show rows of bits before and after, between a start and an end, in columns."""
    before = [bit_spans(old, new, count) for old, new in bits]
    after = [bit_spans(new, old, count) for old, new in bits]
    widest = max(map(width_of, before))
    for start, old_spans, new_spans, end in zip(starts, before, after, ends, strict=True):
        padding = " " * (widest - width_of(old_spans))
        view.out.spans((start, ""), *old_spans, (f"{padding} -> ", ""), *new_spans, (f"{padding}  {end}", ""))


def show_samples(view: View, changes: Sequence[SampleChange], scattered: bool) -> None:
    """Show the lowest byte of every sample before and after."""
    view.out.line(LOW_BYTES)
    numbers = len(str(len(changes)))
    places = [f"sample {change.position:,}, " if scattered else "" for change in changes]
    place_width = max(map(len, places))
    values = [f"value {change.value_before} -> {change.value_after}" for change in changes]
    value_width = max(map(len, values))
    show_rows(
        view,
        [
            f"  {change.number:>{numbers}}. {place:<{place_width}}hide {join_bits(change.hidden_bits)}: "
            for change, place in zip(changes, places, strict=True)
        ],
        [(change.byte_before, change.byte_after) for change in changes],
        [
            f"{value:<{value_width}}  {change_word(change)}"
            for change, value in zip(changes, values, strict=True)
        ],
        BITS_IN_A_BYTE,
    )


def describe_group(group: GroupChange) -> str:
    """Say which sample of a group changed."""
    changed = group.changed
    if changed is None:
        return "no change"
    place = group.samples.index(changed) + 1
    return f"sample {place}: {changed.value_before} -> {changed.value_after}  {change_word(changed)}"


def show_groups(view: View, groups: Sequence[GroupChange]) -> None:
    """Show the lowest bits of every group of samples before and after, and the sample that changed."""
    size = len(groups[0].samples)
    view.out.line(LOWEST_BITS.format(size))
    numbers = len(str(len(groups)))
    rows = [lowest_bits(group) for group in groups]
    show_rows(
        view,
        [
            f"  {group.number:>{numbers}}. hide {join_bits(group.samples[0].hidden_bits)}: "
            for group in groups
        ],
        [(int(before, 2), int(after, 2)) for before, after in rows],
        [
            f"parity {before.count('1') % 2} -> {after.count('1') % 2}  {describe_group(group)}"
            for group, (before, after) in zip(groups, rows, strict=True)
        ],
        size,
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
        "position": change.position,
        "group": change.group,
    }


def group_fields(group: GroupChange) -> dict[str, Any]:
    """Return the JSON fields of one group of samples."""
    before, after = lowest_bits(group)
    changed = group.changed
    return {
        "group": group.number,
        "hidden_bits": join_bits(group.samples[0].hidden_bits),
        "lowest_bits_before": before,
        "lowest_bits_after": after,
        "changed_sample": None if changed is None else group.samples.index(changed) + 1,
    }
