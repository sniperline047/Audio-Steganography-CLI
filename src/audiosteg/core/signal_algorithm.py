"""The description of the ways to hide bits in whole blocks of sound."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING

from audiosteg.core.algorithm import Algorithm
from audiosteg.core.protection import largest_container, protected_size
from audiosteg.errors import MissingLibraryError

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    Numbers = NDArray[np.float64]


def load_numpy() -> ModuleType:
    """Import NumPy only when it is needed."""
    try:
        import numpy
    except ImportError as error:
        missing = MissingLibraryError(
            'This algorithm needs an optional library (NumPy). To install it, run: pip install ".[signal]"'
        )
        missing.add_note("Without it, the other algorithms can be used.")
        raise missing from error
    return numpy


def has_numpy() -> bool:
    """Say whether algorithms that work with whole blocks of sound can be used here."""
    try:
        load_numpy()
    except MissingLibraryError:
        return False
    return True


def check_library(algorithm: object) -> None:
    """Make sure that an algorithm can be used here, if it needs NumPy."""
    if isinstance(algorithm, SignalAlgorithm):
        load_numpy()


@dataclass(frozen=True)
class SignalAlgorithm(ABC):
    """
    One way to hide one bit in each block of sound. A subclass says how.

    :param name: The full name
    :param block_frames: How many frames carry one bit. A frame is one sample of every channel.
    :param history_frames: How many earlier frames are needed to change a frame
    :param tail_frames: How many frames after the last block change too
    :param levels: How strong the change may be. The first that can be read back well is used.
    :param explanation: One line that explains the algorithm to a beginner
    :param strengths: What the algorithm is good at, one sentence each
    :param weaknesses: What the algorithm is bad at, one sentence each
    :param how: One line that explains what it does to the sound
    :param earlier: The algorithms that are detected before it, so their old messages must not stay
    """

    name: str
    block_frames: int
    history_frames: int
    tail_frames: int
    levels: tuple[float, ...]
    explanation: str = ""
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    how: str = ""
    earlier: tuple[Algorithm, ...] = ()

    keyed = False
    detectable = True
    reads_like = None
    bits_per_byte = 1

    @property
    def samples_per_group(self) -> int:
        """Return how many samples of one channel carry a bit."""
        return self.block_frames

    def changed_frames(self, bits: int) -> int:
        """Return how many frames are needed to hide this many bits without an abrupt end."""
        return bits * self.block_frames + self.tail_frames

    def needed_frames(self, container_size: int) -> int:
        """Return how many frames a container of this size needs."""
        return protected_size(container_size) * 8 * self.block_frames

    def largest_container(self, frames: int) -> int:
        """Return the size of the largest container that may fit, or 0. The sound decides whether it does."""
        return largest_container(frames // self.block_frames // 8)

    @abstractmethod
    def prepare(self, first_frame: int, frames: int, bits: Numbers) -> Numbers:
        """
        Return what the changes of all channels have in common, for a piece of the sound.

        :param first_frame: The number of the first frame, always the start of a block
        :param frames: How many frames the piece has
        :param bits: Every bit that is hidden in the file, as 0 or 1
        """

    @abstractmethod
    def make_change(self, sound: Numbers, shared: Numbers) -> Numbers:
        """
        Return what to add to one channel of a piece, before it is multiplied by the level.

        :param sound: The history and the sound to change. 0 is silence.
        :param shared: The result of prepare
        :return: One number for each frame after the history
        """

    @abstractmethod
    def find_signs(self, blocks: Numbers) -> Numbers:
        """
        Measure how much each block looks like a hidden 0 and like a hidden 1.

        :param blocks: One row for each block, with all channels added together
        :return: One row with two numbers for each block
        """

    def read_bits(self, blocks: Numbers) -> list[int]:
        """Return the hidden bit of each block. A block that looks like neither counts as 0."""
        return [int(one > zero) for zero, one in self.find_signs(blocks).tolist()]
