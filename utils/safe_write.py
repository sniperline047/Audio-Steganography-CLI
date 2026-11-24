"""Write files in one step, so a failure never leaves a partial result."""

import errno
import os
import secrets
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO

from utils.output_path import check_output_path, find_file

HARD_LINK_UNSUPPORTED = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EMLINK}


def private_opener(path: str, flags: int) -> int:
    """Create a file that only its owner can read."""
    return os.open(path, flags, 0o600)


def final_mode(path: Path) -> int:
    """Return the existing file's permissions, or the normal permissions for a new file."""
    existing = find_file(str(path))
    if existing is not None:
        return stat.S_IMODE(existing.st_mode) & 0o777
    umask = os.umask(0o077)
    os.umask(umask)
    return 0o666 & ~umask


def copy_to_new_file(source: Path, target: Path) -> None:
    """Copy a file, refusing to replace anything that already exists."""
    with open(target, "xb") as destination:
        try:
            with open(source, "rb") as original:
                shutil.copyfileobj(original, destination)
            destination.flush()
            os.fsync(destination.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise


def move_to_new_file(source: Path, target: Path) -> None:
    """Move a file, refusing to replace anything that already exists."""
    if os.name == "nt":
        os.rename(source, target)
        return
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno not in HARD_LINK_UNSUPPORTED:
            raise
        copy_to_new_file(source, target)
    source.unlink()


@contextmanager
def create_parent_folders(target: Path) -> Iterator[None]:
    """Create missing parent folders and remove them again if the body fails."""
    missing = [folder for folder in target.parents if not folder.exists()]
    created: list[Path] = []
    try:
        for folder in reversed(missing):
            folder.mkdir()
            created.append(folder)
        yield
    except BaseException:
        for folder in reversed(created):
            with suppress(OSError):
                folder.rmdir()
        raise


@contextmanager
def safe_output(input_path: str, output_path: str, overwrite: bool) -> Iterator[BinaryIO]:
    """
    Open a temporary file and move it to a normalized output path when the body succeeds.

    :param input_path: Path to the input file, which must not be replaced
    :param output_path: Path from normalize_output_path
    :param overwrite: Whether an existing output file may be replaced
    """
    target = Path(output_path)
    temporary = target.parent / f".stego_{secrets.token_hex(8)}.tmp"
    with create_parent_folders(target):
        try:
            with open(temporary, "xb", opener=private_opener) as destination:
                yield destination
                destination.flush()
                os.fsync(destination.fileno())
            check_output_path(input_path, output_path, overwrite)
            os.chmod(temporary, final_mode(target))
            if overwrite:
                os.replace(temporary, target)
            else:
                move_to_new_file(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
