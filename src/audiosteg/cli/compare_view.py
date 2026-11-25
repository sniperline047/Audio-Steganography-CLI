"""Show what compare measured."""

import math
from collections.abc import Callable
from decimal import ROUND_FLOOR, Decimal
from fractions import Fraction
from typing import Any

from audiosteg.analysis.quality import EXCELLENT, FAIR, GOOD, IDENTICAL, POOR, Quality
from audiosteg.cli.commands.compare import METRICS, NUMBERS, CompareRequest, SavedDifference
from audiosteg.cli.views import View, clean_for_json, count_word, display_path, format_time
from audiosteg.cli.waveform_view import blocks_for, draw_waveform

LOUD_CHANGE = 1
STYLES = {IDENTICAL: "green", EXCELLENT: "green", GOOD: "green", FAIR: "yellow", POOR: "red"}
SOUNDS_THE_SAME = {
    IDENTICAL: "Yes. Every sample is the same.",
    EXCELLENT: "Very likely. The change is far quieter than the sound, but only listening can tell.",
    GOOD: "Probably. The change is much quieter than the sound, but only listening can tell.",
    FAIR: "Maybe not. Listen for a soft hiss in quiet places.",
    POOR: "Probably not. The change is not much quieter than the sound.",
}


def format_decibels(value: float) -> str:
    """Return decibels with one decimal, rounded down, so that a limit is never shown before it is reached."""
    return f"{Decimal(value).quantize(Decimal('0.1'), ROUND_FLOOR)} dB"


def format_percentage(value: Fraction) -> str:
    """Return a percentage, rounded down. Only nothing is 0%, and only everything is 100%."""
    if value in (0, 100):
        return f"{value}%"
    hundredths = math.floor(value * 100)
    if hundredths == 0:
        return "less than 0.01%"
    return f"{hundredths // 100}.{hundredths % 100:02}%"


def largest_share(quality: Quality) -> str:
    """Compare the largest change with the largest possible sample, which it can pass."""
    percentage = format_percentage(quality.largest_change_percentage)
    if quality.largest_change > quality.format.full_scale:
        return f"{percentage} of the largest possible sample, from one side of silence to the other"
    return f"{percentage} of the largest possible sample"


def format_number(value: Fraction) -> str:
    """Return a number without rounding. It must not have endless decimals."""
    return f"{Decimal(value.numerator) / value.denominator:,f}"


def format_gain(gain: Fraction, wanted: Fraction | None) -> str:
    """Return how much a difference was amplified, and whether that is less than was asked for."""
    capped = ""
    if wanted is not None and gain < wanted:
        times = "time" if wanted == 1 else "times"
        capped = f" (capped from {format_number(wanted)} {times} to a safe level)"
    if gain < 1:
        return f"reduced to {format_percentage(gain * 100)}{capped}"
    if gain == 1:
        return f"not amplified{capped}"
    shown = max(Fraction(math.floor(gain * 100), 100), Fraction(101, 100))
    start = "less than " if shown > gain else ""
    return f"amplified {start}{format_number(shown)} times{capped}"


def format_seconds(quality: Quality, frame: int) -> str:
    """Return the time of a frame."""
    return format_time(frame, quality.format.frame_rate)


def snr_note(quality: Quality) -> str | None:
    """Return why there is no signal-to-noise ratio."""
    if quality.identical:
        return "identical"
    return "silent_original" if quality.silent_original else None


def snr_text(quality: Quality) -> str:
    """Return the signal-to-noise ratio, or why there is none."""
    if quality.identical:
        return "no noise, because nothing changed"
    if quality.snr is None:
        return "none, because the original is silent" + (" in this part" if quality.partial else "")
    return format_decibels(quality.snr)


def psnr_text(quality: Quality) -> str:
    """Return the peak signal-to-noise ratio, or why there is none."""
    return "no noise, because nothing changed" if quality.psnr is None else format_decibels(quality.psnr)


def changes_text(quality: Quality) -> str:
    """Say how many samples changed."""
    if quality.samples == 0:
        return "nothing, because there are no samples"
    percentage = format_percentage(quality.changed_percentage)
    return f"{quality.changed:,} of {count_word(quality.samples, 'sample')} ({percentage})"


def largest_text(quality: Quality) -> str:
    """Say how large the largest change is."""
    return f"{count_word(quality.largest_change, 'step')} ({largest_share(quality)})"


def where_text(quality: Quality) -> str:
    """Say where the changes are."""
    if quality.first_changed is None or quality.last_changed is None:
        return "nowhere"
    first = format_seconds(quality, quality.first_changed)
    return f"from {first} to {format_seconds(quality, quality.last_changed + 1)}"


def sounds_the_same(quality: Quality) -> str:
    """Say how likely it is that nobody hears a difference, without claiming to know."""
    if quality.samples == 0:
        return "There is nothing to hear, because the files have no samples."
    if quality.identical and quality.partial:
        return "Yes, in this part. Every sample of it is the same."
    if quality.silent_original and not quality.identical:
        where = "in this part" if quality.partial else "everywhere"
        return f"Hard to say. The original is silent {where}, so any change could be heard."
    if quality.word in (EXCELLENT, GOOD) and quality.largest_change_percentage > LOUD_CHANGE:
        return (
            "Hard to say. The change is quiet on average, but one sample moved by "
            f"{largest_share(quality)}, which could be a click."
        )
    return SOUNDS_THE_SAME[quality.word]


def show_part(view: View, quality: Quality) -> None:
    """Say which part was compared, unless it was everything."""
    if quality.partial:
        start = format_seconds(quality, quality.part.first)
        end = format_seconds(quality, quality.part.first + quality.part.frames)
        total = format_seconds(quality, quality.total_frames)
        view.out.spans(
            ("Compared part:   ", "bold"), (f"{start} to {end} of {total}. The rest was not compared.", "")
        )


def show_summary(view: View, quality: Quality) -> None:
    """Show three lines for people who do not need numbers."""
    changed = changes_text(quality)
    if not quality.identical:
        changed += f", {where_text(quality)}"
    style = STYLES[quality.word]
    view.out.spans(("Sounds the same? ", "bold"), (sounds_the_same(quality), ""))
    word = quality.word if quality.identical else f"{quality.word} (SNR: {snr_text(quality)})"
    view.out.spans(("Quality:         ", "bold"), (word, style))
    view.out.spans(("Changed:         ", "bold"), (changed, ""))


def show_number(view: View, name: str, value: str, explanation: str) -> None:
    """Show one metric and what it means."""
    view.out.spans((f"{name}: ", "bold"), (value, ""))
    view.out.spans((f"  {explanation}", "dim"))


def show_snr(view: View, quality: Quality) -> None:
    """Show the signal-to-noise ratio."""
    explanation = (
        f"How much stronger the sound is than the change. Higher is better. In words: {quality.word}."
    )
    show_number(view, "SNR", snr_text(quality), explanation)


def show_psnr(view: View, quality: Quality) -> None:
    """Show the peak signal-to-noise ratio."""
    explanation = "How much stronger the loudest possible sound is than the change. Higher is better."
    show_number(view, "PSNR", psnr_text(quality), explanation)


def show_changes(view: View, quality: Quality) -> None:
    """Show how much changed."""
    show_number(
        view,
        "Changed samples",
        changes_text(quality),
        "A sample is one number of one channel. Fewer changes are harder to notice.",
    )
    show_number(
        view,
        "Largest change",
        largest_text(quality),
        "How far one sample moved. One step is the smallest change there is.",
    )


def show_where(view: View, quality: Quality) -> None:
    """Show where the changes are."""
    show_number(view, "Where", where_text(quality), "The time of the first and the last changed sample.")
    show_number(
        view,
        "Changed samples in each tenth",
        ", ".join(f"{count:,}" for count in quality.changed_by_tenth),
        "The compared audio, cut into ten equal parts.",
    )


SHOW_NUMBERS: dict[str, Callable[[View, Quality], None]] = {
    "snr": show_snr,
    "psnr": show_psnr,
    "changes": show_changes,
    "where": show_where,
}


def show_waveforms(view: View, quality: Quality, drawings: dict[str, list[int]]) -> None:
    """Draw the loudness of both files and of their difference over time."""
    blocks = blocks_for(view.out.stream, view.out.drawn)
    loudest = max(drawings["original"] + drawings["encoded"], default=0)
    part = quality.part
    times = f"{format_seconds(quality, part.first)} to {format_seconds(quality, part.first + part.frames)}"
    explanations = {
        "original": f"The loudest sample at each moment, {times}.",
        "encoded": "The same for the encoded file, at the same scale.",
        "difference": "The largest change at each moment, enlarged to fill the height.",
    }
    for name, explanation in explanations.items():
        top = quality.largest_change if name == "difference" else loudest
        view.out.spans((f"Waveform: {name}", "bold"))
        for line in draw_waveform(drawings[name], top, blocks):
            view.out.spans((line.rstrip(), "red" if name == "difference" else "cyan"))
        view.out.spans((f"  {explanation}", "dim"))


def show_saved(view: View, saved: SavedDifference) -> None:
    """Say where the difference was saved."""
    view.out.spans(("Difference saved: ", "bold"), (display_path(saved.file), ""))
    gain = format_gain(saved.gain, saved.wanted_gain)
    view.out.spans((f"  It was {gain}. Its loudest sample is at least 12 dB below the maximum.", "dim"))


def number_fields(quality: Quality, metrics: tuple[str, ...]) -> dict[str, Any]:
    """Return the JSON fields of the chosen metrics. Missing numbers are null."""
    fields: dict[str, dict[str, Any]] = {
        "snr": {"snr_db": quality.snr, "snr_note": snr_note(quality)},
        "psnr": {"psnr_db": quality.psnr, "psnr_note": "identical" if quality.identical else None},
        "changes": {
            "samples": quality.samples,
            "changed_samples": quality.changed,
            "changed_percentage": float(quality.changed_percentage),
            "largest_change": quality.largest_change,
            "largest_change_percentage": float(quality.largest_change_percentage),
        },
        "where": {
            "first_changed_frame": quality.first_changed,
            "last_changed_frame": quality.last_changed,
            "changed_by_tenth": list(quality.changed_by_tenth),
        },
    }
    return {name: value for metric in metrics if metric in fields for name, value in fields[metric].items()}


def scaled(peaks: list[int], full_scale: int) -> list[float]:
    """Return peaks as numbers from 0 to 1."""
    return [peak / full_scale for peak in peaks]


def show_comparison(
    view: View,
    request: CompareRequest,
    quality: Quality,
    drawings: dict[str, list[int]] | None,
    saved: SavedDifference | None,
) -> None:
    """Show what was measured, as a summary or as the chosen metrics."""
    if view.as_json:
        fields: dict[str, Any] = {
            "original": clean_for_json(request.original),
            "encoded": clean_for_json(request.encoded),
            "first_frame": quality.part.first,
            "frames": quality.part.frames,
            "total_frames": quality.total_frames,
            "identical": quality.identical,
            "quality": quality.word,
            **number_fields(quality, request.metrics or NUMBERS),
        }
        if drawings is not None:
            scale = quality.format.full_scale
            fields["waveform"] = {name: scaled(peaks, scale) for name, peaks in drawings.items()}
        if saved is not None:
            fields["difference"] = {
                "file": clean_for_json(saved.file),
                "gain": float(saved.gain),
                "capped": saved.wanted_gain is not None and saved.gain < saved.wanted_gain,
            }
        else:
            fields["difference"] = None
        view.show_json("compare", True, fields)
        return
    show_part(view, quality)
    if not request.metrics:
        show_summary(view, quality)
    for metric in METRICS:
        if metric in request.metrics and metric in SHOW_NUMBERS:
            SHOW_NUMBERS[metric](view, quality)
    if drawings is not None:
        show_waveforms(view, quality, drawings)
    if saved is not None:
        show_saved(view, saved)
