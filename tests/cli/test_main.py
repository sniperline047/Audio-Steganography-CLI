"""Tests for cli/main.py."""

import io
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import IO

import pytest

from algorithms import (
    basic_lsb_steganography,
    enhanced_lsb_steganography_no_flip,
    enhanced_lsb_steganography_with_flip,
)
from cli import main
from cli.config import ALGORITHMS

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_SCRIPT = PROJECT_ROOT / "cli" / "main.py"
TIMEOUT = 60
StartProcess = Callable[[], subprocess.Popen[bytes]]
EXIT = "4"
MAIN_MENU = "1) Encode a message\n2) Decode a message\n3) Calculate accuracy\n4) Exit\n"
ALGORITHM_MENU = (
    "1) Basic LSB Steganography\n"
    "2) Enhanced LSB Steganography with Bit Flipping\n"
    "3) Enhanced LSB Steganography without Bit Flipping\n"
)
DEFAULT_FILES = [
    (1, "basic_lsb_encoded.wav"),
    (2, "enhanced_lsb_encoded_flip.wav"),
    (3, "enhanced_lsb_encoded_no_flip.wav"),
]
ALGORITHM_MODULES = [
    (1, basic_lsb_steganography),
    (2, enhanced_lsb_steganography_with_flip),
    (3, enhanced_lsb_steganography_no_flip),
]

posix_shell = pytest.mark.skipif(os.name == "nt", reason="a POSIX shell is needed to close a stream")
needs_sigint = pytest.mark.skipif(
    os.name == "nt" or signal.getsignal(signal.SIGINT) == signal.SIG_IGN,
    reason="Ctrl-C cannot be sent to one process here",
)


class Result:
    """The outcome of one CLI run."""

    def __init__(self, code: int, output: bytes, errors: bytes) -> None:
        self.code = code
        self.output = output.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        self.errors = errors.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        assert "Traceback" not in self.errors
        assert "Exception ignored" not in self.errors


def environment(encoding: str = "utf-8") -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": encoding}


def run(
    *lines: str | bytes,
    script: Path = MAIN_SCRIPT,
    command: list[str] | None = None,
    cwd: Path | None = None,
    encoding: str = "utf-8",
) -> Result:
    """Run the CLI in a real process and type the lines."""
    typed = b"".join((line if isinstance(line, bytes) else line.encode()) + b"\n" for line in lines)
    finished = subprocess.run(
        command or [sys.executable, str(script)],
        input=typed,
        capture_output=True,
        cwd=cwd,
        env=environment(encoding),
        timeout=TIMEOUT,
    )
    return Result(finished.returncode, finished.stdout, finished.stderr)


def encode_lines(source: Path, output: Path | str, message: str = "hidden", algorithm: int = 1) -> list[str]:
    return ["1", str(algorithm), message, str(source), str(output)]


def decode_lines(path: Path | str, algorithm: int = 1) -> list[str]:
    return ["2", str(algorithm), str(path)]


def accuracy_lines(path: Path, expected: str, algorithm: int = 1) -> list[str]:
    return ["3", expected, str(algorithm), str(path)]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Copy the program so that default paths do not touch the repository."""
    copy = tmp_path / "project"
    for folder in ("algorithms", "cli", "utils", "input"):
        shutil.copytree(PROJECT_ROOT / folder, copy / folder, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


@pytest.fixture
def start(tmp_path: Path) -> StartProcess:
    """Return a function that starts the CLI for a test that must interact with it."""

    def start_process() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmp_path,
            env=environment(),
        )

    return start_process


def read_until(stream: IO[bytes], ending: bytes) -> None:
    """Read until the program shows a prompt."""
    seen = b""
    while not seen.endswith(ending):
        byte = stream.read(1)
        assert byte, f"the program stopped before {ending!r}"
        seen += byte


@pytest.mark.parametrize(("number", "file_name"), DEFAULT_FILES)
def test_default_paths_work_from_another_folder(
    project: Path, tmp_path: Path, number: int, file_name: str
) -> None:
    sample = (project / "input" / "original_sample.wav").read_bytes()
    result = run(
        "1", str(number), "Hello 🎵", "", "",
        "2", str(number), "",
        "3", "Hello 🎵", str(number), "",
        EXIT,
        script=project / "cli" / "main.py",
        cwd=tmp_path,
    )  # fmt: skip
    assert (result.code, result.errors) == (0, "")
    assert "Decoded message: Hello 🎵\n" in result.output
    assert "Accuracy of decoded message: 100.00%\nExact match: yes\n" in result.output
    assert os.listdir(project / "output") == [file_name]
    assert (project / "input" / "original_sample.wav").read_bytes() == sample


@pytest.mark.parametrize(("number", "module"), ALGORITHM_MODULES)
def test_each_menu_number_uses_its_own_algorithm(
    make_wav: Callable[..., Path], tmp_path: Path, number: int, module: ModuleType
) -> None:
    source = make_wav()
    expected = tmp_path / "expected.wav"
    output = tmp_path / "output.wav"
    module.encode(str(source), str(expected), "hidden")
    result = run(*encode_lines(source, output, algorithm=number), *decode_lines(output, number), EXIT)
    assert result.code == 0
    assert output.read_bytes() == expected.read_bytes()
    assert "Decoded message: hidden\n" in result.output


def test_the_module_entry_point_from_the_project_folder(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    result = run(
        *encode_lines(make_wav(), output), *decode_lines(output), EXIT,
        command=[sys.executable, "-m", "cli.main"],
        cwd=PROJECT_ROOT,
    )  # fmt: skip
    assert result.code == 0
    assert "Decoded message: hidden\n" in result.output


def test_relative_paths_belong_to_the_current_folder(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    make_wav()
    result = run("1", "1", "hidden", "input.wav", "a folder/out.wav", EXIT, cwd=tmp_path)
    assert result.code == 0
    assert basic_lsb_steganography.decode(str(tmp_path / "a folder" / "out.wav")) == "hidden"


def test_menus_are_in_the_documented_order() -> None:
    result = run("2", "1", "missing.wav", EXIT)
    assert MAIN_MENU in result.output
    assert ALGORITHM_MENU in result.output
    assert result.output.index(MAIN_MENU) < result.output.index(ALGORITHM_MENU)


def test_invalid_menu_choices_are_asked_again_without_failing() -> None:
    result = run("0", "5", "x", "", EXIT)
    assert (result.code, result.errors) == (0, "")
    assert result.output.count(MAIN_MENU) == 5


def test_an_invalid_algorithm_is_asked_again_and_the_message_is_kept(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(make_wav()), str(output), "hidden")
    result = run("3", "hidden", "4", "", "x", "1", str(output), EXIT)
    assert (result.code, result.errors) == (0, "")
    assert "Exact match: yes\n" in result.output
    assert result.output.count(ALGORITHM_MENU) == 4
    assert result.output.count(MAIN_MENU) == 2


@pytest.mark.parametrize(
    ("answer", "replaced"), [("", False), ("n", False), ("no", False), ("y", True), ("yes", True)]
)
def test_overwrite_prompt(make_wav: Callable[..., Path], tmp_path: Path, answer: str, replaced: bool) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(source), str(output), "old")
    result = run(*encode_lines(source, output, "new"), answer, EXIT)
    assert (result.code, result.errors) == (0, "")
    assert basic_lsb_steganography.decode(str(output)) == ("new" if replaced else "old")
    assert ("Nothing was written." in result.output) is not replaced


def test_a_file_that_appears_after_the_prompts_is_not_replaced(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    answers = encode_lines(source, output)[1:]

    def encode_late(input_path: str, output_path: str, message: str, overwrite: bool) -> None:
        output.write_bytes(b"theirs")
        basic_lsb_steganography.encode(input_path, output_path, message, overwrite)

    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    monkeypatch.setitem(ALGORITHMS[1], "encode", encode_late)
    assert main.run_operation(main.handle_encode) is False
    assert output.read_bytes() == b"theirs"


def test_the_input_file_cannot_be_the_output_and_is_refused_before_any_overwrite_prompt(
    make_wav: Callable[..., Path],
) -> None:
    source = make_wav()
    original = source.read_bytes()
    result = run(*encode_lines(source, source), EXIT)
    assert result.code == 1
    assert "must be different files" in result.errors
    assert "Overwrite" not in result.output
    assert source.read_bytes() == original


def test_an_output_folder_is_refused_before_any_overwrite_prompt(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    result = run(*encode_lines(make_wav(), tmp_path), EXIT)
    assert result.code == 1
    assert "not a regular file" in result.errors
    assert "Overwrite" not in result.output


def test_every_kind_of_failure_is_reported_and_the_menu_continues(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_wav(frames=b"\xff" * 400)
    text = tmp_path / "text.wav"
    text.write_text("not audio " * 10)
    attempts = {
        "missing.wav": decode_lines(tmp_path / "missing.wav"),
        "not a regular file": decode_lines(tmp_path),
        "not a valid PCM WAV": decode_lines(text),
        "No hidden message": accuracy_lines(source, "x"),
        "too large": encode_lines(source, tmp_path / "out.wav", "x" * 100),
        "null": decode_lines("a\0b.wav"),
    }
    for reason, lines in attempts.items():
        result = run(*lines, *decode_lines(source), EXIT)
        assert result.code == 1
        assert reason in result.errors
        assert result.errors.count("Error:") == 2
        assert result.output.count(MAIN_MENU) == 3
    assert not (tmp_path / "out.wav").exists()


def test_a_later_success_does_not_hide_an_earlier_failure(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    lines = [*decode_lines(tmp_path / "missing.wav"), *encode_lines(make_wav(), tmp_path / "out.wav")]
    assert run(*lines, EXIT).code == 1
    assert run(*lines[:3]).code == 1


def test_a_failure_for_lack_of_memory_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def run_out_of_memory(path: str) -> str:
        raise MemoryError

    answers = ["1", ""]
    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    monkeypatch.setitem(ALGORITHMS[1], "decode", run_out_of_memory)
    assert main.run_operation(main.handle_decode) is False
    assert "memory" in capsys.readouterr().err


def test_accuracy_reports_the_difference(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(str(make_wav()), str(output), "hidden")
    result = run(*accuracy_lines(output, "hidXen??"), EXIT)
    assert result.code == 0
    assert "Accuracy of decoded message: 62.50%\nExact match: no\n" in result.output
    assert "Expected length: 8, decoded length: 6\n" in result.output


def test_an_empty_message_is_hidden_and_reported_as_empty(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    result = run(*encode_lines(make_wav(), output, ""), *decode_lines(output), EXIT)
    assert result.code == 0
    assert "The decoded message is empty." in result.output


def test_a_decoded_message_cannot_control_the_terminal(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    basic_lsb_steganography.encode(
        str(make_wav()), str(output), "\x1b]0;title\x07\x9b2J\u202egpj\nAccuracy: 100%"
    )
    result = run(*decode_lines(output), EXIT)
    assert result.code == 0
    expected = "Decoded message: \\x1b]0;title\\x07\\x9b2J\\u202egpj\\nAccuracy: 100%\n"
    assert expected in result.output


def test_paths_cannot_control_the_terminal(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav()
    output = tmp_path / "gpj\u202e.wav"
    result = run(
        *encode_lines(source, output),
        *encode_lines(source, output),
        "n",
        *encode_lines(source, "a\x1b[2J/"),
        EXIT,
    )
    assert result.code == 1
    assert "gpj\\u202e.wav already exists" in result.output
    assert "a\\x1b[2J/" in result.errors
    assert not any(character in result.output + result.errors for character in "\x1b\u202e")


def test_the_message_is_not_shown_or_logged_when_it_is_hidden(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_wav(frames=bytes(400))
    secret = "TOP_SECRET_" + "x" * 20
    folder = tmp_path / "working"
    folder.mkdir()
    result = run(
        *encode_lines(source, tmp_path / "out.wav", secret),
        *encode_lines(source, tmp_path / "too_large.wav", secret * 10),
        *encode_lines(tmp_path / "missing.wav", tmp_path / "no.wav", secret),
        EXIT,
        cwd=folder,
    )
    assert result.code == 1
    assert "TOP_SECRET" not in result.output + result.errors
    assert os.listdir(folder) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["input.wav", "out.wav", "working"]


def test_bytes_that_are_not_text_are_refused(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "out.wav"
    result = run("1", "1", b"bad \xff", str(make_wav()), str(output), EXIT)
    assert result.code == 1
    assert "not valid text" in result.errors
    assert not output.exists()


def test_a_terminal_without_unicode_still_shows_a_message(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "out.wav"
    basic_lsb_steganography.encode(str(make_wav()), str(output), "café 🎵")
    result = run(*decode_lines(output), EXIT, encoding="ascii")
    assert result.code == 0
    assert "Decoded message: caf\\xe9 \\U0001f3b5\n" in result.output


def test_end_of_input_at_the_menu_is_a_normal_exit() -> None:
    assert run().code == 0
    assert run("9").code == 0


@pytest.mark.parametrize("answered", range(1, 6))
def test_end_of_input_during_an_operation_is_a_failure(
    make_wav: Callable[..., Path], tmp_path: Path, answered: int
) -> None:
    output = tmp_path / "out.wav"
    output.write_bytes(b"keep me")
    result = run(*encode_lines(make_wav(), output)[:answered])
    assert result.code == 1
    assert "input ended before the operation finished" in result.errors
    assert output.read_bytes() == b"keep me"


@needs_sigint
def test_ctrl_c_at_the_menu_exits_with_130(start: StartProcess) -> None:
    with start() as process:
        assert process.stdout is not None
        read_until(process.stdout, b"Choice: ")
        process.send_signal(signal.SIGINT)
        output, errors = process.communicate(timeout=TIMEOUT)
    result = Result(process.returncode, output, errors)
    assert result.code == 130
    assert "Interrupted" in result.errors


@needs_sigint
def test_ctrl_c_at_the_overwrite_prompt_keeps_the_old_file(
    make_wav: Callable[..., Path], tmp_path: Path, start: StartProcess
) -> None:
    output_path = tmp_path / "out.wav"
    output_path.write_bytes(b"keep me")
    with start() as process:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write("".join(f"{line}\n" for line in encode_lines(make_wav(), output_path)).encode())
        process.stdin.flush()
        read_until(process.stdout, b"Overwrite it? (y/N): ")
        process.send_signal(signal.SIGINT)
        output, errors = process.communicate(timeout=TIMEOUT)
    assert Result(process.returncode, output, errors).code == 130
    assert output_path.read_bytes() == b"keep me"
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "out.wav"]


def test_a_reader_that_leaves_early_is_a_failure_without_a_traceback(start: StartProcess) -> None:
    with start() as process:
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        read_until(process.stdout, b"Choice: ")
        process.stdout.close()
        process.stdin.write(b"9\n")
        process.stdin.close()
        errors = process.stderr.read()
        process.wait(timeout=TIMEOUT)
    assert Result(process.returncode, b"", errors).code == 1


@pytest.mark.parametrize(
    ("typed_before", "prompt", "typed_after"),
    [(2, b"encode: ", 3), (4, b"]: ", 1), (5, b"(y/N): ", 1)],
    ids=["message", "output_path", "overwrite"],
)
def test_nothing_is_written_after_the_reader_leaves(
    make_wav: Callable[..., Path],
    tmp_path: Path,
    start: StartProcess,
    typed_before: int,
    prompt: bytes,
    typed_after: int,
) -> None:
    output = tmp_path / "out.wav"
    existing = prompt == b"(y/N): "
    if existing:
        output.write_bytes(b"keep me")
    lines = [*encode_lines(make_wav(), output), *(["y"] if existing else [])]
    assert len(lines) == typed_before + typed_after
    with start() as process:
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        process.stdin.write("".join(f"{line}\n" for line in lines[:typed_before]).encode())
        process.stdin.flush()
        read_until(process.stdout, prompt)
        if typed_before == 4:
            read_until(process.stdout, prompt)
        process.stdout.close()
        process.stdin.write("".join(f"{line}\n" for line in lines[typed_before:]).encode())
        process.stdin.close()
        errors = process.stderr.read()
        process.wait(timeout=TIMEOUT)
    result = Result(process.returncode, b"", errors)
    assert result.code == 1
    assert result.errors.strip() == "Error: The output was closed."
    assert output.read_bytes() == b"keep me" if existing else not output.exists()


def test_the_program_stops_without_waiting_when_the_reader_leaves(start: StartProcess) -> None:
    with start() as process:
        assert process.stdin is not None and process.stdout is not None
        read_until(process.stdout, b"Choice: ")
        process.stdout.close()
        process.stdin.write(b"9\n")
        process.stdin.flush()
        assert process.wait(timeout=TIMEOUT) == 1
        process.stdin.close()


@posix_shell
@pytest.mark.parametrize("stream", ["<&-", ">&-"])
def test_a_closed_input_or_output_is_a_failure(stream: str) -> None:
    result = run(command=["sh", "-c", f'"$0" "$1" {stream}', sys.executable, str(MAIN_SCRIPT)])
    assert result.code == 1
    assert "needs an open input and output" in result.errors


@posix_shell
def test_a_closed_error_stream_does_not_change_the_result(make_wav: Callable[..., Path]) -> None:
    command = ["sh", "-c", '"$0" "$1" 2>&-', sys.executable, str(MAIN_SCRIPT)]
    assert run(EXIT, command=command).code == 0
    failed = run(*decode_lines(make_wav(frames=b"\xff" * 400)), EXIT, command=command)
    assert failed.code == 1
    assert failed.output.count(MAIN_MENU) == 2


@posix_shell
def test_an_input_that_cannot_be_read_is_a_failure(tmp_path: Path) -> None:
    command = ["sh", "-c", f'"$0" "$1" 0>"{tmp_path / "write_only"}"', sys.executable, str(MAIN_SCRIPT)]
    result = run(command=command)
    assert result.code == 1
    assert "cannot read its input" in result.errors


@pytest.mark.skipif(not os.path.exists("/dev/full"), reason="this system has no /dev/full")
def test_an_output_that_cannot_be_written_is_a_failure() -> None:
    command = ["sh", "-c", '"$0" "$1" >/dev/full', sys.executable, str(MAIN_SCRIPT)]
    assert run(EXIT, command=command).code == 1


@pytest.mark.parametrize("missing", ["stdin", "stdout", "stderr"])
def test_missing_streams_do_not_crash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{EXIT}\n"))
    monkeypatch.setattr(sys, missing, None)
    if missing == "stderr":
        assert main.main() == 0
        sys.stderr.close()
    else:
        assert main.main() == 1
        assert "needs an open input and output" in capsys.readouterr().err
