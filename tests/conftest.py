"""Shared fixtures."""

import contextlib
import hashlib
import importlib.util
import os
import random
import select
import signal
import subprocess
import sys
import time
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

from audiosteg.cli.commands.hide import SAMPLE_FILE
from audiosteg.core import crypto

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class KnownAnswer(NamedTuple):
    """An encrypted container made by another program from the README."""

    passphrase: str
    message: str
    header: bytes
    salt: bytes
    nonce: bytes
    ciphertext: bytes
    tag: bytes
    key: bytes

    @property
    def body(self) -> bytes:
        return self.salt + self.nonce + self.ciphertext + self.tag

    @property
    def container(self) -> bytes:
        return self.header + self.body


KNOWN_ANSWER = KnownAnswer(
    passphrase="Café ☕",
    message="Hé 🎵",
    header=bytes.fromhex("41535447010100000008"),
    salt=bytes.fromhex("101112131415161718191a1b1c1d1e1f"),
    nonce=bytes.fromhex("a0a1a2a3a4a5a6a7a8a9aaab"),
    ciphertext=bytes.fromhex("94b4be463bf41f25"),
    tag=bytes.fromhex("15834794acd9447aabba741f215de768"),
    key=bytes.fromhex("496133bd0cbf70968e537d34b1d85e6cf64644bbd2f936dd50b0142abc812304"),
)


def repository_audio() -> dict[str, tuple[int, str]]:
    """Describe the sample audio and any audio in the project folder."""
    return {
        str(path): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for folder in (PROJECT_ROOT, PROJECT_ROOT / "src" / "audiosteg" / "data", Path(SAMPLE_FILE).parent)
        for path in folder.glob("*.wav")
    }


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip tests marked needs_crypto without the library, unless AUDIOSTEG_REQUIRE_CRYPTO is set."""
    if os.environ.get("AUDIOSTEG_REQUIRE_CRYPTO") or importlib.util.find_spec("cryptography"):
        return
    for item in items:
        if item.get_closest_marker("needs_crypto"):
            item.add_marker(pytest.mark.skip(reason="the crypto extra is not installed"))


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


@pytest.fixture
def known_answer() -> KnownAnswer:
    """Return the known encrypted container."""
    return KNOWN_ANSWER


@pytest.fixture
def known_randomness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make encryption use the salt and the nonce of the known answer."""
    values = {16: KNOWN_ANSWER.salt, 12: KNOWN_ANSWER.nonce}
    monkeypatch.setattr(crypto, "secrets", SimpleNamespace(token_bytes=values.__getitem__))


@pytest.fixture
def fast_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make keys cheap. The known answers check the real cost."""
    monkeypatch.setattr(crypto, "SCRYPT_N", 2)


@pytest.fixture
def no_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make importing the encryption library fail, whether or not it is installed."""
    for name in ("cryptography", "cryptography.exceptions", "cryptography.hazmat.primitives.ciphers.aead"):
        monkeypatch.setitem(sys.modules, name, None)


@pytest.fixture
def embed() -> Callable[..., bytes]:
    """Return a function that hides bytes in samples as the README says, without the package."""

    def hide(hidden: bytes, size: int, sample_width: int = 1, cover: bytes | None = None) -> bytes:
        digits = "".join(f"{byte:08b}" for byte in hidden)
        if cover is None:
            cover = bytes((index * 37 + 11) % 256 for index in range(len(digits) // size * sample_width + 48))
        frames = bytearray(cover)
        for sample in range(len(digits) // size):
            position = sample * sample_width
            group = int(digits[sample * size : (sample + 1) * size], 2)
            frames[position] = frames[position] >> size << size | group
        return bytes(frames)

    return hide


PROGRAM = [sys.executable, "-m", "audiosteg"]
TIMEOUT = 60
NO_SIGINT = os.name == "nt" or signal.getsignal(signal.SIGINT) == signal.SIG_IGN


class Result:
    """The outcome of one CLI run."""

    def __init__(self, code: int, output: bytes, errors: bytes) -> None:
        self.code = code
        self.raw_output = output
        self.output = output.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        self.errors = errors.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        assert "Traceback" not in self.errors
        assert "Exception ignored" not in self.errors


def environment(**changes: str) -> dict[str, str]:
    """Return an environment that does not depend on the one of the test run."""
    unwanted = ("NO_COLOR", "FORCE_COLOR", "COLORTERM", "COLUMNS", "LINES")
    kept = {name: value for name, value in os.environ.items() if name not in unwanted}
    return {**kept, "PYTHONIOENCODING": "utf-8", "TERM": "xterm-256color", **changes}


@pytest.fixture
def run() -> Callable[..., Result]:
    """Return a function that runs one command in a real process without a terminal."""

    def run_command(
        *words: str | Path,
        stdin: bytes = b"",
        command: list[str] | None = None,
        cwd: Path | None = None,
        encoding: str = "utf-8",
    ) -> Result:
        detached = {} if os.name == "nt" else {"start_new_session": True}
        finished = subprocess.run(
            [*(command or PROGRAM), *map(str, words)],
            input=stdin,
            capture_output=True,
            cwd=cwd,
            env=environment(PYTHONIOENCODING=encoding),
            timeout=TIMEOUT,
            **detached,
        )
        return Result(finished.returncode, finished.stdout, finished.stderr)

    return run_command


TERMINAL_PROGRAM = """
import fcntl, sys, termios
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
from audiosteg.cli.main import main
code = main(sys.argv[1:])
print("Typing is", "shown" if termios.tcgetattr(0)[3] & termios.ECHO else "hidden")
sys.stdin.readline()
sys.exit(code)
"""


class Terminal:
    """The CLI in a real terminal."""

    def __init__(self, folder: Path, words: list[str], columns: int, changes: dict[str, str]) -> None:
        import fcntl
        import pty
        import struct
        import termios

        self.seen = ""
        self.position = 0
        self.controller, self.device = pty.openpty()
        fcntl.ioctl(self.device, termios.TIOCSWINSZ, struct.pack("HHHH", 40, columns, 0, 0))
        self.process = subprocess.Popen(
            [sys.executable, "-c", TERMINAL_PROGRAM, *words],
            stdin=self.device,
            stdout=self.device,
            stderr=self.device,
            cwd=folder,
            env=environment(PROMPT_TOOLKIT_NO_CPR="1", **changes),
            start_new_session=True,
        )
        self.deadline = time.monotonic() + TIMEOUT

    def close(self) -> None:
        self.process.kill()
        os.close(self.controller)
        os.close(self.device)
        self.process.wait()

    def receive(self, seconds: float) -> None:
        if select.select([self.controller], [], [], seconds)[0]:
            self.seen += os.read(self.controller, 4096).decode("utf-8", "replace").replace("\r\n", "\n")

    def read(self, text: str) -> None:
        """Read until the terminal shows the text."""
        while text not in self.seen[self.position :]:
            assert time.monotonic() < self.deadline, f"no {text!r} in {self.seen!r}"
            self.receive(0.1)
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

    def answer(self, question: str, keys: str) -> None:
        """Wait for a question of the guided mode, and type if there is anything to type."""
        self.read(question)
        if keys:
            self.type_hidden(keys)

    def finish(self) -> int:
        """Check that typing is shown again, let the program stop, and return its exit code."""
        self.read("Typing is shown")
        self.type("\n")
        while self.process.poll() is None:
            assert time.monotonic() < self.deadline, "the program did not stop"
            with contextlib.suppress(OSError):
                self.receive(0.05)
        assert "Traceback" not in self.seen
        return self.process.returncode


@pytest.fixture
def terminal(tmp_path: Path) -> Iterator[Callable[..., Terminal]]:
    """Return a function that starts the CLI in a real terminal."""
    pytest.importorskip("termios", reason="this system has no such terminals")
    started: list[Terminal] = []

    def start(*words: str | Path, columns: int = 200, **changes: str) -> Terminal:
        started.append(Terminal(tmp_path, [*map(str, words)], columns, changes))
        return started[-1]

    yield start
    for program in started:
        program.close()
