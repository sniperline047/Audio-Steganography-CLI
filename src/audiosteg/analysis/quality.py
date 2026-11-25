"""Measure how much a copy of a WAV file differs from the original."""

import math
from dataclasses import dataclass
from fractions import Fraction
from operator import mul, sub

from audiosteg.analysis.samples import Pair, Part, SampleFormat, read_pairs, to_values

PLACES = 10
EXCELLENT, GOOD, FAIR, POOR, IDENTICAL = "Excellent", "Good", "Fair", "Poor", "Identical"
QUALITY_LIMITS = ((EXCELLENT, 70), (GOOD, 50), (FAIR, 30))


def decibels(power: int, reference: int) -> float:
    """Return how many decibels one power is above another."""
    return 10 * math.log10(power / reference)


@dataclass(frozen=True)
class Quality:
    """
    What was measured in a part of two files. Samples are whole numbers, where 0 is silence.

    :param format: The format of both files
    :param part: The part that was measured
    :param total_frames: The length of both files
    :param signal: The sum of the squares of the original samples
    :param noise: The sum of the squares of the changes
    :param changed: How many samples changed
    :param largest_change: The largest change of a sample, without its sign
    :param first_changed: The first frame with a change, or None
    :param last_changed: The last frame with a change, or None
    :param changed_by_tenth: How many samples changed in each tenth of the part
    """

    format: SampleFormat
    part: Part
    total_frames: int
    signal: int
    noise: int
    changed: int
    largest_change: int
    first_changed: int | None
    last_changed: int | None
    changed_by_tenth: tuple[int, ...]

    @property
    def samples(self) -> int:
        """Return the number of samples of all channels."""
        return self.part.frames * self.format.channels

    @property
    def partial(self) -> bool:
        """Say whether only a part of the files was measured."""
        return self.part.frames != self.total_frames

    @property
    def identical(self) -> bool:
        """Say whether nothing changed."""
        return self.changed == 0

    @property
    def silent_original(self) -> bool:
        """Say whether every original sample is silence."""
        return self.signal == 0

    def reaches(self, limit: int) -> bool:
        """Say exactly whether the signal-to-noise ratio reaches this many decibels, a multiple of 10."""
        power: int = 10 ** (limit // 10)
        return self.signal >= self.noise * power

    @property
    def snr(self) -> float | None:
        """Return the signal-to-noise ratio in dB, or None if nothing changed or the original is silent."""
        if self.identical or self.silent_original:
            return None
        ratio = decibels(self.signal, self.noise)
        for _, limit in QUALITY_LIMITS:
            if not self.reaches(limit):
                ratio = min(ratio, math.nextafter(limit, 0))
        return ratio

    @property
    def psnr(self) -> float | None:
        """Return the peak signal-to-noise ratio in dB, or None if nothing changed."""
        if self.identical:
            return None
        return decibels(self.format.full_scale**2 * self.samples, self.noise)

    @property
    def word(self) -> str:
        """Return one word for the quality."""
        if self.identical:
            return IDENTICAL
        for word, limit in QUALITY_LIMITS:
            if self.reaches(limit):
                return word
        return POOR

    @property
    def changed_percentage(self) -> Fraction:
        """Return exactly how many percent of the samples changed."""
        return Fraction(100 * self.changed, self.samples) if self.samples else Fraction(0)

    @property
    def largest_change_percentage(self) -> Fraction:
        """Return exactly the largest change in percent of the largest possible sample."""
        return Fraction(100 * self.largest_change, self.format.full_scale)


def measure(pair: Pair, part: Part) -> Quality:
    """Compare a part of two files."""
    signal = noise = changed = largest = 0
    first_changed = last_changed = None
    changed_by_tenth = []
    for tenth in part.split(PLACES):
        frame = tenth.first
        changed_before = changed
        for original_bytes, encoded_bytes in read_pairs(pair, tenth):
            original = to_values(original_bytes, pair.format.sample_width)
            signal += sum(map(mul, original, original))
            if original_bytes != encoded_bytes:
                encoded = to_values(encoded_bytes, pair.format.sample_width)
                changes = list(map(sub, encoded, original))
                noise += sum(map(mul, changes, changes))
                changed += len(changes) - changes.count(0)
                largest = max(largest, max(changes), -min(changes))
                first = next(index for index, change in enumerate(changes) if change)
                if first_changed is None:
                    first_changed = frame + first // pair.format.channels
                last = next(index for index in reversed(range(len(changes))) if changes[index])
                last_changed = frame + last // pair.format.channels
            frame += len(original_bytes) // pair.format.frame_size
        changed_by_tenth.append(changed - changed_before)
    return Quality(
        pair.format,
        part,
        pair.frames,
        signal,
        noise,
        changed,
        largest,
        first_changed,
        last_changed,
        tuple(changed_by_tenth),
    )
