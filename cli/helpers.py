"""Menus and prompts."""

import os
import sys
from collections.abc import Sequence

from cli.config import ALGORITHMS, Algorithm
from utils.text import escape_text


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


def get_file_path(description: str, default_path: str) -> str:
    """
    Get a file path from the user.

    Spaces around the path are removed, and ~ means the user's home folder.

    :param description: What the file is, for example "Input audio file"
    :param default_path: The path used when the user presses Enter
    :return: The chosen path
    """
    path = ask(f"\n{description} [{escape_text(default_path)}]: ").strip()
    if not path:
        return default_path
    expanded_path = os.path.expanduser(path)
    if expanded_path.startswith("~"):
        raise FileNotFoundError(f"No home folder was found for this path: {path}")
    return expanded_path


def display_algorithm_menu() -> None:
    """Display the algorithm selection menu."""
    names = [algorithm["name"] for algorithm in ALGORITHMS.values()]
    display_menu([*names, "Back"], "Select an algorithm")


def choose_algorithm() -> Algorithm | None:
    """Ask for an algorithm until the choice is valid. Return None for Back."""
    while True:
        display_algorithm_menu()
        choice = get_user_choice(len(ALGORITHMS) + 1)
        if choice is not None:
            return ALGORITHMS.get(choice)
