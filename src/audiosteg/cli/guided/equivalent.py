"""Show the command that does the same as the guided mode."""

import os
import shlex
import subprocess

from audiosteg.cli.commands.hide import SAMPLE_WORD

WINDOWS_SAFE = "_-.:\\/ "


def can_show(word: str) -> bool:
    """Say whether a word means the same in every shell of this system."""
    if os.name == "nt":
        return all(character.isalnum() or character in WINDOWS_SAFE for character in word)
    return word.isprintable()


def command_line(*words: str) -> str | None:
    """Return a command for the terminal, or None if a word cannot be shown."""
    if not all(can_show(word) for word in words):
        return None
    return subprocess.list2cmdline(words) if os.name == "nt" else shlex.join(words)


def path_word(path: str) -> str:
    """Return a path that cannot be mistaken for an option or for the sample."""
    return os.path.join(".", path) if path.startswith("-") or path == SAMPLE_WORD else path
