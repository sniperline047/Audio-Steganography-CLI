"""Ask the person at the terminal. Questions go to stderr, so that stdout holds only results."""

import sys


def ask_line(question: str) -> str:
    """Ask a question and read one line."""
    print(question, end="", file=sys.stderr, flush=True)
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.removesuffix("\n")


def ask_yes_no(question: str) -> bool:
    """Ask a yes or no question. Enter means no."""
    while True:
        answer = ask_line(f"{question} (y/N): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Please answer y or n.", file=sys.stderr)
