"""Interactive menu for hiding messages in audio files."""

import io
import os
import sys
from collections.abc import Callable

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cli.accuracy import calculate_accuracy
from cli.config import ALGORITHMS, STANDARD_INPUT_FILE_PATH, Algorithm
from cli.helpers import (
    ask_yes_no,
    display_algorithm_menu,
    display_menu,
    get_file_path,
    get_user_choice,
)
from utils.errors import StegoError
from utils.text import escape_text
from utils.wav_io import check_output_path, check_regular_file

EXIT_CHOICE = 4


def choose_algorithm() -> Algorithm | None:
    """Ask the user for an algorithm."""
    display_algorithm_menu()
    choice = get_user_choice(len(ALGORITHMS))
    return None if choice is None else ALGORITHMS[choice]


def handle_encode() -> None:
    """Ask for a message and hide it in a copy of an audio file."""
    algorithm = choose_algorithm()
    if algorithm is None:
        return
    secret_message = input("Enter the secret message to encode: ")
    input_file = get_file_path("input audio file", STANDARD_INPUT_FILE_PATH)
    output_file = get_file_path("output audio file", algorithm["output_file"])

    check_regular_file(input_file)
    check_output_path(input_file, output_file, overwrite=True)
    overwrite = False
    if os.path.exists(output_file):
        overwrite = ask_yes_no(f"{escape_text(output_file)} already exists. Overwrite it?", default=False)
        if not overwrite:
            print("Nothing was written.")
            return

    algorithm["encode"](input_file, output_file, secret_message, overwrite)
    print(f"Message encoded into {escape_text(output_file)}")


def handle_decode() -> None:
    """Show the message hidden in an audio file."""
    algorithm = choose_algorithm()
    if algorithm is None:
        return
    encoded_file = get_file_path("encoded audio file", algorithm["output_file"])
    decoded_message = algorithm["decode"](encoded_file)
    if decoded_message:
        print(f"Decoded message: {escape_text(decoded_message)}")
    else:
        print("The decoded message is empty.")


def handle_accuracy_check() -> None:
    """Compare the message hidden in an audio file with the expected one."""
    expected_message = input("Enter the expected secret message: ")
    algorithm = choose_algorithm()
    if algorithm is None:
        return
    encoded_file = get_file_path("encoded audio file", algorithm["output_file"])
    result = calculate_accuracy(expected_message, algorithm, encoded_file)
    print(f"Accuracy of decoded message: {result.percentage:.2f}%")
    print(f"Exact match: {'yes' if result.exact_match else 'no'}")
    print(f"Expected length: {result.expected_length}, decoded length: {result.decoded_length}")


def run_operation(operation: Callable[[], None]) -> bool:
    """Run one menu operation and report any error. Return whether it succeeded."""
    try:
        operation()
    except (StegoError, OSError, ValueError) as error:
        print(f"Error: {escape_text(str(error))}", file=sys.stderr)
        return False
    return True


def run_menu() -> int:
    """Show the menu until the user leaves. Return the exit code."""
    operations = {1: handle_encode, 2: handle_decode, 3: handle_accuracy_check}
    failed = False
    try:
        while True:
            display_menu(
                ["Encode a message", "Decode a message", "Calculate accuracy", "Exit"],
                "Select an option",
            )
            choice = get_user_choice(EXIT_CHOICE)
            if choice == EXIT_CHOICE:
                break
            if choice is not None and not run_operation(operations[choice]):
                failed = True
    except (EOFError, KeyboardInterrupt):
        print()
    return 1 if failed else 0


def main() -> int:
    """Run the CLI program."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    if isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(errors="surrogateescape")
    return run_menu()


if __name__ == "__main__":
    sys.exit(main())
