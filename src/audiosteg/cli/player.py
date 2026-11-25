"""Play a WAV file with a player that the system already has."""

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Any, BinaryIO

from audiosteg.cli.errors import PlayerError
from audiosteg.utils.safe_write import private_opener

MAC_PLAYERS = (("/usr/bin/afplay",),)
LINUX_FOLDERS = ("/usr/bin", "/usr/local/bin")
LINUX_PLAYERS = (
    ("aplay", "-q"),
    ("paplay",),
    ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-f", "wav"),
)
ENDING_SIGNALS = ("SIGTERM", "SIGHUP")
SIGNAL_EXIT_CODE = 128
NO_PLAYER = (
    "No known audio player was found. Save the difference with --save_difference FILE and open it yourself."
)
FAILED = "The audio player failed. Save the difference with --save_difference FILE and use another player."


def known_commands() -> Iterator[list[str]]:
    """Yield the commands that could play a file on this system."""
    if sys.platform == "darwin":
        yield from map(list, MAC_PLAYERS)
    elif sys.platform != "win32":
        for name, *options in LINUX_PLAYERS:
            for folder in LINUX_FOLDERS:
                yield [f"{folder}/{name}", *options]


def find_command() -> list[str] | None:
    """Return the first command that exists. The search path and the current folder are never used."""
    for command in known_commands():
        if os.path.isfile(command[0]) and os.access(command[0], os.X_OK):
            return command
    return None


def can_play() -> bool:
    """Say whether this system has a known player."""
    return sys.platform == "win32" or find_command() is not None


def check_player() -> None:
    """Refuse to continue without a player."""
    if not can_play():
        raise PlayerError(NO_PLAYER)


def play_on_windows(path: str, seconds: float) -> None:
    """Play a file with Windows itself."""
    if sys.platform == "win32":
        import winsound

        try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            time.sleep(seconds)
        except RuntimeError as error:
            raise PlayerError(FAILED) from error
        finally:
            winsound.PlaySound(None, 0)


def handlers_of(names: tuple[str, ...]) -> dict[int, Any]:
    """Return the handlers of the signals that can be replaced and are not ignored."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    numbers = [int(getattr(signal, name)) for name in names if hasattr(signal, name)]
    handlers = {number: signal.getsignal(number) for number in numbers}
    return {number: handler for number, handler in handlers.items() if handler not in (None, signal.SIG_IGN)}


@contextmanager
def held_signals() -> Iterator[None]:
    """Hold signals that could end the program, and deliver them afterwards."""
    previous = handlers_of(("SIGINT", *ENDING_SIGNALS))
    held: list[int] = []
    try:
        for number in previous:
            signal.signal(number, lambda number, frame: held.append(number))
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        for number in held:
            signal.raise_signal(number)


def play(path: str, seconds: float) -> None:
    """Play a file until its end. Ctrl-C stops it."""
    if sys.platform == "win32":
        play_on_windows(path, seconds)
        return
    command = find_command()
    if command is None:
        raise PlayerError(NO_PLAYER)
    process = None
    try:
        with held_signals():
            process = subprocess.Popen(
                [*command, path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        exit_code = process.wait()
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
    if exit_code != 0:
        raise PlayerError(FAILED)


@contextmanager
def clean_exit_on_signals() -> Iterator[None]:
    """Let a request to end the program first run the code that cleans up. Later requests wait for it."""
    previous = handlers_of(ENDING_SIGNALS)

    def leave(number: int, frame: FrameType | None) -> None:
        for known in previous:
            signal.signal(known, signal.SIG_IGN)
        raise SystemExit(SIGNAL_EXIT_CODE + number)

    try:
        for number in previous:
            signal.signal(number, leave)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def play_private(write: Callable[[BinaryIO], None], seconds: float) -> None:
    """
    Play sound from a private file that is always removed.

    :param write: Function that writes the WAV file
    :param seconds: How long the sound is
    """
    with clean_exit_on_signals(), tempfile.TemporaryDirectory(prefix="audiosteg_") as folder:
        path = os.path.join(os.path.realpath(folder), "sound.wav")
        with open(path, "xb", opener=private_opener) as destination:
            write(destination)
        play(path, seconds)
