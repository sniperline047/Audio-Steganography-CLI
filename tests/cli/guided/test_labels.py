"""Tests for audiosteg/cli/guided/labels.py."""

import pytest

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.cli.commands.reveal import KEYED_ALGORITHM
from audiosteg.cli.guided import explain_form, hide_form, reveal_form
from audiosteg.cli.guided.labels import algorithm_choice, algorithm_label, explain_choice

EVERY_MISSING = [(), ("no_library",), ("no_numpy",), ("no_library", "no_numpy")]


def use(request: pytest.FixtureRequest, fixtures: tuple[str, ...]) -> None:
    for fixture in fixtures:
        request.getfixturevalue(fixture)


@pytest.mark.parametrize("missing", EVERY_MISSING)
@pytest.mark.parametrize("key", ALGORITHMS)
def test_a_label_is_always_the_key_and_the_name(
    request: pytest.FixtureRequest, missing: tuple[str, ...], key: str
) -> None:
    use(request, missing)
    label = f"{key}: {ALGORITHMS[key].name}"
    assert algorithm_label(key) == algorithm_choice(key).title == explain_choice(key).title == label
    assert algorithm_choice(key).value == explain_choice(key).value == key


@pytest.mark.needs_signal
@pytest.mark.parametrize("key", ALGORITHMS)
def test_only_a_keyed_algorithm_needs_crypto_without_the_library(no_library: None, key: str) -> None:
    needs = "Needs [crypto]. " if key == "lsb_keyed" else ""
    assert algorithm_choice(key).description == f"{needs}{ALGORITHMS[key].explanation}"
    assert explain_choice(key).description == ALGORITHMS[key].explanation


@pytest.mark.parametrize("key", ALGORITHMS)
def test_only_an_algorithm_for_whole_blocks_needs_numpy_without_it(no_numpy: None, key: str) -> None:
    needs = "Needs NumPy. " if key == "echo" else ""
    assert explain_choice(key).description == f"{needs}{ALGORITHMS[key].explanation}"
    assert algorithm_choice(key).description.startswith(needs)


@pytest.mark.needs_signal
@pytest.mark.needs_crypto
@pytest.mark.parametrize("key", ALGORITHMS)
def test_every_hint_is_the_explanation_with_the_libraries(key: str) -> None:
    assert algorithm_choice(key).description == explain_choice(key).description == ALGORITHMS[key].explanation


def test_every_label_fits_in_80_columns_after_the_pointer() -> None:
    assert {key: algorithm_label(key) for key in ALGORITHMS if len(f" > {algorithm_label(key)}") >= 80} == {}


@pytest.mark.parametrize("missing", EVERY_MISSING)
def test_every_hint_fits_in_80_columns(request: pytest.FixtureRequest, missing: tuple[str, ...]) -> None:
    use(request, missing)
    hints = [
        choice.description for key in ALGORITHMS for choice in (algorithm_choice(key), explain_choice(key))
    ]
    assert {hint: len(hint) for hint in hints if len(f"  Description: {hint}") > 80} == {}


@pytest.mark.parametrize("missing", EVERY_MISSING)
def test_every_answered_line_fits_in_80_columns(
    request: pytest.FixtureRequest, missing: tuple[str, ...]
) -> None:
    use(request, missing)
    lines = [
        *(f"? {hide_form.ALGORITHM_QUESTION} {algorithm_choice(key).title}" for key in ALGORITHMS),
        *(f"? {explain_form.ALGORITHM_QUESTION} {explain_choice(key).title}" for key in ALGORITHMS),
        f"? {reveal_form.UNDETECTED_QUESTION} {algorithm_choice(KEYED_ALGORITHM).title}",
    ]
    assert {line: len(line) for line in lines if len(line) > 80} == {}
