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


def test_json_describes_an_algorithm(run: Any) -> None:
    result = json.loads(run("algorithms", "--json").output)
    assert (result["ok"], result["command"]) == (True, "algorithms")
    assert result["algorithms"][1] == {
        "key": "lsb_2",
        "name": ALGORITHMS["lsb_2"].name,
        "bits_per_byte": 2,
        "explanation": ALGORITHMS["lsb_2"].explanation,
        "samples_per_group": 1,
        "needs_passphrase": False,
        "reads_like": None,
        "frames_per_bit": None,
    }
    special = {
        known["key"]: (known["samples_per_group"], known["needs_passphrase"], known["reads_like"])
        for known in result["algorithms"][2:]
    }
    assert special == {
        "lsb_4": (1, False, None),
        "lsb_matching": (1, False, "lsb"),
        "lsb_parity": (8, False, None),
        "lsb_keyed": (1, True, None),
        "echo": (1024, False, None),
    }
    assert [known["frames_per_bit"] for known in result["algorithms"]] == [None] * 6 + [1024]
    assert all(known.keys() == {"key", "name", "bits_per_byte", "explanation"} for known in result["legacy"])
