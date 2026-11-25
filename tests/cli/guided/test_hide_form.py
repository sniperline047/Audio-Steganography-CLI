"""Tests for audiosteg/cli/guided/hide_form.py."""

import os
import random
import re
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import noise_for

from audiosteg import decode, encode
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_four import LSB_4
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.commands import hide
from audiosteg.cli.guided import hide_form
from audiosteg.core import crypto
from audiosteg.errors import MissingLibraryError

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
START = ("What would you like to do?", ENTER)
SAMPLE, OWN_FILE = ("Which audio file?", ENTER), ("Which audio file?", DOWN + ENTER)
INPUT = ("Path of the WAV file:", f"input.wav{ENTER}")
FIRST_ALGORITHM = ("Which algorithm?", ENTER)
OUTPUT = "Output file [input.stego.wav]:"
ENCRYPTION = "Encrypt the message?"
PLAIN, ENCRYPTED = (ENCRYPTION, ENTER), (ENCRYPTION, DOWN + ENTER)
OVERWRITE = "input.stego.wav already exists. Overwrite it?"
COMMAND = re.compile("The same as a command: (.*)")


def message(text: str) -> tuple[str, str]:
    return ("Message to hide:", f"{text}{ENTER}")


def words_of(line: str) -> list[str]:
    """Split a command as a shell of this system does."""
    if os.name == "nt":
        return [word.strip('"') for word in re.findall(r'"[^"]*"|\S+', line)]
    return shlex.split(line)


@pytest.fixture
def encryption(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Return a function that says whether this system can encrypt."""

    def set_available(available: bool) -> None:
        def check() -> None:
            if not available:
                raise MissingLibraryError("Not installed.")

        monkeypatch.setattr(crypto, "check_available", check)

    return set_available


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
def test_back_from_every_question(guide: Any, make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = tmp_path / "input.stego.wav"
    encode(str(make_wav()), str(output), "old", LSB)
    back = DOWN * 2 + ENTER
    result = guide(
        START,
        ("Which audio file?", back),
        START,
        OWN_FILE,
        ("Path of the WAV file:", ESCAPE),
        OWN_FILE,
        INPUT,
        ("Message to hide:", ESCAPE),
        INPUT,
        message("one"),
        ("Which algorithm?", DOWN * (len(ALGORITHMS) - 1) + ENTER),
        message("two"),
        ("Which algorithm?", DOWN + ENTER),
        (ENCRYPTION, back),
        ("Which algorithm?", DOWN + ENTER),
        ENCRYPTED,
        ("Passphrase:", ESCAPE),
        ENCRYPTED,
        ("Passphrase:", f"pass_first{ENTER}"),
        ("Repeat the passphrase:", ESCAPE),
        ("Passphrase:", f"pass_second{ENTER}"),
        ("Repeat the passphrase:", f"pass_second{ENTER}"),
        (OUTPUT, ESCAPE),
        ("Passphrase:", f"pass_third{ENTER}"),
        ("Repeat the passphrase:", f"pass_third{ENTER}"),
        (OUTPUT, ENTER),
        (OVERWRITE, ESCAPE),
        (OUTPUT, ENTER),
        (OVERWRITE, f"n{ENTER}"),
        (OUTPUT, ENTER),
        (OVERWRITE, f"y{ENTER}"),
    )
    assert result.code == 0
    assert "do not match" not in result.text
    assert decode(str(output), LSB_2, passphrase="pass_third") == "two"
    for passphrase in ("pass_first", "pass_second", "pass_third"):
        assert passphrase not in result.text


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
def test_a_passphrase_is_forgotten_when_encryption_is_not_wanted_anymore(
    guide: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav()
    result = guide(
        START,
        OWN_FILE,
        INPUT,
        message("hidden"),
        FIRST_ALGORITHM,
        ENCRYPTED,
        ("Passphrase:", f"sesame{ENTER}"),
        ("Repeat the passphrase:", f"sesame{ENTER}"),
        (OUTPUT, ESCAPE),
        ("Passphrase:", ESCAPE),
        PLAIN,
        (OUTPUT, ENTER),
    )
    assert "no, anyone can read the message" in result.text
    assert " -p" not in COMMAND.search(result.text)[1]
    assert decode(str(tmp_path / "input.stego.wav")) == "hidden"


def test_the_permission_to_overwrite_is_for_one_file_only(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(True)
    output = tmp_path / "input.stego.wav"
    encode(str(make_wav()), str(output), "keep me", LSB)
    result = guide(
        START,
        OWN_FILE,
        INPUT,
        message("new"),
        FIRST_ALGORITHM,
        PLAIN,
        (OUTPUT, ENTER),
        (OVERWRITE, ENTER),
        (OUTPUT, f"other.wav{ENTER}"),
    )
    assert result.code == 0
    assert "--force" not in result.text
    assert decode(str(output)) == "keep me"
    assert decode(str(tmp_path / "other.wav")) == "new"


def test_another_input_file_replaces_the_sample(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(True)
    make_wav()
    result = guide(
        START,
        SAMPLE,
        ("Message to hide:", ESCAPE),
        OWN_FILE,
        INPUT,
        ("Message to hide:", ESCAPE),
        ("Path of the WAV file:", ESCAPE),
        SAMPLE,
        message("hidden"),
        FIRST_ALGORITHM,
        PLAIN,
        ("Output file [sample.stego.wav]:", ENTER),
    )
    assert COMMAND.search(result.text)[1] == "audiosteg hide sample -a lsb -o sample.stego.wav"
    sample, copied = Path(hide.SAMPLE_FILE), tmp_path / "sample.stego.wav"
    assert copied.stat().st_size == sample.stat().st_size


def test_a_wrong_answer_is_asked_again_and_is_not_a_failure(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(True)
    make_wav()
    (tmp_path / "text.wav").write_text("not audio " * 10)
    result = guide(
        START,
        OWN_FILE,
        ("Path of the WAV file:", ENTER),
        ("Path of the WAV file:", f"text.wav{ENTER}"),
        ("Path of the WAV file:", f"miss\u202eing.wav{ENTER}"),
        INPUT,
        message("hidden"),
        FIRST_ALGORITHM,
        PLAIN,
        (OUTPUT, f"input.wav{ENTER}"),
        (OUTPUT, f".{ENTER}"),
        (OUTPUT, ENTER),
    )
    assert result.code == 0
    for reason in (
        "Error: The path is empty.",
        "Error: The input is not a valid PCM WAV file",
        "Error: The file or folder does not exist: miss\\u202eing.wav",
        "Error: The input and output must be different files.",
        "Error: The output path is a folder, not a file: .",
    ):
        assert reason in result.text
    for hint in ("--force", "-o.", "--help"):
        assert hint not in result.text


def test_without_the_library_the_message_is_plain_and_the_guide_says_so(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(False)
    make_wav()
    result = guide(
        START,
        OWN_FILE,
        INPUT,
        message("hidden"),
        FIRST_ALGORITHM,
        (OUTPUT, ESCAPE),
        FIRST_ALGORITHM,
        (OUTPUT, ENTER),
    )
    assert result.code == 0
    assert result.text.count("The message will not be encrypted. Not installed.") == 2
    assert decode(str(tmp_path / "input.stego.wav")) == "hidden"


QUESTIONS = [
    SAMPLE,
    message("one"),
    FIRST_ALGORITHM,
    ENCRYPTED,
    ("Passphrase:", f"sesame{ENTER}"),
    ("Repeat the passphrase:", f"sesame{ENTER}"),
    ("Output file", ENTER),
    ("Overwrite it?", ENTER),
]


@pytest.mark.parametrize("number", range(len(QUESTIONS)))
@pytest.mark.parametrize(("key", "code", "reason"), [(CTRL_C, 130, "Interrupted"), (CTRL_D, 1, "The input")])
def test_leaving_at_any_question_changes_nothing(
    guide: Any,
    encryption: Callable[[bool], None],
    tmp_path: Path,
    number: int,
    key: str,
    code: int,
    reason: str,
) -> None:
    question = QUESTIONS[number][0]
    if question == "Overwrite it?" and key == CTRL_D:
        pytest.skip("a yes or no question has no end of input")
    encryption(True)
    output = tmp_path / "sample.stego.wav"
    output.write_bytes(b"keep me")
    result = guide(START, *QUESTIONS[:number], (question, key), leave=False)
    assert result.code == code
    assert f"Error: {reason}" in result.text
    assert "sesame" not in result.text
    assert output.read_bytes() == b"keep me"
    assert os.listdir(tmp_path) == ["sample.stego.wav"]


NAMES = ["my song.wav", "-p.wav", "sample"]
if os.name != "nt":
    NAMES += ["it's $HOME.wav", "~home.wav"]


@pytest.mark.parametrize(
    ("key", "existing", "passphrase"),
    [
        pytest.param("lsb", False, None, id="plain"),
        pytest.param("lsb_2", True, None, id="overwrite"),
        pytest.param("lsb", True, "sésame", id="encrypted", marks=pytest.mark.needs_crypto),
    ],
)
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.usefixtures("fast_scrypt")
def test_the_suggested_command_does_the_same(
    guide: Any,
    run: Any,
    encryption: Callable[[bool], None],
    make_wav: Callable[..., Path],
    tmp_path: Path,
    name: str,
    key: str,
    existing: bool,
    passphrase: str | None,
) -> None:
    encryption(True)
    folders = [tmp_path / "guided", tmp_path / "command"]
    for folder in folders:
        folder.mkdir()
        make_wav(f"{folder.name}/{name}")
        if existing:
            encode(str(folder / name), str(folder / "-new.wav"), "old", LSB)
    secret = [("Passphrase:", f"{passphrase}{ENTER}"), ("Repeat the passphrase:", f"{passphrase}{ENTER}")]
    typed = name if not name.startswith("~") else f"./{name}"
    result = guide(
        START,
        OWN_FILE,
        ("Path of the WAV file:", f"{typed}{ENTER}"),
        message("my message"),
        ("Which algorithm?", ENTER if key == "lsb" else DOWN + ENTER),
        *([PLAIN] if passphrase is None else [ENCRYPTED, *secret]),
        ("Output file", f"-new.wav{ENTER}"),
        *([("Overwrite it?", f"y{ENTER}")] if existing else []),
        cwd=folders[0],
    )
    assert result.code == 0
    command = COMMAND.search(result.text)[1]
    assert "my message" not in command and "sésame" not in command
    words = words_of(command)
    assert ("--force" in words) is existing
    again = run(
        *words[1:],
        stdin=b"my message\n",
        hidden=(passphrase, passphrase) if passphrase else (),
        terminals=("stdin", "stdout", "stderr"),
        cwd=folders[1],
    )
    assert again.code == 0
    outputs = [folder / "-new.wav" for folder in folders]
    assert [decode(str(output), passphrase=passphrase) for output in outputs] == ["my message"] * 2
    assert (outputs[0].read_bytes() == outputs[1].read_bytes()) is (passphrase is None)


def test_a_name_that_cannot_be_shown_leaves_the_command_out(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(True)
    make_wav()
    result = guide(
        START, OWN_FILE, INPUT, message("x"), FIRST_ALGORITHM, PLAIN, (OUTPUT, f"gpj\u202e.wav{ENTER}")
    )
    assert result.code == 0
    assert "The same command cannot be shown" in result.text
    assert COMMAND.search(result.text) is None
    assert "gpj\\u202e.wav" in result.text


def test_an_unsafe_name_is_shown_escaped_before_it_is_replaced(
    guide: Any, encryption: Callable[[bool], None], tmp_path: Path
) -> None:
    encryption(False)
    (tmp_path / "gpj\u202e.wav").write_bytes(b"keep me")
    result = guide(
        START,
        SAMPLE,
        message("x"),
        FIRST_ALGORITHM,
        ("Output file", f"gpj\u202e.wav{ENTER}"),
        ("gpj\\u202e.wav already exists. Overwrite it?", CTRL_C),
        leave=False,
    )
    assert result.code == 130


def test_a_form_starts_with_the_safe_answers() -> None:
    request = hide_form.HideForm(None).request()
    assert (request.passphrase, request.overwrite) == (None, False)


@pytest.mark.parametrize("answer", ["y", "n"])
def test_enter_after_yes_or_no_does_not_answer_the_next_question(
    guide: Any, encryption: Callable[[bool], None], tmp_path: Path, answer: str
) -> None:
    encryption(False)
    (tmp_path / "sample.stego.wav").write_bytes(b"keep me")
    result = guide(
        START,
        SAMPLE,
        message("new"),
        FIRST_ALGORITHM,
        ("Output file", ENTER),
        ("Overwrite it?", f"{answer}{ENTER}"),
        *([] if answer == "y" else [("Output file", CTRL_C)]),
        leave=answer == "y",
    )
    assert result.code == (0 if answer == "y" else 130)


def test_ctrl_d_at_a_confirmation_ends_the_program(
    guide: Any, encryption: Callable[[bool], None], tmp_path: Path
) -> None:
    encryption(False)
    (tmp_path / "sample.stego.wav").write_bytes(b"keep me")
    start = (START, SAMPLE)
    overwrite = (message("x"), FIRST_ALGORITHM, ("Output file", ENTER), ("Overwrite it?", CTRL_D))
    for prompts in (overwrite, (message(""), ("Hide an empty message?", CTRL_D))):
        assert guide(*start, *prompts, leave=False).code == 1
    assert (tmp_path / "sample.stego.wav").read_bytes() == b"keep me"


def test_an_empty_message_must_be_confirmed(
    guide: Any, encryption: Callable[[bool], None], tmp_path: Path
) -> None:
    encryption(False)
    empty = "Hide an empty message?"
    result = guide(
        START,
        SAMPLE,
        message(""),
        (empty, ENTER),
        message(""),
        (empty, ESCAPE),
        message(""),
        (empty, f"y{ENTER}"),
        FIRST_ALGORITHM,
        ("Output file", ENTER),
    )
    assert result.code == 0
    assert decode(str(tmp_path / "sample.stego.wav")) == ""


def test_a_message_that_is_too_large_is_refused_at_once(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(False)
    make_wav(frames=bytes(800))
    result = guide(
        START,
        OWN_FILE,
        INPUT,
        message("é" * 194),
        message("é" * 193),
        FIRST_ALGORITHM,
        (OUTPUT, ENTER),
    )
    assert result.code == 0
    assert "it needs 388 bytes and the audio file can hold 386 bytes" in result.text
    assert "The message is too large for some algorithms. These can hold it: lsb_4." in result.text
    assert "lsb: Hides" not in result.text
    assert decode(str(tmp_path / "input.stego.wav"), LSB_4) == "é" * 193


@pytest.mark.parametrize(("length", "advice"), [(86, "choose lsb_2"), (386, "type a shorter message")])
def test_a_message_that_encryption_makes_too_large_is_refused_at_once(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], length: int, advice: str
) -> None:
    encryption(True)
    make_wav(frames=bytes(800))
    result = guide(
        START, OWN_FILE, INPUT, message("x" * length), FIRST_ALGORITHM, ENCRYPTED, PLAIN, (OUTPUT, ENTER)
    )
    assert result.code == 0
    assert "Encryption makes the message too large for lsb" in result.text
    assert advice in result.text
    assert "Passphrase:" not in result.text


def test_a_file_that_is_too_small_for_any_message_is_explained(
    guide: Any, make_wav: Callable[..., Path]
) -> None:
    make_wav(frames=bytes(20))
    result = guide(START, OWN_FILE, INPUT, message(""), ("Message to hide:", CTRL_C), leave=False)
    assert result.code == 130
    assert "it needs 0 bytes and the audio file can hold 0 bytes" in result.text
    assert "Hide an empty message?" not in result.text


KEYED = ("Which algorithm?", DOWN * list(ALGORITHMS).index("lsb_keyed") + ENTER)


@pytest.mark.needs_crypto
@pytest.mark.usefixtures("fast_scrypt")
def test_a_keyed_algorithm_asks_for_a_passphrase_and_not_whether_to_encrypt(
    guide: Any, run: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav()
    secret = (("Passphrase:", f"sésame{ENTER}"), ("Repeat the passphrase:", f"sésame{ENTER}"))
    result = guide(
        START,
        OWN_FILE,
        INPUT,
        message("hidden"),
        KEYED,
        ("Passphrase:", ESCAPE),
        FIRST_ALGORITHM,
        (ENCRYPTION, ESCAPE),
        KEYED,
        *secret,
        (OUTPUT, ENTER),
    )
    assert result.code == 0
    assert decode(str(tmp_path / "input.stego.wav"), passphrase="sésame") == "hidden"
    command = COMMAND.search(result.text)[1]
    assert command == "audiosteg hide input.wav -a lsb_keyed -o input.stego.wav -p"
    again = run(
        *words_of(command)[1:],
        "--force",
        stdin=b"hidden\n",
        hidden=("key", "key"),
        terminals=("stdin", "stdout", "stderr"),
    )
    assert again.code == 0
    assert "sésame" not in result.text


def test_a_keyed_algorithm_that_cannot_be_used_is_explained(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(False)
    make_wav()
    result = guide(START, OWN_FILE, INPUT, message("x"), KEYED, FIRST_ALGORITHM, (OUTPUT, ENTER))
    assert "Error: Not installed." in result.text
    assert "lsb_keyed (cannot encrypt here): " in result.text
    assert decode(str(tmp_path / "input.stego.wav")) == "x"


ECHO_NUMBER = ("Which algorithm?", DOWN * list(ALGORITHMS).index("echo") + ENTER)


@pytest.mark.needs_signal
def test_an_echo_is_hidden_and_the_command_does_the_same(
    guide: Any, run: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(False)
    make_wav(frames=noise_for("echo"))
    result = guide(START, OWN_FILE, INPUT, message("hidden"), ECHO_NUMBER, (OUTPUT, ENTER))
    assert result.code == 0
    assert "too large for some algorithms" not in result.text
    output = tmp_path / "input.stego.wav"
    assert decode(str(output)) == "hidden"
    written = output.read_bytes()
    command = COMMAND.search(result.text)[1]
    assert command == "audiosteg hide input.wav -a echo -o input.stego.wav"
    assert run(*words_of(command)[1:], "--force", stdin=b"hidden").code == 0
    assert output.read_bytes() == written


@pytest.mark.needs_signal
def test_a_file_that_is_made_quieter_is_named(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path]
) -> None:
    encryption(False)
    make_wav(frames=bytes(random.Random(1).choices([0, 255], k=500_000)))
    result = guide(START, OWN_FILE, INPUT, message("hidden"), ECHO_NUMBER, (OUTPUT, ENTER))
    assert result.code == 0
    assert "the whole file was made quieter (82.7% of its level)." in result.text


@pytest.mark.needs_signal
def test_a_sound_that_cannot_carry_echoes_is_explained(
    guide: Any, encryption: Callable[[bool], None], make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    encryption(False)
    make_wav(frames=bytes([128]) * 500_000)
    result = guide(START, OWN_FILE, INPUT, message("hidden"), ECHO_NUMBER, (OUTPUT, ENTER))
    assert result.code == 1
    assert "Error: The message could not be read back from this sound, so nothing was saved." in result.text
    assert not (tmp_path / "input.stego.wav").exists()


def test_an_echo_without_numpy_is_explained(
    guide: Any,
    encryption: Callable[[bool], None],
    no_numpy: None,
    make_wav: Callable[..., Path],
    tmp_path: Path,
) -> None:
    encryption(False)
    make_wav(frames=noise_for("echo"))
    result = guide(START, OWN_FILE, INPUT, message("x"), ECHO_NUMBER, FIRST_ALGORITHM, (OUTPUT, ENTER))
    assert 'To install it, run: pip install ".[signal]"' in result.text
    assert "echo (needs NumPy): " in result.text
    assert decode(str(tmp_path / "input.stego.wav")) == "x"


@pytest.mark.parametrize(("length", "offered"), [(46, True), (47, False)])
def test_a_keyed_algorithm_is_offered_only_for_a_message_that_fits_encrypted(
    guide: Any, make_wav: Callable[..., Path], length: int, offered: bool
) -> None:
    make_wav(frames=bytes(800))
    result = guide(START, OWN_FILE, INPUT, message("x" * length), ("Which algorithm?", CTRL_C), leave=False)
    assert ("lsb_keyed" in result.text) is offered
