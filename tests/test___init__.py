"""Tests for audiosteg/__init__.py and the files that are installed with it."""

import inspect
import subprocess
import sys
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
        "Algorithm", "CapacityError", "DamagedMessageError", "InvalidMessageError",
        "MissingLibraryError", "NoMessageError", "NotEncryptedError", "PassphraseRequiredError",
        "StegoError", "UnsafeOutputError", "UnsuitableAudioError", "UnsupportedFormatError",
        "WrongPassphraseError", "decode", "encode",
    }  # fmt: skip


def test_every_public_error_can_be_caught_as_one_type() -> None:
    errors = [getattr(audiosteg, name) for name in audiosteg.__all__ if name.endswith("Error")]
    assert all(issubclass(error, audiosteg.StegoError) for error in errors)


def test_the_public_functions_keep_their_arguments() -> None:
    encode = inspect.signature(audiosteg.encode).parameters
    assert list(encode) == ["input_path", "output_path", "message", "algorithm", "passphrase", "overwrite"]
    assert encode["overwrite"].kind is inspect.Parameter.KEYWORD_ONLY
    assert encode["overwrite"].default is False
    assert encode["passphrase"].kind is inspect.Parameter.KEYWORD_ONLY
    assert encode["passphrase"].default is None
    decode = inspect.signature(audiosteg.decode).parameters
    assert list(decode) == ["path", "algorithm", "passphrase"]
    assert decode["algorithm"].default is None
    assert decode["passphrase"].kind is inspect.Parameter.KEYWORD_ONLY
    assert decode["passphrase"].default is None


def test_importing_the_package_does_not_import_the_libraries_of_the_command_line() -> None:
    code = (
        "import audiosteg, sys; "
        "assert not {'rich', 'questionary', 'prompt_toolkit', 'numpy'} & sys.modules.keys(); "
        "import audiosteg.cli.main; "
        "assert not {'questionary', 'prompt_toolkit', 'numpy'} & sys.modules.keys()"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=60)


def test_type_checkers_can_use_the_package() -> None:
    assert (Path(audiosteg.__file__).parent / "py.typed").is_file()


def test_the_tested_package_is_not_an_old_copy() -> None:
    installed = package_files(Path(audiosteg.__file__).parent)
    source = package_files(PROJECT_ROOT / "src" / "audiosteg")
    changed = {name for name in installed.keys() | source.keys() if installed.get(name) != source.get(name)}
    if changed:
        pytest.fail(f"the installed package is out of date, install it again: {sorted(changed)}")
