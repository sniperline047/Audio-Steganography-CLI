"""Tests for audiosteg/cli/guided/labels.py."""

import pytest

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS
from audiosteg.cli.guided.labels import algorithm_label, explain_label, old_label

MISSING = " (cannot encrypt here)"


@pytest.mark.needs_signal
@pytest.mark.parametrize("key", ALGORITHMS)
def test_only_a_keyed_algorithm_is_marked_without_the_library(no_library: None, key: str) -> None:
    missing = MISSING if key == "lsb_keyed" else ""
    assert algorithm_label(key) == f"{key}{missing}: {ALGORITHMS[key].explanation}"


@pytest.mark.parametrize("key", ALGORITHMS)
def test_only_an_algorithm_for_whole_blocks_is_marked_without_numpy(no_numpy: None, key: str) -> None:
    missing = " (needs NumPy)" if key == "echo" else ""
    assert explain_label(key) == f"{key}{missing}: {ALGORITHMS[key].explanation}"
    assert missing in algorithm_label(key)


@pytest.mark.needs_signal
@pytest.mark.needs_crypto
@pytest.mark.parametrize("key", ALGORITHMS)
def test_nothing_is_marked_with_the_library(key: str) -> None:
    assert algorithm_label(key) == f"{key}: {ALGORITHMS[key].explanation}"


def test_every_label_fits_in_80_columns_after_the_pointer(no_library: None, no_numpy: None) -> None:
    labels = [*map(algorithm_label, ALGORITHMS), *map(old_label, LEGACY_ALGORITHMS)]
    assert {label: len(label) for label in labels if len(f" > {label}") >= 80} == {}
