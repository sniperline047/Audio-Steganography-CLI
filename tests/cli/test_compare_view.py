"""Tests for audiosteg/cli/compare_view.py."""

import io
import json
from fractions import Fraction
from typing import Any

import pytest
from conftest import ALL
from rich.console import Console

from audiosteg.analysis.quality import Quality
from audiosteg.analysis.samples import Part, SampleFormat
from audiosteg.cli.commands.compare import METRICS, CompareRequest, SavedDifference
from audiosteg.cli.compare_view import (
    changes_text,
    format_decibels,
    format_gain,
    format_percentage,
    largest_text,
    show_comparison,
    snr_text,
    sounds_the_same,
    where_text,
)
from audiosteg.cli.views import View


def quality(**changes: Any) -> Quality:
    """Return a comparison of 1000 mono samples of 16 bits."""
    values: dict[str, Any] = {
        "format": SampleFormat(1, 2, 8000),
        "part": Part(0, 1000),
        "total_frames": 1000,
        "signal": 10**9,
        "noise": 10,
        "changed": 10,
        "largest_change": 1,
        "first_changed": 0,
        "last_changed": 9,
        "changed_by_tenth": (10,) + (0,) * 9,
    }
    return Quality(**{**values, **changes})


SAME = {"noise": 0, "changed": 0, "largest_change": 0, "first_changed": None, "last_changed": None}
PART = {"part": Part(0, 500)}


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (70.0, "70.0 dB"),
        (69.99999, "69.9 dB"),
        (0.0, "0.0 dB"),
        (-0.01, "-0.1 dB"),
        (-12.34, "-12.4 dB"),
        (187.96, "187.9 dB"),
    ],
)
def test_decibels_are_rounded_down(value: float, shown: str) -> None:
    assert format_decibels(value) == shown


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (0, "0%"),
        (1e-9, "less than 0.01%"),
        (0.0099999, "less than 0.01%"),
        (0.01, "0.01%"),
        (0.0199, "0.01%"),
        (50, "50.00%"),
        (99.995, "99.99%"),
        (99.9999999, "99.99%"),
        (100, "100%"),
        (100.0000001, "100.00%"),
        (199.999, "199.99%"),
    ],
)
def test_only_nothing_is_0_percent_and_only_everything_is_100_percent(value: float, shown: str) -> None:
    assert format_percentage(value) == shown


@pytest.mark.xfail(strict=True, reason="a float is a little smaller than the exact percentage")
def test_an_exact_percentage_is_not_rounded() -> None:
    exact = quality(part=Part(0, 10_000), total_frames=10_000, changed=29)
    assert "(0.29%)" in changes_text(exact)


@pytest.mark.parametrize(
    ("gain", "wanted", "shown"),
    [
        (Fraction(8230), None, "amplified 8,230 times"),
        (Fraction(5, 2), Fraction(5, 2), "amplified 2.5 times"),
        (
            Fraction(8230, 3),
            Fraction(9000),
            "amplified 2,743.33 times (capped from 9,000 times to a safe level)",
        ),
        (Fraction(8230), Fraction(8230), "amplified 8,230 times"),
        (Fraction(1), None, "amplified 1 times"),
        (Fraction(1, 2), None, "reduced to 50.00%"),
        (Fraction(1, 8), Fraction(1), "reduced to 12.50% (capped from 1 times to a safe level)"),
    ],
)
def test_the_gain_in_words(gain: Fraction, wanted: Fraction | None, shown: str) -> None:
    assert format_gain(gain, wanted) == shown


@pytest.mark.xfail(strict=True, reason="a reduction is rounded up to 100.00%")
def test_a_reduction_is_never_shown_as_100_percent() -> None:
    assert "100.00%" not in format_gain(Fraction(539423503, 539423504), None)


@pytest.mark.xfail(strict=True, reason="the number is rounded to the nearest, unlike other decibels")
def test_a_limit_is_never_shown_before_it_is_reached() -> None:
    almost = quality(signal=10**17 - 1, noise=10**10, format=SampleFormat(1, 4, 8000))
    assert (almost.word, snr_text(almost)) == ("Good", "69.9 dB")


@pytest.mark.parametrize(
    ("changes", "shown"),
    [
        (SAME, "Yes. Every sample is the same."),
        ({**SAME, **PART}, "Yes, in this part. Every sample of it is the same."),
        ({**SAME, "signal": 0}, "Yes. Every sample is the same."),
        (
            {**SAME, "part": Part(0, 0), "total_frames": 0},
            "There is nothing to hear, because the files have no",
        ),
        ({"signal": 0}, "Hard to say. The original is silent everywhere, so any change could be heard."),
        ({"signal": 0, **PART}, "Hard to say. The original is silent in this part, so any"),
        ({}, "Very likely."),
        ({"largest_change": 327}, "Very likely."),
        (
            {"largest_change": 328},
            "Hard to say. The change is quiet on average, but one sample moved by 1.00% of",
        ),
        ({"noise": 1000, "largest_change": 40000}, "Hard to say. The change is quiet on average, but one"),
        ({"noise": 10**4}, "Probably. "),
        ({"noise": 10**5, "largest_change": 328}, "Maybe not. Listen"),
        ({"noise": 10**7, "largest_change": 328}, "Probably not."),
    ],
)
def test_what_can_be_said_about_the_sound(changes: dict[str, Any], shown: str) -> None:
    assert sounds_the_same(quality(**changes)).startswith(shown)


@pytest.mark.parametrize(
    ("largest", "shown"),
    [
        (1, "1 step (less than 0.01% of the largest possible sample)"),
        (32768, "32,768 steps (100% of the largest possible sample)"),
        (
            32769,
            "32,769 steps (100.00% of the largest possible sample, from one side of silence to the other)",
        ),
        (
            65535,
            "65,535 steps (199.99% of the largest possible sample, from one side of silence to the other)",
        ),
    ],
)
def test_the_largest_change_in_words(largest: int, shown: str) -> None:
    assert largest_text(quality(largest_change=largest)) == shown


@pytest.mark.parametrize(
    ("changes", "shown"),
    [
        (SAME, "nowhere"),
        ({}, "from 0.000 s to 0.001 s"),
        ({"first_changed": 999, "last_changed": 999}, "from 0.125 s to 0.125 s"),
        ({"last_changed": 12}, "from 0.000 s to 0.002 s"),
        ({"format": SampleFormat(1, 2, 1000), "first_changed": 5}, "from 0.005 s to 0.010 s"),
    ],
)
def test_where_the_changes_are(changes: dict[str, Any], shown: str) -> None:
    assert where_text(quality(**changes)) == shown


def shown(compared: Quality, **options: Any) -> str:
    request = CompareRequest("a", "b", options.get("metrics", ()))
    output = io.StringIO()
    show_comparison(
        View(output, io.StringIO()), request, compared, options.get("drawings"), options.get("saved")
    )
    return output.getvalue()


def test_the_numbers_of_files_that_are_the_same() -> None:
    assert shown(quality(**SAME)).splitlines()[1:] == [
        "Quality:         Identical",
        "Changed:         0 of 1,000 samples (0%)",
    ]
    text = shown(quality(**SAME), metrics=METRICS[:4])
    for line in (
        "SNR: no noise, because nothing changed\n",
        "In words: Identical.\n",
        "PSNR: no noise, because nothing changed\n",
        "Changed samples: 0 of 1,000 samples (0%)\n",
        "Largest change: 0 steps (0% of the largest possible sample)\n",
        "Where: nowhere\n",
    ):
        assert line in text
    nothing = quality(**SAME, part=Part(0, 0), total_frames=0)
    assert "Changed:         nothing, because there are no samples\n" in shown(nothing)


def test_the_part_is_named() -> None:
    text = shown(quality(part=Part(80, 400), signal=0))
    assert text.startswith(
        "Compared part:   0.010 s to 0.060 s of 0.125 s. The rest was not compared.\nSounds the same? "
    )
    assert "SNR: none, because the original is silent in this part" in text
    assert "SNR: none, because the original is silent)" in shown(quality(signal=0))
    assert shown(quality()).startswith("Sounds the same? ")


def test_waveforms_have_the_same_scale_and_the_difference_its_own() -> None:
    drawings = {"original": [50, 100], "encoded": [50, 75], "difference": [0, 1]}
    text = shown(quality(part=Part(80, 400)), drawings=drawings, metrics=("waveform",))
    assert text.splitlines()[1:] == [
        "Waveform: original",
        " |",
        " |",
        "||",
        "||",
        "  The loudest sample at each moment, 0.010 s to 0.060 s.",
        "Waveform: encoded",
        "",
        " |",
        "||",
        "||",
        "  The same for the encoded file, at the same scale.",
        "Waveform: difference",
        *[" |"] * 4,
        "  The largest change at each moment, enlarged to fill the height.",
    ]
    louder = {"original": [50], "encoded": [100], "difference": [1]}
    lines = shown(quality(), drawings=louder, metrics=("waveform",)).splitlines()
    assert lines[1:5] == ["", "", "|", "|"] and lines[7:11] == ["|"] * 4


def test_a_waveform_of_silence_is_empty() -> None:
    nothing: dict[str, list[int]] = {"original": [], "encoded": [], "difference": []}
    zero = {name: [0, 0] for name in nothing}
    for drawings in (nothing, zero):
        text = shown(quality(**SAME), drawings=drawings, metrics=("waveform",))
        assert text.count("\n\n\n\n\n  ") == 3


def test_a_saved_difference() -> None:
    text = shown(quality(), saved=SavedDifference("x\x1b[2J.wav", Fraction(3), None))
    assert text.endswith(
        "Difference saved: x\\x1b[2J.wav\n"
        "  It was amplified 3 times. Its loudest sample is at least 12 dB below the maximum.\n"
    )


@pytest.mark.parametrize(
    ("changes", "colour"),
    [
        (SAME, "32"),
        ({}, "32"),
        ({"noise": 10**4}, "32"),
        ({"noise": 10**5}, "33"),
        ({"noise": 10**7}, "31"),
    ],
)
def test_the_colour_of_the_word(changes: dict[str, Any], colour: str) -> None:
    output = io.StringIO()
    view = View(output, io.StringIO())
    view.out.coloured = True
    view.out.console = Console(
        file=output, force_terminal=True, color_system="standard", width=40, legacy_windows=False
    )
    show_comparison(view, CompareRequest("a", "b"), quality(**changes), None, None)
    lines = output.getvalue().splitlines()
    assert len(lines) == 3
    assert f"\x1b[{colour}m{quality(**changes).word}" in lines[1]


def test_waveforms_in_a_terminal(run: Any, make_pair: Any) -> None:
    paths = make_pair([0, 10000, 20000, 30000], [0, 10000, 20000, 30001])
    blocks = run("compare", *paths, "--show", "waveform", terminals=ALL)
    assert "\x1b[36m   █" in blocks.output and "\x1b[31m   █" in blocks.output
    assert "   █\n  ▆█\n ▃██\n ███\n" in blocks.text
    for options in ({"encoding": "cp437"}, {"encoding": "ascii"}, {"TERM": "dumb"}, {"words": ["--plain"]}):
        words = options.pop("words", [])
        text = run("compare", *paths, "--show", "waveform", *words, terminals=ALL, **options)
        assert "█" not in text.output and "\x1b" not in text.output
        assert "\n   |\n  :|\n .||\n |||\n" in text.output
    bare = run("compare", *paths, "--show", "waveform", terminals=ALL, NO_COLOR="1")
    assert "█" in bare.output and "\x1b" not in bare.output


def test_json_has_every_number_and_only_what_was_chosen(run: Any, make_pair: Any) -> None:
    def reject(constant: str) -> None:
        raise AssertionError(constant)

    paths = make_pair([3, -4, 0, 12], [3, -2, 0, 11], channels=2)
    result = run("compare", *paths, "--json", terminals=ALL)
    assert (result.code, result.errors) == (0, "")
    fields = json.loads(result.output, parse_constant=reject)
    assert list(fields) == [
        "ok", "command", "original", "encoded", "first_frame", "frames", "total_frames", "identical",
        "quality", "snr_db", "snr_note", "psnr_db", "psnr_note", "samples", "changed_samples",
        "changed_percentage", "largest_change", "largest_change_percentage", "first_changed_frame",
        "last_changed_frame", "changed_by_tenth", "difference",
    ]  # fmt: skip
    assert (fields["ok"], fields["command"], fields["difference"]) == (True, "compare", None)
    assert (fields["original"], fields["encoded"]) == paths
    assert fields["snr_db"] == pytest.approx(15.289167, abs=1e-6)
    assert fields["psnr_db"] == pytest.approx(89.339898, abs=1e-6)
    assert (fields["snr_note"], fields["psnr_note"]) == (None, None)
    assert [fields[name] for name in ("first_frame", "frames", "total_frames")] == [0, 2, 2]
    assert [fields[name] for name in ("samples", "changed_samples", "changed_percentage")] == [4, 2, 50]
    assert (fields["largest_change"], fields["largest_change_percentage"]) == (2, 200 / 32768)
    assert (fields["first_changed_frame"], fields["last_changed_frame"]) == (0, 1)
    assert fields["changed_by_tenth"] == [0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (
            "where,snr",
            {"snr_db", "snr_note", "first_changed_frame", "last_changed_frame", "changed_by_tenth"},
        ),
        ("psnr", {"psnr_db", "psnr_note"}),
        ("waveform", {"waveform"}),
        (
            "changes",
            {
                "samples",
                "changed_samples",
                "changed_percentage",
                "largest_change",
                "largest_change_percentage",
            },
        ),
    ],
)
def test_json_shows_only_the_chosen_numbers(run: Any, make_pair: Any, names: str, expected: set[str]) -> None:
    result = json.loads(run("compare", *make_pair([1], [2]), "--show", names, "--json").output)
    always = {"ok", "command", "original", "encoded", "first_frame", "frames", "total_frames", "identical"}
    assert set(result) == always | {"quality", "difference"} | expected


@pytest.mark.parametrize(
    ("original", "encoded", "snr_note", "psnr_note", "word"),
    [
        ([1], [1], "identical", "identical", "Identical"),
        ([0], [0], "identical", "identical", "Identical"),
        ([0], [1], "silent_original", None, "Poor"),
        ([], [], "identical", "identical", "Identical"),
    ],
)
def test_json_numbers_that_do_not_exist_are_null(
    run: Any,
    make_pair: Any,
    original: list[int],
    encoded: list[int],
    snr_note: str,
    psnr_note: str | None,
    word: str,
) -> None:
    result = run("compare", *make_pair(original, encoded), "--details", "--json")
    for constant in ("NaN", "Infinity"):
        assert constant not in result.output
    fields = json.loads(result.output)
    assert (fields["snr_db"], fields["snr_note"], fields["quality"]) == (None, snr_note, word)
    assert (fields["psnr_db"] is None, fields["psnr_note"]) == (psnr_note is not None, psnr_note)


def test_json_waveforms_are_shares_of_the_largest_possible_sample(run: Any, make_pair: Any) -> None:
    paths = make_pair([-32768, 16384, 0], [32767, 16384, 0])
    result = json.loads(run("compare", *paths, "--show", "waveform", "--json", "--width", "20").output)
    assert result["waveform"] == {
        "original": [1, 0.5, 0],
        "encoded": [32767 / 32768, 0.5, 0],
        "difference": [65535 / 32768, 0, 0],
    }
