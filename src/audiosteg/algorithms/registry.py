"""The numbered lists of algorithms."""

from audiosteg.algorithms.legacy import BASIC_LSB, ENHANCED_LSB, ENHANCED_LSB_FLIP
from audiosteg.algorithms.lsb import LSB, LSB_2
from audiosteg.core.algorithm import Algorithm, LegacyAlgorithm

ALGORITHMS: dict[int, Algorithm] = {
    1: LSB,
    2: LSB_2,
}

LEGACY_ALGORITHMS: dict[int, LegacyAlgorithm] = {
    1: BASIC_LSB,
    2: ENHANCED_LSB_FLIP,
    3: ENHANCED_LSB,
}
