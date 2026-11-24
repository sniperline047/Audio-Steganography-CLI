"""Generate the short original tune in src/audiosteg/data/sample.wav.

Every calculation uses whole numbers, so the file is identical on every computer.
"""

from __future__ import annotations

import wave
from array import array
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "src" / "audiosteg" / "data" / "sample.wav"
SAMPLE_RATE = 22050
STEP_SAMPLES = 2950
FADE_SAMPLES = 180
HALF_CYCLE = 1 << 15
CYCLE = HALF_CYCLE * 2

MELODY_MILLIHERTZ = [
    440000, 659255, 587330, 493883, 739989, 659255, 880000, 554365,
    587330, 440000, 739989, 493883, 659255, 554365, 493883, 440000,
    659255, 440000, 739989, 880000, 587330, 659255, 493883, 739989,
    554365, 659255, 440000, 587330, 493883, 554365, 440000, 440000,
]  # fmt: skip
BASS_MILLIHERTZ = [110000, 146832, 123471, 92499, 110000, 164814, 123471, 110000]


def sine(phase: int) -> int:
    """Approximate a sine wave (Bhaskara's formula), from -10000 to 10000."""
    position = phase % CYCLE
    x = position % HALF_CYCLE
    product = x * (HALF_CYCLE - x)
    value = 10000 * 16 * product // (5 * HALF_CYCLE * HALF_CYCLE - 4 * product)
    return value if position < HALF_CYCLE else -value


def tone(millihertz: int, sample: int) -> int:
    """Return one sample of a soft tone with one overtone."""
    phase = millihertz * sample * CYCLE // (SAMPLE_RATE * 1000)
    return (sine(phase) * 3 + sine(phase * 2)) // 4


def envelope(sample: int, length: int) -> int:
    """Fade a note in and let it decay, from 0 to 1000."""
    remaining = length - sample
    attack = min(sample, FADE_SAMPLES) * 1000 // FADE_SAMPLES
    release = min(remaining, FADE_SAMPLES) * 1000 // FADE_SAMPLES
    decay = 300 + 700 * remaining // length
    return attack * release * decay // 1_000_000


def note(millihertz: int, sample: int, length: int) -> int:
    """Return one sample of a note with its envelope applied."""
    return tone(millihertz, sample) * envelope(sample, length) // 1000


def generate_samples() -> array[int]:
    """Create interleaved left and right samples."""
    samples = array("h")
    bass_length = STEP_SAMPLES * 4
    for index in range(STEP_SAMPLES * len(MELODY_MILLIHERTZ)):
        step, offset = divmod(index, STEP_SAMPLES)
        bass_step, bass_offset = divmod(index, bass_length)
        melody = note(MELODY_MILLIHERTZ[step], offset, STEP_SAMPLES)
        bass = note(BASS_MILLIHERTZ[bass_step], bass_offset, bass_length)
        pan = 35 + 10 * (step % 4)
        samples.append((melody * (100 - pan) + bass * 60) // 70)
        samples.append((melody * pan + bass * 60) // 70)
    return samples


def main() -> None:
    """Write the tune as 16-bit stereo PCM."""
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    samples = generate_samples()
    with wave.open(str(OUTPUT_PATH), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(samples.tobytes())
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
