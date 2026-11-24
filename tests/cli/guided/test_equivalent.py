"""Tests for audiosteg/cli/guided/equivalent.py."""

import ntpath
import os
import shlex
from types import SimpleNamespace

import pytest

from audiosteg.cli.guided import equivalent
from audiosteg.cli.guided.equivalent import command_line, path_word


@pytest.mark.parametrize(
    ("words", "shown"),
    [
        (("audiosteg", "reveal", "a.wav"), "audiosteg reveal a.wav"),
        (("audiosteg", "reveal", "a\x1b[2J.wav"), None),
        (("audiosteg", "reveal", "a\u202e.wav"), None),
        (("audiosteg", "reveal", "a\nb.wav"), None),
    ],
)
def test_only_commands_that_can_be_shown_are_shown(words: tuple[str, ...], shown: str | None) -> None:
    assert command_line(*words) == shown


@pytest.mark.skipif(os.name == "nt", reason="Windows has other rules")
@pytest.mark.parametrize("name", ["my song's.wav", '$(x) `y` "z" !', "a;b&c|d>e.wav", "*?[].wav", "~é 🎵"])
def test_a_shell_changes_nothing(name: str) -> None:
    shown = command_line("audiosteg", "reveal", name)
    assert shown is not None
    assert shlex.split(shown) == ["audiosteg", "reveal", name]


@pytest.mark.parametrize(
    ("path", "shown"),
    [
        (r"C:\My Music\song-1_b.wav", r'audiosteg reveal "C:\My Music\song-1_b.wav"'),
        ("a/é.wav", "audiosteg reveal a/é.wav"),
        *((f"a{character}b.wav", None) for character in "%!^&|<>()$`'\",;=*?[]{}@#~+\u2019\u201c\t\u00a0"),
    ],
)
def test_windows_shows_only_characters_that_every_shell_leaves_alone(
    monkeypatch: pytest.MonkeyPatch, path: str, shown: str | None
) -> None:
    monkeypatch.setattr(equivalent, "os", SimpleNamespace(name="nt", path=ntpath))
    assert command_line("audiosteg", "reveal", path) == shown


@pytest.mark.parametrize("path", ["-p", "--json", "sample"])
def test_a_path_is_never_an_option_or_the_sample(path: str) -> None:
    assert path_word(path) == os.path.join(".", path)


@pytest.mark.parametrize("path", ["sample.wav", "a/sample", "a-b", "/x"])
def test_other_paths_stay_as_they_are(path: str) -> None:
    assert path_word(path) == path
