"""Tests for audiosteg/cli/player.py. No test plays sound."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, BinaryIO

import pytest
from conftest import environment

from audiosteg.cli import player
from audiosteg.cli.errors import PlayerError, error_type

FAKE_PLAYER = """
import json, os, sys, time
log, what, path = sys.argv[1:]
with open(path, "rb") as sound:
    data = sound.read()
info = {
    "process": os.getpid(), "path": path, "data": data.hex(), "folder": os.listdir(os.path.dirname(path)),
    "modes": [os.stat(name).st_mode & 0o777 for name in (path, os.path.dirname(path))],
    "input": sys.stdin.read(),
}
print("noise")
print("noise", file=sys.stderr)
with open(log + ".part", "w") as file:
    json.dump(info, file)
os.replace(log + ".part", log)
if what == "hang":
    time.sleep(60)
sys.exit(int(what))
"""


@pytest.mark.parametrize("name", ["/usr/bin/afplay", "/usr/bin/aplay", "paplay", "ffplay.exe"])
def test_no_test_can_start_a_real_player(run_process: Any, name: str) -> None:
    with pytest.raises(AssertionError, match="tried to play sound"):
        subprocess.Popen([name, "no such file.wav"])
    code = f"import subprocess; subprocess.Popen([{name!r}, 'no such file.wav'])"
    with pytest.raises(AssertionError, match="Traceback"):
        run_process(command=[sys.executable, "-c", code])


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows can play sound itself")
def test_no_test_can_play_sound_with_windows() -> None:
    import winsound

    with pytest.raises(AssertionError, match="tried to play sound"):
        winsound.PlaySound(None, 0)


@pytest.fixture
def fake_player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    """Return a function that makes a Python program the player of this system."""

    def use(what: str) -> list[str]:
        script = tmp_path / "fake_player.py"
        script.write_text(FAKE_PLAYER)
        command = [sys.executable, str(script), str(tmp_path / "log"), what]
        monkeypatch.setattr(player, "sys", SimpleNamespace(platform="darwin"))
        monkeypatch.setattr(player, "MAC_PLAYERS", (tuple(command),))
        return command

    return use


@pytest.fixture
def temporary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return the folder for temporary files."""
    folder = tmp_path / "temporary"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def write_sound(target: BinaryIO) -> None:
    target.write(b"sound")


def test_a_private_file_is_played_and_removed(
    fake_player: Any, temporary: Path, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    fake_player("0")
    player.play_private(write_sound, 0)
    seen = json.loads((tmp_path / "log").read_text())
    folder, name = os.path.split(seen["path"])
    assert (name, seen["folder"], bytes.fromhex(seen["data"])) == ("sound.wav", ["sound.wav"], b"sound")
    assert os.path.dirname(folder) == os.path.realpath(temporary)
    assert os.path.basename(folder).startswith("audiosteg_")
    assert seen["input"] == ""
    if os.name != "nt":
        assert seen["modes"] == [0o600, 0o700]
    assert list(temporary.iterdir()) == []
    assert capfd.readouterr() == ("", "")


def test_a_player_that_fails(fake_player: Any, temporary: Path) -> None:
    fake_player("3")
    with pytest.raises(PlayerError, match="player failed. Save the difference") as error:
        player.play_private(write_sound, 0)
    assert error_type(error.value) == "player"
    assert list(temporary.iterdir()) == []


def test_sound_that_cannot_be_written_is_not_played(
    fake_player: Any, temporary: Path, tmp_path: Path
) -> None:
    fake_player("0")

    def fail(target: BinaryIO) -> None:
        target.write(b"part")
        raise OSError(28, "No space left on device")

    with pytest.raises(OSError, match="No space"):
        player.play_private(fail, 0)
    assert list(temporary.iterdir()) == []
    assert not (tmp_path / "log").exists()


class Interrupted(subprocess.Popen[bytes]):
    """A process that is waited for until Ctrl-C."""

    started: list["Interrupted"] = []
    interrupted = False

    def wait(self, timeout: float | None = None) -> int:
        if not self.interrupted:
            self.interrupted = True
            self.started.append(self)
            raise KeyboardInterrupt
        return super().wait(timeout)


def test_ctrl_c_ends_the_player_and_removes_the_file(
    fake_player: Any, temporary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_player("hang")
    Interrupted.started.clear()
    monkeypatch.setattr(subprocess, "Popen", Interrupted)
    with pytest.raises(KeyboardInterrupt):
        player.play_private(write_sound, 0)
    assert Interrupted.started[0].returncode not in (None, 0)
    assert list(temporary.iterdir()) == []


def test_the_search_path_and_the_current_folder_are_never_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("afplay", "aplay", "paplay", "ffplay"):
        (tmp_path / name).write_text("#!/bin/sh\n")
        (tmp_path / name).chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    for platform in ("linux", "darwin", "freebsd14"):
        monkeypatch.setattr(player, "sys", SimpleNamespace(platform=platform))
        assert player.find_command() is None
        assert not player.can_play()
        with pytest.raises(PlayerError, match="No known audio player was found. Save the difference"):
            player.check_player()
        with pytest.raises(PlayerError, match="No known audio player"):
            player.play("sound.wav", 1)


def test_the_players_of_linux_in_their_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    usual, local = tmp_path / "bin", tmp_path / "local"
    monkeypatch.setattr(player, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(player, "LINUX_FOLDERS", (str(usual), str(local)))
    expected = [
        (local, "ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", "-f", "wav"]),
        (usual, "paplay", []),
        (local, "aplay", ["-q"]),
        (usual, "aplay", ["-q"]),
    ]
    for folder, name, options in expected:
        folder.mkdir(exist_ok=True)
        (folder / name).touch(mode=0o755)
        (folder / name).chmod(0o755)
        assert player.find_command() == [f"{folder}/{name}", *options]
    assert player.can_play()
    player.check_player()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_only_a_file_that_can_be_run_is_a_player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(player, "LINUX_FOLDERS", (str(tmp_path),))
    (tmp_path / "aplay").mkdir()
    (tmp_path / "paplay").touch(mode=0o644)
    assert player.find_command() is None
    (tmp_path / "ffplay").symlink_to(sys.executable)
    command = player.find_command()
    assert command is not None and command[0] == f"{tmp_path}/ffplay"


def test_the_real_players_are_fixed_paths(run_process: Any) -> None:
    code = (
        "import json; from audiosteg.cli import player; "
        "print(json.dumps([player.MAC_PLAYERS, player.LINUX_FOLDERS]))"
    )
    result = run_process(command=[sys.executable, "-c", code])
    assert json.loads(result.output) == [[["/usr/bin/afplay"]], ["/usr/bin", "/usr/local/bin"]]


class FakeWinsound(SimpleNamespace):
    SND_FILENAME, SND_ASYNC, SND_NODEFAULT = 0x20000, 1, 2

    def __init__(self, fail: bool = False) -> None:
        super().__init__(calls=[], fail=fail)

    def PlaySound(self, sound: str | None, flags: int) -> None:
        self.calls.append((sound, flags, sound is not None and Path(sound).read_bytes()))
        if self.fail and sound is not None:
            raise RuntimeError("Failed to play sound")


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> Callable[..., tuple[FakeWinsound, list[float]]]:
    """Return a function that makes this system a Windows with a fake winsound."""

    def use(fail: bool = False, interrupt: bool = False) -> tuple[FakeWinsound, list[float]]:
        winsound, slept = FakeWinsound(fail), []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            if interrupt:
                raise KeyboardInterrupt

        monkeypatch.setitem(sys.modules, "winsound", winsound)
        monkeypatch.setattr(player, "sys", SimpleNamespace(platform="win32"))
        monkeypatch.setattr(player, "time", SimpleNamespace(sleep=sleep))
        return winsound, slept

    return use


@pytest.mark.parametrize(
    ("options", "expected"),
    [({}, None), ({"fail": True}, PlayerError), ({"interrupt": True}, KeyboardInterrupt)],
)
def test_windows_plays_until_the_end_and_always_stops(
    windows: Any, temporary: Path, options: dict[str, bool], expected: type[BaseException] | None
) -> None:
    winsound, slept = windows(**options)
    assert player.can_play()
    player.check_player()
    if expected is None:
        player.play_private(write_sound, 1.5)
    else:
        with pytest.raises(expected):
            player.play_private(write_sound, 1.5)
    (path, flags, data), stop = winsound.calls
    assert (os.path.basename(path), flags, data) == ("sound.wav", 0x20003, b"sound")
    assert stop == (None, 0, False)
    assert slept == ([] if options.get("fail") else [1.5])
    assert list(temporary.iterdir()) == []


def handlers() -> list[Any]:
    names = ("SIGTERM", "SIGHUP", "SIGINT")
    return [signal.getsignal(getattr(signal, name)) for name in names if hasattr(signal, name)]


def test_a_request_to_end_becomes_an_exit_code_and_later_requests_wait() -> None:
    before = handlers()
    cleaned = []
    with pytest.raises(SystemExit) as left, player.clean_exit_on_signals():
        assert signal.getsignal(signal.SIGINT) is before[-1]
        try:
            signal.raise_signal(signal.SIGTERM)
        finally:
            signal.raise_signal(signal.SIGTERM)
            if hasattr(signal, "SIGHUP") and signal.getsignal(signal.SIGHUP) != signal.SIG_DFL:
                signal.raise_signal(signal.SIGHUP)
            cleaned.append(True)
    assert (left.value.code, cleaned) == (143, [True])
    assert handlers() == before


@pytest.mark.parametrize("error", [None, KeyboardInterrupt, OSError])
def test_the_handlers_are_always_restored(error: type[BaseException] | None) -> None:
    before = handlers()
    try:
        with player.clean_exit_on_signals():
            assert handlers()[0] is not before[0]
            if error:
                raise error
    except (KeyboardInterrupt, OSError) as raised:
        assert type(raised) is error
    assert handlers() == before


def test_an_ignored_signal_stays_ignored() -> None:
    before = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        with player.clean_exit_on_signals():
            signal.raise_signal(signal.SIGTERM)
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
    finally:
        signal.signal(signal.SIGTERM, before)


@pytest.mark.parametrize("name", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_a_signal_while_the_player_starts_still_ends_it(
    fake_player: Any, temporary: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    if not hasattr(signal, name):
        pytest.skip("this system has no such signal")
    fake_player("hang")
    started: list[subprocess.Popen[bytes]] = []
    start = subprocess.Popen

    def start_and_signal(*words: Any, **options: Any) -> subprocess.Popen[bytes]:
        started.append(start(*words, **options))
        signal.raise_signal(getattr(signal, name))
        return started[-1]

    monkeypatch.setattr(subprocess, "Popen", start_and_signal)
    before = handlers()
    with pytest.raises((SystemExit, KeyboardInterrupt)):
        player.play_private(write_sound, 0)
    assert started[0].returncode not in (None, 0)
    assert (list(temporary.iterdir()), handlers()) == ([], before)


def test_another_thread_can_play(fake_player: Any, temporary: Path, tmp_path: Path) -> None:
    fake_player("0")
    before = handlers()
    thread = threading.Thread(target=player.play_private, args=(write_sound, 0))
    thread.start()
    thread.join(30)
    assert (tmp_path / "log").exists()
    assert handlers() == before


PLAYING = """
import signal, sys
signal.signal(signal.SIGINT, signal.default_int_handler)
for name in ("SIGTERM", "SIGHUP"):
    signal.signal(getattr(signal, name), signal.SIG_DFL)
from audiosteg.cli import player
from audiosteg.cli.main import main
player.MAC_PLAYERS = (tuple(sys.argv[1].split("|")),)
player.sys = type("System", (), {"platform": "darwin"})
sys.exit(main(sys.argv[2:]))
"""


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
@pytest.mark.parametrize(("name", "code"), [("SIGTERM", 143), ("SIGHUP", 129), ("SIGINT", 130)])
def test_ending_the_program_ends_the_player_and_removes_the_file(
    fake_player: Any, make_pair: Any, temporary: Path, tmp_path: Path, name: str, code: int
) -> None:
    words = ["compare", *make_pair([1, 2], [1, 3]), "--play", "difference"]
    process = subprocess.Popen(
        [sys.executable, "-c", PLAYING, "|".join(fake_player("hang")), *words],
        env=environment(TMPDIR=str(temporary)),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 30
    while not (tmp_path / "log").exists():
        assert time.monotonic() < deadline and process.poll() is None
        time.sleep(0.01)
    seen = json.loads((tmp_path / "log").read_text())
    process.send_signal(getattr(signal, name))
    _, errors = process.communicate(timeout=30)
    assert process.returncode == code
    assert b"Traceback" not in errors
    assert list(temporary.iterdir()) == []
    with pytest.raises(ProcessLookupError):
        os.kill(seen["process"], 0)
