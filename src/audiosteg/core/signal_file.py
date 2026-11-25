"""Hide a container in whole blocks of sound and read it back, a few blocks at a time."""

from __future__ import annotations

import wave
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from audiosteg.core.algorithm import Algorithm
from audiosteg.core.header import HEADER_SIZE, MARKER, Header, parse_header
from audiosteg.core.message_codec import bits_to_bytes, bytes_to_bits, extract_groups
from audiosteg.core.protection import (
    PROTECTED_HEADER_SIZE,
    Restored,
    protect,
    protected_size,
    restore_body,
    restore_header,
)
from audiosteg.core.signal_algorithm import SignalAlgorithm, load_numpy
from audiosteg.core.signal_samples import largest_number, mix_channels, sample_bytes, to_numbers, to_stored
from audiosteg.core.wav_io import AudioData, count_sample_bytes
from audiosteg.errors import DamagedMessageError, StegoError, UnsuitableAudioError

if TYPE_CHECKING:
    from audiosteg.core.signal_algorithm import Numbers
    from audiosteg.core.signal_samples import Bytes

BLOCKS_AT_A_TIME = 64
BYTES_AT_A_TIME = 1 << 20
COMFORTABLE_STRAIN = 0.5


class Sound:
    """Frames of an open file or in memory, and how they are stored."""

    def __init__(
        self, channels: int, sample_width: int, frames: int, read: Callable[[int, int], bytes | memoryview]
    ) -> None:
        """
        Describe the frames.

        :param read: Function that returns stored frames, given the first one and how many
        """
        self.channels = channels
        self.sample_width = sample_width
        self.frames = frames
        self.read = read

    def mix(self, first: int, count: int) -> Numbers:
        """Add all channels of these frames together. Missing frames are left out."""
        np = load_numpy()
        piece = max(BYTES_AT_A_TIME // (self.channels * self.sample_width), 1)
        end = min(first + count, self.frames)
        parts = [np.zeros(0)]
        for start in range(first, end, piece):
            data = self.read(start, min(piece, end - start))
            parts.append(mix_channels(data, self.channels, self.sample_width))
        mixed: Numbers = np.concatenate(parts)
        return mixed


def sound_in_memory(audio: AudioData) -> Sound:
    """Describe the frames of a WAV file that was read."""
    size = audio.channels * audio.sample_width
    view = memoryview(audio.frames)
    return Sound(
        audio.channels,
        audio.sample_width,
        len(audio.frames) // size,
        lambda first, count: view[first * size : (first + count) * size],
    )


def sound_in_file(audio: wave.Wave_read, path: str) -> Sound:
    """Describe the frames of an open WAV file."""
    size = audio.getnchannels() * audio.getsampwidth()

    def read(first: int, count: int) -> bytes:
        audio.setpos(first)
        data = audio.readframes(count)
        return data[: len(data) // size * size]

    return Sound(audio.getnchannels(), audio.getsampwidth(), count_sample_bytes(audio, path) // size, read)


def read_hidden_bytes(sound: Sound, algorithm: SignalAlgorithm, first: int, size: int) -> bytes:
    """Read hidden bytes from the blocks that carry them. Incomplete blocks are left out."""
    bits: list[int] = []
    end = (first + size) * 8
    for block in range(first * 8, end, BLOCKS_AT_A_TIME):
        wanted = min(BLOCKS_AT_A_TIME, end - block)
        mixed = sound.mix(block * algorithm.block_frames, wanted * algorithm.block_frames)
        complete = len(mixed) // algorithm.block_frames
        blocks = mixed[: complete * algorithm.block_frames].reshape(complete, algorithm.block_frames)
        bits += algorithm.read_bits(blocks)
        if complete < wanted:
            break
    return bits_to_bytes(bits)


def find_header(sound: Sound, algorithm: SignalAlgorithm) -> tuple[Header, float] | None:
    """Read the header and how hard it was to correct. Refuse a length that does not fit in the sound."""
    load_numpy()
    if sound.frames < PROTECTED_HEADER_SIZE * 8 * algorithm.block_frames:
        return None
    restored = restore_header(read_hidden_bytes(sound, algorithm, 0, PROTECTED_HEADER_SIZE))
    header = None if restored is None else parse_header(restored.data)
    if restored is None or header is None:
        return None
    if header.container_size > algorithm.largest_container(sound.frames):
        raise DamagedMessageError("The hidden message is damaged: it is longer than the audio file.")
    return header, restored.strain


def read_container(sound: Sound, algorithm: SignalAlgorithm, header: Header) -> Restored:
    """Read and correct the container that a header describes."""
    size = protected_size(header.container_size) - PROTECTED_HEADER_SIZE
    protected = read_hidden_bytes(sound, algorithm, PROTECTED_HEADER_SIZE, size)
    if len(protected) < size:
        raise DamagedMessageError("The audio file ends before the hidden message does.")
    body = restore_body(protected, header.container_size - HEADER_SIZE)
    return Restored(header.to_bytes() + body.data, body.strain)


def channel_pieces(stored: Bytes, frames: int) -> Iterator[tuple[int, Bytes]]:
    """Yield the samples of each channel, a few at a time, with the number of their first frame."""
    for channel in range(stored.shape[1]):
        for first in range(0, len(stored), frames):
            yield first, stored[first : first + frames, channel]


def changed_pieces(
    original: Bytes, bits: Numbers, algorithm: SignalAlgorithm, level: float
) -> Iterator[Numbers]:
    """Yield the changed numbers of each channel, a few blocks at a time."""
    np = load_numpy()
    history = np.zeros(algorithm.history_frames)
    for first, piece in channel_pieces(original, BLOCKS_AT_A_TIME * algorithm.block_frames):
        if first == 0:
            history = np.zeros(algorithm.history_frames)
        sound = np.concatenate([history, to_numbers(piece)])
        history = sound[len(sound) - algorithm.history_frames :]
        changed: Numbers = sound[algorithm.history_frames :] + level * algorithm.make_change(
            sound, first, bits
        )
        yield changed


def find_gain(original: Bytes, bits: Numbers, algorithm: SignalAlgorithm, level: float) -> float:
    """Return 1, or less if the changed sound would be too loud to store."""
    np = load_numpy()
    limit = largest_number(original.shape[-1])
    pieces = changed_pieces(original, bits, algorithm, level)
    peak = max((float(np.abs(piece).max()) for piece in pieces), default=0.0)
    return min(1.0, limit / peak) if peak else 1.0


def embed_bits(
    audio: AudioData, original: bytes, bits: list[int], algorithm: SignalAlgorithm, level: float
) -> float:
    """
    Put bits into the start of the sound.

    :param audio: The sound to change
    :param original: The unchanged frames that the bits need
    :param bits: The bits, one for each block
    :param algorithm: The algorithm
    :param level: How strong the change is
    :return: What every sample of the file has to be multiplied by. Here it was already done.
    """
    np = load_numpy()
    used = algorithm.changed_frames(len(bits))
    before = sample_bytes(original, audio.channels, audio.sample_width)[:used]
    after = sample_bytes(audio.frames, audio.channels, audio.sample_width)[: len(before)]
    numbers = np.asarray(bits, dtype=np.float64)
    gain = find_gain(before, numbers, algorithm, level)
    frames = BLOCKS_AT_A_TIME * algorithm.block_frames
    changed = changed_pieces(before, numbers, algorithm, level)
    for (_, piece), new in zip(channel_pieces(after, frames), changed, strict=True):
        piece[:] = to_stored(gain * new, audio.sample_width)
    return gain


def make_quieter(audio: AudioData, first_frame: int, gain: float) -> None:
    """Multiply every sample from a frame on."""
    stored = sample_bytes(audio.frames, audio.channels, audio.sample_width)[first_frame:]
    for _, piece in channel_pieces(stored, BYTES_AT_A_TIME):
        piece[:] = to_stored(gain * to_numbers(piece), audio.sample_width)


def hide_old_markers(audio: AudioData, earlier: tuple[Algorithm, ...]) -> None:
    """Flip the lowest bit of the first sample if an older message would be detected before the new one."""
    for algorithm in earlier:
        samples = len(MARKER) * 8 // algorithm.bits_per_byte * algorithm.samples_per_group
        low_bytes = bytes(audio.frames[: samples * audio.sample_width : audio.sample_width])
        if bits_to_bytes(extract_groups(low_bytes, algorithm)) == MARKER:
            audio.frames[0] ^= 1


def read_back(audio: AudioData, container: bytes, algorithm: SignalAlgorithm) -> float | None:
    """Return how hard it is to read the container from the changed sound, or None if it is impossible."""
    sound = sound_in_memory(audio)
    try:
        found = find_header(sound, algorithm)
        if found is None:
            return None
        header, strain = found
        restored = read_container(sound, algorithm, header)
    except StegoError:
        return None
    return max(strain, restored.strain) if restored.data == container else None


def embed_container(audio: AudioData, container: bytes, algorithm: SignalAlgorithm) -> None:
    """
    Put a container into the sound with the weakest level that can be read back well.

    If no level is comfortable, the strongest one is used if it can be read back at all.
    """
    bits = list(bytes_to_bits(protect(container)))
    size = algorithm.changed_frames(len(bits)) * audio.channels * audio.sample_width
    original = bytes(audio.frames[:size])
    for level in algorithm.levels:
        gain = embed_bits(audio, original, bits, algorithm, level)
        hide_old_markers(audio, algorithm.earlier)
        strain = read_back(audio, container, algorithm)
        if strain is not None and (strain <= COMFORTABLE_STRAIN or level == algorithm.levels[-1]):
            break
    else:
        raise UnsuitableAudioError(
            "The message could not be read back from this sound, so nothing was saved. "
            "The sound may be too quiet or too simple, such as silence or pure tones."
        )
    if gain < 1:
        make_quieter(audio, len(original) // (audio.channels * audio.sample_width), gain)
