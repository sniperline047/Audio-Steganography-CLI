"""Menus and prompts."""

from collections.abc import Sequence

from cli.config import ALGORITHMS
from utils.text import escape_text


def display_menu(options: Sequence[str], header: str) -> None:
    """Display a menu with a header and a list of options."""
    print(f"\n{header}:")
    for idx, option in enumerate(options, 1):
        print(f"{idx}) {option}")


def get_user_choice(num_options: int) -> int | None:
    """Get a menu choice, or None if it is not valid."""
    try:
        choice = int(input("\nChoice: "))
    except ValueError:
        print("\nPlease enter a valid number!")
        return None
    if 1 <= choice <= num_options:
        return choice
    print("\nInvalid choice, please select a valid option.")
    return None


def ask_yes_no(question: str, default: bool) -> bool:
    """Ask a yes or no question. Enter selects the default."""
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{question} ({hint}): ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def get_file_path(description: str, default_path: str) -> str:
    """
    Get a file path from the user.

    :param description: What the file is, for example "input audio file"
    :param default_path: The path used when the user presses Enter
    :return: The chosen path
    """
    shown_path = escape_text(default_path)
    if ask_yes_no(f"\nUse the default {description} ({shown_path})?", default=True):
        return default_path
    path = input(f"Enter the path to the {description} (press Enter for the default): ")
    return path if path.strip() else default_path


def display_algorithm_menu() -> None:
    """Display the algorithm selection menu."""
    display_menu([algorithm["name"] for algorithm in ALGORITHMS.values()], "Select an algorithm")
