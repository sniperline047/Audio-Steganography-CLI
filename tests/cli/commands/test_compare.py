"""Tests for audiosteg/cli/commands/compare.py."""

import json
import os
import shutil
import sys
import wave
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, pack

from audiosteg.analysis import difference
from audiosteg.cli import player
from audiosteg.cli.commands.compare import HINT, gain_number, number, width_number
from audiosteg.cli.commands.hide import SAMPLE_FILE
from audiosteg.cli.errors import UsageError

SUMMARY = (
    "Sounds the same? Very likely. The change is far quieter than the sound, but only listening can tell.\n"
    "Quality:         Excellent (SNR: 86.0 dB)\n"
    "Changed:         1 of 8,000 samples (0.01%), from 0.013 s to 0.013 s\n"
)


@pytest.fixture
def pair(make_pair: Callable[..., tuple[str, str]]) -> tuple[str, str]:
    """Two files of one second, with one step of difference in frame 100."""
    original = [225] * 8000
    return make_pair(original, [*original[:100], 226, *original[101:]])


def test_three_lines_for_people_who_do_not_need_numbers(run: Any, pair: tuple[str, str]) -> None:
    result = run("compare", *pair)
    assert (result.code, result.output, result.errors) == (0, SUMMARY, f"{HINT}\n")
    assert run("compare", *pair, terminals=ALL).errors.startswith("Comparing the files...\n")


SHOWN = {
    "snr": "SNR: 86.0 dB",
    "psnr": "PSNR: 129.3 dB",
    "changes": "Changed samples: 1 of 8,000",
    "where": "Where: from 0.013 s",
    "waveform": "Waveform: original",
}


@pytest.mark.parametrize(
    ("words", "names"),
    [
        (["--details"], ["snr", "psnr", "changes", "where", "waveform"]),
        (["--show", "snr"], ["snr"]),
        (["--show", "where,psnr"], ["psnr", "where"]),
        (["--show", "waveform", "--show", "changes,snr,changes"], ["snr", "changes", "waveform"]),
        (["--show=psnr", "--show=psnr"], ["psnr"]),
    ],
)
def test_the_chosen_metrics_are_shown_once_and_in_order(
    run: Any, pair: tuple[str, str], words: list[str], names: list[str]
) -> None:
    result = run("compare", *pair, *words, "--plain")
    assert (result.code, result.errors) == (0, "")
    for name, text in SHOWN.items():
        assert result.output.count(text) == (name in names)
    positions = [
        result.output.index(f"\n{SHOWN[name]}" if i else SHOWN[name]) for i, name in enumerate(names)
    ]
    assert positions == sorted(positions)
    assert "Sounds the same?" not in result.output


@pytest.mark.parametrize(
    ("words", "reason"),
    [
        (
            ["--show", ""],
            "--show needs names separated by commas. Choose from: snr, psnr, changes, where, wave",
        ),
        (["--show", "snr,"], "--show needs names"),
        (["--show", "SNR"], "--show needs names"),
        (["--show", "snr", "--show", "SECRET"], "--show needs names"),
        (["--show", "snr", "--details"], "not allowed with argument"),
        (["--from", "-1"], "--from, --to, and --gain need a number"),
        (["--from=-1"], "--from, --to, and --gain need a number such as 2 or 0.5."),
        (["--to", "nan"], "--from, --to, and --gain need a number"),
        (["--to", "1e3"], "--from, --to, and --gain need a number"),
        (["--to", "0,5"], "--from, --to, and --gain need a number"),
        (["--from", "1234567890"], "--from, --to, and --gain need a number"),
        (["--from", ".5"], "--from, --to, and --gain need a number"),
        (["--from", "٣"], "--from, --to, and --gain need a number"),
        (["--from", "0.5", "--to", "0.5"], "--from must be smaller than --to."),
        (["--from", "0.5", "--to", "0.2"], "--from must be smaller than --to."),
        (["--from", "1"], "--from and --to must be inside the audio, which is 1.000 s long."),
        (["--to", "1.0002"], "--from and --to must be inside the audio"),
        (["--to", "0"], "There is no sample between --from and --to."),
        (["--from", "0.50001", "--to", "0.50002"], "There is no sample between --from and --to."),
        (["--width", "19", "--details"], "--width needs a whole number from 20 to 500."),
        (["--width", "501", "--details"], "--width needs a whole number"),
        (["--width", "30.0", "--details"], "--width needs a whole number"),
        (["--width", "1234567890", "--details"], "--width needs a whole number"),
        (["--width", "30"], "--width needs --details or --show waveform."),
        (["--width", "30", "--show", "snr"], "--width needs --details or --show waveform."),
        (["--gain", "2"], "--gain needs --play, --play difference, or --save_difference."),
        (["--gain", "2", "--play", "original"], "--gain needs --play"),
        (["--gain", "0.999", "--play"], "--gain needs a number from 1 on."),
        (["--gain", "x", "--play"], "--from, --to, and --gain need a number"),
        (["--force"], "--force needs --save_difference."),
        (["--save_difference", ""], "A path is empty."),
        (["--play=SECRET"], "--play can have one of these values: original, encoded, difference."),
        (["--play="], "--play can have one of these values"),
        (["--play=all"], "--play can have one of these values"),
        (["--play", "SECRET"], "There is an extra word. --play can have one of these values"),
        (["SECRET"], "unknown option or an extra word"),
    ],
)
def test_options_that_make_no_sense(
    run: Any, pair: tuple[str, str], sounds: list[Any], words: list[str], reason: str
) -> None:
    result = run("compare", *pair, *words)
    assert (result.code, result.output) == (2, "")
    assert reason in result.errors and "SECRET" not in result.errors
    assert sounds == []


def test_missing_files_are_usage_errors_and_files_that_do_not_exist_are_not(
    run: Any, pair: tuple[str, str]
) -> None:
    assert (run("compare").code, run("compare", "a.wav").code) == (2, 2)
    for words in ((pair[0], "missing.wav"), ("missing.wav", pair[1])):
        result = run("compare", *words)
        assert (result.code, result.output) == (1, "")
        assert "does not exist: missing.wav" in result.errors


def test_the_numbers_that_options_accept() -> None:
    assert (number("0"), number("2"), number("0.5")) == (0, 2, Fraction(1, 2))
    assert number("999999999.999999999") == Fraction(10**18 - 1, 10**9)
    assert (gain_number("1"), gain_number("1.5")) == (1, Fraction(3, 2))
    assert (width_number("20"), width_number("500"), width_number("0020")) == (20, 500, 20)
    with pytest.raises(UsageError):
        number("2\n")


@pytest.mark.parametrize(
    ("words", "first", "frames"),
    [
        ([], 0, 8000),
        (["--from", "0"], 0, 8000),
        (["--from", "0.5"], 4000, 4000),
        (["--to", "1"], 0, 8000),
        (["--to", "0.0125"], 0, 100),
        (["--from", "0.0125", "--to", "0.012625"], 100, 1),
        (["--from", "0.9999"], 7999, 1),
        (["--from", "0.0002", "--to", "0.00049"], 1, 2),
    ],
)
def test_a_part_by_its_times(
    run: Any, pair: tuple[str, str], words: list[str], first: int, frames: int
) -> None:
    fields = json.loads(run("compare", *pair, *words, "--json").output)
    assert (fields["first_frame"], fields["frames"], fields["total_frames"]) == (first, frames, 8000)
    assert fields["identical"] is not (first <= 100 < first + frames)
    text = run("compare", *pair, *words).output
    assert ("The rest was not compared." in text) is (frames < 8000)


def test_files_without_samples(run: Any, make_pair: Any) -> None:
    paths = make_pair([], [])
    result = run("compare", *paths, "--details", "--save_difference", "d.wav")
    assert result.code == 0
    assert "nothing, because there are no samples" in result.output
    assert result.errors == "There is no difference in what was compared, so nothing was saved.\n"
    for words in (["--from", "0"], ["--to", "0.1"]):
        assert "The files have no samples" in run("compare", *paths, *words).errors


@pytest.mark.parametrize(
    ("words", "options", "columns"),
    [
        ([], {}, 100),
        ([], {"columns": 60}, 60),
        (["--width", "30"], {"columns": 60}, 30),
        (["--width", "200"], {"columns": 60}, 200),
        ([], {"terminals": ALL, "columns": 300}, 100),
        ([], {"terminals": ALL, "columns": 12}, 12),
        (["--width", "200"], {"terminals": ALL, "columns": 60}, 60),
        (["--width", "200"], {"terminals": ALL, "columns": 60, "TERM": "dumb"}, 60),
        (["--width", "40"], {"terminals": ALL, "columns": 60}, 40),
        (["--width", "500"], {"terminals": ALL, "columns": 600}, 500),
    ],
)
def test_the_width_of_a_waveform(
    run: Any, pair: tuple[str, str], words: list[str], options: dict[str, Any], columns: int
) -> None:
    result = run("compare", *pair, "--show", "waveform", *words, NO_COLOR="1", **options)
    lines = result.output.splitlines()
    assert len(lines[1]) == columns
    assert (
        len(
            json.loads(run("compare", *pair, "--details", "--json", columns=33).output)["waveform"][
                "original"
            ]
        )
        == 80
    )


def test_a_json_width_is_never_limited_by_a_terminal(run: Any, pair: tuple[str, str]) -> None:
    words = ["--show", "waveform", "--json", "--width", "200"]
    result = json.loads(run("compare", *pair, *words, terminals=ALL, columns=40).output)
    assert {len(values) for values in result["waveform"].values()} == {200}


def read_wav(path: Path) -> tuple[int, int, int, bytes]:
    with wave.open(str(path)) as audio:
        return (*audio.getparams()[:3], audio.readframes(audio.getnframes()))


@pytest.mark.parametrize(
    ("words", "value", "said", "json_gain", "capped"),
    [
        ([], 8230, "amplified 8,230 times.", 8230, False),
        (["--gain", "2.5"], 3, "amplified 2.5 times.", 2.5, False),
        (["--gain", "8230"], 8230, "amplified 8,230 times.", 8230, False),
        (
            ["--gain", "8231"],
            8230,
            "amplified 8,230 times (capped from 8,231 times to a safe level).",
            8230,
            True,
        ),
    ],
)
def test_saving_the_difference(
    run: Any,
    pair: tuple[str, str],
    tmp_path: Path,
    words: list[str],
    value: int,
    said: str,
    json_gain: float,
    capped: bool,
) -> None:
    result = run("compare", *pair, "--save_difference", "new/d.wav", *words)
    assert result.code == 0
    saved = tmp_path / "new" / "d.wav"
    assert f"Difference saved: {os.path.join('new', 'd.wav')}\n  It was {said} Its loudest" in result.output
    expected = [0] * 8000
    expected[100] = value
    assert read_wav(saved) == (1, 2, 8000, pack(expected, 16))
    fields = json.loads(
        run("compare", *pair, "--save_difference", saved, "--force", "--json", *words).output
    )["difference"]
    assert fields == {
        "file": str(Path(os.path.realpath(tmp_path), "new", "d.wav")),
        "gain": json_gain,
        "capped": capped,
    }
    assert sorted(os.listdir(tmp_path)) == ["a.wav", "b.wav", "new"]


def test_only_the_part_is_saved(run: Any, pair: tuple[str, str], tmp_path: Path) -> None:
    words = ["--from", "0.012375", "--to", "0.012625", "--gain", "3", "--save_difference", "d.wav"]
    assert run("compare", *pair, *words).code == 0
    assert read_wav(tmp_path / "d.wav")[3] == pack([0, 3], 16)


def test_the_sample_cannot_be_replaced_by_its_difference(run: Any, tmp_path: Path) -> None:
    assert run("hide", "sample", "-m", "x").code == 0
    copy = shutil.copy(SAMPLE_FILE, tmp_path / "c.wav")
    for words in (["sample", copy], [tmp_path / "sample.stego.wav", copy]):
        result = run("compare", *words, "--save_difference", SAMPLE_FILE, "--force")
        assert (result.code, result.output) == (1, "")


def test_the_sample_word_is_for_both_files(run: Any, tmp_path: Path) -> None:
    assert "Every sample is the same" in run("compare", "sample", "sample").output
    shutil.copy(SAMPLE_FILE, tmp_path / "sample")
    fields = json.loads(run("compare", "./sample", "sample", "--json").output)
    assert (fields["original"], fields["encoded"]) == ("./sample", SAMPLE_FILE)


def test_an_input_is_never_replaced(run: Any, pair: tuple[str, str], tmp_path: Path) -> None:
    before = [Path(path).read_bytes() for path in pair]
    names = [*pair, "./a.wav", "./b.wav", "folder/../b.wav"]
    (tmp_path / "folder").mkdir()
    os.link(pair[0], tmp_path / "hard_a.wav")
    os.link(pair[1], tmp_path / "hard_b.wav")
    names += ["hard_a.wav", "hard_b.wav"]
    if os.path.exists(pair[0].replace("a.wav", "A.WAV")):
        names += ["A.WAV", "B.WAV"]
    for name in names:
        for force in ([], ["--force"]):
            result = run("compare", *pair, "--save_difference", name, *force)
            assert (result.code, result.output) == (1, "")
            assert "The input and output must be different files." in result.errors
    assert [Path(path).read_bytes() for path in pair] == before


@pytest.mark.parametrize(("name", "problem"), [("folder", "not a regular file"), ("folder/", "is a folder")])
def test_a_folder_is_never_replaced(
    run: Any, pair: tuple[str, str], tmp_path: Path, name: str, problem: str
) -> None:
    (tmp_path / "folder").mkdir()
    result = run("compare", *pair, "--save_difference", name, "--force")
    assert (result.code, problem in result.errors) == (1, True)


def test_a_link_is_never_replaced(run: Any, pair: tuple[str, str], tmp_path: Path) -> None:
    (tmp_path / "target.wav").write_bytes(b"keep")
    try:
        (tmp_path / "link.wav").symlink_to(tmp_path / "target.wav")
    except OSError:
        pytest.skip("this system does not allow links")
    result = run("compare", *pair, "--save_difference", "link.wav", "--force")
    assert (result.code, "is a symbolic link" in result.errors) == (1, True)
    assert (tmp_path / "target.wav").read_bytes() == b"keep"


def test_a_file_is_replaced_only_with_permission(run: Any, pair: tuple[str, str], tmp_path: Path) -> None:
    saved = tmp_path / "d.wav"
    words = ["compare", *pair, "--save_difference", "d.wav"]
    for options, code in (
        ({}, 1),
        ({"terminals": ALL, "stdin": b"n\n"}, 1),
        ({"terminals": ALL, "stdin": b"\n"}, 1),
        ({"terminals": ("stdout", "stderr"), "stdin": b"y\n"}, 1),
        ({"terminals": ALL, "stdin": b"y\n"}, 0),
    ):
        saved.write_bytes(b"keep")
        assert run(*words, **options).code == code
        assert (saved.read_bytes() == b"keep") is (code == 1)
    saved.write_bytes(b"keep")
    result = run(*words)
    assert result.output == ""
    assert "already exists: d.wav\nAdd --force to replace it, or choose another name" in result.errors
    error = json.loads(run(*words, "--json").output)["error"]
    assert (error["type"], "another name for the difference" in error["hint"]) == ("file_exists", True)
    assert run(*words, "--force").code == 0
    assert read_wav(saved)[0] == 1


def test_without_a_difference_nothing_is_written_or_replaced(
    run: Any, pair: tuple[str, str], tmp_path: Path
) -> None:
    (tmp_path / "d.wav").write_bytes(b"keep")
    for name in ("d.wav", "new/e.wav"):
        for words in ([pair[0], pair[0]], [*pair, "--to", "0.01"]):
            result = run("compare", *words, "--save_difference", name, "--force")
            assert result.code == 0
            assert result.errors.endswith(
                "There is no difference in what was compared, so nothing was saved.\n"
            )
    assert (tmp_path / "d.wav").read_bytes() == b"keep"
    assert not (tmp_path / "new").exists()


def test_an_output_that_turns_into_an_input_is_not_replaced(
    run: Any, pair: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = Path(pair[1]).read_bytes()
    real = difference.write_difference
    (tmp_path / "d.wav").touch()

    def link_then_write(*args: Any) -> None:
        (tmp_path / "d.wav").unlink()
        os.link(pair[1], tmp_path / "d.wav")
        real(*args)

    monkeypatch.setattr(difference, "write_difference", link_then_write)
    result = run("compare", *pair, "--save_difference", "d.wav", "--force")
    assert result.code == 1
    assert Path(pair[1]).read_bytes() == before == (tmp_path / "d.wav").read_bytes()
    assert [name for name in os.listdir(tmp_path) if name.endswith(".tmp")] == []


def test_a_file_that_changes_leaves_nothing_behind(
    run: Any, pair: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(difference, "choose_gain", lambda *args: Fraction(8231))
    result = run("compare", *pair, "--save_difference", "new/d.wav")
    assert (result.code, result.output) == (1, "")
    assert "A file changed while it was being read." in result.errors
    assert sorted(os.listdir(tmp_path)) == ["a.wav", "b.wav"]


@pytest.mark.parametrize(
    ("words", "reason", "hint"),
    [
        (
            ["a.wav", "short.wav"],
            "The lengths differ: 2 and 1 frames.",
            "Compare a WAV file with the copy of it",
        ),
        (["cut.wav", "a.wav"], "shorter than its header says.", "This is about the original file."),
        (["a.wav", "cut.wav"], "shorter than its header says.", "This is about the encoded file."),
        (["a.wav", "text.wav"], "not a valid PCM WAV file", "This is about the encoded file."),
    ],
)
def test_files_that_cannot_be_compared(
    run: Any, make_samples: Any, tmp_path: Path, words: list[str], reason: str, hint: str
) -> None:
    whole = make_samples("a.wav", [1, 2]).read_bytes()
    make_samples("short.wav", [1])
    (tmp_path / "cut.wav").write_bytes(whole[:-1])
    (tmp_path / "text.wav").write_text("text")
    result = run("compare", *words, "--save_difference", "d.wav")
    assert (result.code, result.output) == (1, "")
    assert reason in result.errors and hint in result.errors
    error = json.loads(run("compare", *words, "--json").output)["error"]
    assert (error["type"], hint in error["hint"]) == ("unsupported_format", True)


def played_values(sounds: list[tuple[bytes, float]], tmp_path: Path) -> list[bytes]:
    result = []
    for data, _ in sounds:
        (tmp_path / "played.wav").write_bytes(data)
        result.append(read_wav(tmp_path / "played.wav")[3])
    return result


WHOLE = ["original", "encoded", "difference"]


@pytest.mark.parametrize(
    ("words", "names"),
    [
        (["{a}", "{b}", "--play"], WHOLE),
        (["--play", "{a}", "{b}"], WHOLE),
        (["{a}", "--play", "{b}"], WHOLE),
        (["{a}", "{b}", "--play", "--plain"], WHOLE),
        (["{a}", "{b}", "--play", "original"], ["original"]),
        (["--play", "encoded", "{a}", "{b}"], ["encoded"]),
        (["{a}", "--play", "difference", "{b}"], ["difference"]),
        (["{a}", "{b}", "--play=difference"], ["difference"]),
        (["{a}", "{b}", "--play", "original", "--play", "encoded"], ["encoded"]),
        (["{a}", "{b}", "--play", "original", "--play"], WHOLE),
        (["--play", "--", "original", "difference"], WHOLE),
        (["--play", "./original", "./difference"], WHOLE),
        (["--play", "original", "original", "difference"], ["original"]),
        (["original", "difference", "--play", "difference"], ["difference"]),
        (["original", "difference", "--play"], WHOLE),
    ],
)
def test_what_is_played(
    run: Any, make_pair: Any, tmp_path: Path, sounds: list[Any], words: list[str], names: list[str]
) -> None:
    a, b = make_pair([10, 20, 30], [10, 21, 28])
    shutil.copy(a, tmp_path / "original")
    shutil.copy(b, tmp_path / "difference")
    result = run("compare", *[word.format(a=a, b=b) for word in words])
    assert result.code == 0, result.errors
    values = {"original": [10, 20, 30], "encoded": [10, 21, 28], "difference": [0, 4115, -8230]}
    assert played_values(sounds, tmp_path) == [pack(values[name], 16) for name in names]
    assert [seconds for _, seconds in sounds] == [3 / 8000] * len(names)
    said = [line for line in result.errors.splitlines() if line.startswith("Playing")]
    expected = {
        "original": "Playing the original (0.000 s). Ctrl-C stops.",
        "encoded": "Playing the encoded file (0.000 s). Ctrl-C stops.",
        "difference": "Playing the difference, amplified 4,115 times (0.000 s). Ctrl-C stops.",
    }
    assert said == [expected[name] for name in names]
    assert "Playing" not in result.output


def test_only_the_part_is_played_with_the_wanted_gain(
    run: Any, pair: tuple[str, str], tmp_path: Path, sounds: list[Any]
) -> None:
    words = ["--play", "--from", "0.0125", "--to", "0.01275", "--gain", "9000"]
    result = run("compare", *pair, *words)
    assert played_values(sounds, tmp_path) == [
        pack(values, 16) for values in ([225, 225], [226, 225], [8230, 0])
    ]
    assert {seconds for _, seconds in sounds} == {2 / 8000}
    assert "amplified 8,230 times (capped from 9,000 times to a safe level) (0.000 s)" in result.errors


def test_no_difference_is_not_played(run: Any, pair: tuple[str, str], sounds: list[Any]) -> None:
    result = run("compare", pair[0], pair[0], "--play")
    assert (result.code, len(sounds)) == (0, 2)
    assert result.errors.endswith("There is no difference to play in what was compared.\n")


def test_playing_needs_text_and_a_player(
    run: Any, pair: tuple[str, str], tmp_path: Path, sounds: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    refused = json.loads(run("compare", *pair, "--play", "--json").output)
    assert refused["error"]["message"] == "--play cannot be used with --json."
    monkeypatch.setattr(player, "can_play", lambda: False)
    result = run("compare", *pair, "--play", "--save_difference", "d.wav")
    assert (result.code, result.output) == (1, "")
    assert result.errors.startswith("Error: No known audio player was found. Save the difference with --save")
    assert sounds == [] and not (tmp_path / "d.wav").exists()


def test_nothing_is_played_unless_it_is_wanted(run: Any, pair: tuple[str, str], sounds: list[Any]) -> None:
    assert run("compare", *pair, "--details", "--save_difference", "d.wav").code == 0
    assert run("compare", *pair, terminals=ALL).code == 0
    assert sounds == []


def test_the_numbers_come_before_the_sound(
    run: Any, pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch, sounds: list[Any]
) -> None:
    shown: list[str] = []

    def record(path: str, seconds: float) -> None:
        sys.stdout.flush()
        shown.append(sys.stdout.buffer.getvalue().decode())
        raise KeyboardInterrupt

    monkeypatch.setattr(player, "play", record)
    result = run("compare", *pair, "--play", "original")
    assert result.code == 130
    assert shown[0].replace("\r\n", "\n") == SUMMARY
    assert result.errors.endswith("Error: Interrupted.\n")


INJECTION = "x\x1b[2J\x1b]0;t\x07‮[red].wav"


@pytest.mark.parametrize("terminals", [(), ALL])
def test_a_name_cannot_control_the_terminal(
    run: Any, pair: tuple[str, str], terminals: tuple[str, ...]
) -> None:
    commands = [["compare", INJECTION, pair[1]], ["compare", pair[0], INJECTION]]
    if os.name != "nt":
        commands += [["compare", *pair, "--save_difference", INJECTION]] * 2
    for words in commands:
        result = run(*words, terminals=terminals)
        assert "x\\x1b[2J\\x1b]0;t\\x07\\u202e[red].wav" in result.text
        for unsafe in ("\x1b[2J", "\x1b]", "\x07", "‮"):
            assert unsafe not in result.seen
        assert run(*words, "--json").output.isascii()


@pytest.mark.xfail(strict=True, reason="a duration is rounded up, so the time that is shown is refused")
def test_the_duration_that_is_shown_is_accepted(run: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(frames=bytes(49_996), frame_rate=10_000)
    shown = run("inspect", "input.wav").output.split("Duration: ")[1].split(" s ")[0]
    assert run("compare", "input.wav", "input.wav", "--to", shown).code == 0
