"""Convert stored samples to numbers and back with NumPy, so that nothing can wrap around."""

from __future__ import annotations

from typing import TYPE_CHECKING

from audiosteg.core.signal_algorithm import load_numpy

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from audiosteg.core.signal_algorithm import Numbers

    Bytes = NDArray[np.uint8]


def sample_bytes(data: bytearray | bytes | memoryview, channels: int, sample_width: int) -> Bytes:
    """Look at stored frames as bytes, by frame, channel, and byte of the sample. Nothing is copied."""
    np = load_numpy()
    view: Bytes = np.frombuffer(data, dtype=np.uint8).reshape(-1, channels, sample_width)
    return view


def to_numbers(stored: Bytes) -> Numbers:
    """Return samples as numbers, where 0 is silence. The last axis holds the bytes of a sample."""
    np = load_numpy()
    sample_width = stored.shape[-1]
    if sample_width == 1:
        numbers: Numbers = stored[..., 0].astype(np.float64) - 128
        return numbers
    numbers = stored[..., -1].astype(np.int8).astype(np.float64)
    for position in reversed(range(sample_width - 1)):
        numbers = numbers * 256 + stored[..., position]
    return numbers


def largest_number(sample_width: int) -> int:
    """Return the largest number that a sample can store."""
    return (1 << (8 * sample_width - 1)) - 1


def to_stored(numbers: Numbers, sample_width: int) -> Bytes:
    """Round numbers and return them as stored samples. A number that is too large becomes the nearest."""
    np = load_numpy()
    limit = largest_number(sample_width)
    whole = np.clip(np.rint(numbers), -limit - 1, limit).astype(np.int64)
    if sample_width == 1:
        whole += 128
    stored: Bytes = np.empty((*whole.shape, sample_width), dtype=np.uint8)
    for position in range(sample_width):
        stored[..., position] = (whole >> (8 * position)) & 255
    return stored


def mix_channels(data: bytes | memoryview, channels: int, sample_width: int) -> Numbers:
    """Add all channels of stored frames together."""
    mixed: Numbers = to_numbers(sample_bytes(data, channels, sample_width)).sum(axis=1)
    return mixed
