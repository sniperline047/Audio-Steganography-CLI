"""Tests for audiosteg/utils/output_path.py."""

import os
from pathlib import Path

import pytest

from audiosteg.errors import UnsafeOutputError
from audiosteg.utils.output_path import check_output_path, check_windows_path, normalize_output_path


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """Create an input file."""
    path = tmp_path / "input.wav"
    path.write_bytes(b"input")
    return path


def make_symlink(link: Path, target: Path) -> None:
    """Create a symbolic link, or skip the test where the system does not allow it."""
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("this system does not allow symbolic links")


@pytest.mark.parametrize(
    "path",
    [
        "CON", "nul", "folder/aux.wav", "C:\\folder\\COM1.tar.gz", "LPT9 .wav", "com¹.wav", "CONIN$",
        "conout$", "prn/file.wav", "file.wav.", "file.wav ", "folder./file.wav", "folder \\file.wav",
        "file.wav:stream", "folder/file.wav::$DATA", "C:CON", "...",
    ],
)  # fmt: skip
def test_windows_paths_that_would_become_another_file_are_refused(path: str) -> None:
    with pytest.raises(UnsafeOutputError):
        check_windows_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "C:\\folder\\file.wav", "folder/file.wav", "..\\file.wav", ".\\file.wav", "\\\\server\\share\\a.wav",
        "console.wav", "com10.wav", "com0.wav", "my.nul.wav", " leading.wav", "a b.wav", "folder\\",
    ],
)  # fmt: skip
def test_normal_windows_paths_are_allowed(path: str) -> None:
    check_windows_path(path)


@pytest.mark.skipif(os.name != "nt", reason="these names are only special on Windows")
def test_windows_names_are_checked_on_windows(tmp_path: Path) -> None:
    with pytest.raises(UnsafeOutputError, match="device"):
        normalize_output_path(str(tmp_path / "NUL"))


@pytest.mark.skipif(os.name == "nt", reason="these names are special on Windows")
def test_windows_names_are_ordinary_elsewhere(tmp_path: Path) -> None:
    path = os.path.join(os.path.realpath(tmp_path), "NUL")
    assert normalize_output_path(path) == path


@pytest.mark.parametrize("path", ["", "a\0.wav"])
def test_paths_that_name_no_file_are_refused(path: str) -> None:
    with pytest.raises(UnsafeOutputError):
        normalize_output_path(path)


@pytest.mark.parametrize("ending", ["/", "/.", "/..", "//"])
def test_a_path_that_ends_like_a_folder_is_refused(source: Path, ending: str) -> None:
    with pytest.raises(UnsafeOutputError):
        normalize_output_path(f"{source}{ending}")
    with pytest.raises(UnsafeOutputError):
        normalize_output_path(ending)


@pytest.mark.parametrize("ending", ["/", "/."])
def test_a_folder_path_that_does_not_exist_is_refused(tmp_path: Path, ending: str) -> None:
    with pytest.raises(UnsafeOutputError):
        normalize_output_path(f"{tmp_path}/new_folder{ending}")


def test_a_relative_path_becomes_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    folder = os.path.realpath(tmp_path)
    assert normalize_output_path("out.wav") == os.path.join(folder, "out.wav")
    assert normalize_output_path("a/../b/out.wav") == os.path.join(folder, "b", "out.wav")


def test_linked_folders_are_followed_but_the_file_name_is_not(tmp_path: Path, source: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    make_symlink(tmp_path / "linked", folder)
    make_symlink(folder / "link.wav", source)
    expected = os.path.join(os.path.realpath(folder), "link.wav")
    assert normalize_output_path(str(tmp_path / "linked" / "link.wav")) == expected


@pytest.mark.parametrize("overwrite", [False, True])
def test_a_free_path_is_accepted(tmp_path: Path, source: Path, overwrite: bool) -> None:
    check_output_path(str(source), str(tmp_path / "new.wav"), overwrite)


@pytest.mark.parametrize("overwrite", [False, True])
def test_the_input_file_itself_is_refused(source: Path, overwrite: bool) -> None:
    with pytest.raises(UnsafeOutputError, match="different files"):
        check_output_path(str(source), str(source), overwrite)


def test_a_hard_link_to_the_input_is_refused(tmp_path: Path, source: Path) -> None:
    link = tmp_path / "hard_link.wav"
    try:
        os.link(source, link)
    except OSError:
        pytest.skip("this file system has no hard links")
    with pytest.raises(UnsafeOutputError, match="different files"):
        check_output_path(str(source), str(link), overwrite=True)


@pytest.mark.parametrize("target", ["input.wav", "other.wav", "missing.wav"])
def test_symbolic_links_are_refused_even_when_dangling(tmp_path: Path, source: Path, target: str) -> None:
    (tmp_path / "other.wav").write_bytes(b"other")
    link = tmp_path / "link.wav"
    make_symlink(link, tmp_path / target)
    with pytest.raises(UnsafeOutputError, match="symbolic link"):
        check_output_path(str(source), str(link), overwrite=True)


def test_a_folder_is_refused(tmp_path: Path, source: Path) -> None:
    with pytest.raises(UnsafeOutputError, match="not a regular file"):
        check_output_path(str(source), str(tmp_path), overwrite=True)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="this system has no named pipes")
def test_a_named_pipe_is_refused(tmp_path: Path, source: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(UnsafeOutputError, match="not a regular file"):
        check_output_path(str(source), str(tmp_path / "pipe"), overwrite=True)


def test_an_existing_file_needs_permission_to_overwrite(tmp_path: Path, source: Path) -> None:
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        check_output_path(str(source), str(existing), overwrite=False)
    check_output_path(str(source), str(existing), overwrite=True)


def test_a_read_only_file_is_not_replaced(tmp_path: Path, source: Path) -> None:
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"old")
    existing.chmod(0o444)
    if os.access(existing, os.W_OK):
        pytest.skip("this user may write to read-only files")
    try:
        with pytest.raises(PermissionError):
            check_output_path(str(source), str(existing), overwrite=True)
    finally:
        existing.chmod(0o644)
