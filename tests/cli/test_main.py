"""Tests for audiosteg/cli/main.py."""

import io
import json
import os
import shutil
import sys
import sysconfig
from collections.abc import Callable
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

import pytest
from conftest import PROGRAM

from audiosteg import decode
from audiosteg.cli import main
from audiosteg.cli.commands import reveal

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
posix_shell = pytest.mark.skipif(os.name == "nt", reason="a POSIX shell is needed to close a stream")


def shell(redirection: str) -> list[str]:
    return ["sh", "-c", f'"$0" "$@" {redirection}', *PROGRAM]


def test_the_console_command_from_the_project_folder(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    command = shutil.which("audiosteg", path=sysconfig.get_path("scripts"))
    assert command is not None, "the audiosteg command is not installed"
    output = tmp_path / "output.wav"
    words = ["hide", make_wav(), "-m", "hidden", "-o", output]
    assert run(*words, command=[command], cwd=PROJECT_ROOT).code == 0
    assert decode(str(output)) == "hidden"
    assert run("unknown", command=[command]).code == 2


def test_the_console_command_starts_the_whole_program() -> None:
    entry_points = distribution("audiosteg").entry_points
    assert entry_points.select(name="audiosteg")["audiosteg"].load() is main.main


def test_the_guided_mode_needs_a_terminal(run: Any) -> None:
    result = run()
    assert (result.code, result.output) == (2, "")
    assert "usage: audiosteg" in result.errors


def test_a_dumb_terminal_cannot_show_menus(terminal: Any) -> None:
    program = terminal(TERM="dumb")
    program.read("The guided mode needs a terminal")
    assert program.finish() == 2
    assert "\x1b" not in program.seen


@pytest.mark.parametrize("words", [[], ["hide"], ["reveal"], ["verify"], ["algorithms"]])
def test_every_command_has_help_with_examples(run: Any, words: list[str]) -> None:
    result = run(*words, "--help", encoding="ascii")
    assert (result.code, result.errors) == (0, "")
    assert "examples:\n" in result.output


def test_the_version(run: Any) -> None:
    version = distribution("audiosteg").version
    assert run("--version").output == f"audiosteg {version}\n"
    assert json.loads(run("--version", "--json").output)["version"] == version


@pytest.mark.parametrize(
    "words",
    [
        ["hide", "in.wav", "-m", "x", "-p", "TOP_SECRET"],
        ["hide", "in.wav", "-p=TOP_SECRET"],
        ["hide", "in.wav", "-pTOP_SECRET"],
        ["hide", "in.wav", "--passphrase=TOP_SECRET"],
        ["hide", "in.wav", "-a", "TOP_SECRET"],
        ["reveal", "in.wav", "--legacy", "TOP_SECRET"],
        ["reveal", "in.wav", "--TOP_SECRET"],
        ["-p", "TOP_SECRET"],
        ["TOP_SECRET"],
        ["hide"],
        ["hide", "in.wav", "-m"],
        ["hide", "in.wav", "-m", "x", "--message_file", "TOP_SECRET"],
        ["reveal", "in.wav", "-a", "lsb", "--legacy", "basic"],
        ["--TOP_SECRET"],
    ],
)
@pytest.mark.parametrize("as_json", [False, True])
def test_wrong_usage_never_shows_a_value(run: Any, words: list[str], as_json: bool) -> None:
    result = run(*words, *(["--json"] if as_json else []))
    assert result.code == 2
    assert "SECRET" not in result.output + result.errors
    if as_json:
        error = json.loads(result.output)["error"]
        assert (error["type"], error["exit_code"]) == ("usage", 2)
    else:
        assert result.errors.startswith("Error: ")


def test_a_failure_for_lack_of_memory_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def run_out_of_memory(path: str) -> None:
        raise MemoryError

    monkeypatch.setattr(reveal, "detect", run_out_of_memory)
    assert main.main(["reveal", "x.wav"]) == 1
    assert "memory" in capsys.readouterr().err


def test_ctrl_c_is_reported(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def interrupt(path: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(reveal, "detect", interrupt)
    assert main.main(["reveal", "x.wav", "--json"]) == 130
    assert json.loads(capsys.readouterr().out)["error"]["type"] == "interrupted"


@posix_shell
def test_a_closed_output_is_a_failure_and_changes_nothing(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "out.wav"
    result = run("hide", make_wav(), "-m", "x", "-o", output, command=shell(">&-"))
    assert result.code == 1
    assert "needs an open output" in result.errors
    assert not output.exists()


@posix_shell
def test_a_closed_input_matters_only_if_it_is_needed(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source, output = make_wav(), tmp_path / "out.wav"
    assert run("hide", source, "-o", output, command=shell("<&-")).code == 2
    assert not output.exists()
    assert run("hide", source, "-m", "x", "-o", output, command=shell("<&-")).code == 0


@posix_shell
def test_a_closed_error_stream_does_not_change_the_result(run: Any, make_wav: Callable[..., Path]) -> None:
    source = make_wav(frames=b"\xff" * 400)
    assert run("algorithms", command=shell("2>&-")).code == 0
    assert run("reveal", source, command=shell("2>&-")).code == 1


@posix_shell
def test_an_input_that_cannot_be_read_is_a_failure(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    command = shell(f'0>"{tmp_path / "write_only"}"')
    assert run("hide", make_wav(), "-o", tmp_path / "out.wav", command=command).code == 1
    assert not (tmp_path / "out.wav").exists()


@pytest.mark.skipif(not os.path.exists("/dev/full"), reason="this system has no /dev/full")
@pytest.mark.parametrize("words", [["algorithms"], ["algorithms", "--json"], ["--help"]])
def test_an_output_that_cannot_be_written_is_a_failure(run: Any, words: list[str]) -> None:
    assert run(*words, command=shell(">/dev/full")).code == 1


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
