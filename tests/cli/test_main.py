"""Tests for audiosteg/cli/main.py."""

import io
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Callable
from importlib.metadata import distribution
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, PROGRAM, TIMEOUT, environment

from audiosteg import decode, encode
from audiosteg.algorithms.lsb import LSB
from audiosteg.cli import main
from audiosteg.cli.commands import reveal
from audiosteg.cli.views import View

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
posix_shell = pytest.mark.skipif(os.name == "nt", reason="a POSIX shell is needed to close a stream")


def shell(redirection: str) -> list[str]:
    return ["sh", "-c", f'"$0" "$@" {redirection}', *PROGRAM]


def test_the_console_command_from_the_project_folder(
    run_process: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    command = shutil.which("audiosteg", path=sysconfig.get_path("scripts"))
    assert command is not None, "the audiosteg command is not installed"
    output = tmp_path / "output.wav"
    words = ["hide", make_wav(), "-m", "hidden", "-o", output]
    assert run_process(*words, command=[command], cwd=PROJECT_ROOT).code == 0
    assert decode(str(output)) == "hidden"


def test_the_console_command_starts_the_whole_program() -> None:
    entry_points = distribution("audiosteg").entry_points
    assert entry_points.select(name="audiosteg")["audiosteg"].load() is main.main


GUIDED = ["questionary", "prompt_toolkit", "cryptography"]
ANALYSIS = ["audiosteg.analysis.quality", "audiosteg.analysis.walkthrough", "audiosteg.analysis.inspection"]


@pytest.mark.parametrize(
    ("words", "unwanted"),
    [
        (["hide", "input.wav", "-m", "x", "-o", "out.wav"], [*GUIDED, *ANALYSIS, "audiosteg.cli.player"]),
        (["algorithms"], [*GUIDED, *ANALYSIS, "audiosteg.cli.player"]),
        (["explain"], [*GUIDED, "audiosteg.cli.player", *ANALYSIS[::2]]),
        (["inspect", "input.wav"], [*GUIDED, "audiosteg.cli.player", *ANALYSIS[:2]]),
        (["compare", "input.wav", "input.wav", "--json"], [*GUIDED, "audiosteg.cli.player", *ANALYSIS[1:]]),
    ],
)
def test_commands_load_only_what_they_need(
    make_wav: Callable[..., Path], tmp_path: Path, words: list[str], unwanted: list[str]
) -> None:
    program = (
        "import sys; from audiosteg.cli.main import main; code = main(sys.argv[2:]); "
        "print([name for name in sys.argv[1].split() if name in sys.modules], code, file=sys.stderr)"
    )
    make_wav()
    finished = subprocess.run(
        [sys.executable, "-c", program, " ".join(unwanted), *words],
        capture_output=True,
        cwd=tmp_path,
        env=environment(),
        timeout=TIMEOUT,
    )
    assert finished.stderr.split()[-2:] == [b"[]", b"0"]


@pytest.mark.parametrize("terminals", [c for size in range(3) for c in combinations(ALL, size)])
def test_the_guided_mode_needs_three_terminals(run: Any, terminals: tuple[str, ...]) -> None:
    result = run(terminals=terminals)
    assert (result.code, result.output) == (2, "")
    assert "usage: audiosteg" in result.errors
    assert "Error: The guided mode needs a terminal. Choose a command instead." in result.errors


@pytest.mark.parametrize("term", ["dumb", "unknown"])
def test_a_dumb_terminal_cannot_show_menus(run: Any, term: str) -> None:
    result = run(terminals=ALL, TERM=term)
    assert (result.code, "\x1b" in result.seen) == (2, False)
    assert "The guided mode needs a terminal" in result.errors


def test_the_guided_mode_has_no_json(run: Any) -> None:
    result = run("--json", terminals=ALL)
    document = json.loads(result.output)
    assert (result.code, document["command"], document["error"]["type"]) == (2, None, "usage")


def test_the_version(run: Any) -> None:
    version = distribution("audiosteg").version
    assert run("--version").output == f"audiosteg {version}\n"
    expected = {"ok": True, "command": None, "version": version}
    assert json.loads(run("--version", "--json").output) == expected


def test_ctrl_c_while_an_error_is_shown_is_not_a_traceback(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(*words: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(View, "show_error", interrupt)
    assert run("reveal", "missing.wav").code == 130


def test_a_shared_interrupt_line_is_only_for_a_terminal(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(path: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(reveal, "detect", interrupt)
    for terminals, start in (((), "Error: Interrupted."), (("stderr",), "\nError: Interrupted.")):
        result = run("reveal", "x.wav", terminals=terminals, NO_COLOR="1")
        assert (result.code, result.errors) == (130, f"{start}\n")


def test_a_program_error_is_not_hidden(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(path: str) -> None:
        raise ZeroDivisionError

    monkeypatch.setattr(reveal, "detect", fail)
    with pytest.raises(ZeroDivisionError):
        run("reveal", "x.wav")


@posix_shell
def test_a_closed_output_is_a_failure_and_changes_nothing(
    run_process: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "out.wav"
    result = run_process("hide", make_wav(), "-m", "x", "-o", output, command=shell(">&-"))
    assert result.code == 1
    assert "needs an open output" in result.errors
    assert not output.exists()


@posix_shell
@pytest.mark.parametrize("stream", ["<&-", "2>&-"])
@pytest.mark.parametrize("command", ["hide", "reveal", "verify"])
def test_a_closed_input_or_error_stream_matters_only_if_it_is_needed(
    run_process: Any, make_wav: Callable[..., Path], tmp_path: Path, stream: str, command: str
) -> None:
    encode(str(make_wav()), str(tmp_path / "plain.wav"), "x", LSB)
    words = {"hide": ["input.wav", "-m", "x"], "reveal": ["plain.wav"], "verify": ["plain.wav", "-m", "x"]}
    result = run_process(command, *words[command], command=shell(stream))
    assert result.code == 0
    assert result.output


@posix_shell
def test_a_closed_input_is_not_a_message(
    run_process: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    assert run_process("hide", make_wav(), "-o", "out.wav", command=shell("<&-")).code == 2
    assert not (tmp_path / "out.wav").exists()


@posix_shell
def test_an_input_that_cannot_be_read_is_a_failure(
    run_process: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    command = shell(f'0>"{tmp_path / "write_only"}"')
    assert run_process("hide", make_wav(), "-o", "out.wav", command=command).code == 1
    assert not (tmp_path / "out.wav").exists()


@pytest.mark.skipif(not os.path.exists("/dev/full"), reason="this system has no /dev/full")
@pytest.mark.parametrize("words", [["algorithms"], ["algorithms", "--json"], ["--help"]])
def test_an_output_that_cannot_be_written_is_a_failure(run_process: Any, words: list[str]) -> None:
    assert run_process(*words, command=shell(">/dev/full")).code == 1


@pytest.mark.parametrize("words", [["algorithms"], ["--help"], ["--version", "--json"]])
def test_a_reader_that_left_is_a_failure_without_a_traceback(tmp_path: Path, words: list[str]) -> None:
    reading, writing = os.pipe()
    os.close(reading)
    process = subprocess.run(
        [*PROGRAM, *words], stdout=writing, stderr=subprocess.PIPE, env=environment(), timeout=TIMEOUT
    )
    os.close(writing)
    assert process.returncode == 1
    assert process.stderr.strip() in (b"", b"Error: The output was closed.")


@pytest.mark.parametrize("missing", ["stdin", "stdout", "stderr"])
def test_missing_streams_do_not_crash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    monkeypatch.setattr(sys, missing, None)
    if missing == "stdout":
        assert main.main(["algorithms"]) == 1
        assert "needs an open output" in capsys.readouterr().err
        return
    assert main.main(["algorithms"]) == 0
    if missing == "stderr":
        sys.stderr.close()
    else:
        sys.stdin.close()


def test_an_unknown_command_is_told_about_help(run: Any) -> None:
    assert "add --help" in run("unknown").errors
