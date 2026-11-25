"""Tests for audiosteg/core/signal_algorithm.py."""

import sys
from types import ModuleType
from typing import Any

import pytest

from audiosteg.algorithms.echo import ECHO
from audiosteg.algorithms.lsb import LSB
from audiosteg.core.signal_algorithm import SignalAlgorithm, check_library, has_numpy, load_numpy
from audiosteg.errors import MissingLibraryError


def test_numpy_that_is_missing_is_explained(no_numpy: None) -> None:
    with pytest.raises(MissingLibraryError, match=r'pip install "\.\[signal\]"') as caught:
        load_numpy()
    assert caught.value.__notes__ == ["Without it, the other algorithms can be used."]
    assert not has_numpy()
    with pytest.raises(MissingLibraryError):
        check_library(ECHO)
    check_library(LSB)


def test_numpy_that_is_broken_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def find_spec(self, name: str, path: Any, target: ModuleType | None = None) -> None:
            if name == "numpy":
                raise ImportError("DLL load failed")

    monkeypatch.delitem(sys.modules, "numpy", raising=False)
    monkeypatch.setattr(sys, "meta_path", [Broken(), *sys.meta_path])
    assert not has_numpy()


@pytest.mark.needs_signal
def test_numpy_that_is_there_is_used() -> None:
    assert load_numpy().__name__ == "numpy"
    assert has_numpy()
    check_library(ECHO)


def test_what_every_algorithm_for_blocks_has_in_common_with_the_others() -> None:
    assert (ECHO.keyed, ECHO.detectable, ECHO.reads_like) == (False, True, None)
    assert (ECHO.bits_per_byte, ECHO.samples_per_group) == (1, ECHO.block_frames)


@pytest.mark.parametrize(
    ("frames", "container"),
    [(0, 0), (42 * 8 * 1024, 0), (43 * 8 * 1024 - 1, 0), (43 * 8 * 1024, 11), (46 * 8 * 1024, 14)],
)
def test_the_frames_that_a_container_needs(frames: int, container: int) -> None:
    assert ECHO.largest_container(frames) == container
    if container:
        assert ECHO.needed_frames(container) == frames


def test_a_description_without_functions_cannot_be_used() -> None:
    with pytest.raises(TypeError, match="abstract"):
        SignalAlgorithm("Test", 1, 0, 0, (1.0,))  # type: ignore[abstract]


@pytest.mark.needs_signal
def test_the_larger_sign_decides_the_bit() -> None:
    import numpy as np

    class Signs(SignalAlgorithm):
        def make_change(self, sound: Any, first_frame: int, bits: Any) -> Any:
            return sound

        def find_signs(self, blocks: Any) -> Any:
            return blocks

    signs = Signs("Test", 2, 0, 5, (1.0,))
    assert signs.read_bits(np.array([[1.0, 2.0], [2.0, 1.0], [0.0, 0.0], [-2.0, -1.0]])) == [1, 0, 0, 1]
    assert signs.read_bits(np.zeros((0, 2))) == []
    assert signs.changed_frames(3) == 11
