"""Tests for audiosteg/algorithms/echo.py."""

import math
import random
import zlib
from cmath import exp, pi
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import pack

from audiosteg import decode, encode
from audiosteg.algorithms.echo import ECHO
from audiosteg.core.protection import protect

pytestmark = pytest.mark.needs_signal

BLOCK = 1024


def noise(frames: int, seed: int = 1, loudness: int = 6000) -> list[int]:
    chooser = random.Random(seed)
    return [chooser.randint(-loudness, loudness) for _ in range(frames)]


def fade(position: int) -> float:
    """Return how far the change to the next block has come, as documented."""
    return 0.5 - 0.5 * math.cos(math.pi * min(position, 256) / 256)


def independent_echo(samples: list[int], bits: list[int], level: float) -> list[int]:
    """Add echoes as the documentation says, without the package."""
    wanted = {0: [0, *[1 - bit for bit in bits], 0], 1: [0, *bits, 0]}
    result = list(samples)
    for frame in range(min(len(bits) * BLOCK + 128, len(samples))):
        block, position = divmod(frame + 128, BLOCK)
        echo = 0.0
        for bit, delay in ((0, 25), (1, 50)):
            loudness = wanted[bit][block] * (1 - fade(position)) + wanted[bit][block + 1] * fade(position)
            echo += loudness * (samples[frame - delay] if frame >= delay else 0)
        result[frame] = round(samples[frame] + level * echo)
    return result


def spectrum(values: list[complex]) -> list[complex]:
    """Return the discrete Fourier transform."""
    if len(values) == 1:
        return values
    even, odd = spectrum(values[::2]), spectrum(values[1::2])
    half = len(values) // 2
    turned = [exp(-2j * pi * index / len(values)) * odd[index] for index in range(half)]
    return [a + b for a, b in zip(even, turned, strict=True)] + [
        a - b for a, b in zip(even, turned, strict=True)
    ]


def independent_bits(samples: list[int], blocks: int) -> Iterator[int]:
    """Read bits as the documentation says, without the package."""
    window = [0.5 - 0.5 * math.cos(2 * math.pi * index / BLOCK) for index in range(BLOCK)]
    for block in range(blocks):
        part = samples[block * BLOCK : (block + 1) * BLOCK]
        logarithms = [
            math.log(abs(value) ** 2 + 1)
            for value in spectrum([complex(a * b) for a, b in zip(part, window, strict=True)])
        ]
        zero, one = (
            sum(
                value * math.cos(2 * math.pi * index * delay / BLOCK)
                for index, value in enumerate(logarithms)
            )
            for delay in (25, 50)
        )
        yield int(one > zero)


def container(message: bytes) -> bytes:
    content = b"ASTG\x01\x00" + len(message).to_bytes(4, "big") + message
    return content + zlib.crc32(content).to_bytes(4, "big")


def bits_of(data: bytes) -> list[int]:
    return [int(digit) for byte in data for digit in f"{byte:08b}"]


def test_a_file_of_another_program_is_read(make_samples: Callable[..., Path]) -> None:
    bits = bits_of(protect(container(b"Hello")))
    changed = independent_echo(noise(len(bits) * BLOCK), bits, 0.3)
    path = str(make_samples("other.wav", changed))
    assert decode(path, ECHO) == "Hello"
    assert decode(path) == "Hello"


def test_another_program_reads_and_makes_the_same(
    make_samples: Callable[..., Path], read_frames: Callable[[Path], bytes], tmp_path: Path
) -> None:
    bits = bits_of(protect(container(b"Hi")))
    samples = noise(len(bits) * BLOCK + 500, seed=2)
    output = tmp_path / "output.wav"
    encode(str(make_samples("input.wav", samples)), str(output), "Hi", ECHO)
    expected = independent_echo(samples, bits, 0.2)
    assert read_frames(output) == pack(expected, 16)
    read = list(independent_bits(expected, 100))
    assert sum(a != b for a, b in zip(read, bits, strict=False)) <= 3


def test_blocks_are_read_like_another_program_reads_them() -> None:
    import numpy as np

    samples = noise(12 * BLOCK, seed=3, loudness=200)
    blocks = np.array(samples, dtype=np.float64).reshape(12, BLOCK)
    assert ECHO.read_bits(blocks) == list(independent_bits(samples, 12))


def test_an_echo_is_a_peak_in_the_cepstrum_at_its_delay() -> None:
    import numpy as np

    sound = np.array(noise(BLOCK + 50, seed=4), dtype=np.float64)
    for delay in ECHO.delays:
        echoed = sound[50:] + 0.5 * sound[50 - delay : -delay]
        cepstrum = ECHO.find_cepstra(echoed.reshape(1, -1))[0]
        assert int(np.argmax(cepstrum[10:512])) + 10 == delay
        assert cepstrum[delay] == pytest.approx(0.5, abs=0.15)


def test_silence_has_no_bits() -> None:
    import numpy as np

    signs = ECHO.find_signs(np.zeros((2, BLOCK)))
    assert np.isfinite(signs).all()
    assert ECHO.read_bits(np.zeros((2, BLOCK))) == [0, 0]


def test_the_echo_changes_smoothly_and_ends_after_the_last_block() -> None:
    import numpy as np

    bits = np.array([1.0, 0.0, 0.0, 1.0])
    frames = ECHO.changed_frames(4)
    ones = ECHO.loudness(0, frames, bits)
    zeros = ECHO.loudness(0, frames, 1 - bits)
    assert abs(np.diff(ones)).max() < 0.01
    assert (ones + zeros)[128:-256] == pytest.approx(1)
    assert (ones[0], ones[512], ones[1024], ones[1600]) == pytest.approx((0.5, 1, 0.5, 0))
    assert (ones + zeros)[-1] < 0.01
    assert frames == 4 * 1024 + 128
    pieces = [ECHO.loudness(first, min(1024, frames - first), bits) for first in range(0, frames, 1024)]
    assert np.concatenate(pieces) == pytest.approx(ones)


def test_the_loudness_is_computed_once_for_all_channels(
    make_samples: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int] = []
    original = type(ECHO).prepare

    def prepare(self: Any, first_frame: int, frames: int, bits: Any) -> Any:
        calls.append(first_frame)
        return original(self, first_frame, frames, bits)

    monkeypatch.setattr(type(ECHO), "prepare", prepare)
    for channels in (1, 4):
        values = [value for value in noise(46 * 8 * BLOCK) for _ in range(channels)]
        source = make_samples("input.wav", values, channels=channels)
        encode(str(source), str(tmp_path / "output.wav"), "", ECHO, overwrite=True)
    assert calls == 4 * list(range(0, 46 * 8 * BLOCK, 64 * BLOCK))
