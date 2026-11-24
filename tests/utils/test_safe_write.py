"""Tests for audiosteg/utils/safe_write.py."""

import errno
import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg.errors import UnsafeOutputError
from audiosteg.utils.safe_write import safe_output

posix_only = pytest.mark.skipif(os.name == "nt", reason="Windows has no POSIX permissions or umask")
hard_links_used = pytest.mark.skipif(os.name == "nt", reason="Windows renames instead of linking")


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """Create a folder with an input file and an older output file."""
    resolved = tmp_path.resolve()
    (resolved / "input.wav").write_bytes(b"input")
    (resolved / "old.wav").write_bytes(b"old")
    return resolved


def save(folder: Path, name: str, overwrite: bool, before_end: Callable[[], object] = lambda: None) -> None:
    """Write new content, then run an action before the file is moved into place."""
    with safe_output(str(folder / "input.wav"), str(folder / name), overwrite) as destination:
        destination.write(b"new")
        before_end()


def contents(folder: Path) -> dict[str, bytes | None]:
    """Describe every file and folder."""
    return {
        path.relative_to(folder).as_posix(): path.read_bytes() if path.is_file() else None
        for path in folder.rglob("*")
    }


def fail(*arguments: Any, **options: Any) -> None:
    raise OSError(errno.ENOSPC, "No space left on device")


def interrupt(*arguments: Any, **options: Any) -> None:
    raise KeyboardInterrupt


def test_a_new_file_is_created_with_missing_folders(folder: Path) -> None:
    save(folder, "a/b/new.wav", overwrite=False)
    assert contents(folder) == {
        "input.wav": b"input", "old.wav": b"old", "a": None, "a/b": None, "a/b/new.wav": b"new",
    }  # fmt: skip


def test_an_existing_file_is_replaced_only_when_allowed(folder: Path) -> None:
    with pytest.raises(FileExistsError):
        save(folder, "old.wav", overwrite=False)
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"old"}
    save(folder, "old.wav", overwrite=True)
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"new"}


def test_the_old_file_stays_readable_until_the_new_one_is_complete(folder: Path) -> None:
    seen: list[bytes] = []
    save(folder, "old.wav", True, lambda: seen.append((folder / "old.wav").read_bytes()))
    assert seen == [b"old"]


@pytest.mark.parametrize("error", [fail, interrupt])
@pytest.mark.parametrize("name", ["old.wav", "a/b/new.wav"])
def test_a_failed_write_leaves_everything_as_it_was(
    folder: Path, name: str, error: Callable[..., None]
) -> None:
    before = contents(folder)
    with pytest.raises((OSError, KeyboardInterrupt)):
        save(folder, name, True, error)
    assert contents(folder) == before


@pytest.mark.parametrize("error", [fail, interrupt])
@pytest.mark.parametrize("function", ["fsync", "chmod", "replace"])
@pytest.mark.parametrize("name", ["old.wav", "a/b/new.wav"])
def test_a_failed_step_leaves_everything_as_it_was(
    folder: Path, monkeypatch: pytest.MonkeyPatch, name: str, function: str, error: Callable[..., None]
) -> None:
    before = contents(folder)
    monkeypatch.setattr(os, function, error)
    with pytest.raises((OSError, KeyboardInterrupt)):
        save(folder, name, overwrite=True)
    assert contents(folder) == before


@pytest.mark.parametrize("overwrite", [False, True])
def test_data_reaches_the_disk_before_the_file_appears(
    folder: Path, monkeypatch: pytest.MonkeyPatch, overwrite: bool
) -> None:
    synced: list[tuple[int, bool]] = []
    real_fsync = os.fsync

    def record(descriptor: int) -> None:
        real_fsync(descriptor)
        synced.append((os.fstat(descriptor).st_size, (folder / "new.wav").exists()))

    monkeypatch.setattr(os, "fsync", record)
    save(folder, "new.wav", overwrite)
    assert synced == [(3, False)]


@pytest.mark.parametrize("failure", [fail, interrupt])
def test_a_failed_move_of_a_new_file_leaves_nothing(
    folder: Path, monkeypatch: pytest.MonkeyPatch, failure: Callable[..., None]
) -> None:
    before = contents(folder)
    monkeypatch.setattr(os, "rename" if os.name == "nt" else "link", failure)
    with pytest.raises((OSError, KeyboardInterrupt)):
        save(folder, "a/new.wav", overwrite=False)
    assert contents(folder) == before


def test_folders_that_already_existed_or_are_in_use_are_kept(folder: Path) -> None:
    (folder / "kept").mkdir()

    def add_file_then_fail() -> None:
        (folder / "kept" / "made" / "theirs.txt").write_bytes(b"theirs")
        fail()

    with pytest.raises(OSError):
        save(folder, "kept/empty/new.wav", False, fail)
    assert (folder / "kept").is_dir() and not (folder / "kept" / "empty").exists()
    with pytest.raises(OSError) as caught:
        save(folder, "kept/made/new.wav", False, add_file_then_fail)
    assert caught.value.errno == errno.ENOSPC
    assert contents(folder / "kept") == {"made": None, "made/theirs.txt": b"theirs"}


def test_a_file_that_appears_during_the_write_is_kept(folder: Path) -> None:
    with pytest.raises(FileExistsError):
        save(folder, "new.wav", False, lambda: (folder / "new.wav").write_bytes(b"theirs"))
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"old", "new.wav": b"theirs"}


def test_a_file_that_appears_after_the_last_check_is_kept(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_chmod = os.chmod

    def chmod_while_a_file_appears(path: Path, mode: int) -> None:
        real_chmod(path, mode)
        (folder / "new.wav").write_bytes(b"theirs")

    monkeypatch.setattr(os, "chmod", chmod_while_a_file_appears)
    with pytest.raises(FileExistsError):
        save(folder, "new.wav", overwrite=False)
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"old", "new.wav": b"theirs"}


def test_an_output_that_becomes_the_input_during_the_write_is_kept(folder: Path) -> None:
    def link_output_to_input() -> None:
        try:
            os.link(folder / "input.wav", folder / "new.wav")
        except OSError:
            pytest.skip("this file system has no hard links")

    with pytest.raises(UnsafeOutputError):
        save(folder, "new.wav", True, link_output_to_input)
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"old", "new.wav": b"input"}


@hard_links_used
@pytest.mark.parametrize("code", [errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EMLINK])
def test_a_new_file_is_copied_where_hard_links_are_not_supported(
    folder: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def refuse_link(*arguments: Any) -> None:
        raise OSError(code, "hard links are not supported")

    monkeypatch.setattr(os, "link", refuse_link)
    save(folder, "new.wav", overwrite=False)
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"old", "new.wav": b"new"}


@hard_links_used
@pytest.mark.parametrize("failure", [fail, interrupt])
def test_a_failed_copy_leaves_nothing(
    folder: Path, monkeypatch: pytest.MonkeyPatch, failure: Callable[..., None]
) -> None:
    def refuse_link(*arguments: Any) -> None:
        raise OSError(errno.ENOTSUP, "hard links are not supported")

    before = contents(folder)
    monkeypatch.setattr(os, "link", refuse_link)
    monkeypatch.setattr(shutil, "copyfileobj", failure)
    with pytest.raises((OSError, KeyboardInterrupt)):
        save(folder, "new.wav", overwrite=False)
    assert contents(folder) == before


@hard_links_used
def test_a_copy_that_cannot_reach_the_disk_leaves_nothing(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync
    synced: list[int] = []

    def refuse_link(*arguments: Any) -> None:
        raise OSError(errno.ENOTSUP, "hard links are not supported")

    def fail_the_second_time(descriptor: int) -> None:
        synced.append(descriptor)
        if len(synced) == 2:
            fail()
        real_fsync(descriptor)

    before = contents(folder)
    monkeypatch.setattr(os, "link", refuse_link)
    monkeypatch.setattr(os, "fsync", fail_the_second_time)
    with pytest.raises(OSError):
        save(folder, "new.wav", overwrite=False)
    assert contents(folder) == before


@hard_links_used
def test_the_copy_does_not_replace_a_file_that_just_appeared(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse_link_while_a_file_appears(*arguments: Any) -> None:
        (folder / "new.wav").write_bytes(b"theirs")
        raise OSError(errno.ENOTSUP, "hard links are not supported")

    monkeypatch.setattr(os, "link", refuse_link_while_a_file_appears)
    with pytest.raises(FileExistsError):
        save(folder, "new.wav", overwrite=False)
    assert contents(folder) == {"input.wav": b"input", "old.wav": b"old", "new.wav": b"theirs"}


@posix_only
def test_the_unfinished_file_is_private(folder: Path) -> None:
    modes: list[int] = []

    def record_mode() -> None:
        modes.extend(stat.S_IMODE(path.stat().st_mode) for path in folder.glob(".stego_*"))

    old_umask = os.umask(0)
    try:
        save(folder, "new.wav", False, record_mode)
    finally:
        os.umask(old_umask)
    assert modes == [0o600]


@posix_only
@pytest.mark.parametrize(("umask", "mode"), [(0o022, 0o644), (0o077, 0o600), (0o002, 0o664)])
def test_a_new_file_follows_the_umask_and_leaves_it_unchanged(folder: Path, umask: int, mode: int) -> None:
    old_umask = os.umask(umask)
    try:
        save(folder, "new.wav", overwrite=False)
    finally:
        umask_after = os.umask(old_umask)
    assert stat.S_IMODE((folder / "new.wav").stat().st_mode) == mode
    assert umask_after == umask


@posix_only
@pytest.mark.parametrize(("before", "after"), [(0o640, 0o640), (0o666, 0o666), (0o4755, 0o755)])
def test_a_replaced_file_keeps_its_permissions_without_special_bits(
    folder: Path, before: int, after: int
) -> None:
    (folder / "old.wav").chmod(before)
    save(folder, "old.wav", overwrite=True)
    assert stat.S_IMODE((folder / "old.wav").stat().st_mode) == after


def test_a_missing_folder_below_a_file_is_an_error(folder: Path) -> None:
    before = contents(folder)
    with pytest.raises(OSError):
        save(folder, "old.wav/new.wav", overwrite=False)
    assert contents(folder) == before
