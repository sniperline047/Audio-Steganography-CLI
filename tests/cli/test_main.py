"""Tests for audiosteg/cli/main.py."""

import contextlib
import hashlib
import io
import os
import select
import shutil
import signal
import subprocess
import sys
import sysconfig
import threading
import time
from collections.abc import Callable, Iterator
from importlib.metadata import distribution
from pathlib import Path
from typing import IO, Any

import pytest

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli import main
from audiosteg.core import crypto
from audiosteg.errors import MissingLibraryError, UnsafeOutputError

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROGRAM = [sys.executable, "-m", "audiosteg"]
TIMEOUT = 60
StartProcess = Callable[[], subprocess.Popen[bytes]]
EXIT = "4"
BACK = str(len(ALGORITHMS) + 1)
INVALID_ALGORITHM = str(len(ALGORITHMS) + 2)
MAIN_MENU = "1) Encode a message\n2) Decode a message\n3) Calculate accuracy\n4) Exit\n"
ALGORITHM_MENU = (
    "1) LSB (1 bit per sample, best quality)\n"
    "2) LSB_2 (2 bits per sample, double capacity)\n"
    + "".join(f"{number}) {ALGORITHMS[number].name}\n" for number in sorted(ALGORITHMS) if number > 2)
    + f"{BACK}) Back\n"
)
LEGACY_MENU = (
    "1) Basic LSB Steganography\n"
    "2) Enhanced LSB Steganography with Bit Flipping\n"
    "3) Enhanced LSB Steganography without Bit Flipping\n"
    "4) Back\n"
)
LEGACY_BACK = "4"
DEFAULT_FILE = "message_encoded.wav"
MENU_ALGORITHMS = [(1, LSB), (2, LSB_2)]
NO_PASSPHRASE = [""] if crypto.is_available() else []

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


NOT_ENCRYPTED = "This message was not encrypted, so anyone could have written it.\n"
ENCRYPTED = "This message was encrypted.\n"
PASSPHRASE_PROMPT = "Passphrase, not shown while you type [none]: "


def environment(encoding: str = "utf-8") -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": encoding}


def run(
    *lines: str | bytes,
    command: list[str] | None = None,
    cwd: Path | None = None,
    encoding: str = "utf-8",
) -> Result:
    """Run the CLI in a real process and type the lines."""
    typed = b"".join((line if isinstance(line, bytes) else line.encode()) + b"\n" for line in lines)
    finished = subprocess.run(
        command or PROGRAM,
        input=typed,
        capture_output=True,
        cwd=cwd,
        env=environment(encoding),
        timeout=TIMEOUT,
    )
    return Result(finished.returncode, finished.stdout, finished.stderr)


def encode_lines(source: Path, output: Path | str, message: str = "hidden", algorithm: int = 1) -> list[str]:
    return ["1", str(algorithm), message, *NO_PASSPHRASE, str(source), str(output)]


def decode_lines(path: Path | str) -> list[str]:
    return ["2", str(path)]


def encrypt_lines(source: Path, output: Path | str, passphrase: str, algorithm: int = 1) -> list[str]:
    return ["1", str(algorithm), "hidden", passphrase, passphrase, str(source), str(output)]


def accuracy_lines(path: Path, expected: str) -> list[str]:
    return ["3", str(path), expected]


@pytest.fixture
def start(tmp_path: Path) -> Iterator[StartProcess]:
    """Return a function that starts the CLI for an interactive test, and stop it if it hangs."""
    timers: list[threading.Timer] = []

    def start_process() -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            PROGRAM,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmp_path,
            env=environment(),
        )
        timers.append(threading.Timer(TIMEOUT, process.kill))
        timers[-1].start()
        return process

    yield start_process
    for timer in timers:
        timer.cancel()


def read_until(stream: IO[bytes], ending: bytes) -> None:
    """Read until the program shows a prompt."""
    seen = b""
    while not seen.endswith(ending):
        byte = stream.read(1)
        assert byte, f"the program stopped before {ending!r}"
        seen += byte


@pytest.mark.parametrize("number", sorted(ALGORITHMS))
def test_default_paths_use_the_included_sample_and_the_current_folder(tmp_path: Path, number: int) -> None:
    sample = Path(main.SAMPLE_FILE).read_bytes()
    result = run(
        "1", str(number), "Hello 🎵", *NO_PASSPHRASE, "", "",
        "2", "",
        "3", "", "Hello 🎵",
        EXIT,
        cwd=tmp_path,
    )  # fmt: skip
    assert (result.code, result.errors) == (0, "")
    assert "Input audio file [included sample]: " in result.output
    assert f"Output audio file [{DEFAULT_FILE}]: " in result.output
    assert result.output.count(f"Encoded audio file [{DEFAULT_FILE}]: ") == 2
    assert "Decoded message: Hello 🎵\n" in result.output
    assert "Accuracy of decoded message: 100.00%\nExact match: yes\n" in result.output
    assert os.listdir(tmp_path) == [DEFAULT_FILE]
    assert Path(main.SAMPLE_FILE).read_bytes() == sample


@pytest.mark.parametrize(("number", "algorithm"), MENU_ALGORITHMS)
def test_each_menu_number_uses_its_own_algorithm(
    make_wav: Callable[..., Path], tmp_path: Path, number: int, algorithm: Algorithm
) -> None:
    source = make_wav()
    expected = tmp_path / "expected.wav"
    output = tmp_path / "output.wav"
    encode(str(source), str(expected), "hidden", algorithm)
    result = run(*encode_lines(source, output, algorithm=number), *decode_lines(output), EXIT)
    assert result.code == 0
    assert output.read_bytes() == expected.read_bytes()
    assert "Decoded message: hidden\n" in result.output


def test_the_console_command_from_the_project_folder(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    command = shutil.which("audiosteg", path=sysconfig.get_path("scripts"))
    assert command is not None, "the audiosteg command is not installed"
    output = tmp_path / "output.wav"
    result = run(
        *encode_lines(make_wav(), output), *decode_lines(output), EXIT,
        command=[command],
        cwd=PROJECT_ROOT,
    )  # fmt: skip
    assert result.code == 0
    assert "Decoded message: hidden\n" in result.output
    assert run("1", "1", command=[command]).code == 1


def test_the_console_command_starts_the_whole_program() -> None:
    entry_points = distribution("audiosteg").entry_points
    assert entry_points.select(name="audiosteg")["audiosteg"].load() is main.main


def test_relative_paths_belong_to_the_current_folder(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    make_wav()
    result = run("1", "1", "hidden", *NO_PASSPHRASE, "input.wav", "a folder/out.wav", EXIT, cwd=tmp_path)
    assert result.code == 0
    assert decode(str(tmp_path / "a folder" / "out.wav"), LSB) == "hidden"


def test_menus_are_in_the_documented_order() -> None:
    result = run("1", BACK, EXIT)
    assert MAIN_MENU in result.output
    assert ALGORITHM_MENU in result.output
    assert result.output.index(MAIN_MENU) < result.output.index(ALGORITHM_MENU)


def test_old_algorithms_are_offered_only_when_nothing_is_detected(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    old = make_wav(name="old.wav", frames=bytes(32))
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden", LSB)
    found = run(*decode_lines(output), EXIT)
    assert LEGACY_MENU not in found.output
    result = run(*decode_lines(old), "1", *accuracy_lines(old, "1")[:2], "1", "", EXIT)
    assert (result.code, result.errors) == (0, "")
    assert result.output.count(LEGACY_MENU) == 2
    assert "The decoded message is empty." in result.output
    assert "Exact match: yes" in result.output


def test_invalid_menu_choices_are_asked_again_without_failing() -> None:
    result = run("0", "5", "x", "", EXIT)
    assert (result.code, result.errors) == (0, "")
    assert result.output.count(MAIN_MENU) == 5


def test_an_invalid_algorithm_is_asked_again(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    lines = encode_lines(make_wav(), output)
    result = run("1", INVALID_ALGORITHM, "", "x", *lines[1:], EXIT)
    assert (result.code, result.errors) == (0, "")
    assert decode(str(output), LSB) == "hidden"
    assert result.output.count(ALGORITHM_MENU) == 4
    assert result.output.count(MAIN_MENU) == 2


@pytest.mark.parametrize(
    ("answer", "replaced"), [("", False), ("n", False), ("no", False), ("y", True), ("yes", True)]
)
def test_overwrite_prompt(make_wav: Callable[..., Path], tmp_path: Path, answer: str, replaced: bool) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    encode(str(source), str(output), "old", LSB)
    result = run(*encode_lines(source, output, "new"), answer, EXIT)
    assert (result.code, result.errors) == (0, "")
    assert decode(str(output), LSB) == ("new" if replaced else "old")
    assert ("Nothing was written." in result.output) is not replaced


def test_a_file_that_appears_after_the_prompts_is_not_replaced(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_wav()
    output = tmp_path / "output.wav"
    answers = encode_lines(source, output)[1:]

    def encode_late(
        input_path: str,
        output_path: str,
        message: str,
        algorithm: Algorithm,
        *,
        passphrase: str | None,
        overwrite: bool,
    ) -> None:
        output.write_bytes(b"theirs")
        encode(input_path, output_path, message, algorithm, passphrase=passphrase, overwrite=overwrite)

    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    monkeypatch.setattr(main, "encode", encode_late)
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


@pytest.mark.parametrize("kind", ["path", "linked_folder", "hard_link", "symbolic_link", "other_case"])
def test_the_included_sample_cannot_be_the_output(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    sample = folder / "sample.wav"
    sample.write_bytes(b"sample")
    output = {"path": sample, "other_case": folder / "SAMPLE.WAV"}.get(kind, tmp_path / "link.wav")
    try:
        if kind == "linked_folder":
            (tmp_path / "linked").symlink_to(folder, target_is_directory=True)
            output = tmp_path / "linked" / "sample.wav"
        elif kind == "hard_link":
            os.link(sample, output)
        elif kind == "symbolic_link":
            output.symlink_to(sample)
    except OSError:
        pytest.skip("this system does not allow this kind of link")
    if not output.exists():
        pytest.skip("this file system tells letter cases apart")
    answers = [*encode_lines(make_wav(), output)[1:], "y"]
    monkeypatch.setattr(main, "SAMPLE_FILE", str(sample))
    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    reason = "symbolic link" if kind == "symbolic_link" else "included sample"
    with pytest.raises(UnsafeOutputError, match=reason):
        main.handle_encode()
    assert answers == ["y"]
    assert sample.read_bytes() == b"sample"


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
        "No hidden message": ["3", str(source), "1", "x"],
        "too large": encode_lines(source, tmp_path / "out.wav", "x" * 100),
        "null": decode_lines("a\0b.wav"),
    }
    for reason, lines in attempts.items():
        result = run(*lines, *decode_lines(source), "1", EXIT)
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
    assert run(*lines[:2]).code == 1


def test_a_failure_for_lack_of_memory_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def run_out_of_memory(path: str) -> None:
        raise MemoryError

    answers = [""]
    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    monkeypatch.setattr(main, "detect", run_out_of_memory)
    assert main.run_operation(main.handle_decode) is False
    assert "memory" in capsys.readouterr().err


def test_accuracy_reports_the_difference(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "hidden", LSB)
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
    encode(str(make_wav()), str(output), "\x1b]0;title\x07\x9b2J\u202egpj\nAccuracy: 100%", LSB)
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
    result = run("1", "1", b"bad \xff", *NO_PASSPHRASE, str(make_wav()), str(output), EXIT)
    assert result.code == 1
    assert "not valid text" in result.errors
    assert not output.exists()


def test_a_terminal_without_unicode_still_shows_a_message(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "out.wav"
    encode(str(make_wav()), str(output), "café 🎵", LSB)
    result = run(*decode_lines(output), EXIT, encoding="ascii")
    assert result.code == 0
    assert "Decoded message: caf\\xe9 \\U0001f3b5\n" in result.output


def test_end_of_input_at_the_menu_is_a_normal_exit() -> None:
    assert run().code == 0
    assert run("9").code == 0


@pytest.mark.parametrize("answered", range(1, len(NO_PASSPHRASE) + 6))
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
    [(2, b"encode: ", 3), (4, b"Output audio file [message_encoded.wav]: ", 1), (5, b"(y/N): ", 1)],
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
    if typed_before > 2:
        typed_before += len(NO_PASSPHRASE)
    else:
        typed_after += len(NO_PASSPHRASE)
    assert len(lines) == typed_before + typed_after
    with start() as process:
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        process.stdin.write("".join(f"{line}\n" for line in lines[:typed_before]).encode())
        process.stdin.flush()
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
    result = run(command=["sh", "-c", f'"$0" "$@" {stream}', *PROGRAM])
    assert result.code == 1
    assert "needs an open input and output" in result.errors


@posix_shell
def test_a_closed_error_stream_does_not_change_the_result(make_wav: Callable[..., Path]) -> None:
    command = ["sh", "-c", '"$0" "$@" 2>&-', *PROGRAM]
    assert run(EXIT, command=command).code == 0
    failed = run(*decode_lines(make_wav(frames=b"\xff" * 400)), "1", EXIT, command=command)
    assert failed.code == 1
    assert failed.output.count(MAIN_MENU) == 2


@posix_shell
def test_an_input_that_cannot_be_read_is_a_failure(tmp_path: Path) -> None:
    command = ["sh", "-c", f'"$0" "$@" 0>"{tmp_path / "write_only"}"', *PROGRAM]
    result = run(command=command)
    assert result.code == 1
    assert "cannot read its input" in result.errors


@pytest.mark.skipif(not os.path.exists("/dev/full"), reason="this system has no /dev/full")
def test_an_output_that_cannot_be_written_is_a_failure() -> None:
    command = ["sh", "-c", '"$0" "$@" >/dev/full', *PROGRAM]
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


@pytest.mark.parametrize(
    "operation", [("1", BACK), ("2", "input.wav", LEGACY_BACK), ("3", "input.wav", LEGACY_BACK)]
)
def test_back_returns_to_the_main_menu(
    make_wav: Callable[..., Path], tmp_path: Path, operation: tuple[str, ...]
) -> None:
    make_wav()
    result = run(*operation, EXIT, cwd=tmp_path)
    assert result.code == 0
    assert result.errors == ""
    assert result.output.count(MAIN_MENU) == 2


def test_a_missing_sample_does_not_block_other_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "output.wav"
    output.write_bytes(b"old")
    monkeypatch.setattr(main, "SAMPLE_FILE", str(tmp_path / "missing.wav"))
    main.check_not_sample(str(output))


def test_the_menu_says_that_a_plain_message_is_not_protected(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    output = tmp_path / "output.wav"
    old = make_wav(name="old.wav", frames=bytes(32))
    lines = [*encode_lines(make_wav(), output), *decode_lines(output), *accuracy_lines(output, "hidden")]
    result = run(*lines, *decode_lines(old), "1", *accuracy_lines(old, "1")[:2], "1", "", EXIT)
    assert (result.code, result.errors) == (0, "")
    assert f"Message encoded, not encrypted, into {output}\n" in result.output
    assert f"{NOT_ENCRYPTED}Decoded message: hidden\n" in result.output
    assert f"{NOT_ENCRYPTED}The decoded message is empty.\n" in result.output
    assert result.output.count(f"{NOT_ENCRYPTED}Accuracy of decoded message: 100.00%\n") == 2
    assert result.output.count(NOT_ENCRYPTED) == 4
    assert ENCRYPTED not in result.output


@pytest.mark.needs_crypto
@pytest.mark.parametrize(("number", "algorithm"), MENU_ALGORITHMS)
def test_an_encrypted_message_from_start_to_end(
    make_wav: Callable[..., Path], tmp_path: Path, number: int, algorithm: Algorithm
) -> None:
    output = tmp_path / "output.wav"
    result = run(
        *encrypt_lines(make_wav(), output, "sésame 🎵", number),
        *decode_lines(output), "sésame 🎵",
        *accuracy_lines(output, "sésame 🎵"), "hidXen",
        EXIT,
    )  # fmt: skip
    assert (result.code, result.errors) == (0, "")
    assert f"Message encrypted and encoded into {output}\n" in result.output
    assert f"{ENCRYPTED}Decoded message: hidden\n" in result.output
    assert f"{ENCRYPTED}Accuracy of decoded message: 83.33%\nExact match: no\n" in result.output
    assert result.output.count("Passphrase, not shown while you type: ") == 2
    assert NOT_ENCRYPTED not in result.output
    assert "sésame" not in result.output
    assert LEGACY_MENU not in result.output
    assert decode(str(output), algorithm, passphrase="sésame 🎵") == "hidden"


@pytest.mark.needs_crypto
def test_a_wrong_or_missing_passphrase_is_a_failure(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], known_answer: Any
) -> None:
    path = make_wav(frames=embed(known_answer.container, 1))
    result = run(
        *decode_lines(path), "WRONG_KEY",
        *decode_lines(path), "",
        *accuracy_lines(path, ""), "Hé 🎵",
        EXIT,
    )  # fmt: skip
    assert result.code == 1
    assert result.errors.count("Error:") == 3
    assert "Error: Wrong passphrase, or the message was changed." in result.errors
    assert result.errors.count("Error: The hidden message is encrypted. A passphrase is needed.") == 2
    assert "WRONG_KEY" not in result.output + result.errors
    assert ENCRYPTED not in result.output
    assert NOT_ENCRYPTED not in result.output
    assert result.output.count(MAIN_MENU) == 4


@pytest.mark.needs_crypto
@pytest.mark.parametrize(
    ("passphrase", "reason"),
    [(b"TOP_SECRET \xff", "characters that are not valid text"), (b"TOP_SECRET \0", "a null character")],
    ids=["not_text", "null"],
)
def test_an_unusable_passphrase_is_refused_without_showing_it(
    make_wav: Callable[..., Path], tmp_path: Path, passphrase: bytes, reason: str
) -> None:
    output = tmp_path / "output.wav"
    result = run("1", "1", "hidden", passphrase, passphrase, str(make_wav()), str(output), EXIT)
    assert result.code == 1
    assert f"Error: The passphrase contains {reason}." in result.errors
    assert "SECRET" not in result.output + result.errors
    assert sorted(os.listdir(tmp_path)) == ["input.wav"]


@pytest.mark.needs_crypto
def test_passphrases_that_do_not_match_are_asked_again(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "output.wav"
    result = run("1", "1", "hidden", "one", "two", "", str(make_wav()), str(output), EXIT)
    assert (result.code, result.errors) == (0, "")
    assert result.output.count(PASSPHRASE_PROMPT) == 2
    assert "The passphrases do not match. Please try again.\n" in result.output
    assert decode(str(output), LSB) == "hidden"


@pytest.mark.needs_crypto
@pytest.mark.parametrize("answers", [["key"], ["key", "other"], ["key", "key"]])
def test_end_of_input_around_the_passphrase_is_a_failure(tmp_path: Path, answers: list[str]) -> None:
    result = run("1", "1", "hidden", *answers, cwd=tmp_path)
    assert result.code == 1
    assert "input ended before the operation finished" in result.errors
    assert os.listdir(tmp_path) == []


@pytest.mark.needs_crypto
def test_the_passphrase_stays_out_of_files_and_output(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    folder = tmp_path / "working"
    folder.mkdir()
    source = make_wav()
    output = tmp_path / "out.wav"
    result = run(
        *encrypt_lines(source, output, "TOP_SECRET"),
        *encrypt_lines(tmp_path / "missing.wav", tmp_path / "no.wav", "TOP_SECRET"),
        *encrypt_lines(source, source, "TOP_SECRET"),
        EXIT,
        cwd=folder,
    )
    assert result.code == 1
    assert result.errors.count("Error:") == 2
    assert "TOP_SECRET" not in result.output + result.errors
    assert b"TOP_SECRET" not in output.read_bytes()
    assert os.listdir(folder) == []
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "out.wav", "working"]


def test_an_encoded_file_does_not_show_its_passphrase() -> None:
    encoded_file = main.EncodedFile("path.wav", LSB, "TOP_SECRET")
    assert "TOP_SECRET" not in repr(encoded_file)
    assert encoded_file.passphrase == "TOP_SECRET"


def test_without_the_library_messages_are_plain_and_the_menu_says_so(
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    tmp_path: Path,
) -> None:
    package = tmp_path / "broken" / "cryptography"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise ImportError('not here')\n")
    start = f"import sys; sys.path.insert(0, {str(package.parent)!r})"
    command = [sys.executable, "-c", f"{start}; from audiosteg.cli.main import main; sys.exit(main())"]
    private = make_wav(name="private.wav", frames=embed(known_answer.container, 1))
    output = tmp_path / "output.wav"
    result = run(
        "1", "1", "hidden", str(make_wav()), str(output),
        *decode_lines(output),
        *decode_lines(private),
        *accuracy_lines(private, "x")[:2],
        EXIT,
        command=command,
    )  # fmt: skip
    assert result.code == 1
    assert "The message will not be encrypted. Encryption usually needs: pip install" in result.output
    assert "Passphrase" not in result.output
    assert f"Message encoded, not encrypted, into {output}\n" in result.output
    assert "Decoded message: hidden\n" in result.output
    assert result.errors.count("Error: Encryption needs an optional library. To install it, run: pip") == 2
    assert result.output.count(MAIN_MENU) == 5


@pytest.mark.needs_crypto
@pytest.mark.parametrize("problem", ["no_scrypt", "refused_scrypt", "refused_aes"])
def test_a_system_that_cannot_encrypt_is_explained_before_any_passphrase(
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    problem: str,
) -> None:
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.ciphers import aead

    def refuse_scrypt(*args: Any, **options: Any) -> bytes:
        raise ValueError("refused")

    def refuse_aes(key: bytes) -> None:
        raise UnsupportedAlgorithm("refused")

    if problem == "no_scrypt":
        monkeypatch.delattr(hashlib, "scrypt")
    elif problem == "refused_scrypt":
        monkeypatch.setattr(hashlib, "scrypt", refuse_scrypt)
    else:
        monkeypatch.setattr(aead, "AESGCM", refuse_aes)
    output = tmp_path / "output.wav"
    private = make_wav(name="private.wav", frames=embed(known_answer.container, 1))
    answers = ["1", "hidden", str(make_wav()), str(output), str(private), "unread"]
    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    assert main.run_operation(main.handle_encode) is True
    assert "The message will not be encrypted." in capsys.readouterr().out
    assert decode(str(output)) == "hidden"
    with pytest.raises(MissingLibraryError):
        main.handle_decode()
    assert answers == ["unread"]


def test_a_damaged_message_is_not_offered_the_old_algorithms(
    make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    path = make_wav(frames=embed(b"ASTG\x02\0\0\0\0\0", 1))
    result = run(*decode_lines(path), EXIT)
    assert result.code == 1
    assert "format version 2" in result.errors
    assert LEGACY_MENU not in result.output


@pytest.mark.parametrize(("number", "answer"), [("1", "one"), ("2", "two"), ("3", "two")])
def test_an_old_file_is_read_with_the_chosen_algorithm(
    make_wav: Callable[..., Path], number: str, answer: str
) -> None:
    digits = f"{24:032b}" + "".join(f"{byte:08b}" for byte in answer.encode())
    if answer == "one":
        frames = bytes(int(digit) for digit in digits)
    else:
        frames = bytes(int(digits[start : start + 2], 2) << 2 for start in range(0, len(digits), 2))
    result = run(*decode_lines(make_wav(frames=frames)), number, EXIT)
    assert (result.code, result.errors) == (0, "")
    assert f"Decoded message: {answer}\n" in result.output


TERMINAL_PROGRAM = """
import fcntl, sys, termios
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
from audiosteg.cli.main import main
code = main()
print("Typing is", "shown" if termios.tcgetattr(0)[3] & termios.ECHO else "hidden")
sys.stdin.readline()
sys.exit(code)
"""


class Terminal:
    """The CLI in a real terminal."""

    def __init__(self, folder: Path) -> None:
        import pty

        self.seen = ""
        self.position = 0
        self.controller, self.device = pty.openpty()
        self.process = subprocess.Popen(
            [sys.executable, "-c", TERMINAL_PROGRAM],
            stdin=self.device,
            stdout=self.device,
            stderr=self.device,
            cwd=folder,
            env=environment(),
            start_new_session=True,
        )
        self.deadline = time.monotonic() + TIMEOUT

    def close(self) -> None:
        self.process.kill()
        self.process.wait()
        os.close(self.controller)
        os.close(self.device)

    def read(self, text: str) -> None:
        """Read until the terminal shows the text."""
        while text not in self.seen[self.position :]:
            assert time.monotonic() < self.deadline, f"no {text!r} in {self.seen!r}"
            if select.select([self.controller], [], [], 0.1)[0]:
                self.seen += os.read(self.controller, 4096).decode("utf-8", "replace").replace("\r\n", "\n")
        self.position = self.seen.index(text, self.position) + len(text)

    def echoes(self) -> bool:
        import termios

        return bool(termios.tcgetattr(self.device)[3] & termios.ECHO)

    def type(self, text: str) -> None:
        os.write(self.controller, text.encode())

    def type_hidden(self, text: str) -> None:
        """Type once the terminal hides the typing."""
        while self.echoes():
            assert time.monotonic() < self.deadline, "the terminal still shows what is typed"
            time.sleep(0.01)
        self.type(text)

    def finish(self) -> int:
        """Check that typing is shown again, let the program stop, and return its exit code."""
        self.read("Typing is shown")
        self.type("\n")
        while self.process.poll() is None:
            assert time.monotonic() < self.deadline, "the program did not stop"
            if select.select([self.controller], [], [], 0.05)[0]:
                with contextlib.suppress(OSError):
                    os.read(self.controller, 4096)
        return self.process.returncode


@pytest.fixture
def terminal(tmp_path: Path) -> Iterator[Terminal]:
    """Start the CLI in a real terminal."""
    pytest.importorskip("termios", reason="this system has no such terminals")
    program = Terminal(tmp_path)
    yield program
    program.close()


def type_message(terminal: Terminal) -> None:
    for prompt, answer in [("Choice: ", "1"), ("Choice: ", "1"), ("encode: ", "my message")]:
        terminal.read(prompt)
        terminal.type(f"{answer}\n")


@pytest.mark.needs_crypto
def test_a_terminal_never_shows_the_passphrase(
    make_wav: Callable[..., Path], tmp_path: Path, terminal: Terminal
) -> None:
    make_wav()
    type_message(terminal)
    for prompt, answer in [
        (PASSPHRASE_PROMPT, "sésame"),
        ("Repeat the passphrase: ", "sesame"),
        (f"do not match. Please try again.\n{PASSPHRASE_PROMPT}", "sésame"),
        ("Repeat the passphrase: ", "sésame"),
    ]:
        terminal.read(prompt)
        terminal.type_hidden(f"{answer}\n")
    for prompt, answer in [
        ("[included sample]: ", "input.wav"),
        ("Output audio file", ""),
        ("Choice: ", "2"),
    ]:
        terminal.read(prompt)
        terminal.type(f"{answer}\n")
    terminal.read("Encoded audio file")
    terminal.type("\n")
    terminal.read("Passphrase, not shown while you type: ")
    terminal.type_hidden("sésame\n")
    terminal.read(f"{ENCRYPTED}Decoded message: my message\n")
    terminal.read("Choice: ")
    terminal.type(f"{EXIT}\n")
    assert terminal.finish() == 0
    assert "encode: my message" in terminal.seen
    assert "same" not in terminal.seen
    assert "Traceback" not in terminal.seen


@needs_sigint
@pytest.mark.needs_crypto
@pytest.mark.parametrize(
    ("key", "code", "reason"),
    [("\x04", 1, "The input ended"), ("\x03", 130, "Interrupted.")],
    ids=["end_of_input", "ctrl_c"],
)
@pytest.mark.parametrize("repeated", [False, True])
def test_leaving_a_hidden_prompt_shows_typing_again(
    tmp_path: Path, terminal: Terminal, key: str, code: int, reason: str, repeated: bool
) -> None:
    type_message(terminal)
    terminal.read(PASSPHRASE_PROMPT)
    if repeated:
        terminal.type_hidden("sesame\n")
        terminal.read("Repeat the passphrase: ")
    terminal.type_hidden(key)
    terminal.read(f"Error: {reason}")
    assert terminal.finish() == code
    assert "sesame" not in terminal.seen
    assert "Traceback" not in terminal.seen
    assert os.listdir(tmp_path) == []
