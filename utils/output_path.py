"""Check output paths so that no other file can be damaged."""

import ntpath
import os
import stat

from utils.errors import UnsafeOutputError

WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{port}{number}" for port in ("COM", "LPT") for number in "123456789¹²³"
}


def check_windows_path(path: str) -> None:
    """Refuse names that Windows would silently turn into a different file."""
    path_without_drive = ntpath.splitdrive(path)[1]
    for name in path_without_drive.replace("/", "\\").split("\\"):
        if name in ("", ".", ".."):
            continue
        if ":" in name or name.endswith((".", " ")):
            raise UnsafeOutputError(f"The output path is not allowed on Windows: {path}")
        if name.split(".")[0].rstrip().upper() in WINDOWS_DEVICES:
            raise UnsafeOutputError(f"The output path is a Windows device name: {path}")


def normalize_output_path(path: str) -> str:
    """
    Return one absolute path to use for every check, prompt, and write.

    Links in the parent folders are followed. The file name itself is kept, so
    a symbolic link there can still be refused.
    """
    if not path:
        raise UnsafeOutputError("The output path is empty.")
    if "\0" in path:
        raise UnsafeOutputError("The output path contains a null character.")
    if os.name == "nt":
        check_windows_path(path)
    folder, name = os.path.split(path)
    if name in ("", ".", ".."):
        raise UnsafeOutputError(f"The output path is a folder, not a file: {path}")
    return os.path.join(os.path.realpath(folder), name)


def find_file(path: str) -> os.stat_result | None:
    """Describe what is at a path without following a link, or return None if nothing is."""
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def check_output_path(input_path: str, output_path: str, overwrite: bool) -> None:
    """Refuse a normalized output path that could damage the input or another existing file."""
    existing = find_file(output_path)
    if existing is None:
        return
    if stat.S_ISLNK(existing.st_mode):
        raise UnsafeOutputError(f"The output path is a symbolic link: {output_path}")
    if os.path.samefile(input_path, output_path):
        raise UnsafeOutputError("The input and output must be different files.")
    if not stat.S_ISREG(existing.st_mode):
        raise UnsafeOutputError(f"The output path is not a regular file: {output_path}")
    if not overwrite:
        raise FileExistsError(f"The output file already exists: {output_path}")
    if not os.access(output_path, os.W_OK):
        raise PermissionError(f"The output file is read-only: {output_path}")
