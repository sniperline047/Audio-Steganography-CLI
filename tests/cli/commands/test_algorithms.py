"""Tests for audiosteg/cli/commands/algorithms.py."""

import json
from typing import Any

from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS


def test_every_algorithm_is_listed_in_order(run: Any) -> None:
    result = run("algorithms")
    assert (result.code, result.errors) == (0, "")
    lines = [
        f"{key}: {known.explanation}" for key, known in [*ALGORITHMS.items(), *LEGACY_ALGORITHMS.items()]
    ]
    assert [line for line in result.output.splitlines() if line in lines] == lines


def test_json_lists_every_algorithm(run: Any) -> None:
    result = json.loads(run("algorithms", "--json").output)
    assert [algorithm["key"] for algorithm in result["algorithms"]] == list(ALGORITHMS)
    assert [algorithm["key"] for algorithm in result["legacy"]] == list(LEGACY_ALGORITHMS)
