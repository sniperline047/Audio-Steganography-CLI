"""Tests for audiosteg/cli/guided/labels.py."""

import pytest

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.guided.labels import algorithm_label

MISSING = " (needs encryption, which is not available here)"


@pytest.mark.parametrize("key", ALGORITHMS)
def test_only_a_keyed_algorithm_is_marked_without_the_library(no_library: None, key: str) -> None:
    missing = MISSING if key == "lsb_keyed" else ""
    assert algorithm_label(key) == f"{key}{missing}: {ALGORITHMS[key].explanation}"


@pytest.mark.needs_crypto
@pytest.mark.parametrize("key", ALGORITHMS)
def test_nothing_is_marked_with_the_library(key: str) -> None:
    assert algorithm_label(key) == f"{key}: {ALGORITHMS[key].explanation}"
