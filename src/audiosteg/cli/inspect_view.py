"""Show what inspect found."""

from audiosteg.analysis.inspection import FoundMessage, Inspection
from audiosteg.analysis.samples import seconds
from audiosteg.cli.views import Rows, View, clean_for_json, count_word, display_path

CHANNEL_NAMES = {1: "1 (mono)", 2: "2 (stereo)"}
NONE_DETECTED = "none detected"
LIMITS = "Messages of older versions and of other tools cannot be detected."
HEADER_ONLY = "Only the header of the message was read, so damage further on is not detected."


def describe_message(message: FoundMessage) -> str:
    """Describe a detected message in one line."""
    if message.problem is not None:
        return f"{message.algorithm}, cannot be used. {message.problem}"
    if message.size is None:
        raise ValueError("A message without a problem needs a size.")
    protection = "encrypted" if message.encrypted else "not encrypted"
    return f"{message.algorithm}, {protection}, {count_word(message.size, 'byte')}"


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
            },
        )
        return
    rows: Rows = [
        ("File", display_path(path)),
        ("Format", f"{8 * sample_format.sample_width}-bit PCM WAV"),
        ("Channels", CHANNEL_NAMES.get(sample_format.channels, str(sample_format.channels))),
        ("Sample rate", f"{sample_format.frame_rate:,} Hz"),
        ("Duration", f"{duration:.3f} s ({count_word(inspection.frames, 'frame')})"),
    ]
    for capacity in inspection.capacities:
        sizes = f"{count_word(capacity.plain, 'byte')}, or {capacity.encrypted:,} encrypted"
        rows.append((f"Room with {capacity.algorithm}", sizes))
    if inspection.cannot_hide is not None:
        rows.append(("Room", f"none. {inspection.cannot_hide}"))
    messages = [describe_message(message) for message in inspection.messages]
    rows += [("Hidden message", message) for message in messages or [NONE_DETECTED]]
    view.out.panel("What this file holds", rows, "cyan")
    view.note(HEADER_ONLY if messages else LIMITS)
