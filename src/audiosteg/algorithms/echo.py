"""Hide one bit in each block of sound with a short echo. The delay of the echo is the bit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_four import LSB_4
from audiosteg.algorithms.lsb_parity import LSB_PARITY
from audiosteg.core.signal_algorithm import SignalAlgorithm, load_numpy

if TYPE_CHECKING:
    from audiosteg.core.signal_algorithm import Numbers

BLOCK_FRAMES = 1024
FADE_FRAMES = 256
DELAYS = (25, 50)


@dataclass(frozen=True)
class EchoHiding(SignalAlgorithm):
    """
    Add an echo to every block, after a delay that says whether the block carries 0 or 1.

    :param delays: The delay for 0 and the delay for 1, in frames
    :param fade_frames: How many frames the change from one echo to the next takes
    """

    delays: tuple[int, int] = DELAYS
    fade_frames: int = FADE_FRAMES

    def loudness(self, first_frame: int, frames: int, wanted: Numbers) -> Numbers:
        """
        Return how loud an echo is at each frame, from 0 to 1, with smooth changes between the blocks.

        :param wanted: 1 for each block that has this echo, and 0 for each other
        """
        np = load_numpy()
        steps = np.concatenate([[0.0], wanted, [0.0]])
        shifted = np.arange(first_frame, first_frame + frames) + self.fade_frames // 2
        block, offset = np.divmod(shifted, self.block_frames)
        fade = 0.5 - 0.5 * np.cos(np.pi * np.minimum(offset, self.fade_frames) / self.fade_frames)
        loudness: Numbers = steps[block] * (1 - fade) + steps[block + 1] * fade
        return loudness

    def make_change(self, sound: Numbers, first_frame: int, bits: Numbers) -> Numbers:
        """Return the two echoes, each where its bit is hidden."""
        frames = len(sound) - self.history_frames
        early, late = (sound[self.history_frames - delay :][:frames] for delay in self.delays)
        zeros = self.loudness(first_frame, frames, 1 - bits)
        ones = self.loudness(first_frame, frames, bits)
        return zeros * early + ones * late

    def find_cepstra(self, blocks: Numbers) -> Numbers:
        """
        Return the cepstrum of each block: the spectrum of the logarithm of its spectrum.

        An echo makes waves in the spectrum, and so a peak in the cepstrum at its delay.
        """
        np = load_numpy()
        window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(self.block_frames) / self.block_frames)
        power = np.abs(np.fft.rfft(blocks * window, axis=1)) ** 2
        cepstra: Numbers = np.fft.irfft(np.log(power + 1), n=self.block_frames, axis=1)
        return cepstra

    def find_signs(self, blocks: Numbers) -> Numbers:
        """Return the cepstrum of each block at the two delays."""
        return self.find_cepstra(blocks)[:, list(self.delays)]


ECHO = EchoHiding(
    name="Echo (1 bit per block of 1,024 frames)",
    block_frames=BLOCK_FRAMES,
    history_frames=max(DELAYS),
    tail_frames=FADE_FRAMES // 2,
    levels=(0.2, 0.3, 0.4, 0.5),
    explanation="Hides 1 bit in each block as a short echo. Audible.",
    strengths=(
        "The bits are in the sound itself and not in the lowest bits of the samples.",
        "Error correction repairs some bits that are read wrong.",
    ),
    weaknesses=(
        "The echo can be heard, like a small room or a slightly metallic sound.",
        "It holds very little: a minute of CD audio holds about 140 bytes.",
        "It does not work with every sound, such as silence or pure tones.",
        "Anyone who looks for echoes can find the message.",
    ),
    how="Each block gets a quiet echo of itself. A short delay means 0, and a longer one means 1.",
    earlier=(LSB, LSB_2, LSB_4, LSB_PARITY),
)
