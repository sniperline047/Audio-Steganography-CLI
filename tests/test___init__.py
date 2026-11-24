"""Tests for audiosteg/__init__.py and the files that are installed with it."""

import inspect
from pathlib import Path

import pytest

import audiosteg

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def package_files(folder: Path) -> dict[str, bytes]:
    """Read the code of a package."""
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.suffix in (".py", ".typed")
    }


def test_the_public_names() -> None:
    namespace: dict[str, object] = {}
    exec("from audiosteg import *", namespace)
    assert namespace.keys() - {"__builtins__"} == {
        "Algorithm", "CapacityError", "InvalidMessageError", "NoMessageError", "StegoError",
        "UnsafeOutputError", "UnsupportedFormatError", "decode", "encode",
    }  # fmt: skip


def test_every_public_error_can_be_caught_as_one_type() -> None:
    errors = [getattr(audiosteg, name) for name in audiosteg.__all__ if name.endswith("Error")]
    assert all(issubclass(error, audiosteg.StegoError) for error in errors)


def test_the_public_functions_keep_their_arguments() -> None:
    encode = inspect.signature(audiosteg.encode).parameters
    assert list(encode) == ["input_path", "output_path", "message", "algorithm", "overwrite"]
    assert encode["overwrite"].kind is inspect.Parameter.KEYWORD_ONLY
    assert encode["overwrite"].default is False
    assert list(inspect.signature(audiosteg.decode).parameters) == ["path", "algorithm"]


def test_type_checkers_can_use_the_package() -> None:
    assert (Path(audiosteg.__file__).parent / "py.typed").is_file()


def test_the_tested_package_is_not_an_old_copy() -> None:
    installed = package_files(Path(audiosteg.__file__).parent)
    source = package_files(PROJECT_ROOT / "src" / "audiosteg")
    changed = {name for name in installed.keys() | source.keys() if installed.get(name) != source.get(name)}
    if changed:
        pytest.fail(f"the installed package is out of date, install it again: {sorted(changed)}")
