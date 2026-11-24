"""The algorithms, by the names that the commands use."""

from audiosteg.algorithms.legacy import BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.core.algorithm import Algorithm, LegacyAlgorithm

ALGORITHMS: dict[str, Algorithm] = {
    "lsb": LSB,
    "lsb_2": LSB_2,
}

LEGACY_ALGORITHMS: dict[str, LegacyAlgorithm] = {
    "basic": BASIC_LSB,
    "enhanced_flip": ENHANCED_LSB_FLIP,
    "enhanced": ENHANCED_LSB,
}
