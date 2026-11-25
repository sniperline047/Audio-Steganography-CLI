"""Tests for audiosteg/algorithms/registry.py."""

import re
from collections.abc import Callable
from itertools import product
from pathlib import Path
from typing import Any

import pytest
from conftest import EVERY_KEY, PLAIN_KEYS, needed_passphrase, noise_for

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms.echo import ECHO
from audiosteg.algorithms.legacy import BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_four import LSB_4
from audiosteg.algorithms.lsb_keyed import LSB_KEYED
from audiosteg.algorithms.lsb_matching import LSB_MATCHING
from audiosteg.algorithms.lsb_parity import LSB_PARITY
from audiosteg.algorithms.registry import ALGORITHMS, LEGACY_ALGORITHMS, reading_key
from audiosteg.analysis.inspection import inspect as look_at

every_byte_algorithm = pytest.mark.parametrize(
    "algorithm",
    [known for known in ALGORITHMS.values() if isinstance(known, Algorithm)],
    ids=lambda algorithm: algorithm.name,
)


def test_the_documented_names_and_the_order_of_detection_do_not_change() -> None:
    assert list(ALGORITHMS.items()) == [
        ("lsb", LSB),
        ("lsb_2", LSB_2),
        ("lsb_4", LSB_4),
        ("lsb_matching", LSB_MATCHING),
        ("lsb_parity", LSB_PARITY),
        ("lsb_keyed", LSB_KEYED),
        ("echo", ECHO),
    ]
    assert LEGACY_ALGORITHMS == {
        "basic": BASIC_LSB,
        "enhanced_flip": ENHANCED_LSB_FLIP,
        "enhanced": ENHANCED_LSB,
    }


@pytest.mark.parametrize("algorithms", [ALGORITHMS, LEGACY_ALGORITHMS])
def test_every_algorithm_has_a_usable_name_and_one_line_of_explanation(algorithms: Any) -> None:
    for key, algorithm in algorithms.items():
        assert re.fullmatch("[a-z][a-z0-9_]*", key)
        assert algorithm.explanation and algorithm.explanation.isprintable()


def test_no_two_algorithms_look_the_same() -> None:
    algorithms = [*ALGORITHMS.values(), *LEGACY_ALGORITHMS.values()]
    names = [algorithm.name.casefold() for algorithm in algorithms]
    assert len(set(names)) == len(names)


@every_byte_algorithm
def test_every_byte_carries_every_group_of_bits(algorithm: Algorithm) -> None:
    for byte, bits in product(range(256), product(range(2), repeat=algorithm.bits_per_byte)):
        changed = algorithm.embed_bits(byte, bits)
        assert 0 <= changed <= 255
        assert tuple(algorithm.extract_bits(changed)) == bits


@pytest.mark.parametrize("key", EVERY_KEY)
def test_every_algorithm_hides_and_reveals_a_message(
    make_wav: Callable[..., Path], fast_scrypt: None, tmp_path: Path, key: str
) -> None:
    output, algorithm, passphrase = tmp_path / "output.wav", ALGORITHMS[key], needed_passphrase(key)
    source = make_wav(frames=noise_for(key))
    encode(str(source), str(output), "Hello 🎵", algorithm, passphrase=passphrase)
    assert decode(str(output), algorithm, passphrase=passphrase) == "Hello 🎵"
    assert decode(str(output), passphrase=passphrase) == "Hello 🎵"


@pytest.mark.parametrize("old", PLAIN_KEYS)
@pytest.mark.parametrize("new", PLAIN_KEYS)
def test_a_new_message_is_never_mistaken_for_an_older_one(
    make_wav: Callable[..., Path], tmp_path: Path, old: str, new: str
) -> None:
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    noise = noise_for(old) or noise_for(new)
    encode(str(make_wav(frames=noise)), str(first), "an older message", ALGORITHMS[old])
    encode(str(first), str(second), "new", ALGORITHMS[new])
    assert decode(str(second)) == "new"
    survives = [old] if old == "echo" != new else []
    found = [message.algorithm for message in look_at(str(second)).messages]
    assert found == [reading_key(new), *survives]


def test_the_name_that_a_message_is_reported_under() -> None:
    assert {key: reading_key(key) for key in ALGORITHMS if reading_key(key) != key} == {"lsb_matching": "lsb"}
