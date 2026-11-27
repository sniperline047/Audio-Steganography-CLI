"""The algorithms, by the names that the commands use."""

from audiosteg.algorithms.echo import ECHO
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.algorithms.lsb_four import LSB_4
from audiosteg.algorithms.lsb_keyed import LSB_KEYED
from audiosteg.algorithms.lsb_matching import LSB_MATCHING
from audiosteg.algorithms.lsb_parity import LSB_PARITY
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.signal_algorithm import SignalAlgorithm

ALGORITHMS: dict[str, Algorithm | SignalAlgorithm] = {
    "lsb": LSB,
    "lsb_2": LSB_2,
    "lsb_4": LSB_4,
    "lsb_matching": LSB_MATCHING,
    "lsb_parity": LSB_PARITY,
    "lsb_keyed": LSB_KEYED,
    "echo": ECHO,
}


def reading_key(key: str) -> str:
    """Return the name that a message is reported under, which can be the name of another algorithm."""
    reader = ALGORITHMS[key].reads_like
    return next((name for name, known in ALGORITHMS.items() if known is reader), key)
