"""Hide one character as echoes in real sound, one step at a time."""

from __future__ import annotations

from dataclasses import dataclass

from audiosteg.algorithms.echo import EchoHiding
from audiosteg.analysis.samples import Part, SampleFormat, read_blocks, read_format
from audiosteg.analysis.walkthrough import find_sound
from audiosteg.core.message_codec import bits_to_bytes, bytes_to_bits, bytes_to_message, message_to_bytes
from audiosteg.core.signal_algorithm import load_numpy
from audiosteg.core.signal_file import Sound, embed_bits, sound_in_memory
from audiosteg.core.wav_io import AudioData, check_input_size, open_pcm_wav
from audiosteg.errors import CapacityError, DamagedMessageError

PICTURE_DELAYS = range(15, 61)


@dataclass(frozen=True)
class EchoBlock:
    """
    What happened to one block.

    :param number: Its number in the walkthrough, from 1 on
    :param hidden_bit: The bit that it carries
    :param delay: The delay of its echo, in frames
    :param peaks_before: Its cepstrum at the delays of 0 and 1, before the change
    :param peaks_after: The same after the change
    """

    number: int
    hidden_bit: int
    delay: int
    peaks_before: tuple[float, float]
    peaks_after: tuple[float, float]

    @property
    def read_bit(self) -> int:
        """Return the bit that is read from the changed block."""
        return int(self.peaks_after[1] > self.peaks_after[0])

    @property
    def clearness(self) -> float:
        """Return how far the right number is above the other one."""
        return self.peaks_after[self.hidden_bit] - self.peaks_after[1 - self.hidden_bit]


@dataclass(frozen=True)
class EchoWalkthrough:
    """
    One character that was hidden as echoes.

    :param letter: The character
    :param data: Its UTF-8 bytes
    :param format: The format of the file
    :param first_frame: The first frame that was used
    :param silent: Whether the whole file is silent
    :param level: How strong the echo is, compared with the sound
    :param gain: What the sound was multiplied by, so that the result is not too loud
    :param blocks: What happened to each block
    :param picture_block: The number of the block with the clearest echo
    :param picture_before: Its cepstrum at the delays of the picture, before the change
    :param picture_after: The same after the change
    """

    letter: str
    data: bytes
    format: SampleFormat
    first_frame: int
    silent: bool
    level: float
    gain: float
    blocks: tuple[EchoBlock, ...]
    picture_block: int
    picture_before: tuple[float, ...]
    picture_after: tuple[float, ...]

    @property
    def right_bits(self) -> int:
        """Return how many bits are read as they were hidden."""
        return sum(block.read_bit == block.hidden_bit for block in self.blocks)

    @property
    def read_back(self) -> str | None:
        """Return the character that is read, or None if the bits that are read are not one."""
        try:
            return bytes_to_message(bits_to_bytes(block.read_bit for block in self.blocks))
        except DamagedMessageError:
            return None


def find_cepstra(sound: Sound, algorithm: EchoHiding, blocks: int) -> list[list[float]]:
    """Return the cepstrum of each block."""
    load_numpy()
    mixed = sound.mix(0, blocks * algorithm.block_frames)
    cepstra: list[list[float]] = algorithm.find_cepstra(mixed.reshape(blocks, -1)).tolist()
    return cepstra


def read_excerpt(path: str, algorithm: EchoHiding, bits: int) -> tuple[AudioData, int, bool]:
    """Return a part of a file that can be heard, its first frame, and whether the whole file is silent."""
    check_input_size(path)
    with open_pcm_wav(path) as audio:
        sample_format = read_format(audio)
        frames, needed = audio.getnframes(), bits * algorithm.block_frames
        if frames < needed:
            raise CapacityError(
                f"The audio file is too short to hide one character. It needs {needed:,} frames here."
            )
        sound, volume = find_sound(audio)
        first = min(sound, frames - needed)
        part = Part(first, min(algorithm.changed_frames(bits), frames - first))
        data = bytearray(b"".join(read_blocks(audio, part)))
    return AudioData(*sample_format, data), first, volume == 0


def peaks_of(cepstrum: list[float], algorithm: EchoHiding) -> tuple[float, float]:
    """Return a cepstrum at the delays of 0 and 1."""
    zero, one = algorithm.delays
    return cepstrum[zero], cepstrum[one]


def walk_through_echo(path: str, letter: str, algorithm: EchoHiding) -> EchoWalkthrough:
    """Hide one character in a part of a WAV file that can be heard. No file is changed."""
    load_numpy()
    data = message_to_bytes(letter)
    bits = list(bytes_to_bits(data))
    audio, first_frame, silent = read_excerpt(path, algorithm, len(bits))
    original, sound = bytes(audio.frames), sound_in_memory(audio)
    before = find_cepstra(sound, algorithm, len(bits))
    for level in algorithm.levels:
        gain = embed_bits(audio, original, bits, algorithm, level)
        after = find_cepstra(sound, algorithm, len(bits))
        blocks = tuple(
            EchoBlock(
                number,
                bit,
                algorithm.delays[bit],
                peaks_of(old, algorithm),
                peaks_of(new, algorithm),
            )
            for number, (bit, old, new) in enumerate(zip(bits, before, after, strict=True), start=1)
        )
        if all(block.read_bit == block.hidden_bit for block in blocks):
            break
    clearest = max(blocks, key=lambda block: block.clearness).number
    return EchoWalkthrough(
        letter,
        data,
        SampleFormat(audio.channels, audio.sample_width, audio.frame_rate),
        first_frame,
        silent,
        level,
        gain,
        blocks,
        clearest,
        tuple(before[clearest - 1][delay] for delay in PICTURE_DELAYS),
        tuple(after[clearest - 1][delay] for delay in PICTURE_DELAYS),
    )
