"""Menus and prompts."""

import os
import sys
import warnings
from collections.abc import Mapping, Sequence
from contextlib import suppress
from getpass import GetPassWarning, getpass
from typing import TypeVar

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.core.algorithm import Algorithm, LegacyAlgorithm
from audiosteg.utils.text import escape_text

AnyAlgorithm = TypeVar("AnyAlgorithm", Algorithm, LegacyAlgorithm)


class OutputClosedError(Exception):
    """Nobody can see the program's output anymore."""


def display_menu(options: Sequence[str], header: str) -> None:
    """Display a menu with a header and a list of options."""
    print(f"\n{header}:")
    for idx, option in enumerate(options, 1):
        print(f"{idx}) {option}")


def require_output() -> None:
    """Write any waiting output, and stop if nobody can see it."""
    try:
        sys.stdout.flush()
    except OSError as error:
        raise OutputClosedError("The output was closed.") from error


def ask(prompt: str) -> str:
    """Show a prompt and read one line."""
    print(prompt, end="")
    require_output()
    return input()


def read_hidden_line() -> str:
    """Read one line without showing it. Input that is not a terminal is read normally."""
    if not sys.stdin.isatty():
        return input()
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        try:
            with suppress(UnicodeDecodeError):
                return getpass("")
        except GetPassWarning as error:
            raise OSError("This terminal cannot hide the passphrase.") from error
    raise ValueError("The passphrase contains characters that are not valid text.")


def ask_hidden(prompt: str) -> str:
    """Show a prompt and read one line without showing it."""
    print(prompt, end="")
    require_output()
    return read_hidden_line()


def ask_new_passphrase() -> str | None:
    """Ask for a passphrase twice, until both match. Return None if the answer is empty."""
    while True:
        passphrase = ask_hidden("Passphrase, not shown while you type [none]: ")
        if not passphrase:
            return None
        if ask_hidden("Repeat the passphrase: ") == passphrase:
            return passphrase
        print("The passphrases do not match. Please try again.")


def get_user_choice(num_options: int) -> int | None:
    """Get a menu choice, or None if it is not valid."""
    answer = ask("\nChoice: ")
    try:
        choice = int(answer)
    except ValueError:
        print("\nPlease enter a valid number!")
        return None
    if 1 <= choice <= num_options:
        return choice
    print("\nInvalid choice, please select a valid option.")
    return None


def ask_yes_no(question: str) -> bool:
    """Ask a yes or no question. Enter means no."""
    while True:
        answer = ask(f"{question} (y/N): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Please answer y or n.")


def get_file_path(description: str, default_path: str, default_label: str | None = None) -> str:
    """
    Get a file path from the user.

    Spaces around the path are removed, and ~ means the user's home folder.

    :param description: What the file is, for example "Input audio file"
    :param default_path: The path used when the user presses Enter
    :param default_label: The text shown instead of the default path
    :return: The chosen path
    """
    path = ask(f"\n{description} [{escape_text(default_label or default_path)}]: ").strip()
    if not path:
        return default_path
    expanded_path = os.path.expanduser(path)
    if expanded_path.startswith("~"):
        raise FileNotFoundError(f"No home folder was found for this path: {path}")
    return expanded_path


def choose_from(algorithms: Mapping[int, AnyAlgorithm], header: str) -> AnyAlgorithm | None:
    """Ask for one of the algorithms until the choice is valid. Return None for Back."""
    while True:
        display_menu([*(algorithm.name for algorithm in algorithms.values()), "Back"], header)
        choice = get_user_choice(len(algorithms) + 1)
        if choice is not None:
            return algorithms.get(choice)


def choose_algorithm() -> Algorithm | None:
    """Ask for the algorithm that hides a message."""
    return choose_from(ALGORITHMS, "Select an algorithm")


def choose_legacy_algorithm() -> LegacyAlgorithm | None:
    """Ask for the algorithm of a file made by an older version."""
    return choose_from(LEGACY_ALGORITHMS, "Select an old algorithm")
