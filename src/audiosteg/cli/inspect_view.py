"""Show what inspect found."""

from audiosteg.algorithms.registry import ALGORITHMS, reading_key
from audiosteg.analysis.inspection import Capacity, FoundMessage, Inspection
from audiosteg.analysis.samples import seconds
from audiosteg.cli.commands.reveal import not_checked
from audiosteg.cli.views import Rows, View, clean_for_json, count_word, display_path, format_time

CHANNEL_NAMES = {1: "1 (mono)", 2: "2 (stereo)"}
NONE_DETECTED = "none detected"
LIMITS = "Messages of lsb_keyed, of older versions, and of other tools cannot be detected."
HEADER_ONLY = "Only the header of the message was read, so damage further on is not detected."


def describe_message(message: FoundMessage) -> str:
    """Describe a detected message in one line."""
    if message.problem is not None:
        return f"{message.algorithm}, cannot be used. {message.problem}"
    if message.size is None:
        raise ValueError("A message without a problem needs a size.")
    protection = "encrypted" if message.encrypted else "not encrypted"
    return f"{message.algorithm}, {protection}, {count_word(message.size, 'byte')}"


def describe_estimate(capacity: Capacity) -> str:
    """Describe how much an algorithm may be able to hide, if the sound decides it."""
    if capacity.plain == 0:
        return "none, the sound is too short"
    plain = count_word(capacity.plain, "byte")
    return f"at most {plain}, or {capacity.encrypted:,} encrypted. Not every sound works."


def describe_capacity(capacity: Capacity) -> str:
    """Describe in one line how much an algorithm can hide."""
    if capacity.at_most:
        return describe_estimate(capacity)
    if capacity.always_encrypted:
        return f"{count_word(capacity.encrypted, 'byte')}, always encrypted"
    return f"{count_word(capacity.plain, 'byte')}, or {capacity.encrypted:,} encrypted"


def look_alikes(inspection: Inspection) -> list[str]:
    """Return one sentence for every algorithm whose messages look the same as a message that was found."""
    found = {message.algorithm for message in inspection.messages}
    return [
        f"A message hidden with {key} looks the same as one hidden with {reading_key(key)}."
        for key in ALGORITHMS
        if reading_key(key) != key and reading_key(key) in found
    ]


def show_inspection(view: View, path: str, inspection: Inspection) -> None:
    """Show what is known about a file."""
    sample_format = inspection.format
    duration = float(seconds(inspection.frames, sample_format))
    if view.as_json:
        view.show_json(
            "inspect",
            True,
            {
                "file": clean_for_json(path),
                "bits": 8 * sample_format.sample_width,
                "channels": sample_format.channels,
                "sample_rate": sample_format.frame_rate,
                "frames": inspection.frames,
                "seconds": duration,
                "cannot_hide": inspection.cannot_hide and clean_for_json(inspection.cannot_hide),
                "capacity": [vars(capacity) for capacity in inspection.capacities],
                "messages": [vars(message) for message in inspection.messages],
                "not_checked": list(inspection.not_checked),
            },
        )
        return
    length = count_word(inspection.frames, "frame") if inspection.frames else "no samples"
    rows: Rows = [
        ("File", display_path(path)),
        ("Format", f"{8 * sample_format.sample_width}-bit PCM WAV"),
        ("Channels", CHANNEL_NAMES.get(sample_format.channels, str(sample_format.channels))),
        ("Sample rate", f"{sample_format.frame_rate:,} Hz"),
        ("Duration", f"{format_time(inspection.frames, sample_format.frame_rate)} ({length})"),
    ]
    for capacity in inspection.capacities:
        rows.append((f"Room with {capacity.algorithm}", describe_capacity(capacity)))
    if inspection.cannot_hide is not None:
        rows.append(("Room", f"none. {inspection.cannot_hide}"))
    messages = [describe_message(message) for message in inspection.messages]
    rows += [("Hidden message", message) for message in messages or [NONE_DETECTED]]
    view.out.panel("What this file holds", rows, "cyan")
    found, missing = look_alikes(inspection), not_checked(inspection.not_checked)
    view.note(" ".join([HEADER_ONLY, *found] if messages else [LIMITS, *missing]))
