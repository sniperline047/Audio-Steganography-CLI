"""Tests for audiosteg/cli/explain_view.py."""

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, PROJECT_ROOT

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.explain_view import bit_spans, mark_changed, show_letter
from audiosteg.core.algorithm import Algorithm


def test_the_list(run: Any) -> None:
    result = run("explain")
    known = [f"{key}: {value.explanation}" for key, value in ALGORITHMS.items()]
    old = [f"{key}: {value.explanation} (old files only)" for key, value in LEGACY_ALGORITHMS.items()]
    assert result.output.splitlines() == ["What can be explained", *known, *old]
    assert result.errors == "To see one work, name it: audiosteg explain lsb\n"
    as_json = run("explain", "--json")
    fields = json.loads(as_json.output)
    assert as_json.errors == ""
    assert fields == {**json.loads(run("algorithms", "--json").output), "command": "explain"}


def test_the_whole_text_is_the_one_in_the_documentation(run: Any) -> None:
    documentation = (PROJECT_ROOT / "docs" / "commands.md").read_text("utf-8")
    example = documentation.split("This is the output of `audiosteg explain lsb`:")[1].split("```")[1]
    result = run("explain", "lsb")
    assert (result.code, result.errors) == (0, "")
    assert result.output == example.removeprefix("\n")


@pytest.mark.parametrize("key", LEGACY_ALGORITHMS)
def test_an_old_algorithm_says_why_it_was_replaced(run: Any, key: str) -> None:
    algorithm = LEGACY_ALGORITHMS[key]
    result = run("explain", key)
    assert (result.code, result.errors) == (0, "")
    assert result.output.splitlines() == [
        algorithm.name,
        algorithm.explanation,
        "It can read old files, but it cannot hide new messages. It was replaced because:",
        *[f"- {reason}" for reason in algorithm.replaced_because],
        f"To read an old file: audiosteg reveal old.wav --legacy {key}",
    ]
    assert len(algorithm.replaced_because) >= 3
    fields = json.loads(run("explain", key, "--json").output)
    assert fields == {
        "ok": True,
        "command": "explain",
        "key": key,
        "name": algorithm.name,
        "bits_per_byte": algorithm.bits_per_byte,
        "explanation": algorithm.explanation,
        "legacy": True,
        "replaced_because": list(algorithm.replaced_because),
    }


def test_only_what_is_true_is_said_about_old_algorithms() -> None:
    assert "middle bits" not in " ".join(LEGACY_ALGORITHMS["basic"].replaced_because)
    for key in ("enhanced", "enhanced_flip"):
        assert "middle bits" in " ".join(LEGACY_ALGORITHMS[key].replaced_because)


@pytest.mark.parametrize(
    ("byte", "other", "groups"),
    [
        (0b00000000, 0b00000000, [("00000000", False)]),
        (0b10110100, 0b10110101, [("1011010", False), ("0", True)]),
        (0b10110111, 0b10110100, [("101101", False), ("11", True)]),
        (0b11111111, 0b01111110, [("1", True), ("111111", False), ("1", True)]),
        (0b11111111, 0b00000000, [("11111111", True)]),
    ],
)
def test_changed_bits_are_marked(byte: int, other: int, groups: list[tuple[str, bool]]) -> None:
    assert mark_changed(byte, other) == groups
    shown = "".join(text for text, _ in bit_spans(byte, other))
    assert shown == "".join(f"[{bits}]" if changed else bits for bits, changed in groups)


@pytest.mark.parametrize(
    ("letter", "shown"),
    [
        ("h", "'h'"),
        ("\\", "'\\'"),
        ("'", '"\'"'),
        ('"', "'\"'"),
        (" ", "' '"),
        ("🎵", "'🎵'"),
        ("́", "U+0301, which joins the character before it,"),
        ("️", "U+FE0F, which joins the character before it,"),
        ("⃝", "U+20DD, which joins the character before it,"),
        ("\U000e0100", "U+E0100, which joins the character before it,"),
    ],
)
def test_a_character_in_quotes(letter: str, shown: str) -> None:
    assert show_letter(letter) == shown


@pytest.mark.parametrize(
    ("letter", "shown"),
    [
        ("\x1b", "'\\x1b'"),
        ("\x9b", "'\\x9b'"),
        ("\n", "'\\n'"),
        ("‮", "'\\u202e'"),
        ("‍", "'\\u200d'"),
        ("", "'\\ue000'"),
        ("\U000e0001", "'\\U000e0001'"),
        ("\\", "'\\'"),
        ("[", "'['"),
    ],
)
@pytest.mark.parametrize("terminals", [(), ALL])
def test_a_character_cannot_control_the_terminal(
    run: Any, letter: str, shown: str, terminals: tuple[str, ...]
) -> None:
    result = run("explain", "lsb", "--letter", letter, terminals=terminals)
    assert result.code == 0
    assert f"The character {shown} is {len(letter.encode())} byte" in result.text
    assert f"gives {shown} again." in result.text
    if letter not in "\n\\[\x1b":
        assert letter not in result.seen
    as_json = run("explain", "lsb", "--letter", letter, "--json")
    assert as_json.output.isascii()
    fields = json.loads(as_json.output)
    assert (fields["letter"], fields["read_back"], fields["utf_8"]) == (letter, letter, letter.encode().hex())


def test_every_byte_of_a_long_character(run: Any) -> None:
    output = run("explain", "lsb_2", "--letter", "☕").output
    assert (
        "The character '☕' is 3 bytes in UTF-8:\n  0xe2 = 11100010\n  0x98 = 10011000\n  0x95 = 10010101\n\n"
    ) in output
    assert "\n12 samples of the included tune, from " in output
    hidden = re.findall(r"^ +(\d+)\. hide (\d\d): ", output, re.MULTILINE)
    assert "".join(bits for _, bits in hidden) == "111000101001100010010101"
    assert "\n   9. hide" in output and "\n  10. hide" in output
    assert [int(number) for number, _ in hidden] == list(range(1, 13))


def test_the_rows_are_aligned_and_right(run: Any, make_samples: Callable[..., Path]) -> None:
    make_samples("a.wav", [-32768, 8, 3, 0], channels=2)
    make_samples("a.wav", [32767, -8, 3, 0])
    result = run("explain", "lsb_2", "--letter", "N", "--file", "a.wav")
    assert result.output.split("[brackets].\n")[1].split("\n\n")[0].splitlines() == [
        "  1. hide 01: 111111[1]1 -> 111111[0]1  value 32767 -> 32765  -2",
        "  2. hide 00: 11111000   -> 11111000    value -8 -> -8        no change",
        "  3. hide 11: 00000011   -> 00000011    value 3 -> 3          no change",
        "  4. hide 10: 000000[0]0 -> 000000[1]0  value 0 -> 2          +2",
    ]
    assert (
        "2 of 4 samples changed, by at most 2 here. This algorithm can change a sample by at most 3, out"
        in (result.output)
    )
    assert "4 samples of a.wav, from 0.000 s on (frame 0).\nThe hide" in result.output
    assert "out of 32,768." in result.output


def test_a_silent_file(run: Any, make_samples: Callable[..., Path]) -> None:
    make_samples("a.wav", [0] * 8, 8)
    result = run("explain", "lsb", "--letter", "\0", "--file", "a.wav")
    assert "(frame 0).\nThe whole file is silent.\nThe hide command" in result.output
    assert "0 of 8 samples changed, by at most 0 here." in result.output and "out of 128." in result.output
    fields = json.loads(run("explain", "lsb", "--file", "a.wav", "--json").output)
    assert (fields["silent"], fields["first_frame"]) == (True, 0)
    assert fields["samples"][0] == {
        "hidden_bits": "0",
        "low_byte_before": "10000000",
        "low_byte_after": "10000000",
        "value_before": 0,
        "value_after": 0,
        "change": 0,
    }
    assert fields["samples"][1]["low_byte_before"] == "10000000"
    assert fields["samples"][1]["low_byte_after"] == "10000001"


def test_the_largest_change_has_no_sign(run: Any, make_samples: Callable[..., Path]) -> None:
    make_samples("a.wav", [99] * 8)
    output = run("explain", "lsb", "--letter", "\0", "--file", "a.wav").output
    assert "8 of 8 samples changed, by at most 1 here." in output


def test_what_is_read_back_is_not_taken_for_granted(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    wrong = Algorithm(
        "Wrong",
        8,
        lambda byte, bits: int("".join(map(str, bits)), 2) + 1,
        lambda byte: tuple(int(bit) for bit in f"{byte:08b}"),
    )
    monkeypatch.setitem(ALGORITHMS, "wrong", wrong)
    assert json.loads(run("explain", "wrong", "--json").output)["read_back"] == "i"
    assert "Reading the same bits gives 'i'" in run("explain", "wrong").output


def test_json_of_a_new_algorithm(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    high = Algorithm(
        name="High",
        bits_per_byte=4,
        embed_bits=lambda byte, bits: byte & 15 | int("".join(map(str, bits)), 2) << 4,
        extract_bits=lambda byte: tuple(int(bit) for bit in f"{byte >> 4:04b}"),
        explanation="Uses four high bits.",
    )
    monkeypatch.setitem(ALGORITHMS, "high", high)
    fields = json.loads(run("explain", "high", "--json").output)
    assert (fields["key"], fields["name"], fields["bits_per_byte"]) == ("high", "High", 4)
    assert (fields["legacy"], fields["strengths"], fields["weaknesses"]) == (False, [], [])
    assert [row["hidden_bits"] for row in fields["samples"]] == ["0110", "1000"]
    assert [row["low_byte_after"][:4] for row in fields["samples"]] == ["0110", "1000"]
    assert (fields["read_back"], fields["largest_possible_change"]) == ("h", 240)
    output = run("explain", "high").output
    assert "Strengths" not in output and "Weaknesses" not in output
    assert "Uses four high bits." in output and '-m "Hello" -a high\n' in output
    assert "high: Uses four high bits.\n" in run("explain").output


def test_changed_bits_have_a_colour_only_in_a_terminal(run: Any) -> None:
    coloured = run("explain", "lsb", terminals=ALL, columns=40)
    assert "\x1b[1;30;43m[1]" in coloured.output
    plain = run("explain", "lsb").output
    assert coloured.text == plain
    for options in ({"NO_COLOR": "1"}, {"TERM": "dumb"}, {"encoding": "ascii"}):
        assert run("explain", "lsb", terminals=ALL, columns=40, **options).output == plain
    assert run("explain", "lsb", "--plain", terminals=ALL).output == plain


@pytest.mark.skipif(os.name == "nt", reason="Windows does not allow such names")
def test_a_file_name_cannot_control_the_terminal(run: Any, make_samples: Callable[..., Path]) -> None:
    name = "x\x1b[2J‮\n.wav"
    make_samples(name, [9] * 8)
    result = run("explain", "lsb", "--file", name, terminals=ALL)
    assert "8 samples of x\\x1b[2J\\u202e\\n.wav, from 0.000 s" in result.text
    assert "\x1b[2J" not in result.seen and "‮" not in result.seen


def test_samples_that_already_held_the_bits(run: Any, make_samples: Any) -> None:
    make_samples("a.wav", [1000] * 64)
    advice = "These samples already held the bits, so nothing had to change. To see a change, try another"
    assert advice in run("explain", "lsb", "--file", "a.wav", "--letter", "\0").output
    assert advice not in run("explain", "lsb", "--file", "a.wav").output
