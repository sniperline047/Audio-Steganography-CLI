"""Tests for audiosteg/algorithms/detection.py."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audiosteg import Algorithm, decode, encode
from audiosteg.algorithms import detection
from audiosteg.algorithms.detection import detect
from audiosteg.algorithms.legacy import BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_keyed import LSB_KEYED
from audiosteg.algorithms.lsb_matching import LSB_MATCHING
from audiosteg.core import crypto
from audiosteg.core.algorithm import LegacyAlgorithm
from audiosteg.core.header import Header
from audiosteg.errors import (
    DamagedMessageError,
    MissingLibraryError,
    NoMessageError,
    NotEncryptedError,
    PassphraseRequiredError,
    UnsupportedFormatError,
    WrongPassphraseError,
)

PLAIN = bytes.fromhex("4153544701000000000348c3a9a411cc3b")
OLD_BASIC = bytes(int(digit) for digit in f"{24:032b}" + "".join(f"{byte:08b}" for byte in b"Old"))

SECOND_BIT = Algorithm(
    "Second bit", 1, lambda byte, bits: (byte & 253) | (bits[0] << 1), lambda byte: ((byte >> 1) & 1,)
)

both = pytest.mark.parametrize("algorithm", [LSB, LSB_2], ids=["LSB", "LSB_2"])


@both
def test_the_algorithm_of_a_plain_message_is_found(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], algorithm: Algorithm
) -> None:
    path = str(make_wav(frames=embed(PLAIN, algorithm.bits_per_byte)))
    assert detect(path) == (algorithm, Header(False, 3))
    assert decode(path) == "Hé"


@both
def test_an_encrypted_message_is_found_without_the_library(
    make_wav: Callable[..., Path],
    embed: Callable[..., bytes],
    known_answer: Any,
    no_library: None,
    algorithm: Algorithm,
) -> None:
    path = str(make_wav(frames=embed(known_answer.container, algorithm.bits_per_byte)))
    assert detect(path) == (algorithm, Header(True, 8))
    with pytest.raises(PassphraseRequiredError):
        decode(path)
    with pytest.raises(MissingLibraryError):
        decode(path, passphrase=known_answer.passphrase)


@both
@pytest.mark.needs_crypto
def test_an_encrypted_message_made_by_another_program_is_read(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], known_answer: Any, algorithm: Algorithm
) -> None:
    path = str(make_wav(frames=embed(known_answer.container, algorithm.bits_per_byte)))
    assert decode(path, passphrase="Café ☕") == known_answer.message


@pytest.mark.parametrize("frames", [b"", b"\0", bytes(79), bytes(4000), b"\xff" * 4000, OLD_BASIC])
def test_audio_without_a_message(make_wav: Callable[..., Path], frames: bytes) -> None:
    path = str(make_wav(frames=frames))
    assert detect(path) is None
    with pytest.raises(NoMessageError, match="No hidden message was found"):
        decode(path)
    with pytest.raises(NoMessageError):
        decode(path, passphrase="key")


@both
def test_a_damaged_message_is_reported_and_not_treated_as_missing(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], algorithm: Algorithm
) -> None:
    size = algorithm.bits_per_byte
    for hidden, error in [
        (b"ASTG\x02" + PLAIN[5:], UnsupportedFormatError),
        (b"ASTG\x01\x02" + PLAIN[6:], UnsupportedFormatError),
        (PLAIN[:6] + b"\xff" + PLAIN[7:], DamagedMessageError),
    ]:
        path = str(make_wav(frames=embed(hidden, size)))
        with pytest.raises(error):
            detect(path)
        with pytest.raises(error):
            decode(path)
    path = str(make_wav(frames=embed(PLAIN[:-1] + b"\0", size)))
    assert detect(path) == (algorithm, Header(False, 3))
    with pytest.raises(DamagedMessageError):
        decode(path)


def test_the_first_algorithm_in_the_list_wins(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detection, "ALGORITHMS", {"lsb": LSB, "lsb_2": LSB_2, "second": SECOND_BIT})
    old = tmp_path / "old.wav"
    new = tmp_path / "new.wav"
    encode(str(make_wav()), str(old), "old", LSB)
    encode(str(old), str(new), "new", SECOND_BIT)
    assert decode(str(new)) == "old"
    assert decode(str(new), SECOND_BIT) == "new"


def test_a_new_algorithm_is_detected_after_it_is_added_to_the_list(
    make_wav: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.wav"
    encode(str(make_wav()), str(output), "new", SECOND_BIT)
    monkeypatch.setattr(detection, "ALGORITHMS", {"lsb": LSB, "lsb_2": LSB_2})
    assert detect(str(output)) is None
    monkeypatch.setattr(detection, "ALGORITHMS", {"lsb": LSB, "lsb_2": LSB_2, "second": SECOND_BIT})
    assert decode(str(output)) == "new"


def test_a_given_algorithm_is_the_only_one_tried(
    make_wav: Callable[..., Path], embed: Callable[..., bytes]
) -> None:
    path = str(make_wav(frames=embed(PLAIN, 2)))
    with pytest.raises(NoMessageError):
        decode(path, LSB)


@pytest.mark.parametrize("algorithm", [None, LSB])
def test_a_passphrase_for_a_plain_message_is_refused(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], algorithm: Algorithm | None
) -> None:
    path = str(make_wav(frames=embed(PLAIN, 1)))
    with pytest.raises(NotEncryptedError):
        decode(path, algorithm, passphrase="key")


@pytest.mark.parametrize("algorithm", [BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP])
def test_a_passphrase_for_an_old_file_is_refused(
    make_wav: Callable[..., Path], algorithm: LegacyAlgorithm
) -> None:
    with pytest.raises(NotEncryptedError, match="Older versions never encrypted"):
        decode(str(make_wav(frames=OLD_BASIC)), algorithm, passphrase="key")


def test_old_files_are_read_only_with_a_chosen_algorithm(make_wav: Callable[..., Path]) -> None:
    path = str(make_wav(frames=OLD_BASIC))
    with pytest.raises(NoMessageError):
        decode(path)
    assert decode(path, BASIC_LSB) == "Old"


@pytest.mark.parametrize("algorithm", [None, LSB, BASIC_LSB])
@pytest.mark.parametrize("passphrase", ["", "a\0b", "\udcff"])
def test_an_unusable_passphrase_is_refused_for_every_file(
    make_wav: Callable[..., Path], algorithm: Algorithm | LegacyAlgorithm | None, passphrase: str
) -> None:
    with pytest.raises(ValueError, match="The passphrase"):
        decode(str(make_wav()), algorithm, passphrase=passphrase)


@pytest.mark.parametrize("algorithm", ["LSB", 1, LSB.embed_bits])
def test_something_that_is_not_an_algorithm_is_refused(make_wav: Callable[..., Path], algorithm: Any) -> None:
    with pytest.raises(TypeError, match="must be an Algorithm"):
        decode(str(make_wav()), algorithm)


@pytest.fixture
def keyed(make_wav: Callable[..., Path], tmp_path: Path, fast_scrypt: None) -> str:
    output = tmp_path / "keyed.wav"
    encode(str(make_wav()), str(output), "hidden", LSB_KEYED, passphrase="sesame")
    return str(output)


@pytest.mark.needs_crypto
def test_a_keyed_message_is_found_only_with_its_passphrase(keyed: str) -> None:
    assert detect(keyed) is None
    assert decode(keyed, passphrase="sesame") == decode(keyed, LSB_KEYED, passphrase="sesame") == "hidden"
    with pytest.raises(NoMessageError, match=r"No hidden message was found\.$"):
        decode(keyed)


@pytest.mark.needs_crypto
def test_a_wrong_passphrase_is_the_same_as_no_message(keyed: str, make_wav: Callable[..., Path]) -> None:
    reasons = set()
    for path in (keyed, str(make_wav()), str(make_wav(frames=b""))):
        for algorithm in (None, LSB_KEYED):
            with pytest.raises(NoMessageError) as caught:
                decode(path, algorithm, passphrase="wrong")
            reasons.add(str(caught.value))
    assert len(reasons) == 1


@pytest.mark.needs_crypto
def test_a_detected_message_is_never_read_as_a_keyed_one(keyed: str, tmp_path: Path) -> None:
    both = str(tmp_path / "both.wav")
    encode(keyed, both, "plain", LSB)
    with pytest.raises(NotEncryptedError):
        decode(both, passphrase="sesame")
    encode(keyed, both, "encrypted", LSB, passphrase="other", overwrite=True)
    with pytest.raises(WrongPassphraseError):
        decode(both, passphrase="sesame")
    assert decode(both, passphrase="other") == "encrypted"


@pytest.mark.needs_crypto
def test_a_plain_message_can_hold_a_keyed_one_that_is_named(
    make_wav: Callable[..., Path], tmp_path: Path, fast_scrypt: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain, both = str(tmp_path / "plain.wav"), str(tmp_path / "both.wav")
    encode(str(make_wav()), plain, "plain", SECOND_BIT)
    encode(plain, both, "hidden", LSB_KEYED, passphrase="sesame")
    monkeypatch.setattr(detection, "ALGORITHMS", {"second": SECOND_BIT, "lsb_keyed": LSB_KEYED})
    assert decode(both) == "plain"
    with pytest.raises(NotEncryptedError):
        decode(both, passphrase="sesame")
    assert decode(both, LSB_KEYED, passphrase="sesame") == "hidden"


def test_no_key_is_made_without_a_passphrase_or_with_a_detected_message(
    make_wav: Callable[..., Path], embed: Callable[..., bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(passphrase: bytes, salt: bytes) -> bytes:
        raise AssertionError("a key was made")

    monkeypatch.setattr(crypto, "derive_key", refuse)
    with pytest.raises(NoMessageError):
        decode(str(make_wav()))
    with pytest.raises(NotEncryptedError):
        decode(str(make_wav(frames=embed(PLAIN, 1))), passphrase="key")


def test_a_message_of_lsb_matching_is_found_as_lsb(make_wav: Callable[..., Path], tmp_path: Path) -> None:
    output = str(tmp_path / "output.wav")
    encode(str(make_wav()), output, "hidden", LSB_MATCHING)
    assert detect(output) == (LSB, Header(False, 6))
