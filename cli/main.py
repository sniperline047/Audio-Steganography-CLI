"""Interactive menu for hiding messages in audio files."""

import contextlib
import io
import os
import sys
from collections.abc import Callable

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cli.accuracy import calculate_accuracy
from cli.config import STANDARD_INPUT_FILE_PATH
from cli.helpers import (
    OutputClosedError,
    ask,
    ask_yes_no,
    choose_algorithm,
    display_menu,
    get_file_path,
    get_user_choice,
    require_output,
)
from utils.errors import StegoError
from utils.output_path import check_output_path, normalize_output_path
from utils.text import escape_text
from utils.wav_io import check_regular_file

EXIT_CHOICE = 4


def handle_encode() -> None:
    """Ask for a message and hide it in a copy of an audio file."""
    algorithm = choose_algorithm()
    secret_message = ask("Enter the secret message to encode: ")
    input_file = get_file_path("Input audio file", STANDARD_INPUT_FILE_PATH)
    chosen_path = get_file_path("Output audio file", algorithm["output_file"])

    check_regular_file(input_file)
    output_file = normalize_output_path(chosen_path)
    check_output_path(input_file, output_file, overwrite=True)
    overwrite = False
    if os.path.exists(output_file):
        overwrite = ask_yes_no(f"{escape_text(output_file)} already exists. Overwrite it?")
        if not overwrite:
            print("Nothing was written.")
            return

    print("Encoding...")
    require_output()
    algorithm["encode"](input_file, output_file, secret_message, overwrite)
    print(f"Message encoded into {escape_text(output_file)}")


def handle_decode() -> None:
    """Show the message hidden in an audio file."""
    algorithm = choose_algorithm()
    encoded_file = get_file_path("Encoded audio file", algorithm["output_file"])
    decoded_message = algorithm["decode"](encoded_file)
    if decoded_message:
        print(f"Decoded message: {escape_text(decoded_message)}")
    else:
        print("The decoded message is empty.")


def handle_accuracy_check() -> None:
    """Compare the message hidden in an audio file with the expected one."""
    expected_message = ask("Enter the expected secret message: ")
    algorithm = choose_algorithm()
    encoded_file = get_file_path("Encoded audio file", algorithm["output_file"])
    result = calculate_accuracy(expected_message, algorithm, encoded_file)
    print(f"Accuracy of decoded message: {result.percentage:.2f}%")
    print(f"Exact match: {'yes' if result.exact_match else 'no'}")
    print(f"Expected length: {result.expected_length}, decoded length: {result.decoded_length}")


def show_error(message: str) -> None:
    """Print an error, even if it contains unsafe characters or stderr is closed."""
    with contextlib.suppress(OSError):
        print(f"\nError: {escape_text(message)}", file=sys.stderr)


def run_operation(operation: Callable[[], None]) -> bool:
    """Run one menu operation and report any error. Return whether it succeeded."""
    try:
        operation()
    except (StegoError, OSError, ValueError) as error:
        show_error(str(error))
        return False
    except MemoryError:
        show_error("The file is too large for the available memory.")
        return False
    return True


def run_menu() -> int:
    """Show the menu until the user leaves. Return the exit code."""
    operations = {1: handle_encode, 2: handle_decode, 3: handle_accuracy_check}
    failed = False
    while True:
        display_menu(
            ["Encode a message", "Decode a message", "Calculate accuracy", "Exit"],
            "Select an option",
        )
        try:
            choice = get_user_choice(EXIT_CHOICE)
        except EOFError:
            print()
            break
        if choice == EXIT_CHOICE:
            break
        if choice is not None and not run_operation(operations[choice]):
            failed = True
    return 1 if failed else 0


def prepare_streams() -> None:
    """Accept and show text that the terminal's encoding does not support."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    if isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(errors="surrogateescape")


def flush_output() -> bool:
    """Write any waiting output. Return False if the output is closed."""
    try:
        sys.stdout.flush()
    except OSError:
        with contextlib.suppress(OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return False
    return True


def run_session() -> int:
    """Run the menu and report why it stopped early, if it did. Return the exit code."""
    try:
        return run_menu()
    except EOFError:
        show_error("The input ended before the operation finished.")
        return 1
    except KeyboardInterrupt:
        show_error("Interrupted.")
        return 130
    except OutputClosedError as error:
        show_error(str(error))
        return 1
    except OSError as error:
        show_error(f"The program cannot read its input or write its output: {error}")
        return 1


def main() -> int:
    """Run the CLI program."""
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    if sys.stdin is None or sys.stdout is None:
        show_error("The program needs an open input and output.")
        return 1
    prepare_streams()
    exit_code = run_session()
    if not flush_output():
        return exit_code or 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
