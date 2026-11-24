"""Tests for scripts/generate_sample_audio.py."""

from pathlib import Path

import pytest

from cli.config import STANDARD_INPUT_FILE_PATH
from scripts import generate_sample_audio


def test_the_script_creates_the_committed_sample_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = generate_sample_audio.OUTPUT_PATH
    assert committed == Path(STANDARD_INPUT_FILE_PATH)
    generated = tmp_path / "input" / "sample.wav"
    monkeypatch.setattr(generate_sample_audio, "OUTPUT_PATH", generated)
    generate_sample_audio.main()
    assert generated.read_bytes() == committed.read_bytes()
