"""Tests for audiosteg/cli/echo_view.py."""

import json
import random
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, PROJECT_ROOT

from audiosteg.algorithms.echo import ECHO
from audiosteg.cli.echo_view import make_ruler

pytestmark = pytest.mark.needs_signal

FIELDS_OF_THE_OTHERS = {
    "ok", "command", "key", "name", "bits_per_byte", "explanation", "samples_per_group",
    "needs_passphrase", "reads_like", "frames_per_bit", "legacy", "letter", "utf_8", "file", "first_frame",
    "silent", "how", "demo_seed", "samples", "groups", "read_back", "largest_possible_change", "strengths",
    "weaknesses",
}  # fmt: skip


@pytest.fixture
def noise(make_samples: Callable[..., Path]) -> Path:
    chooser = random.Random(1)
    return make_samples("noise.wav", [chooser.randint(-9000, 9000) for _ in range(40_000)])


def test_the_whole_text_is_the_one_in_the_documentation(run: Any) -> None:
    documentation = (PROJECT_ROOT / "docs" / "commands.md").read_text("utf-8")
    example = documentation.split("This is the output of `audiosteg explain echo`:")[1].split("```")[1]
    result = run("explain", "echo")
    assert (result.code, result.errors) == (0, "")
    number = re.compile(r"-?\d\.\d{3}\b")
    shown = [number.sub("#", line) for line in result.output.splitlines() if not line.startswith("  |")]
    expected = example.removeprefix("\n").splitlines()
    assert shown == [number.sub("#", line) for line in expected if not line.startswith("  |")]


def test_every_number_is_the_one_in_json(run: Any, noise: Path) -> None:
    text = run("explain", "echo", "--letter", "M", "--file", "noise.wav").output
    fields = json.loads(run("explain", "echo", "--letter", "M", "--file", "noise.wav", "--json").output)
    assert fields.keys() == FIELDS_OF_THE_OTHERS | {"delays", "level", "gain", "blocks"}
    assert (fields["key"], fields["delays"], fields["frames_per_bit"]) == ("echo", [25, 50], 1024)
    assert (fields["read_back"], fields["samples"], fields["groups"]) == ("M", [], [])
    assert "".join(str(block["hidden_bit"]) for block in fields["blocks"]) == f"{ord('M'):08b}"
    for block in fields["blocks"]:
        start, (zero, one) = f"  {block['block']}. ", block["peaks_after"]
        echo = f"echo after {block['delay']} frames ({block['delay'] / 8:.2f} ms)"
        assert f"{start}hide {block['hidden_bit']}: {echo}\n" in text
        assert f"{start}at 25: {zero:6.3f}   at 50: {one:6.3f}   read {block['read_bit']}, right\n" in text
    assert f"The echo is {fields['level']:.0%} as strong as the sound." in text
    assert "8 of 8 bits read right, which gives 'M'.\n" in text
    assert "from 0.0" in text and "8 blocks of 1,024 frames of noise.wav" in text


def test_bits_that_are_read_wrong_are_shown(run: Any, make_samples: Callable[..., Path]) -> None:
    make_samples("silence.wav", [0] * 10_000)
    result = run("explain", "echo", "--file", "silence.wav")
    assert result.code == 0
    assert "The whole file is silent.\n" in result.output
    assert "read 0, wrong\n" in result.output
    assert "5 of 8 bits read right, which gives '\\x00'.\nSome bits were read wrong" in result.output


def test_sound_that_is_made_quieter_is_named(run: Any, make_samples: Callable[..., Path]) -> None:
    chooser = random.Random(1)
    make_samples("loud.wav", [chooser.choice([-32768, 32767]) for _ in range(10_000)])
    output = run("explain", "echo", "--file", "loud.wav").output
    assert "so everything was made quieter (83.3%).\n" in output


@pytest.mark.parametrize(
    ("options", "bars"),
    [({}, False), ({"terminals": ALL}, True), ({"terminals": ALL, "encoding": "ascii"}, False)],
)
def test_the_picture_uses_only_what_the_output_can_show(
    run: Any, noise: Path, options: dict[str, Any], bars: bool
) -> None:
    output = run("explain", "echo", "--file", "noise.wav", NO_COLOR="1", **options).output
    assert ("█" in output) is bars
    assert output.isascii() is not bars
    lines = output.splitlines()
    first = next(index for index, line in enumerate(lines) if "before, at delays from 15 to 60" in line)
    pictures = [lines[first + 1 : first + 5], lines[first + 7 : first + 11]]
    assert all(line.startswith("  |") and len(line) == 49 for picture in pictures for line in picture)
    assert lines[first + 5] == lines[first + 11] == "             ^25                      ^50"
    marked = {line.index("^") for line in lines if line.startswith("   ") and "^25" in line}
    assert marked == {3 + 25 - 15}


def test_each_step_waits(run: Any, noise: Path) -> None:
    result = run("explain", "echo", "--file", "noise.wav", "--step", stdin=b"\n" * 4, terminals=ALL)
    assert result.code == 0
    assert result.text.count("Press Enter to continue.") == 4


def test_the_ruler_marks_the_delays() -> None:
    ruler = make_ruler(ECHO.delays)
    assert [ruler.index(f"^{delay}") + 15 for delay in ECHO.delays] == [25, 50]
