"""Tests for audiosteg/analysis/quality.py."""

from collections.abc import Callable
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from audiosteg.analysis import samples
from audiosteg.analysis.quality import Quality, measure
from audiosteg.analysis.samples import Part, SampleFormat, open_pair
from audiosteg.cli.commands.hide import SAMPLE_FILE


def measured(paths: tuple[str, str], first: int = 0, frames: int | None = None) -> Quality:
    with open_pair(*paths) as pair:
        return measure(pair, Part(first, pair.frames if frames is None else frames))


def decibels(ratio: Fraction) -> Decimal:
    with localcontext(prec=40):
        return 10 * (Decimal(ratio.numerator) / Decimal(ratio.denominator)).log10()


def close(value: float | None, expected: Decimal) -> bool:
    return value is not None and abs(Decimal(value) - expected) < Decimal("1e-9")


@pytest.mark.parametrize(("bits", "full"), [(8, 128), (16, 32768), (24, 8388608), (32, 2147483648)])
@pytest.mark.parametrize("channels", [1, 2])
def test_small_files_by_hand(
    make_pair: Callable[..., tuple[str, str]], bits: int, full: int, channels: int
) -> None:
    quality = measured(make_pair([3, -4, 0, 12], [3, -2, 0, 11], bits, channels=channels))
    assert (quality.signal, quality.noise, quality.changed, quality.largest_change) == (169, 5, 2, 2)
    assert quality.samples == 4
    assert close(quality.snr, decibels(Fraction(169, 5)))
    assert close(quality.psnr, decibels(Fraction(full * full * 4, 5)))
    assert quality.changed_percentage == 50
    assert Fraction(quality.largest_change_percentage) == Fraction(200, full)
    if channels == 1:
        assert (quality.first_changed, quality.last_changed) == (1, 3)
        assert quality.changed_by_tenth == (0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    else:
        assert (quality.first_changed, quality.last_changed) == (0, 1)
        assert quality.changed_by_tenth == (0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


@pytest.mark.parametrize("bits", [8, 16, 24, 32])
@pytest.mark.parametrize("sign", [1, -1])
def test_the_largest_possible_change(make_pair: Callable[..., tuple[str, str]], bits: int, sign: int) -> None:
    full = 2 ** (bits - 1)
    ends = [-full, full - 1][::sign]
    quality = measured(make_pair([ends[0]], [ends[1]], bits))
    assert (quality.signal, quality.noise) == (ends[0] ** 2, (2 * full - 1) ** 2)
    assert quality.largest_change == 2 * full - 1
    assert 199 < quality.largest_change_percentage < 200
    assert (quality.changed_percentage, quality.word) == (100, "Poor")
    assert close(quality.psnr, decibels(Fraction(full * full, (2 * full - 1) ** 2)))


def test_255_channels(make_pair: Callable[..., tuple[str, str]]) -> None:
    original = [1] * 510
    encoded = [1] * 254 + [0] + [1] * 254 + [2]
    quality = measured(make_pair(original, encoded, channels=255))
    assert (quality.samples, quality.changed) == (510, 2)
    assert (quality.first_changed, quality.last_changed) == (0, 1)
    encoded[254] = 1
    assert measured(make_pair(original, encoded, channels=255)).first_changed == 1


def quality_of(signal: int, noise: int) -> Quality:
    sample_format = SampleFormat(1, 2, 8000)
    return Quality(sample_format, Part(0, 4), 4, signal, noise, int(noise > 0), 1, 0, 0, (0,) * 10)


@pytest.mark.parametrize(("word", "limit"), [("Excellent", 70), ("Good", 50), ("Fair", 30)])
@pytest.mark.parametrize("noise", [1, 3, 2**31 - 1, 10**18])
def test_a_limit_is_reached_exactly(word: str, limit: int, noise: int) -> None:
    reached = noise * 10 ** (limit // 10)
    assert quality_of(reached, noise).word == word
    assert quality_of(reached, noise).snr == limit
    assert quality_of(reached - 1, noise).word != word


def test_the_words_of_real_files(make_pair: Callable[..., tuple[str, str]]) -> None:
    for value, word in [(3163, "Excellent"), (3162, "Good"), (317, "Good"), (316, "Fair"), (31, "Poor")]:
        assert measured(make_pair([value] * 4, [value] * 3 + [value + 2], 16)).word == word


def test_nothing_changed_and_silence(make_pair: Callable[..., tuple[str, str]]) -> None:
    same = measured(make_pair([5, -5], [5, -5]))
    assert (same.identical, same.silent_original, same.snr, same.psnr) == (True, False, None, None)
    assert (same.first_changed, same.last_changed, same.largest_change) == (None, None, 0)
    silent = measured(make_pair([0, 0], [0, 1]))
    assert (silent.identical, silent.silent_original, silent.snr) == (False, True, None)
    assert close(silent.psnr, decibels(Fraction(2 * 32768**2)))
    both = measured(make_pair([0, 0], [0, 0], 8))
    assert (both.word, both.silent_original, both.snr) == ("Identical", True, None)


def test_no_samples(make_pair: Callable[..., tuple[str, str]]) -> None:
    empty = measured(make_pair([], []))
    assert (empty.samples, empty.changed_percentage, empty.identical, empty.partial) == (0, 0, True, False)
    assert empty.changed_by_tenth == (0,) * 10


def test_a_part_counts_only_itself(make_pair: Callable[..., tuple[str, str]]) -> None:
    paths = make_pair([9] * 20, [8] + [9] * 9 + [5, 9, 7] + [9] * 6 + [1], channels=1)
    quality = measured(paths, 10, 5)
    assert (quality.signal, quality.noise, quality.changed) == (405, 20, 2)
    assert (quality.first_changed, quality.last_changed, quality.largest_change) == (10, 12, 4)
    assert quality.changed_by_tenth == (0, 1, 0, 0, 0, 1, 0, 0, 0, 0)
    assert (quality.partial, quality.total_frames, quality.samples) == (True, 20, 5)
    assert not measured(paths, 0, 20).partial
    assert measured(paths, 1, 9).identical


@pytest.mark.parametrize("block_bytes", [1, 6, 1000])
def test_the_block_size_changes_nothing(
    make_pair: Callable[..., tuple[str, str]], monkeypatch: pytest.MonkeyPatch, block_bytes: int
) -> None:
    monkeypatch.setattr(samples, "BLOCK_BYTES", block_bytes)
    original = list(range(-60, 60))
    encoded = list(original)
    for index, change in [(7, 1), (8, -5), (51, 4), (117, -2)]:
        encoded[index] += change
    quality = measured(make_pair(original, encoded, channels=3))
    assert (quality.noise, quality.changed, quality.largest_change) == (46, 4, 5)
    assert (quality.first_changed, quality.last_changed) == (2, 39)
    assert quality.signal == sum(value * value for value in original)
    assert quality.changed_by_tenth == (2, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def test_the_readme_numbers_of_the_sample(
    run: Any, tmp_path: Path, read_frames: Callable[[Path], bytes]
) -> None:
    assert run("hide", "sample", "-m", "Hello").code == 0
    quality = measured((SAMPLE_FILE, str(tmp_path / "sample.stego.wav")))
    before = memoryview(read_frames(Path(SAMPLE_FILE))).cast("h").tolist()
    after = memoryview(read_frames(tmp_path / "sample.stego.wav")).cast("h").tolist()
    noise = sum((new - old) ** 2 for new, old in zip(after, before, strict=True))
    assert (quality.noise, quality.changed) == (noise, 78)
    assert close(quality.snr, decibels(Fraction(sum(value * value for value in before), noise)))
    assert 106.2 <= (quality.snr or 0) < 106.3
