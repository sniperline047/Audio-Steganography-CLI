"""Shared fixtures."""

import atexit
import contextlib
import hashlib
import importlib.util
import io
import os
import random
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from asyncio import get_running_loop
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest
import rich.console
from prompt_toolkit.application import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output
from questionary import Question

from audiosteg.cli import passphrase as passphrase_module
from audiosteg.cli import player
from audiosteg.cli.commands.hide import SAMPLE_FILE
from audiosteg.cli.main import main
from audiosteg.core import crypto

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOUND_GUARD = """
import os, sys
PLAYERS = {"afplay", "aplay", "paplay", "ffplay"}
STARTS = {"subprocess.Popen", "os.posix_spawn", "os.exec", "os.system"}

def words_of(value):
    if isinstance(value, (str, bytes, os.PathLike)):
        return os.fsdecode(value).split()
    return [word for part in value for word in words_of(part)] if isinstance(value, (list, tuple)) else []

def refuse_sound(event, args):
    names = {os.path.splitext(os.path.basename(word))[0] for part in args[:2] for word in words_of(part)} \
        if event in STARTS else set()
    if names & PLAYERS:
        play_nothing()

def play_nothing(*args, **options):
    raise AssertionError("A test tried to play sound.")

sys.addaudithook(refuse_sound)
try:
    import winsound
except ImportError:
    pass
else:
    winsound.PlaySound = winsound.Beep = winsound.MessageBeep = play_nothing
"""


def pytest_configure() -> None:
    """Make starting a real player an error, in this process and in every Python process it starts."""
    folder = tempfile.mkdtemp(prefix="audiosteg_tests_")
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    Path(folder, "sitecustomize.py").write_text(SOUND_GUARD)
    paths = [folder, os.environ.get("PYTHONPATH", "")]
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, paths))
    exec(SOUND_GUARD, {})


@pytest.fixture(autouse=True)
def no_real_player(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test run on a system without a player."""
    monkeypatch.setattr(player, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(player, "MAC_PLAYERS", ())
    monkeypatch.setattr(player, "LINUX_FOLDERS", ())


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


def pack(values: list[int], bits: int) -> bytes:
    """Return numbers as the README says that samples are stored, without the package."""
    if bits == 8:
        return bytes(value + 128 for value in values)
    return b"".join(value.to_bytes(bits // 8, "little", signed=True) for value in values)


@pytest.fixture
def make_samples(make_wav: Callable[..., Path]) -> Callable[..., Path]:
    """Return a function that creates a WAV file from numbers, where 0 is silence."""

    def make(name: str, values: list[int], bits: int = 16, channels: int = 1, frame_rate: int = 8000) -> Path:
        return make_wav(name, pack(values, bits), channels, bits // 8, frame_rate)

    return make


@pytest.fixture
def make_pair(make_samples: Callable[..., Path]) -> Callable[..., tuple[str, str]]:
    """Return a function that creates a.wav and b.wav from two lists of numbers."""

    def make(original: list[int], encoded: list[int], bits: int = 16, **options: int) -> tuple[str, str]:
        first = make_samples("a.wav", original, bits, **options)
        return str(first), str(make_samples("b.wav", encoded, bits, **options))

    return make


@pytest.fixture
def sounds(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, float]]:
    """Return what would be played: the bytes of every file, and how long it is. Nothing is played."""
    played: list[tuple[bytes, float]] = []

    def record(path: str, seconds: float) -> None:
        played.append((Path(path).read_bytes(), seconds))

    monkeypatch.setattr(player, "can_play", lambda: True)
    monkeypatch.setattr(player, "play", record)
    return played


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


def environment(**changes: str) -> dict[str, str]:
    """Return an environment that does not depend on the one of the test run."""
    unwanted = ("NO_COLOR", "FORCE_COLOR", "COLORTERM", "COLUMNS", "LINES")
    kept = {name: value for name, value in os.environ.items() if name not in unwanted}
    return {**kept, "PYTHONIOENCODING": "utf-8", "TERM": "xterm-256color", **changes}


def remove_styles(shown: str) -> str:
    """Return what a terminal showed, without colours and cursor movements."""
    return re.sub(r"\x1b(\[[0-?]*[ -/]*[@-~]|[=>])", "", shown)


class Result:
    """The outcome of one CLI run."""

    def __init__(self, code: int, output: bytes, errors: bytes, seen: bytes = b"") -> None:
        self.code = code
        self.raw_output = output
        self.output = output.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        self.errors = errors.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        self.seen = seen.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
        assert "Traceback" not in self.errors
        assert "Exception ignored" not in self.errors

    @property
    def text(self) -> str:
        """What a terminal showed, without colours and cursor movements."""
        return remove_styles(self.seen)


class Pipe(io.BytesIO):
    """An output that also adds everything to one transcript."""

    def __init__(self, transcript: bytearray) -> None:
        super().__init__()
        self.transcript = transcript

    def write(self, data: Any) -> int:
        self.transcript += data
        return super().write(data)


class Stream(io.TextIOWrapper):
    """A standard stream that may pretend to be a terminal."""

    terminal = False

    def isatty(self) -> bool:
        return self.terminal


class Console:
    """Runs the CLI in this process, on every system, with streams that may pretend to be a terminal."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
        self.monkeypatch = monkeypatch
        self.folder = folder

    def run(
        self,
        *words: str | Path,
        stdin: bytes = b"",
        hidden: tuple[str | type[BaseException], ...] = (),
        cwd: Path | None = None,
        encoding: str = "utf-8",
        terminals: tuple[str, ...] = (),
        columns: int = 300,
        broken: tuple[str, ...] = (),
        prompts: tuple[tuple[str, Any], ...] = (),
        typing: type[io.BytesIO] = io.BytesIO,
        **changes: str,
    ) -> Result:
        """
        Run one command.

        :param words: The command line
        :param stdin: What is typed or piped
        :param hidden: What is typed where typing is hidden, or errors to raise there
        :param terminals: The streams that are terminals
        :param broken: The streams whose reader has left
        :param prompts: Questions of the guided mode, and the keys that answer each
        :param typing: The kind of input, which may raise errors
        :param changes: Changes of the environment
        """
        transcript = bytearray()
        raw = {"stdin": typing(stdin), "stdout": Pipe(transcript), "stderr": Pipe(transcript)}
        answers = iter(hidden)

        def getpass(prompt: str) -> str:
            transcript.extend(prompt.encode())
            answer = next(answers)
            if isinstance(answer, str):
                return answer
            raise answer

        def write_nowhere(data: Any) -> int:
            raise BrokenPipeError(32, "Broken pipe")

        with self.monkeypatch.context() as patch:
            patch.chdir(cwd or self.folder)
            for name in ("NO_COLOR", "FORCE_COLOR", "COLORTERM", "LINES"):
                patch.delenv(name, raising=False)
            for name, value in {"TERM": "xterm-256color", "COLUMNS": str(columns), **changes}.items():
                patch.setenv(name, value)
            patch.setattr(rich.console, "WINDOWS", False)
            patch.setattr(passphrase_module, "getpass", getpass)
            for name, buffer in raw.items():
                stream = Stream(buffer, encoding=encoding, write_through=True)
                stream.terminal = name in terminals
                if name in broken:
                    patch.setattr(buffer, "write", write_nowhere)
                patch.setattr(sys, name, stream)
            with answer_questions(patch, prompts, transcript, columns):
                code = main([str(word) for word in words])
            result = Result(code, raw["stdout"].getvalue(), raw["stderr"].getvalue(), bytes(transcript))
        assert next(answers, None) is None, "a hidden answer was not used"
        return result


@contextlib.contextmanager
def answer_questions(
    patch: pytest.MonkeyPatch, prompts: tuple[tuple[str, Any], ...], transcript: bytearray, columns: int
) -> Iterator[None]:
    """Answer the questions of the guided mode with keys from a pipe. This works on every system."""
    script = iter(prompts)
    original = Question.unsafe_ask

    with create_pipe_input() as keys:

        def ask(question: Question, patch_stdout: bool = False) -> Any:
            expected, answer = next(script, ("", None))
            start = len(transcript)
            answered = False

            def shown() -> str:
                return remove_styles(bytes(transcript[start:]).decode("utf-8", "replace"))

            def fail(reason: str) -> None:
                if not question.application.future.done():
                    question.application.exit(exception=AssertionError(f"{reason}: {shown()}"))

            def type_answer(application: Any) -> None:
                nonlocal answered
                if answered:
                    return
                answered = True
                application.timeoutlen = application.ttimeoutlen = 0.02
                get_running_loop().call_later(10, fail, f"{expected!r} was not answered")
                if answer is None or expected not in shown():
                    fail(f"{expected!r} was expected, not this question")
                elif isinstance(answer, str):
                    keys.send_text(answer)
                else:
                    answer(application)

            question.application.after_render += type_answer
            return original(question, patch_stdout)

        patch.setattr(Question, "unsafe_ask", ask)
        screen = Vt100_Output(
            sys.stdout, lambda: Size(rows=40, columns=columns), term="xterm-256color", enable_cpr=False
        )
        with create_app_session(input=keys, output=screen):
            yield
    assert next(script, None) is None, "a question was not asked"


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[..., Result]:
    """Return a function that runs one command in this process, in tmp_path, without a terminal."""
    return Console(monkeypatch, tmp_path).run


ALL = ("stdin", "stdout", "stderr")


@pytest.fixture
def guide(run: Callable[..., Result]) -> Callable[..., Result]:
    """Return a function that answers the questions of the guided mode, the last of them with Ctrl-D."""

    def answer(*prompts: tuple[str, Any], leave: bool = True, **options: Any) -> Result:
        leaving = (("What would you like to do?", "\x04"),) if leave else ()
        return run(prompts=(*prompts, *leaving), terminals=ALL, **options)

    return answer


@pytest.fixture
def run_process(tmp_path: Path) -> Callable[..., Result]:
    """Return a function that runs one command in a real process without a terminal."""

    def run_command(
        *words: str | Path, stdin: bytes = b"", command: list[str] | None = None, cwd: Path = tmp_path
    ) -> Result:
        detached = {} if os.name == "nt" else {"start_new_session": True}
        finished = subprocess.run(
            [*(command or PROGRAM), *map(str, words)],
            input=stdin,
            capture_output=True,
            cwd=cwd,
            env=environment(),
            timeout=TIMEOUT,
            **detached,
        )
        return Result(finished.returncode, finished.stdout, finished.stderr)

    return run_command


TERMINAL_PROGRAM = """
import fcntl, sys, termios
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
from audiosteg.cli import player
from audiosteg.cli.main import main
player.MAC_PLAYERS = player.LINUX_FOLDERS = ()
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
