"""Tests for audiosteg/cli/commands/hide.py."""

import hashlib
import io
import json
import os
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL, EVERY_KEY, NO_SIGINT, PLAIN_KEYS, marked, needed_passphrase, noise_for

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.commands import hide
from audiosteg.cli.commands.hide import HideRequest, check_not_sample, check_output, default_output
from audiosteg.cli.results import HideResult
from audiosteg.errors import UnsafeOutputError

needs_sigint = pytest.mark.skipif(NO_SIGINT, reason="Ctrl-C cannot be sent to one process here")
every_algorithm = pytest.mark.parametrize("key", EVERY_KEY)
every_algorithm_for_the_sample = pytest.mark.parametrize(
    "key", [marked(key) for key, known in ALGORITHMS.items() if isinstance(known, Algorithm)]
)


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    folder = tmp_path / "keys"
    folder.mkdir()
    path = folder / "key.txt"
    path.write_text("TOP_SECRET\n")
    path.chmod(0o600)
    return path


@pytest.mark.needs_signal
def test_a_sound_that_is_too_short_for_echoes_is_explained(run: Any, tmp_path: Path) -> None:
    result = run("hide", "sample", "-m", "Hello", "-a", "echo")
    assert (result.code, result.output) == (1, "")
    assert result.errors == (
        "Error: The audio file is too short for this algorithm, even for an empty message. "
        "With echo, this message needs at least 18.9 s of sound like this. "
        "Use the algorithm lsb, which can hold it, or a longer audio file.\n"
    )
    assert os.listdir(tmp_path) == []


@pytest.mark.needs_signal
@pytest.mark.parametrize("message", ["", "Hello"])
def test_the_reason_for_a_short_sound_names_no_sizes(run: Any, message: str) -> None:
    errors = run("hide", "sample", "-m", message, "-a", "echo").errors
    assert "even for an empty message" in errors and "0 bytes" not in errors


@pytest.mark.needs_signal
def test_a_file_that_is_made_quieter_is_named(run: Any, make_wav: Callable[..., Path]) -> None:
    make_wav(name="loud.wav", frames=bytes(random.Random(1).choices([0, 255], k=500_000)))
    loud = run("hide", "loud.wav", "-m", "Hello", "-a", "echo")
    assert loud.code == 0
    note = "The result would have been too loud, so the whole file was made quieter (82.7% of its level).\n"
    assert loud.errors == note
    fields = json.loads(run("hide", "loud.wav", "-m", "Hello", "-a", "echo", "--force", "--json").output)
    assert fields["gain"] == pytest.approx(0.827, abs=0.001)
    make_wav(name="soft.wav", frames=bytes(random.Random(1).choices(range(100, 156), k=500_000)))
    soft = run("hide", "soft.wav", "-m", "Hello", "-a", "echo")
    assert (soft.code, soft.errors) == (0, "")
    assert json.loads(run("hide", "soft.wav", "-m", "x", "-o", "a.wav", "--json").output)["gain"] == 1.0


@pytest.mark.needs_signal
def test_a_sound_that_cannot_carry_echoes_is_explained(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav(frames=bytes([128]) * 500_000)
    result = run("hide", "input.wav", "-m", "Hello", "-a", "echo")
    assert (result.code, result.output) == (1, "")
    assert result.errors == (
        "Error: The message could not be read back from this sound, so nothing was saved. "
        "The sound may be too quiet or too simple, such as silence or pure tones, it may already hold "
        "a message of this kind, or its channels may cancel each other.\n"
        "Use another audio file, or an algorithm that works with every sound, such as lsb.\n"
    )
    assert os.listdir(tmp_path) == ["input.wav"]


def test_a_missing_numpy_is_explained_before_anything_is_asked(
    run: Any, no_numpy: None, tmp_path: Path
) -> None:
    result = run("hide", "sample", "-a", "echo", "-p", terminals=ALL, NO_COLOR="1")
    assert result.code == 1
    assert result.seen == (
        "Error: This algorithm needs an optional library (NumPy). "
        'To install it, run: pip install ".[signal]"\n'
        "Without it, the other algorithms can be used.\n"
    )
    as_json = json.loads(run("hide", "sample", "-a", "echo", "--json").output)
    assert as_json["error"]["type"] == "missing_library"
    assert os.listdir(tmp_path) == []


@every_algorithm_for_the_sample
@pytest.mark.usefixtures("fast_scrypt")
def test_the_sample_and_the_current_folder_are_used(run: Any, tmp_path: Path, key: str) -> None:
    sample = Path(hide.SAMPLE_FILE).read_bytes()
    passphrase = needed_passphrase(key)
    asks = {"hidden": (passphrase, passphrase), "terminals": ALL} if passphrase else {}
    result = run("hide", "sample", "-m", "Hello 🎵", "-a", key, cwd=tmp_path, **asks)
    assert result.code == 0
    assert bool(result.errors) is bool(passphrase)
    assert os.listdir(tmp_path) == ["sample.stego.wav"]
    output = str(tmp_path / "sample.stego.wav")
    assert decode(output, ALGORITHMS[key], passphrase=passphrase) == "Hello 🎵"
    assert Path(hide.SAMPLE_FILE).read_bytes() == sample


@pytest.mark.parametrize("key", PLAIN_KEYS)
@pytest.mark.usefixtures("first_choices")
def test_each_name_uses_its_own_algorithm(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, key: str
) -> None:
    source, expected = make_wav(frames=noise_for(key)), tmp_path / "expected.wav"
    output = tmp_path / "output.wav"
    encode(str(source), str(expected), "hidden", ALGORITHMS[key])
    assert run("hide", source, "-m", "hidden", "-a", key, "-o", output).code == 0
    assert output.read_bytes() == expected.read_bytes()


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
@pytest.mark.parametrize("words", [[], ["-p"]])
def test_a_keyed_algorithm_asks_for_a_passphrase_with_or_without_the_option(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, words: list[str]
) -> None:
    output = tmp_path / "out.wav"
    request = ["hide", make_wav(), "-m", "MY_MESSAGE", "-a", "lsb_keyed", "-o", output, *words]
    result = run(*request, hidden=("sesame", "sesame"), terminals=ALL)
    assert result.code == 0
    assert "Encrypted: yes" in run(*request, "--plain", "--force", hidden=("s", "s"), terminals=ALL).text
    assert "sesame" not in result.seen and "MY_MESSAGE" not in result.seen
    assert decode(str(output), passphrase="s") == "MY_MESSAGE"


def test_a_keyed_algorithm_without_any_passphrase_is_refused_before_anything_is_read(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    words = ["hide", make_wav(), "-a", "lsb_keyed"]
    result = run(*words, stdin=b"TOP_SECRET")
    assert (result.code, result.output) == (1, "")
    assert "lsb_keyed always encrypts the message. A passphrase is needed.\n" in result.errors
    assert "--passphrase_file" in result.errors
    error = json.loads(run(*words, "--json").output)["error"]
    assert (error["type"], error["exit_code"]) == ("passphrase_required", 1)
    assert os.listdir(tmp_path) == ["input.wav"]


def test_a_keyed_algorithm_without_the_library_is_explained(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, no_library: None
) -> None:
    result = run("hide", make_wav(), "-m", "x", "-a", "lsb_keyed", terminals=ALL)
    assert (result.code, "Error: Encryption needs an optional library." in result.errors) == (1, True)
    assert os.listdir(tmp_path) == ["input.wav"]


@pytest.mark.needs_crypto
def test_the_largest_keyed_message_is_named(
    run: Any, make_wav: Callable[..., Path], key_file: Path, tmp_path: Path, fast_scrypt: None
) -> None:
    source, output = make_wav(frames=bytes(800)), tmp_path / "out.wav"
    words = ["hide", source, "-a", "lsb_keyed", "--passphrase_file", key_file, "-o", output]
    refused = run(*words, stdin=b"x" * 47)
    assert "needs 47 bytes and the audio file can hold 46 bytes. Use the algorithm lsb_2" in refused.errors
    assert run(*words, stdin=b"x" * 46).code == 0
    assert decode(str(output), passphrase="TOP_SECRET") == "x" * 46


@pytest.mark.parametrize(
    ("name", "output"),
    [
        ("song.wav", "song.stego.wav"),
        ("a folder/song.final.WAV", "song.final.stego.wav"),
        ("no_extension", "no_extension.stego.wav"),
    ],
)
def test_the_default_output(name: str, output: str) -> None:
    assert default_output(name) == output


def test_relative_paths_belong_to_the_current_folder(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav()
    result = run("hide", "input.wav", "-m", "hidden", "-o", "a folder/out.wav", cwd=tmp_path)
    assert result.code == 0
    assert decode(str(tmp_path / "a folder" / "out.wav")) == "hidden"


@pytest.mark.parametrize("message", [b"exact \r\n text\n", "Hé 🎵".encode()])
@pytest.mark.parametrize("from_file", [True, False])
def test_a_file_and_a_pipe_are_hidden_exactly(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, message: bytes, from_file: bool
) -> None:
    output = tmp_path / "out.wav"
    (tmp_path / "message.txt").write_bytes(message)
    words = ["--message_file", tmp_path / "message.txt"] if from_file else []
    result = run("hide", make_wav(), *words, "-o", output, stdin=b"" if from_file else message)
    assert result.code == 0
    assert decode(str(output)).encode() == message


def test_no_message_is_not_an_empty_message(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source, output = make_wav(), tmp_path / "out.wav"
    assert run("hide", source, "-o", output).code == 2
    assert not output.exists()
    assert run("hide", source, "-m", "", "-o", output).code == 0
    assert decode(str(output)) == ""


@pytest.mark.parametrize("data", [b"bad \xff", b"x" * 100_000], ids=["not_text", "too_large"])
def test_unusable_messages_are_refused_without_showing_them(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, data: bytes
) -> None:
    output = tmp_path / "out.wav"
    result = run("hide", make_wav(), "-o", output, stdin=data)
    assert result.code == 1
    assert "not valid UTF-8" in result.errors or "message is too large" in result.errors
    assert "bad" not in result.errors and "xx" not in result.errors
    assert not output.exists()


@pytest.mark.parametrize(
    ("answer", "replaced"), [("", False), ("n", False), ("no", False), ("y", True), ("yes", True)]
)
def test_a_terminal_asks_before_overwriting(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, answer: str, replaced: bool
) -> None:
    source, output = make_wav(), tmp_path / "output.wav"
    encode(str(source), str(output), "old", ALGORITHMS["lsb"])
    words = ["hide", source, "-m", "new", "-o", output]
    result = run(*words, stdin=f"{answer}\n".encode(), terminals=ALL)
    assert "output.wav already exists. Overwrite it? (y/N): " in result.errors
    assert result.code == (0 if replaced else 1)
    assert decode(str(output)) == ("new" if replaced else "old")
    assert ("Error: Nothing was written." in result.errors) is not replaced


@pytest.mark.parametrize("missing", ["stdin", "stderr"])
def test_the_overwrite_question_needs_a_terminal_for_input_and_errors(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, missing: str
) -> None:
    (tmp_path / "output.wav").write_bytes(b"old")
    terminals = tuple(name for name in ALL if name != missing)
    words = ["hide", make_wav(), "-m", "new", "-o", "output.wav"]
    result = run(*words, stdin=b"y\n", terminals=terminals)
    assert (result.code, "--force" in result.errors) == (1, True)
    assert (tmp_path / "output.wav").read_bytes() == b"old"
    piped = run(*words, stdin=b"y\n", terminals=("stdin", "stderr"))
    assert piped.code == 0
    assert "Overwrite it?" not in piped.output


@pytest.mark.parametrize("kind", ["message", "passphrase", "hard_link"])
def test_the_message_and_passphrase_files_cannot_be_the_output(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, kind: str
) -> None:
    path = tmp_path / "text.wav"
    path.write_text("precious")
    path.chmod(0o600)
    output = path
    if kind == "hard_link":
        output = tmp_path / "link.wav"
        os.link(path, output)
    option = "--passphrase_file" if kind == "passphrase" else "--message_file"
    words = ["hide", make_wav(), option, path, "-o", output, "--force"]
    result = run(*words, *(["-m", "x"] if kind == "passphrase" else []))
    assert result.code == 1
    assert "The output path is the message file or the passphrase file." in result.errors
    assert path.read_text() == "precious"


def test_the_word_sample_is_the_included_tune_and_a_path_is_a_file(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav(name="sample")
    sizes = []
    for word in ("sample", "./sample"):
        assert run("hide", word, "-m", "x", "-o", "out.wav", "--force").code == 0
        sizes.append((tmp_path / "out.wav").stat().st_size)
    assert sizes[0] == Path(hide.SAMPLE_FILE).stat().st_size
    assert sizes[1] == (tmp_path / "sample").stat().st_size


def test_an_empty_path_is_refused(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav()
    for option in ("-o", "--message_file", "--passphrase_file", "input"):
        words = ["hide", ""] if option == "input" else ["hide", source, option, ""]
        result = run(*words)
        assert (result.code, "Error: A path is empty." in result.errors) == (2, True)
    assert os.listdir(tmp_path) == ["input.wav"]


@pytest.mark.parametrize("encrypted", [False, pytest.param(True, marks=pytest.mark.needs_crypto)])
@pytest.mark.usefixtures("fast_scrypt")
def test_the_largest_message_fits_and_one_byte_more_does_not(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, key_file: Path, encrypted: bool
) -> None:
    source, output = make_wav(frames=bytes(800)), tmp_path / "out.wav"
    passphrase = "TOP_SECRET" if encrypted else None
    limit = 800 * 4 // 8 - (54 if encrypted else 14)
    words = ["hide", source, "-a", "lsb_4", "-o", output]
    words += ["--passphrase_file", key_file] if encrypted else []
    refused = run(*words, stdin=b"x" * (limit + 1))
    assert (refused.code, output.exists()) == (1, False)
    assert f"can hold {limit} bytes" in refused.errors
    assert run(*words, stdin=b"x" * limit).code == 0
    assert decode(str(output), passphrase=passphrase) == "x" * limit


def test_nothing_is_asked_about_a_file_that_cannot_be_used(run: Any, tmp_path: Path) -> None:
    (tmp_path / "text.wav").write_text("not audio " * 10)
    for name in ("text.wav", "missing.wav"):
        result = run("hide", name, terminals=ALL, stdin=b"x\n")
        assert (result.code, "Message to hide" in result.seen) == (1, False)


def test_without_a_terminal_only_force_overwrites(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source, output = make_wav(), tmp_path / "output.wav"
    encode(str(source), str(output), "old", ALGORITHMS["lsb"])
    result = run("hide", source, "-m", "new", "-o", output)
    assert result.code == 1
    assert "already exists" in result.errors and "--force" in result.errors
    assert decode(str(output)) == "old"
    assert run("hide", source, "-m", "new", "-o", output, "--force").code == 0
    assert decode(str(output)) == "new"


def test_a_file_that_appears_after_the_checks_is_not_replaced(
    make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_wav()
    output, exists = check_output(str(source), str(tmp_path / "output.wav"))
    Path(output).write_bytes(b"theirs")
    with pytest.raises(FileExistsError):
        hide.hide(HideRequest(str(source), output, "hidden", "lsb", None, exists))
    assert Path(output).read_bytes() == b"theirs"


@pytest.mark.parametrize("force", [[], ["--force"]])
def test_the_input_file_cannot_be_the_output(
    run: Any, make_wav: Callable[..., Path], force: list[str]
) -> None:
    source = make_wav()
    original = source.read_bytes()
    result = run("hide", source, "-m", "x", "-o", source, *force)
    assert result.code == 1
    assert "must be different files" in result.errors
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
    monkeypatch.setattr(hide, "SAMPLE_FILE", str(sample))
    reason = "symbolic link" if kind == "symbolic_link" else "included sample"
    with pytest.raises(UnsafeOutputError, match=reason):
        check_output(str(make_wav()), str(output))
    assert sample.read_bytes() == b"sample"


def test_a_missing_sample_does_not_block_other_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "output.wav"
    output.write_bytes(b"old")
    monkeypatch.setattr(hide, "SAMPLE_FILE", str(tmp_path / "missing.wav"))
    check_not_sample(str(output))


def test_an_output_folder_is_refused_before_any_overwrite_question(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    result = run("hide", make_wav(), "-m", "x", "-o", tmp_path, terminals=ALL)
    assert (result.code, "not a regular file" in result.errors) == (1, True)
    assert "Overwrite" not in result.seen


def test_a_message_that_fits_another_algorithm_is_told_so(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    source, output = make_wav(frames=bytes(800)), tmp_path / "new" / "out.wav"
    fits = run("hide", source, "-m", "x" * 100, "-o", output)
    assert fits.code == 1
    assert "needs 100 bytes and the audio file can hold 86 bytes. Use the algorithm lsb_2" in fits.errors
    too_large = run("hide", source, "-m", "x" * 400, "-o", output)
    assert too_large.code == 1
    assert "lsb_2" not in too_large.errors
    assert "longer audio file" in too_large.errors
    assert os.listdir(tmp_path) == ["input.wav"]


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
def test_a_passphrase_file_encrypts_and_stays_out_of_files_and_output(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, key_file: Path
) -> None:
    folder = tmp_path / "working"
    folder.mkdir()
    source, output = make_wav(), tmp_path / "out.wav"
    words = ["-m", "MY_MESSAGE", "--passphrase_file", key_file]
    for options, code in [
        ([source, "-o", output], 0),
        ([tmp_path / "missing.wav"], 1),
        ([source, "-o", source], 1),
        ([source, "-o", output], 1),
        ([source, "-o", output, "--json"], 1),
        ([source, "-o", output, "--force", "--json"], 0),
        ([source, "-o", output, "--unknown"], 2),
    ]:
        result = run("hide", *options, *words, cwd=folder)
        assert result.code == code
        assert "TOP_SECRET" not in result.output + result.errors
        assert "MY_MESSAGE" not in result.output + result.errors
    assert b"TOP_SECRET" not in output.read_bytes()
    assert decode(str(output), passphrase="TOP_SECRET") == "MY_MESSAGE"
    assert os.listdir(folder) == []
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "keys", "out.wav", "working"]


def test_a_request_does_not_show_its_secrets() -> None:
    request = HideRequest("in.wav", "out.wav", "MY_MESSAGE", "lsb", "TOP_SECRET", False)
    assert "SECRET" not in repr(request) and "MESSAGE" not in repr(request)


@pytest.mark.needs_crypto
def test_a_terminal_never_shows_the_passphrase(
    terminal: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    program = terminal("hide", make_wav(), "-p", "-o", "out.wav")
    program.read("Message to hide: ")
    program.type("my message\n")
    prompt = "Passphrase, not shown while you type: "
    for question, answer in [
        (prompt, "sésame"),
        ("Repeat the passphrase: ", "sesame"),
        ("do not match. Please try again.\n" + prompt, "sésame"),
        ("Repeat the passphrase: ", "sésame"),
    ]:
        program.read(question)
        program.type_hidden(f"{answer}\n")
    assert program.finish() == 0
    assert "same" not in program.seen
    assert decode(str(tmp_path / "out.wav"), passphrase="sésame") == "my message"


def test_a_message_and_a_passphrase_typed_in_any_terminal(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = []

    def remember(request: HideRequest) -> HideResult:
        requests.append(request)
        return HideResult(request.input_file, request.output_file, request.algorithm, True)

    monkeypatch.setattr(hide, "hide", remember)
    monkeypatch.setattr(hide.crypto, "check_available", lambda: None)
    hidden = ("key", "Key", "", "key\n", "key", "key")
    result = run("hide", make_wav(), "-p", stdin=b" my message \n", hidden=hidden, terminals=ALL)
    assert result.code == 0
    assert (requests[0].message, requests[0].passphrase) == (" my message ", "key")
    for reason in ("do not match", "The passphrase is empty", "line break"):
        assert f"{reason}" in result.errors
    assert result.errors.count("Please try again.") == 3


PROMPTS = ["overwrite", "message", "passphrase", "repeated"]


@pytest.mark.parametrize(("error", "code"), [(EOFError, 1), (KeyboardInterrupt, 130)])
@pytest.mark.parametrize("prompt", PROMPTS)
def test_leaving_any_prompt_changes_nothing(
    run: Any,
    make_wav: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    error: type[BaseException],
    code: int,
) -> None:
    monkeypatch.setattr(hide.crypto, "check_available", lambda: None)
    source, output = make_wav(), tmp_path / "out.wav"
    output.write_bytes(b"keep me")
    number = PROMPTS.index(prompt)

    class Typing(io.BytesIO):
        def read1(self, size: int | None = -1) -> bytes:
            line = self.readline()
            if line:
                return line
            raise error

    typed = [b"y\n", b"my message\n"][:number]
    hidden = {2: (error,), 3: ("sesame", error)}.get(number, ())
    stdin = b"".join(typed)
    result = run("hide", source, "-p", "-o", output, stdin=stdin, hidden=hidden, terminals=ALL, typing=Typing)
    assert result.code == code
    assert "Error: Interrupted." in result.errors or "Error: The input ended" in result.errors
    assert "sesame" not in result.seen
    assert output.read_bytes() == b"keep me"
    assert sorted(os.listdir(tmp_path)) == ["input.wav", "out.wav"]


@needs_sigint
@pytest.mark.parametrize(
    ("key", "code", "reason", "prompt"),
    [
        ("\x04", 1, "The input ended", "message"),
        ("\x03", 130, "Interrupted.", "overwrite"),
        pytest.param("\x03", 130, "Interrupted.", "repeated", marks=pytest.mark.needs_crypto),
        pytest.param("\x04", 1, "The input ended", "passphrase", marks=pytest.mark.needs_crypto),
    ],
)
def test_leaving_a_prompt_shows_typing_again_and_changes_nothing(
    terminal: Any,
    make_wav: Callable[..., Path],
    tmp_path: Path,
    key: str,
    code: int,
    reason: str,
    prompt: str,
) -> None:
    source, output = make_wav(), tmp_path / "out.wav"
    if prompt == "overwrite":
        output.write_bytes(b"keep me")
    option = ["-p"] if prompt in ("passphrase", "repeated") else []
    program = terminal("hide", source, *option, "-o", output)
    if prompt == "overwrite":
        program.read("(y/N): ")
        program.type(key)
    else:
        program.read("Message to hide: ")
        program.type(key if prompt == "message" else "my message\n")
    if prompt in ("passphrase", "repeated"):
        program.read("while you type: ")
        program.type_hidden(key if prompt == "passphrase" else "sesame\n")
    if prompt == "repeated":
        program.read("Repeat the passphrase: ")
        program.type_hidden(key)
    program.read(f"Error: {reason}")
    assert program.finish() == code
    assert "sesame" not in program.seen
    assert output.read_bytes() == b"keep me" if prompt == "overwrite" else not output.exists()


def test_a_prompted_passphrase_without_a_terminal_is_refused(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    result = run("hide", make_wav(), "-m", "x", "-p", "-o", tmp_path / "out.wav", stdin=b"key\nkey\n")
    assert result.code == 1
    assert not (tmp_path / "out.wav").exists()


def test_without_the_library_plain_messages_work_and_a_passphrase_is_refused(
    run: Any,
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    tmp_path: Path,
    key_file: Path,
    no_library: None,
) -> None:
    private = make_wav(name="private.wav", frames=embed(known_answer.container, 1))
    source, output = make_wav(), tmp_path / "output.wav"
    refused = run("hide", source, "-m", "x", "--passphrase_file", key_file, "-o", output)
    assert refused.code == 1
    assert not output.exists()
    assert run("hide", source, "-m", "hidden", "-o", output).code == 0
    assert run("reveal", output).output == "hidden"
    unread = run("reveal", private, "--passphrase_file", key_file)
    assert unread.code == 1
    for result in (refused, unread):
        assert "Error: Encryption needs an optional library. To install it, run: pip" in result.errors


@pytest.mark.needs_crypto
@pytest.mark.parametrize(
    ("problem", "reason"),
    [
        ("no_scrypt", "does not support scrypt"),
        ("refused_scrypt", "refuses scrypt"),
        ("refused_aes", "AES-GCM"),
    ],
)
def test_a_system_that_cannot_encrypt_is_explained_before_any_passphrase(
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    problem: str,
    reason: str,
) -> None:
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.ciphers import aead

    from audiosteg.cli import main, passphrase

    def refuse_scrypt(*args: Any, **options: Any) -> bytes:
        raise ValueError("refused")

    def refuse_aes(key: bytes) -> None:
        raise UnsupportedAlgorithm("refused")

    def refuse_question(prompt: str) -> str:
        raise AssertionError("the passphrase was asked")

    if problem == "no_scrypt":
        monkeypatch.delattr(hashlib, "scrypt")
    elif problem == "refused_scrypt":
        monkeypatch.setattr(hashlib, "scrypt", refuse_scrypt)
    else:
        monkeypatch.setattr(aead, "AESGCM", refuse_aes)
    monkeypatch.setattr(passphrase, "ask_hidden", refuse_question)
    output = tmp_path / "output.wav"
    private = make_wav(name="private.wav", frames=embed(known_answer.container, 1))
    for words in (
        ["hide", str(make_wav()), "-m", "x", "-p", "-o", str(output)],
        ["reveal", str(private), "-p"],
    ):
        assert main.main(words) == 1
        shown = capsys.readouterr().err
        assert reason in shown
        assert "pip install" not in shown
    assert not output.exists()


def test_paths_cannot_control_the_terminal(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source = make_wav()
    output = tmp_path / "[red]gpj\u202e.wav"
    results = [run("hide", source, "-m", "x", "-o", output) for _ in range(2)]
    results.append(run("hide", source, "-m", "x", "-o", "a\x1b[2J/"))
    assert [result.code for result in results] == [0, 1, 1]
    assert "[red]gpj\\u202e.wav" in results[0].output
    assert "[red]gpj\\u202e.wav" in results[1].errors
    assert "a\\x1b[2J/" in results[2].errors
    for result in results:
        assert not any(character in result.output + result.errors for character in "\x1b\u202e")


def test_a_terminal_shows_no_markup_from_a_path(run: Any, make_wav: Callable[..., Path]) -> None:
    name = "[bold red]x[link=a]:smile:\u202e.wav" if os.name != "nt" else "[bold red]x[link=a]\u202e.wav"
    words = ["hide", make_wav(), "-m", "x", "-o", name]
    result = run(*words, terminals=ALL, COLORTERM="truecolor")
    assert result.code == 0
    assert name.replace("\u202e", "\\u202e") in result.text
    assert "╭" in result.text


def test_json_describes_the_result(run: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    source, output = make_wav(), tmp_path / "out.wav"
    result = run("hide", source, "-m", "TOP_SECRET", "-o", output, "--json")
    assert result.errors == ""
    assert "SECRET" not in result.output
    assert json.loads(result.output) == {
        "ok": True,
        "command": "hide",
        "input": str(source),
        "output": os.path.join(os.path.realpath(tmp_path), "out.wav"),
        "algorithm": "lsb",
        "encrypted": False,
        "gain": 1.0,
    }


def test_a_file_that_appears_during_the_questions_is_not_replaced(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    class Typing(io.BytesIO):
        def read1(self, size: int | None = -1) -> bytes:
            (tmp_path / "out.wav").write_bytes(b"theirs")
            return super().read1(size)

    result = run("hide", make_wav(), "-o", "out.wav", stdin=b"x\n", terminals=ALL, typing=Typing)
    assert (result.code, "already exists" in result.errors) == (1, True)
    assert (tmp_path / "out.wav").read_bytes() == b"theirs"


@pytest.mark.needs_crypto
def test_no_algorithm_is_advised_that_cannot_hold_the_encrypted_message(
    run: Any, make_wav: Callable[..., Path], key_file: Path
) -> None:
    result = run("hide", make_wav(frames=bytes(800)), "-m", "x" * 160, "--passphrase_file", key_file)
    assert (result.code, "lsb_2" in result.errors, "algorithm lsb_4" in result.errors) == (1, False, True)


def test_typed_bytes_that_are_not_text_are_refused_without_showing_them(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    result = run("hide", make_wav(), stdin=b"PRIVATE \xff\n", terminals=ALL, NO_COLOR="1")
    assert result.code == 1
    assert "Error: The message contains characters that are not valid text." in result.errors
    assert "PRIVATE" not in result.errors and os.listdir(tmp_path) == ["input.wav"]


@pytest.mark.needs_crypto
def test_a_passphrase_file_with_a_byte_order_mark_is_refused(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    key_file, output = tmp_path / "key.txt", tmp_path / "out.wav"
    key_file.write_bytes("\ufeffkey".encode())
    result = run("hide", make_wav(), "-m", "x", "-o", output, "--passphrase_file", key_file)
    assert result.code == 1
    assert "byte order mark" in result.errors
    assert not output.exists()


def test_an_existing_output_is_named_relative_to_the_current_folder(
    run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav()
    (tmp_path / "out.wav").write_bytes(b"keep me")
    result = run("hide", "input.wav", "-m", "x", "-o", "out.wav", cwd=tmp_path)
    assert "already exists: out.wav\n" in result.errors
