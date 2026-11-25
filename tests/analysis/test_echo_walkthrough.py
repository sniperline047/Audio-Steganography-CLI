"""Tests for audiosteg/analysis/echo_walkthrough.py."""

import random
from collections.abc import Callable
from pathlib import Path

import pytest

from audiosteg.algorithms.echo import ECHO
from audiosteg.analysis.echo_walkthrough import PICTURE_DELAYS, walk_through_echo
from audiosteg.cli.commands.hide import SAMPLE_FILE
from audiosteg.core import wav_io
from audiosteg.errors import CapacityError, MissingLibraryError, UnsupportedFormatError

BLOCK = 1024


def noise(frames: int, loudness: int = 8000) -> list[int]:
    chooser = random.Random(1)
    return [chooser.randint(-loudness, loudness) for _ in range(frames)]


@pytest.mark.needs_signal
@pytest.mark.parametrize("letter", ["h", "é", "🎵"])
def test_a_character_is_hidden_and_read(make_samples: Callable[..., Path], letter: str) -> None:
    path = make_samples("input.wav", [0] * 5000 + noise(40 * BLOCK))
    before = path.read_bytes()
    walkthrough = walk_through_echo(str(path), letter, ECHO)
    assert path.read_bytes() == before
    data = letter.encode()
    assert (walkthrough.letter, walkthrough.data, walkthrough.read_back) == (letter, data, letter)
    digits = [int(digit) for byte in data for digit in f"{byte:08b}"]
    assert [block.hidden_bit for block in walkthrough.blocks] == digits
    assert [block.read_bit for block in walkthrough.blocks] == digits
    assert [block.delay for block in walkthrough.blocks] == [ECHO.delays[digit] for digit in digits]
    assert [block.number for block in walkthrough.blocks] == list(range(1, len(digits) + 1))
    assert walkthrough.right_bits == len(digits)
    assert walkthrough.first_frame >= 4096
    assert (walkthrough.silent, walkthrough.gain) == (False, 1)
    assert walkthrough.level in ECHO.levels
    assert walkthrough.format == (1, 2, 8000)


@pytest.mark.needs_signal
def test_the_numbers_belong_together(make_samples: Callable[..., Path]) -> None:
    walkthrough = walk_through_echo(str(make_samples("input.wav", noise(40 * BLOCK))), "h", ECHO)
    block = walkthrough.blocks[walkthrough.picture_block - 1]
    assert block.clearness == max(other.clearness for other in walkthrough.blocks)
    for picture, peaks in (
        (walkthrough.picture_before, block.peaks_before),
        (walkthrough.picture_after, block.peaks_after),
    ):
        assert len(picture) == len(PICTURE_DELAYS)
        assert tuple(picture[PICTURE_DELAYS.index(delay)] for delay in ECHO.delays) == peaks


@pytest.mark.needs_signal
def test_the_included_tune(read_frames: Callable[[Path], bytes]) -> None:
    walkthrough = walk_through_echo(SAMPLE_FILE, "h", ECHO)
    assert walkthrough.first_frame == 259
    assert walkthrough.right_bits >= 7


@pytest.mark.needs_signal
def test_silence_and_loud_sound(make_samples: Callable[..., Path]) -> None:
    silent = walk_through_echo(str(make_samples("silent.wav", [0] * 8 * BLOCK)), "h", ECHO)
    assert (silent.silent, silent.level, silent.first_frame) == (True, ECHO.levels[-1], 0)
    assert silent.right_bits == 5
    assert silent.read_back == "\0"
    loud = walk_through_echo(str(make_samples("loud.wav", noise(8 * BLOCK, 32767))), "h", ECHO)
    assert loud.gain < 1


@pytest.mark.needs_signal
def test_bits_that_are_no_character(make_samples: Callable[..., Path]) -> None:
    walkthrough = walk_through_echo(str(make_samples("silent.wav", [0] * 16 * BLOCK)), "é", ECHO)
    assert walkthrough.read_back == "\0\0"
    flipped = tuple(
        block.__class__(block.number, block.hidden_bit, block.delay, (0.0, 0.0), (0.0, 1.0))
        for block in walkthrough.blocks
    )
    object.__setattr__(walkthrough, "blocks", flipped)
    assert walkthrough.read_back is None


@pytest.mark.needs_signal
def test_a_file_that_cannot_be_used(
    make_samples: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = str(make_samples("input.wav", noise(8 * BLOCK - 1)))
    with pytest.raises(CapacityError, match="It needs 8,192 frames here"):
        walk_through_echo(path, "h", ECHO)
    monkeypatch.setattr(wav_io, "MAX_INPUT_SIZE", 100)
    with pytest.raises(UnsupportedFormatError, match="too large"):
        walk_through_echo(path, "h", ECHO)


def test_without_numpy(no_numpy: None) -> None:
    with pytest.raises(MissingLibraryError):
        walk_through_echo(SAMPLE_FILE, "h", ECHO)
