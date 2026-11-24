"""Shared fixtures."""

import hashlib
import random
import wave
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from audiosteg.cli.main import SAMPLE_FILE

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def repository_audio() -> dict[str, tuple[int, str]]:
    """Describe the sample audio and any audio in the project folder."""
    return {
        str(path): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for folder in (PROJECT_ROOT, PROJECT_ROOT / "src" / "audiosteg" / "data", Path(SAMPLE_FILE).parent)
        for path in folder.glob("*.wav")
    }


@pytest.fixture(scope="session", autouse=True)
def repository_audio_is_untouched() -> Iterator[None]:
    """Fail the run if a test changes the sample audio or writes audio to the project folder."""
    before = repository_audio()
    yield
    assert repository_audio() == before


@pytest.fixture
def make_wav(tmp_path: Path) -> Callable[..., Path]:
    """Return a function that creates a real PCM WAV file in tmp_path."""

    def make(
        name: str = "input.wav",
        frames: bytes | None = None,
        channels: int = 1,
        sample_width: int = 1,
        frame_rate: int = 8000,
    ) -> Path:
        path = tmp_path / name
        if frames is None:
            frames = random.Random(7).randbytes(4008)
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(channels)
            audio.setsampwidth(sample_width)
            audio.setframerate(frame_rate)
            audio.writeframes(frames)
        return path

    return make


@pytest.fixture
def read_frames() -> Callable[[Path], bytes]:
    """Return a function that reads every sample byte of a WAV file."""

    def read(path: Path) -> bytes:
        with wave.open(str(path), "rb") as audio:
            return audio.readframes(audio.getnframes())

    return read
