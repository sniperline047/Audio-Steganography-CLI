"""Tests for scripts/generate_sample_audio.py."""

from pathlib import Path

import pytest

from audiosteg.cli.main import SAMPLE_FILE
from scripts import generate_sample_audio


def test_the_script_creates_the_committed_sample_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = generate_sample_audio.OUTPUT_PATH
    assert committed.read_bytes() == Path(SAMPLE_FILE).read_bytes()
    generated = tmp_path / "data" / "sample.wav"
    monkeypatch.setattr(generate_sample_audio, "OUTPUT_PATH", generated)
    generate_sample_audio.main()
    assert generated.read_bytes() == committed.read_bytes()
