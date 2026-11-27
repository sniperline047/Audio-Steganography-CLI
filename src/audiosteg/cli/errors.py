"""Errors of the command line, and plain explanations of every error."""

import re

from audiosteg.errors import (
    MissingLibraryError,
    NoMessageError,
    PassphraseRequiredError,
    StegoError,
    UnsuitableAudioError,
)


class UsageError(Exception):
    """The command line is wrong."""


class CancelledError(Exception):
    """The person decided not to continue."""


class PlayerError(StegoError):
    """Sound cannot be played."""


class OutputClosedError(Exception):
    """Nobody can see the program's output anymore."""


def error_type(error: BaseException) -> str:
    """Return the stable name of an error for JSON output."""
    if isinstance(error, (StegoError, UsageError, CancelledError, OutputClosedError)):
        name = re.sub("(?<!^)(?=[A-Z])", "_", type(error).__name__).lower()
        return name.removesuffix("_error")
    if isinstance(error, KeyboardInterrupt):
        return "interrupted"
    if isinstance(error, EOFError):
        return "input_ended"
    if isinstance(error, MemoryError):
        return "out_of_memory"
    if isinstance(error, FileNotFoundError):
        return "file_not_found"
    if isinstance(error, FileExistsError):
        return "file_exists"
    return "file" if isinstance(error, OSError) else "invalid_value"


def explain_file_error(error: OSError) -> str:
    """Explain a problem with a file."""
    name = error.filename2 or error.filename
    if name == "":
        return "The path is empty."
    if error.errno is None or name is None:
        return error.strerror or str(error)
    if isinstance(error, FileNotFoundError):
        return f"The file or folder does not exist: {name}. Check the spelling and the current folder."
    if isinstance(error, FileExistsError):
        return f"The file already exists: {name}"
    if isinstance(error, PermissionError):
        return f"Permission was denied: {name}. Check who may use this file or folder."
    if isinstance(error, IsADirectoryError):
        return f"This is a folder, not a file: {name}. Give the path of a file."
    return f"{error.strerror}: {name}"


def explain(error: BaseException) -> str:
    """Explain an error in plain English. Passphrases and messages never appear in it."""
    if isinstance(error, KeyboardInterrupt):
        return "Interrupted."
    if isinstance(error, EOFError):
        return "The input ended before the operation finished."
    if isinstance(error, MemoryError):
        return "There is not enough memory for this operation."
    if isinstance(error, OSError):
        return explain_file_error(error)
    return str(error)


NO_MESSAGE_HINT = "Check that this is the file that hide made, and that it was not converted or edited."


def next_step(error: BaseException) -> str | None:
    """Say what to do about an error of a command, if the error does not say so itself. Notes come first."""
    notes = getattr(error, "__notes__", None)
    if notes:
        return " ".join(notes)
    if isinstance(error, UsageError):
        return "To see how a command is used, add --help."
    if isinstance(error, FileExistsError):
        return "Add --force to replace it, or choose another file with -o."
    if isinstance(error, PassphraseRequiredError):
        return "Run the command in a terminal, or use --passphrase_file."
    if isinstance(error, NoMessageError):
        return NO_MESSAGE_HINT
    if isinstance(error, UnsuitableAudioError):
        return "Use another audio file, or an algorithm that works with every sound, such as lsb."
    if isinstance(error, MissingLibraryError):
        return "Without it, only messages that are not encrypted can be used."
    return None
