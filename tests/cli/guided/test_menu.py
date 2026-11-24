"""Tests for audiosteg/cli/guided/menu.py."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg import decode

DOWN, ENTER, ESCAPE, CTRL_C, CTRL_D = "\x1b[B", "\r", "\x1b", "\x03", "\x04"
MENU = "What would you like to do?"
HIDE, REVEAL, VERIFY, INSPECT, COMPARE, EXPLAIN, ALGORITHMS, EXIT = (
    (MENU, DOWN * number + ENTER) for number in range(8)
)


@pytest.mark.needs_crypto
def test_a_real_terminal_from_start_to_end(terminal: Any, tmp_path: Path) -> None:
    program = terminal(COLORTERM="truecolor")
    for question, keys in [
        HIDE,
        ("Which audio file?", DOWN * 2 + ENTER),
        HIDE,
        ("Which audio file?", ENTER),
        ("Message to hide:", ESCAPE),
        ("Which audio file?", ENTER),
        ("Message to hide:", f"hidden{ENTER}"),
        ("Which algorithm?", DOWN + ENTER),
        ("Encrypt the message?", DOWN + ENTER),
        ("Passphrase:", f"sesame{ENTER}"),
        ("Repeat the passphrase:", f"sesam{ENTER}"),
        ("do not match", ""),
        ("Passphrase:", f"sesame{ENTER}"),
        ("Repeat the passphrase:", f"sesame{ENTER}"),
        ("Output file [", ENTER),
        ("audiosteg hide sample -a lsb_2 -o sample.stego.wav -p", ""),
        INSPECT,
        ("WAV file (sample means the included tune) [sample.stego.wav]", ENTER),
        ("lsb_2, encrypted, 6 bytes", ""),
        COMPARE,
        ("Original (sample means the included tune) [sample]", ENTER),
        ("Copy with the hidden message [sample.stego.wav]", ENTER),
        ("How much do you want to see?", DOWN + ENTER),
        ("Waveform: difference", ""),
        ("audiosteg compare sample sample.stego.wav --details", ""),
        EXPLAIN,
        ("Which algorithm?", DOWN + ENTER),
        ("Character to hide [h]", ENTER),
        ("audiosteg explain lsb_2", ""),
        REVEAL,
        ("hidden message [", ENTER),
        ("Passphrase:", f"sesame{ENTER}"),
        ("audiosteg reveal sample.stego.wav", ""),
        ("This message was encrypted.", ""),
        EXIT,
    ]:
        program.answer(question, keys)
    assert program.finish() == 0
    assert "sesam" not in program.seen
    assert program.seen.count("Audio Steganography CLI") == 1
    assert decode(str(tmp_path / "sample.stego.wav"), passphrase="sesame") == "hidden"


@pytest.fixture
def plain(no_library: None) -> None:
    """Leave the question about encryption out."""


@pytest.mark.usefixtures("plain")
def test_hide_reveal_and_verify_the_sample(guide: Any, tmp_path: Path) -> None:
    result = guide(
        HIDE,
        ("Which audio file?", ENTER),
        ("Message to hide:", f"my message{ENTER}"),
        ("Which algorithm?", DOWN + ENTER),
        ("Output file [sample.stego.wav]:", ENTER),
        REVEAL,
        ("hidden message [sample.stego.wav]:", ENTER),
        VERIFY,
        ("hidden message [sample.stego.wav]:", ENTER),
        ("Expected message:", f"other{ENTER}"),
        ALGORITHMS,
        EXIT,
        leave=False,
        NO_COLOR="1",
    )
    assert result.code == 0
    assert decode(str(tmp_path / "sample.stego.wav")) == "my message"
    position = 0
    for text in [
        "Audio Steganography CLI",
        "Esc goes back",
        MENU,
        "Hiding the message...",
        "Message hidden",
        "The same as a command: audiosteg hide sample -a lsb_2 -o sample.stego.wav\n",
        MENU,
        "The same as a command: audiosteg reveal sample.stego.wav\n",
        "my message\nThis message was not encrypted, so anyone could have written it.\n",
        MENU,
        "The message does not match",
        "The same as a command: audiosteg verify sample.stego.wav\n",
        MENU,
        "enhanced_flip",
        "The same as a command: audiosteg algorithms\n",
        MENU,
    ]:
        position = result.text.index(text, position) + len(text)
    assert result.text.count("Audio Steganography CLI") == 1


@pytest.mark.usefixtures("plain")
def test_a_failure_returns_to_the_menu_and_a_later_success_does_not_hide_it(
    guide: Any, make_wav: Callable[..., Path], tmp_path: Path
) -> None:
    make_wav(frames=b"\xff" * 800)
    result = guide(
        REVEAL,
        ("hidden message:", f"input.wav{ENTER}"),
        ("older version hide", ENTER),
        REVEAL,
        ("hidden message:", ESCAPE),
        HIDE,
        ("Which audio file?", DOWN + ENTER),
        ("Path of the WAV file:", f"input.wav{ENTER}"),
        ("Message to hide:", f"fits{ENTER}"),
        ("Which algorithm?", ENTER),
        ("Output file", ENTER),
        EXIT,
        leave=False,
    )
    assert result.code == 1
    assert "Error: No hidden message was found." in result.text
    assert decode(str(tmp_path / "input.stego.wav")) == "fits"


def test_escape_at_the_menu_asks_again_and_the_end_of_input_leaves(guide: Any) -> None:
    result = guide((MENU, ESCAPE), (MENU, CTRL_D), leave=False)
    assert result.code == 0
    assert "Error" not in result.text


def test_back_from_every_first_question_returns_to_the_menu(guide: Any, tmp_path: Path) -> None:
    result = guide(
        HIDE,
        ("Which audio file?", DOWN * 2 + ENTER),
        REVEAL,
        ("hidden message:", ESCAPE),
        VERIFY,
        ("hidden message:", ESCAPE),
        INSPECT,
        ("WAV file (sample means the included tune) [sample]:", ESCAPE),
        COMPARE,
        ("Original (sample means the included tune) [sample]:", ESCAPE),
        EXPLAIN,
        ("Which algorithm?", DOWN * 5 + ENTER),
        EXPLAIN,
        ("Which algorithm?", ESCAPE),
        EXIT,
        leave=False,
    )
    assert result.code == 0
    assert os.listdir(tmp_path) == []


def test_ctrl_c_at_the_menu(guide: Any) -> None:
    result = guide((MENU, CTRL_C), leave=False)
    assert result.code == 130
    assert result.text.endswith("Error: Interrupted.\n")


@pytest.mark.parametrize("name", ["stdout", "stderr"])
def test_a_reader_that_left(run: Any, name: str) -> None:
    prompts = () if name == "stdout" else ((MENU, CTRL_D),)
    result = run(terminals=("stdin", "stdout", "stderr"), broken=(name,), prompts=prompts)
    assert result.code == (1 if name == "stdout" else 0)


def test_the_last_files_are_offered_and_never_mean_the_sample(
    guide: Any, make_wav: Callable[..., Path], tmp_path: Path, no_library: None
) -> None:
    make_wav()
    result = guide(
        HIDE,
        ("Which audio file?", DOWN + ENTER),
        ("Path of the WAV file:", f"input.wav{ENTER}"),
        ("Message to hide:", f"x{ENTER}"),
        ("Which algorithm?", ENTER),
        ("Output file", f"sample{ENTER}"),
        INSPECT,
        (f"[{os.path.join('.', 'sample')}]:", ENTER),
        COMPARE,
        ("Original (sample means the included tune) [input.wav]:", ENTER),
        (f"Copy with the hidden message [{os.path.join('.', 'sample')}]:", ENTER),
        ("How much", ENTER),
        EXIT,
        leave=False,
    )
    assert result.code == 0
    inside = os.path.join(".", "sample")
    assert f"The same as a command: audiosteg inspect {inside}\n" in result.text
    assert f"The same as a command: audiosteg compare input.wav {inside}\n" in result.text
    assert "Hidden message" in result.text and "lsb, not encrypted, 1 byte" in result.text


def test_an_error_after_the_questions_returns_to_the_menu(guide: Any, make_wav: Callable[..., Path]) -> None:
    result = guide(
        INSPECT, ("WAV file", f"missing.wav{ENTER}"), INSPECT, ("WAV file", ENTER), EXIT, leave=False
    )
    assert result.code == 1
    assert "does not exist: missing.wav" in result.text
    assert result.text.count("The same as a command:") == 1
