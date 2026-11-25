"""Show how a character is hidden as echoes."""

from collections.abc import Callable
from typing import Any

from audiosteg.algorithms.echo import EchoHiding
from audiosteg.analysis.echo_walkthrough import PICTURE_DELAYS, EchoBlock, EchoWalkthrough
from audiosteg.cli.commands.hide import SAMPLE_WORD, find_seconds
from audiosteg.cli.explain_view import (
    show_character,
    show_letter,
    show_sentences,
    show_step,
    show_steps,
    source_name,
)
from audiosteg.cli.views import View, clean_for_json, count_word, describe, format_time
from audiosteg.cli.waveform_view import blocks_for, draw_waveform

PICTURE_SCALE = 1000
EXAMPLE = "Hello"
CD_RATE = 44100
FROM_THE_START = (
    "The hide command itself starts at the first frame, and adds a header and error correction "
    "to the message."
)
CEPSTRUM = (
    "An echo makes waves in the spectrum, the list of how loud each pitch is. "
    "The cepstrum shows these waves: it is high at the delay of the echo."
)
ALL_RIGHT = "Every bit was read right. In a whole message, error correction repairs some wrong bits."
SOME_WRONG = (
    "Some bits were read wrong, which happens with echoes. In a whole message, error correction repairs "
    "some wrong bits, and hide refuses a sound with too many."
)


def milliseconds(frames: int, frame_rate: int) -> str:
    """Return how long a delay is."""
    return f"{1000 * frames / frame_rate:.2f} ms"


def show_place(view: View, path: str, walkthrough: EchoWalkthrough, algorithm: EchoHiding) -> None:
    """Show which blocks are used."""
    rate = walkthrough.format.frame_rate
    start = format_time(walkthrough.first_frame, rate)
    show_step(
        view,
        "Step 2: take real sound",
        f"{count_word(len(walkthrough.blocks), 'block')} of {algorithm.block_frames:,} frames of "
        f"{source_name(path)}, from {start} on (frame {walkthrough.first_frame:,}).",
        f"One block is {milliseconds(algorithm.block_frames, rate)} long and carries one bit.",
        *(["The whole file is silent."] if walkthrough.silent else []),
        FROM_THE_START,
    )


def show_echoes(view: View, walkthrough: EchoWalkthrough, algorithm: EchoHiding) -> None:
    """Show which echo each block gets."""
    rate = walkthrough.format.frame_rate
    quieter = (
        [f"The result was too loud, so everything was made quieter ({walkthrough.gain:.0%})."]
        if walkthrough.gain < 1
        else []
    )
    show_step(
        view,
        "Step 3: add an echo to each block",
        algorithm.how,
        *[
            f"  {block.number}. hide {block.hidden_bit}: echo after {block.delay} frames "
            f"({milliseconds(block.delay, rate)})"
            for block in walkthrough.blocks
        ],
        f"The echo is {walkthrough.level:.0%} as strong as the sound. Between blocks it changes smoothly.",
        *quieter,
    )


def draw_cepstrum(view: View, heights: tuple[float, ...], top: float) -> list[str]:
    """Draw a cepstrum, without what is below 0."""
    peaks = [max(round(height * PICTURE_SCALE), 0) for height in heights]
    return draw_waveform(peaks, round(top * PICTURE_SCALE), blocks_for(view.out.stream, view.out.drawn))


def make_ruler(delays: tuple[int, int]) -> str:
    """Return a line that marks two delays below a picture."""
    ruler = ""
    for delay in delays:
        ruler = f"{ruler:<{PICTURE_DELAYS.index(delay)}}^{delay}"
    return ruler


def show_pictures(view: View, walkthrough: EchoWalkthrough, algorithm: EchoHiding) -> None:
    """Draw the cepstrum of the clearest block before and after the change."""
    top = max(*walkthrough.picture_before, *walkthrough.picture_after)
    for title, heights in (("before", walkthrough.picture_before), ("after", walkthrough.picture_after)):
        view.out.line(
            f"The cepstrum of block {walkthrough.picture_block} {title}, at delays from {PICTURE_DELAYS[0]} "
            f"to {PICTURE_DELAYS[-1]} frames:"
        )
        for line in draw_cepstrum(view, heights, top):
            view.out.line(f"  |{line}")
        view.out.line(f"   {make_ruler(algorithm.delays)}")


def describe_peaks(block: EchoBlock, algorithm: EchoHiding) -> str:
    """Describe in one line what is read from a block."""
    zero, one = block.peaks_after
    verdict = "right" if block.read_bit == block.hidden_bit else "wrong"
    return (
        f"  {block.number}. at {algorithm.delays[0]}: {zero:6.3f}   at {algorithm.delays[1]}: {one:6.3f}"
        f"   read {block.read_bit}, {verdict}"
    )


def show_reading(view: View, walkthrough: EchoWalkthrough, algorithm: EchoHiding) -> None:
    """Show the cepstrum of every block and the bits that are read from it."""
    show_step(view, "Step 4: look for the echoes", CEPSTRUM)
    show_pictures(view, walkthrough, algorithm)
    view.out.line("The higher of the two numbers decides the bit:")
    for block in walkthrough.blocks:
        view.out.line(describe_peaks(block, algorithm))
    right, total = walkthrough.right_bits, len(walkthrough.blocks)
    letter = walkthrough.read_back
    result = f", which gives {show_letter(letter)}" if letter is not None else ""
    view.out.line(f"{right} of {count_word(total, 'bit')} read right{result}.")
    view.out.line(ALL_RIGHT if right == total else SOME_WRONG)


def show_advice(view: View, key: str, algorithm: EchoHiding) -> None:
    """Show the strengths, the weaknesses, and commands to try."""
    show_sentences(view, algorithm)
    seconds = find_seconds(len(EXAMPLE), algorithm, encrypted=False, frame_rate=CD_RATE)
    show_step(
        view,
        "Try it",
        f'  audiosteg hide song.wav -m "{EXAMPLE}" -a {key}',
        "  audiosteg compare song.wav song.stego.wav --details",
        f"The file song.wav is one of yours. At {CD_RATE:,} frames a second, this message needs "
        f"{seconds:.1f} s of it, so the tune {SAMPLE_WORD} is too short.",
    )


def block_fields(block: EchoBlock) -> dict[str, Any]:
    """Return the JSON fields of one block."""
    return {
        "block": block.number,
        "hidden_bit": block.hidden_bit,
        "delay": block.delay,
        "peaks_before": list(block.peaks_before),
        "peaks_after": list(block.peaks_after),
        "read_bit": block.read_bit,
    }


def walkthrough_fields(
    key: str, path: str, walkthrough: EchoWalkthrough, algorithm: EchoHiding
) -> dict[str, Any]:
    """Return the JSON fields of a walkthrough. Those that only other algorithms have are empty."""
    return {
        **describe({key: algorithm})[0],
        "legacy": False,
        "letter": walkthrough.letter,
        "utf_8": walkthrough.data.hex(),
        "file": clean_for_json(path),
        "first_frame": walkthrough.first_frame,
        "silent": walkthrough.silent,
        "how": algorithm.how,
        "demo_seed": None,
        "samples": [],
        "groups": [],
        "read_back": walkthrough.read_back,
        "largest_possible_change": None,
        "strengths": list(algorithm.strengths),
        "weaknesses": list(algorithm.weaknesses),
        "delays": list(algorithm.delays),
        "level": walkthrough.level,
        "gain": walkthrough.gain,
        "blocks": [block_fields(block) for block in walkthrough.blocks],
    }


def show_echo_walkthrough(
    view: View,
    key: str,
    path: str,
    walkthrough: EchoWalkthrough,
    algorithm: EchoHiding,
    pause: Callable[[], None] | None,
) -> None:
    """Show every step, with a pause between them if that is wanted."""
    if view.as_json:
        view.show_json("explain", True, walkthrough_fields(key, path, walkthrough, algorithm))
        return
    steps: list[Callable[[], None]] = [
        lambda: show_character(view, walkthrough.letter, walkthrough.data),
        lambda: show_place(view, path, walkthrough, algorithm),
        lambda: show_echoes(view, walkthrough, algorithm),
        lambda: show_reading(view, walkthrough, algorithm),
        lambda: show_advice(view, key, algorithm),
    ]
    show_steps(view, algorithm, steps, pause)
